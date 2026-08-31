"""Local remaining-deck ledger reconciled against the authoritative deck count."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .memory.deck import DeckInfoSnapshot, card_family


@dataclass(frozen=True)
class LedgerRow:
    card_id: int
    initial: int
    remaining: int


class DeckLedger:
    """Track which known cards have left the player's original 40-card deck.

    The game only publishes a total deck count during battle.  Card identities are
    assigned when a self card first appears in a draw event, hand, or directly on
    the field.  Any unmatched count remains explicit instead of being guessed.
    """

    def __init__(self, deck: DeckInfoSnapshot) -> None:
        self.deck = deck
        self.initial = deck.counter()
        self.remaining = deck.counter()
        self._seen_uids: set[int] = set()
        self._seen_draw_events: set[tuple[int, int]] = set()
        self._last_deck_count: int | None = None
        self._unknown_removed = 0
        self._burned_cards = 0
        self._burned_card_ids: list[int] = []

    def record_burn(self, count: int = 1, card_ids: tuple[int, ...] = ()) -> None:
        """Record draws lost because the local hand was already full.

        Identified cards have already been consumed by ``_draw_cards`` during
        ``update``; the IDs here are retained for display and training output.
        """
        if count > 0:
            self._burned_cards += count
            for runtime_card_id in card_ids[:count]:
                card_id = self._deck_card_id(runtime_card_id)
                if card_id is not None:
                    self._burned_card_ids.append(card_id)

    @property
    def identified_removed(self) -> int:
        return sum(self.initial.values()) - sum(self.remaining.values())

    def _deck_card_id(self, runtime_card_id: int) -> int | None:
        if runtime_card_id in self.initial:
            return runtime_card_id
        family = card_family(runtime_card_id)
        matches = [card_id for card_id in self.initial if card_family(card_id) == family]
        return matches[0] if len(matches) == 1 else None

    def _consume(self, runtime_card_id: int) -> bool:
        card_id = self._deck_card_id(runtime_card_id)
        if card_id is None or self.remaining[card_id] <= 0:
            return False
        self.remaining[card_id] -= 1
        return True

    @staticmethod
    def _mine(snapshot: dict[str, object]) -> dict[str, object] | None:
        root = snapshot.get("root")
        if not isinstance(root, dict):
            return None
        players = root.get("players")
        if not isinstance(players, (list, tuple)) or not players or not isinstance(players[0], dict):
            return None
        return players[0]

    @staticmethod
    def _visible_cards(
        mine: dict[str, object],
        zones: tuple[str, ...] = ("hand", "field"),
    ) -> list[tuple[int, int]]:
        values: list[tuple[int, int]] = []
        for zone in zones:
            cards = mine.get(zone, ())
            if not isinstance(cards, (list, tuple)):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                uid = card.get("unique_id")
                card_id = card.get("base_card_id") or card.get("card_id")
                if isinstance(uid, int) and uid > 0 and isinstance(card_id, int) and card_id > 0:
                    values.append((uid, card_id))
        return values

    def _draw_cards(self, snapshot: dict[str, object]) -> list[tuple[int, int]]:
        values: list[tuple[int, int]] = []
        events = snapshot.get("events", ())
        if not isinstance(events, (list, tuple)):
            return values
        for event in events:
            if not isinstance(event, dict) or not event.get("is_ally"):
                continue
            if event.get("type") not in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect"}:
                continue
            sequence = event.get("sequence")
            cards = event.get("cards", ())
            if not isinstance(sequence, int) or not isinstance(cards, (list, tuple)):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                uid = card.get("unique_id")
                card_id = card.get("base_card_id") or card.get("card_id")
                if not isinstance(uid, int) or not isinstance(card_id, int):
                    continue
                event_key = (sequence, uid)
                if event_key not in self._seen_draw_events:
                    self._seen_draw_events.add(event_key)
                    values.append((uid, card_id))
        return values

    def update(self, snapshot: dict[str, object]) -> dict[str, object]:
        mine = self._mine(snapshot)
        if mine is None or not isinstance(mine.get("deck_count"), int):
            return self.to_dict()
        deck_count = int(mine["deck_count"])
        target_removed = max(0, sum(self.initial.values()) - deck_count)

        # During mulligan the game briefly exposes the cards being returned and
        # their replacements under different UIDs while the deck count still
        # represents only four cards outside the deck.  Assigning identities at
        # turn 0 permanently charges a replacement draw to the wrong card.  Wait
        # for the first real turn, when the hand and deck count are coherent.
        turn = mine.get("turn")
        if self._last_deck_count is None and isinstance(turn, int) and turn <= 0:
            self._unknown_removed = target_removed
            return self.to_dict(deck_count=deck_count)

        candidates: list[tuple[int, int]] = []
        candidates.extend(self._draw_cards(snapshot))

        if self._last_deck_count is None:
            # Current hand cards and play history do not overlap.  A current
            # field card usually also occurs in play history, so including the
            # field here would double-charge it when the tracker starts midgame.
            candidates.extend(self._visible_cards(mine, ("hand",)))
            history = mine.get("played_card_ids", ())
            if isinstance(history, (list, tuple)):
                for index, item in enumerate(history):
                    if isinstance(item, (list, tuple)) and item and isinstance(item[0], int):
                        candidates.append((-(index + 1), item[0]))
        else:
            candidates.extend(self._visible_cards(mine))

        capacity = max(0, target_removed - self.identified_removed)
        for uid, card_id in candidates:
            if uid > 0 and uid in self._seen_uids:
                continue
            if uid > 0:
                self._seen_uids.add(uid)
            if capacity > 0 and self._consume(card_id):
                capacity -= 1

        self._unknown_removed = max(0, target_removed - self.identified_removed)
        self._last_deck_count = deck_count
        return self.to_dict(deck_count=deck_count)

    def to_dict(self, *, deck_count: int | None = None) -> dict[str, object]:
        rows = [
            LedgerRow(card_id=card.card_id, initial=card.count, remaining=self.remaining[card.card_id])
            for card in self.deck.cards
        ]
        return {
            "deck_id": self.deck.deck_id,
            "deck_name": self.deck.deck_name,
            "deck_format": self.deck.deck_format,
            "class_id": self.deck.class_id,
            "authoritative_deck_count": deck_count if deck_count is not None else self._last_deck_count,
            "identified_removed": self.identified_removed,
            "unknown_removed": self._unknown_removed,
            "burned_cards": self._burned_cards,
            "burned_card_ids": list(self._burned_card_ids),
            "rows": [row.__dict__ for row in rows],
        }
