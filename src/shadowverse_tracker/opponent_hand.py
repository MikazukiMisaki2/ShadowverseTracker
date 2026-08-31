"""Track opponent hand cards whose identity or type became public."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

from .card_catalog import canonical_card_id


# Effects that create a publicly known card in the opponent's hand.  The
# table is intentionally data-driven so new card interactions can be added
# without changing the UI or memory decoder.
KNOWN_HAND_EFFECTS: dict[int, dict[str, object]] = {
    # 魅惑的魅魔·莉莉姆: Last Words adds a Bat to its owner's hand.
    10052110: {"on_destroy": ((90051120, 1),)},
    # 碎裂的盗匪: Last Words adds a copy of itself (without Last Words).
    10941110: {"on_destroy": ((10941110, 1),)},
    # 尽小花·伊鞠: on entry, discard one and draw a spell from the deck.
    10574120: {"on_play_unknown_spell": 1},
}


def _history_ids(value: object) -> Iterator[int]:
    if not isinstance(value, (list, tuple)):
        return
    for item in value:
        if isinstance(item, (list, tuple)) and item and isinstance(item[0], int):
            yield int(item[0])
        elif isinstance(item, int):
            yield int(item)


@dataclass
class OpponentKnownHand:
    """Incremental, conservative ledger for only publicly known hand cards."""

    cards: Counter[object] = field(default_factory=Counter)
    _played_count: int = 0
    _destroyed_count: int = 0
    _event_sequences: set[int] = field(default_factory=set)

    def reset(self) -> None:
        self.cards.clear()
        self._played_count = 0
        self._destroyed_count = 0
        self._event_sequences.clear()

    def update(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        events = snapshot.get("events")
        if isinstance(events, (list, tuple)):
            for event in events:
                if not isinstance(event, dict) or bool(event.get("is_ally")):
                    continue
                sequence = event.get("sequence")
                if not isinstance(sequence, int) or sequence in self._event_sequences:
                    continue
                self._event_sequences.add(sequence)
                self._consume_public_draw(event)

        played = opponent.get("played_card_ids", ())
        played_items = list(_history_ids(played))
        if len(played_items) < self._played_count:
            self._played_count = 0
        for card_id in played_items[self._played_count:]:
            self._consume_play(card_id)
        self._played_count = len(played_items)

        destroyed = opponent.get("destroyed_card_ids", ())
        destroyed_items = list(_history_ids(destroyed))
        if len(destroyed_items) < self._destroyed_count:
            self._destroyed_count = 0
        for card_id in destroyed_items[self._destroyed_count:]:
            self._consume_destroy(card_id)
        self._destroyed_count = len(destroyed_items)

    def _consume_public_draw(self, event: dict[str, object]) -> None:
        event_type = str(event.get("type") or "")
        if event_type in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect"}:
            cards = event.get("cards")
            if isinstance(cards, (list, tuple)):
                for card in cards:
                    if not isinstance(card, dict):
                        continue
                    value = card.get("base_card_id") or card.get("card_id")
                    if isinstance(value, int) and value > 0:
                        self.cards[canonical_card_id(value)] += 1
            return

        # Future decoder versions may be able to identify a hidden draw's
        # type without revealing its exact CardId.  Accept those annotations
        # while leaving ordinary hidden draws uncounted.
        kind = str(event.get("known_kind") or event.get("card_kind") or "").casefold()
        if bool(event.get("is_spell")) or kind in {"spell", "法术"}:
            amount = event.get("draw_num") or event.get("add_num") or 1
            if isinstance(amount, int) and amount > 0:
                self.cards["unknown_spell"] += amount

    def _consume_play(self, card_id: int) -> None:
        key = canonical_card_id(card_id)
        if self.cards.get(key, 0) > 0:
            self.cards[key] -= 1
            if self.cards[key] <= 0:
                del self.cards[key]
        effect = KNOWN_HAND_EFFECTS.get(key, {})
        if effect.get("on_play_unknown_spell"):
            # The play history may be the first snapshot after an effect
            # resolved, so do not depend on the deck count still being > 0.
            self.cards["unknown_spell"] += int(effect["on_play_unknown_spell"])

    def _consume_destroy(self, card_id: int) -> None:
        effect = KNOWN_HAND_EFFECTS.get(canonical_card_id(card_id), {})
        for generated_id, amount in effect.get("on_destroy", ()):
            if isinstance(generated_id, int) and isinstance(amount, int) and amount > 0:
                self.cards[canonical_card_id(generated_id)] += amount


__all__ = ["KNOWN_HAND_EFFECTS", "OpponentKnownHand"]
