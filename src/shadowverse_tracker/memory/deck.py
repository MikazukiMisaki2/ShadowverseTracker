"""Decode and discover complete user deck lists kept by the IL2CPP client."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable, Protocol

from .battle import read_il2cpp_type_name, read_reference_collection
from .discovery import find_pointer_references_many


class DeckMemoryReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...
    def read_u64(self, address: int) -> int: ...
    def read_u32(self, address: int) -> int: ...
    def read_i32(self, address: int) -> int: ...
    def read_c_string(self, address: int, maximum: int = 512) -> str: ...


MAX_DECK_KINDS = 40
MAX_DECK_COPIES = 3
EXPECTED_DECK_SIZE = 40


@dataclass(frozen=True)
class DeckCard:
    card_id: int
    count: int


@dataclass(frozen=True)
class DeckInfoSnapshot:
    address: str
    deck_id: int
    deck_name: str
    class_id: int
    deck_format: int
    cards: tuple[DeckCard, ...]

    @property
    def total_cards(self) -> int:
        return sum(card.count for card in self.cards)

    def counter(self) -> Counter[int]:
        return Counter({card.card_id: card.count for card in self.cards})

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["total_cards"] = self.total_cards
        return value


@dataclass(frozen=True)
class DeckSelection:
    deck_ids: tuple[int, ...]
    selected_index: int
    deck_format: int

    @property
    def selected_deck_id(self) -> int | None:
        if 0 <= self.selected_index < len(self.deck_ids):
            return self.deck_ids[self.selected_index]
        return None


def read_managed_string(reader: DeckMemoryReader, address: int, *, maximum: int = 256) -> str:
    if not address:
        return ""
    length = reader.read_i32(address + 0x10)
    if length < 0 or length > maximum:
        raise ValueError(f"implausible managed string length {length} at 0x{address:X}")
    return reader.read(address + 0x14, length * 2).decode("utf-16-le", errors="replace")


def read_deck_info(reader: DeckMemoryReader, address: int) -> DeckInfoSnapshot:
    if not address:
        raise ValueError("null DeckInfo")
    card_list = reader.read_u64(address + 0x40)
    card_addresses = read_reference_collection(reader, card_list, maximum=MAX_DECK_KINDS)
    cards: list[DeckCard] = []
    seen: set[int] = set()
    for card_address in card_addresses:
        if not card_address:
            raise ValueError("null DeckCardInfo")
        card_id = reader.read_u32(card_address + 0x10)
        count = reader.read_i32(card_address + 0x14)
        if card_id <= 0 or card_id in seen:
            raise ValueError(f"invalid or duplicate deck card id {card_id}")
        if not 1 <= count <= MAX_DECK_COPIES:
            raise ValueError(f"invalid copy count {count} for {card_id}")
        seen.add(card_id)
        cards.append(DeckCard(card_id=card_id, count=count))
    result = DeckInfoSnapshot(
        address=f"0x{address:016X}",
        deck_id=reader.read_i32(address + 0x10),
        deck_name=read_managed_string(reader, reader.read_u64(address + 0x18)),
        class_id=reader.read_i32(address + 0x20),
        deck_format=reader.read_i32(address + 0x50),
        cards=tuple(cards),
    )
    if result.total_cards != EXPECTED_DECK_SIZE:
        raise ValueError(f"expected a {EXPECTED_DECK_SIZE}-card deck, found {result.total_cards}")
    return result


def find_deck_infos(reader, *, class_pointer_rva: int) -> tuple[DeckInfoSnapshot, ...]:
    """Find all structurally valid, live DeckInfo objects in private memory."""
    module = reader.module("GameAssembly.dll")
    class_address = reader.read_u64(module.base_address + class_pointer_rva)
    if not class_address:
        return ()
    candidates = (
        candidate
        for candidate, _ in find_pointer_references_many(reader, (class_address,), maximum_hits=4096)
    )
    return decode_deck_info_candidates(reader, candidates)


def decode_deck_info_candidates(
    reader: DeckMemoryReader,
    candidates: Iterable[int],
) -> tuple[DeckInfoSnapshot, ...]:
    decks: dict[tuple[int, int, tuple[tuple[int, int], ...]], DeckInfoSnapshot] = {}
    for candidate in candidates:
        try:
            if read_il2cpp_type_name(reader, candidate) != "Wizard2.Domain.DeckInfoData.DeckInfo":
                continue
            deck = read_deck_info(reader, candidate)
        except (OSError, ValueError, LookupError):
            continue
        signature = (
            deck.deck_format,
            deck.deck_id,
            tuple((card.card_id, card.count) for card in deck.cards),
        )
        decks.setdefault(signature, deck)
    return tuple(decks.values())


def read_practice_deck_selection(reader: DeckMemoryReader, address: int) -> DeckSelection | None:
    """Read the exact deck choice shown on the practice-battle confirmation page."""
    if not address:
        return None
    select_info = reader.read_u64(address + 0x30)
    if not select_info:
        return None
    ids_array = reader.read_u64(select_info + 0x20)
    if not ids_array:
        return None
    length = reader.read_u64(ids_array + 0x18)
    if length > 8:
        raise ValueError(f"implausible selected deck id count {length}")
    deck_ids = tuple(reader.read_i32(ids_array + 0x20 + index * 4) for index in range(length))
    return DeckSelection(
        deck_ids=deck_ids,
        selected_index=reader.read_i32(select_info + 0x28),
        deck_format=reader.read_i32(select_info + 0x2C),
    )


def select_deck_by_choice(
    decks: Iterable[DeckInfoSnapshot],
    selection: DeckSelection | None,
) -> DeckInfoSnapshot | None:
    if selection is None or selection.selected_deck_id is None:
        return None
    matches = [
        deck
        for deck in decks
        if deck.deck_id == selection.selected_deck_id
        and deck.deck_format == selection.deck_format
    ]
    return matches[0] if len(matches) == 1 else None


def card_family(card_id: int) -> int:
    """Collapse runtime/evolved art variants to the printed card family."""
    return card_id // 10


def select_matching_deck(
    decks: Iterable[DeckInfoSnapshot],
    observed_card_ids: Iterable[int],
) -> tuple[DeckInfoSnapshot | None, int, bool]:
    """Choose a cached deck by public self-card evidence.

    Returns ``(deck, score, unambiguous)``.  A caller should keep waiting when
    there is no evidence or when two different lists have the same best score.
    """
    exact_observed = {card_id for card_id in observed_card_ids if card_id > 0}
    if not exact_observed:
        return None, 0, False
    observed_families = {card_family(card_id) for card_id in exact_observed}
    ranked: list[tuple[int, DeckInfoSnapshot]] = []
    for deck in decks:
        exact = {card.card_id for card in deck.cards}
        families = {card_family(card.card_id) for card in deck.cards}
        exact_hits = len(exact_observed & exact)
        family_hits = len(observed_families & families)
        misses = len(observed_families - families)
        score = exact_hits * 4 + family_hits * 2 - misses * 8
        ranked.append((score, deck))
    if not ranked:
        return None, 0, False
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best = ranked[0]
    unambiguous = best_score > 0 and (len(ranked) == 1 or ranked[1][0] < best_score)
    return best, best_score, unambiguous


def observed_self_card_ids(snapshot: dict[str, object]) -> tuple[int, ...]:
    root = snapshot.get("root")
    if not isinstance(root, dict):
        return ()
    players = root.get("players")
    if not isinstance(players, (list, tuple)) or not players or not isinstance(players[0], dict):
        return ()
    mine = players[0]
    values: set[int] = set()
    hand = mine.get("hand", ())
    if isinstance(hand, (list, tuple)):
        for card in hand:
            if isinstance(card, dict):
                value = card.get("base_card_id") or card.get("card_id")
                if isinstance(value, int) and value > 0:
                    values.add(value)
    field = mine.get("field", ())
    if isinstance(field, (list, tuple)):
        for card in field:
            if isinstance(card, dict) and isinstance(card.get("card_id"), int):
                values.add(int(card["card_id"]))
    for key in ("played_card_ids", "destroyed_card_ids"):
        history = mine.get(key, ())
        if isinstance(history, (list, tuple)):
            for item in history:
                if isinstance(item, (list, tuple)) and item and isinstance(item[0], int) and item[0] > 0:
                    values.add(item[0])
    return tuple(sorted(values))
