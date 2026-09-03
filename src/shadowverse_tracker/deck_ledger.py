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

    @staticmethod
    def _token_field_uids(snapshot: dict[str, object]) -> tuple[set[int], bool]:
        """Return token-created field UIDs and whether token provenance is unknown.

        A response batch can contain both a generated token and a real
        ``PutCardFromDeck`` result.  The old all-or-nothing check discarded
        every field candidate whenever *any* token response was present, so a
        genuine direct summon in that batch was never charged to the ledger.
        When the decoder supplies target UIDs, exclude only those cards.  If a
        token response has no target list (for example an older client or a
        card that vanished between polls), retain the conservative behaviour
        and do not infer any field card from that batch.
        """
        events = snapshot.get("events", ())
        if not isinstance(events, (list, tuple)):
            return set(), False
        token_uids: set[int] = set()
        unknown = False
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "BattleResponsePutToken":
                continue
            targets = event.get("targets")
            found_target = False
            if isinstance(targets, (list, tuple)):
                for target in targets:
                    if not isinstance(target, dict):
                        continue
                    uid = target.get("unique_id")
                    if isinstance(uid, int) and uid > 0:
                        token_uids.add(uid)
                        found_target = True
            if not found_target:
                unknown = True
        # Some client builds expose the provenance directly on the public
        # FieldCard even after the short-lived PutToken response has expired.
        # ``IsSameNameToken`` is particularly important for a generated card
        # whose ID also exists in the selected deck (for example 天晶魔手).
        # Treat that flag as stronger evidence than field appearance, while a
        # missing UID remains conservative and keeps the batch unidentified.
        mine = DeckLedger._mine(snapshot)
        field = mine.get("field") if isinstance(mine, dict) else None
        if isinstance(field, (list, tuple)):
            for card in field:
                if not isinstance(card, dict) or card.get("is_same_name_token") is not True:
                    continue
                uid = card.get("unique_id")
                if isinstance(uid, int) and uid > 0:
                    token_uids.add(uid)
                else:
                    unknown = True
        return token_uids, unknown

    @staticmethod
    def _token_hand_uids(snapshot: dict[str, object]) -> tuple[set[int], bool]:
        """Return hand UIDs created by ``HandToken`` responses.

        A generated copy can enter the hand before it is played.  Its card ID
        may be identical to a real deck card, so treating every visible hand
        card as a deck draw would silently lower the wrong ledger row.
        """
        events = snapshot.get("events", ())
        if not isinstance(events, (list, tuple)):
            return set(), False
        token_uids: set[int] = set()
        unknown = False
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "BattleResponseHandToken":
                continue
            values = event.get("cards") or event.get("targets")
            found = False
            if isinstance(values, (list, tuple)):
                for value in values:
                    card = value.get("card") if isinstance(value, dict) and isinstance(value.get("card"), dict) else value
                    if not isinstance(card, dict):
                        continue
                    uid = card.get("unique_id")
                    if isinstance(uid, int) and uid > 0:
                        token_uids.add(uid)
                        found = True
            if not found and bool(event.get("is_ally")):
                unknown = True
        return token_uids, unknown

    @staticmethod
    def _direct_deck_field_provenance(
        snapshot: dict[str, object],
    ) -> tuple[set[int], Counter[int]]:
        """Return field UIDs/card IDs explicitly reported as deck summons.

        This is only used when a neighbouring ``PutToken`` response has no
        target UID.  In that case the token cannot safely be matched to a
        visible field card, but an explicit ``PutCardFromDeck`` target remains
        strong evidence and should not be discarded with the old batch-wide
        token guard.
        """
        events = snapshot.get("events", ())
        if not isinstance(events, (list, tuple)):
            return set(), Counter()
        uids: set[int] = set()
        card_counts: Counter[int] = Counter()
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "BattleResponsePutCardFromDeck":
                continue
            values = event.get("cards") or event.get("targets")
            if not values and isinstance(event.get("card"), dict):
                values = [event["card"]]
            if not isinstance(values, (list, tuple)):
                continue
            for value in values:
                card = value.get("card") if isinstance(value, dict) and isinstance(value.get("card"), dict) else value
                if not isinstance(card, dict):
                    continue
                uid = card.get("unique_id")
                card_id = card.get("base_card_id") or card.get("card_id")
                if isinstance(uid, int) and uid > 0:
                    uids.add(uid)
                if isinstance(card_id, int) and card_id > 0:
                    card_counts[card_id] += 1
        return uids, card_counts

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
        token_hand_uids, unknown_hand_token = self._token_hand_uids(snapshot)
        visible_hand = self._visible_cards(mine, ("hand",))
        if not unknown_hand_token:
            candidates.extend((uid, card_id) for uid, card_id in visible_hand if uid not in token_hand_uids)

        if self._last_deck_count is None:
            # Current hand cards and play history do not overlap.  A current
            # field card usually also occurs in play history, so including the
            # field here would double-charge it when the tracker starts midgame.
            history = mine.get("played_card_ids", ())
            if isinstance(history, (list, tuple)):
                for index, item in enumerate(history):
                    if isinstance(item, (list, tuple)) and item and isinstance(item[0], int):
                        candidates.append((-(index + 1), item[0]))
        else:
            # Cards summoned directly from the deck never enter our hand, so a
            # newly observed field UID is useful evidence.  Consume public
            # draws and hand cards first; ``capacity`` below guarantees that
            # the named rows never exceed the authoritative deck decrease.
            # ``HandToken`` cards are generated and must not consume the
            # selected deck.  If the response omitted all target UIDs, avoid
            # guessing any visible hand card from that batch.
            # ``PutToken`` is the explicit provenance signal for generated
            # cards.  In particular, 希姆 can create 天晶魔手 with the same ID as
            # a real deck card.  Exclude only token UIDs when the response
            # identifies them, while still allowing a direct deck summon in
            # the same response batch to consume its named row.
            token_uids, unknown_token_provenance = self._token_field_uids(snapshot)
            field_cards = self._visible_cards(mine, ("field",))
            if not unknown_token_provenance:
                candidates.extend((uid, card_id) for uid, card_id in field_cards if uid not in token_uids)
            else:
                # If the token response is incomplete, use only the cards
                # explicitly named by a direct deck summon.  This preserves
                # the safe behavior for an unknown token while allowing a
                # direct summon in the same response batch to decrement the
                # selected deck's named row.
                direct_uids, direct_card_counts = self._direct_deck_field_provenance(snapshot)
                for uid, card_id in field_cards:
                    if uid in direct_uids:
                        candidates.append((uid, card_id))
                        if direct_card_counts.get(card_id, 0) > 0:
                            direct_card_counts[card_id] -= 1
                for uid, card_id in field_cards:
                    if uid in direct_uids:
                        continue
                    if direct_card_counts.get(card_id, 0) > 0:
                        candidates.append((uid, card_id))
                        direct_card_counts[card_id] -= 1

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
