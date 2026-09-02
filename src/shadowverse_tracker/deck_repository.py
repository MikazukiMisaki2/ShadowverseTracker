"""Persistent local repository for user-imported official decks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from .memory.deck import DeckCard, DeckInfoSnapshot, EXPECTED_DECK_SIZE, MAX_DECK_COPIES
from .official_deck import OfficialDeck


SCHEMA_VERSION = 1


def default_repository_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "ShadowverseTracker" / "decks.json"
    return Path.home() / ".shadowverse_tracker" / "decks.json"


@dataclass(frozen=True)
class SavedDeck:
    key: str
    name: str
    class_id: int
    format_version: int
    cards: tuple[DeckCard, ...]
    source: str = ""
    created_at: str = ""

    @property
    def total_cards(self) -> int:
        return sum(card.count for card in self.cards)

    def to_snapshot(self) -> DeckInfoSnapshot:
        return DeckInfoSnapshot(
            address="local-repository",
            deck_id=0,
            deck_name=self.name,
            class_id=self.class_id,
            deck_format=self.format_version,
            cards=self.cards,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "class_id": self.class_id,
            "format_version": self.format_version,
            "cards": [card.__dict__ for card in self.cards],
            "source": self.source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SavedDeck":
        cards_value = value.get("cards", ())
        if not isinstance(cards_value, list):
            raise ValueError("invalid saved deck cards")
        cards = tuple(
            DeckCard(card_id=int(card["card_id"]), count=int(card["count"]))
            for card in cards_value
            if isinstance(card, dict)
        )
        result = cls(
            key=str(value["key"]),
            name=str(value["name"]),
            class_id=int(value["class_id"]),
            format_version=int(value["format_version"]),
            cards=cards,
            source=str(value.get("source", "")),
            created_at=str(value.get("created_at", "")),
        )
        if not result.key or not result.name or result.total_cards != EXPECTED_DECK_SIZE:
            raise ValueError("invalid saved 40-card deck")
        return result


class DeckRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_repository_path()
        self.decks: list[SavedDeck] = []
        self.active_key: str | None = None

    def load(self) -> "DeckRepository":
        if not self.path.exists():
            return self
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or int(value.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("不支持的本地牌组仓库格式")
        deck_values = value.get("decks", ())
        if not isinstance(deck_values, list):
            raise ValueError("本地牌组仓库已损坏")
        self.decks = [SavedDeck.from_dict(deck) for deck in deck_values if isinstance(deck, dict)]
        active = value.get("active_key")
        self.active_key = str(active) if active and any(deck.key == active for deck in self.decks) else None
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        value = {
            "schema_version": SCHEMA_VERSION,
            "active_key": self.active_key,
            "decks": [deck.to_dict() for deck in self.decks],
        }
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def add_official(self, name: str, deck: OfficialDeck) -> SavedDeck:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("牌组名称不能为空")
        saved = SavedDeck(
            key=uuid.uuid4().hex,
            name=clean_name,
            class_id=deck.class_id,
            format_version=deck.format_version,
            cards=deck.cards,
            source=deck.source,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.decks.append(saved)
        self.active_key = saved.key
        self.save()
        return saved

    def active(self) -> SavedDeck | None:
        return next((deck for deck in self.decks if deck.key == self.active_key), None)

    def select(self, key: str) -> SavedDeck:
        deck = next((deck for deck in self.decks if deck.key == key), None)
        if deck is None:
            raise KeyError(key)
        self.active_key = deck.key
        self.save()
        return deck

    def clear_selection(self) -> None:
        """Keep saved decks but make the active deck empty.

        Puzzle/teaching battles do not necessarily use a registered 40-card
        deck.  Clearing the selection is distinct from deleting a saved deck
        and is persisted so reconnecting does not silently reattach a deck
        ledger.
        """
        self.active_key = None
        self.save()

    def update_cards(self, key: str, cards: tuple[DeckCard, ...]) -> SavedDeck:
        """Replace a deck list while preserving its key and match statistics."""
        deck = next((item for item in self.decks if item.key == key), None)
        if deck is None:
            raise KeyError(key)
        if not cards or sum(card.count for card in cards) != EXPECTED_DECK_SIZE:
            raise ValueError(f"牌组必须正好包含 {EXPECTED_DECK_SIZE} 张牌")
        if any(card.card_id <= 0 or not 1 <= card.count <= MAX_DECK_COPIES for card in cards):
            raise ValueError("每种卡牌数量必须在 1 到 3 张之间")
        if len({card.card_id for card in cards}) != len(cards):
            raise ValueError("牌组中不能重复添加同一个 CardId")
        updated = SavedDeck(
            key=deck.key,
            name=deck.name,
            class_id=deck.class_id,
            format_version=deck.format_version,
            cards=tuple(cards),
            source=deck.source,
            created_at=deck.created_at,
        )
        self.decks = [updated if item.key == key else item for item in self.decks]
        self.active_key = key
        self.save()
        return updated

    def delete(self, key: str) -> None:
        original = len(self.decks)
        self.decks = [deck for deck in self.decks if deck.key != key]
        if len(self.decks) == original:
            raise KeyError(key)
        if self.active_key == key:
            self.active_key = self.decks[0].key if self.decks else None
        self.save()
