"""Track opponent hand cards whose identity or type became public."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

from .card_catalog import canonical_card_id
from .card_effects import inferred_hand_additions, is_spell, magic_boost_amount


# Effects that create a publicly known card in the opponent's hand.  The
# table is intentionally data-driven so new card interactions can be added
# without changing the UI or memory decoder.
KNOWN_HAND_EFFECTS: dict[int, dict[str, object]] = {
    # 魅惑的魅魔·莉莉姆: Last Words adds a Bat to its owner's hand.
    10052110: {"on_destroy_add": ((90051120, 1),)},
    # 碎裂的盗匪: Last Words adds a copy of itself (without Last Words).
    10941110: {"on_destroy_add": ((10941110, 1),)},
    # 尽小花·伊鞠: on entry, discard one and draw a spell from the deck.
    10574120: {"on_play_add": (("unknown_spell", 1),)},
}


# Keep these keys stable: they are written into the JSONL observation log and
# can therefore be used directly as categorical features by training tools.
UNKNOWN_CARD_TYPE_LABELS: dict[str, str] = {
    "unknown_spell": "未知法术",
    "unknown_follower": "未知随从",
    "unknown_amulet": "未知护符",
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
    magic_boost: int = 0
    _is_mage: bool = False
    # Per-turn counters are kept separately so the overlay can show a useful
    # timeline (T1:0, T2:1, Total:3) instead of only the running total.
    turn_magic_boost: dict[int, int] = field(default_factory=dict)
    current_turn: int = 0
    evolution_count: int = 0
    saint_daphen_turn: int | None = None
    saint_daphen_triggers: list[tuple[int, int]] = field(default_factory=list)
    liberation_count: int = 0
    _evolved_signatures: set[tuple[int, int]] = field(default_factory=set)
    recent_evolution_events: list[tuple[int, int, str]] = field(default_factory=list)
    recent_actions: list[tuple[int, int, int, str]] = field(default_factory=list)
    _action_sequence: int = 0
    _last_evolve_points: int | None = None
    _last_super_evolve_points: int | None = None
    _last_hand_count: int | None = None

    def reset(self) -> None:
        self.cards.clear()
        self._played_count = 0
        self._destroyed_count = 0
        self._event_sequences.clear()
        self.magic_boost = 0
        self._is_mage = False
        self.turn_magic_boost.clear()
        self.current_turn = 0
        self.evolution_count = 0
        self.saint_daphen_turn = None
        self.saint_daphen_triggers.clear()
        self.liberation_count = 0
        self._evolved_signatures.clear()
        self.recent_evolution_events.clear()
        self.recent_actions.clear()
        self._action_sequence = 0
        self._last_evolve_points = None
        self._last_super_evolve_points = None
        self._last_hand_count = None

    def to_training_dict(self) -> dict[str, object]:
        """Return a stable, JSON-serializable public-hand observation.

        Exact cards and type-only draws are deliberately separate.  A model
        can use the former as a known card ID and the latter as a constraint;
        it must not treat a type-only draw as an identified card.
        """
        known_cards: list[dict[str, int]] = []
        known_types: list[dict[str, object]] = []
        for value, count in self.cards.items():
            if not isinstance(count, int) or count <= 0:
                continue
            if isinstance(value, int) and value > 0:
                known_cards.append({"card_id": value, "count": count})
            elif isinstance(value, str) and value in UNKNOWN_CARD_TYPE_LABELS:
                known_types.append(
                    {
                        "kind": value.removeprefix("unknown_"),
                        "count": count,
                    }
                )
        known_cards.sort(key=lambda item: item["card_id"])
        known_types.sort(key=lambda item: str(item["kind"]))
        return {
            "known_cards": known_cards,
            "known_types": known_types,
            "magic_boost": self.magic_boost if self._is_mage else None,
            "turn_magic_boost": {str(k): v for k, v in sorted(self.turn_magic_boost.items())},
            "evolution_count": self.evolution_count,
            "current_turn": self.current_turn,
            "saint_daphen_turn": self.saint_daphen_turn,
            "saint_daphen_triggers": [
                {"turn": turn, "base_evolution": base} for turn, base in self.saint_daphen_triggers
            ],
            "liberation_count": self.liberation_count,
            "recent_evolution_events": [
                {"turn": turn, "card_id": card_id, "kind": kind}
                for turn, card_id, kind in self.recent_evolution_events[-20:]
            ],
            "recent_actions": [
                {"turn": turn, "card_id": card_id, "kind": kind, "order": order}
                for turn, order, card_id, kind in self.recent_actions[-40:]
            ],
        }

    def update(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        self._is_mage = snapshot.get("opponent_class_id") == 3
        turn_value = opponent.get("turn")
        # During the local player's end step the opponent player object can
        # temporarily report turn 0/previous turn.  Prefer the battle-wide
        # turn supplied by the decoder and never overwrite a valid turn with
        # zero, otherwise the just-recorded boost is put into T0 and appears
        # lost in the UI.
        if not isinstance(turn_value, int) or turn_value <= 0:
            turn_value = snapshot.get("current_turn", self.current_turn)
        if isinstance(turn_value, int) and turn_value > 0:
            self.current_turn = turn_value
        if self.current_turn > 0:
            self.turn_magic_boost.setdefault(self.current_turn, 0)
        self._update_evolution_count(opponent)
        hand = opponent.get("hand")
        hand_count = len(hand) if isinstance(hand, (list, tuple)) else None
        previous_hand_count = self._last_hand_count
        self._effect_hand_count_delta = (
            hand_count - previous_hand_count
            if isinstance(hand_count, int) and isinstance(previous_hand_count, int)
            else None
        )
        supplied_evolution = opponent.get("evolution_count", opponent.get("evolve_count"))
        if isinstance(supplied_evolution, int) and supplied_evolution >= 0:
            self.evolution_count = supplied_evolution
        events = snapshot.get("events")
        if isinstance(events, (list, tuple)):
            for event in events:
                if not isinstance(event, dict) or bool(event.get("is_ally")):
                    continue
                sequence = event.get("sequence")
                if not isinstance(sequence, int) or sequence in self._event_sequences:
                    continue
                self._event_sequences.add(sequence)
                event_name = str(event.get("type") or "").casefold()
                if "evolve" in event_name or "进化" in event_name:
                    amount = event.get("count", event.get("amount", 1))
                    if isinstance(amount, int) and amount > 0:
                        self.evolution_count += amount
                self._consume_public_draw(event)

        played = opponent.get("played_card_ids", ())
        played_items = list(_history_ids(played))
        if len(played_items) < self._played_count:
            self._played_count = 0
        for card_id in played_items[self._played_count:]:
            self._consume_play(card_id, opponent)
        self._played_count = len(played_items)

        destroyed = opponent.get("destroyed_card_ids", ())
        destroyed_items = list(_history_ids(destroyed))
        if len(destroyed_items) < self._destroyed_count:
            self._destroyed_count = 0
        for card_id in destroyed_items[self._destroyed_count:]:
            self._consume_destroy(card_id)
        self._destroyed_count = len(destroyed_items)
        self._last_hand_count = hand_count
        # General Liberation Art progress is independent of Saint Daphen.
        self.liberation_count = self.current_turn + self.evolution_count

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
                        key = canonical_card_id(value)
                        self.cards[key] += 1
                        # Saint Daphen only starts its own Liberation Art
                        # tracker when it is added by Invocation; playing a
                        # copy from hand must not create a trigger.
                        if key == 10404110 and event_type == "BattleResponseDrawOpenWithEffect" and self.current_turn > 0:
                            self.saint_daphen_turn = self.current_turn
                            self.saint_daphen_triggers.append((self.current_turn, self.evolution_count))
            return

        # Future decoder versions may be able to identify a hidden draw's
        # type without revealing its exact CardId.  Accept those annotations
        # while leaving ordinary hidden draws uncounted.
        kind = str(event.get("known_kind") or event.get("card_kind") or "").casefold()
        if bool(event.get("is_spell")) or kind in {"spell", "法术"}:
            amount = event.get("draw_num") or event.get("add_num") or 1
            if isinstance(amount, int) and amount > 0:
                self.cards["unknown_spell"] += amount

    def _consume_play(self, card_id: int, opponent: dict[str, object] | None = None) -> None:
        key = canonical_card_id(card_id)
        boost = 0
        if self._is_mage and is_spell(key):
            boost += 1
        if self.cards.get(key, 0) > 0:
            self.cards[key] -= 1
            if self.cards[key] <= 0:
                del self.cards[key]
        effect = KNOWN_HAND_EFFECTS.get(key, {})
        self._add_effect(effect.get("on_play_add"))
        if not effect.get("on_play_add"):
            self._add_effect(inferred_hand_additions(key, "play"))
        if self._is_mage:
            boost += magic_boost_amount(key, "play")
        # 洋荷在场时，后续每个其他随从入场都会使手牌发动一次魔力增幅。
        # 优先使用场面中的 card_id；没有场面数据时不做臆测。
        if self._is_mage and key != 10834120 and self._yonghe_active(opponent):
            metadata_type = self._card_type(key)
            if metadata_type == 1:
                boost += 1
        if boost:
            self.magic_boost += boost
            if self.current_turn > 0:
                self.turn_magic_boost[self.current_turn] = self.turn_magic_boost.get(self.current_turn, 0) + boost
        if self.current_turn > 0:
            self._action_sequence += 1
            self.recent_actions.append((self.current_turn, self._action_sequence, key, "使用"))

    def _update_evolution_count(self, opponent: dict[str, object]) -> None:
        """Count normal and super-evolutions from public field state.

        The memory model exposes ``evolve_state`` on field cards but does not
        expose a cumulative evolution counter. Tracking each unique card's
        transition lets us count both normal and super-evolution exactly once.
        """
        evolve_points = opponent.get("evolve_points")
        super_evolve_points = opponent.get("super_evolve_points")
        spent_evolve = isinstance(evolve_points, int) and isinstance(self._last_evolve_points, int) and evolve_points < self._last_evolve_points
        spent_super = isinstance(super_evolve_points, int) and isinstance(self._last_super_evolve_points, int) and super_evolve_points < self._last_super_evolve_points
        field = opponent.get("field")
        if not isinstance(field, (list, tuple)):
            self._last_evolve_points = evolve_points if isinstance(evolve_points, int) else self._last_evolve_points
            self._last_super_evolve_points = super_evolve_points if isinstance(super_evolve_points, int) else self._last_super_evolve_points
            return
        for index, card in enumerate(field):
            if not isinstance(card, dict):
                continue
            state = card.get("evolve_state")
            if not isinstance(state, int) or state <= 0:
                continue
            uid = card.get("unique_id")
            card_id = card.get("base_card_id") or card.get("card_id")
            signature = (int(uid) if isinstance(uid, int) and uid else index, int(card_id) if isinstance(card_id, int) else 0)
            if signature in self._evolved_signatures:
                continue
            self._evolved_signatures.add(signature)
            self.evolution_count += 1
            if self.current_turn > 0 and isinstance(card_id, int):
                manual = spent_super if state >= 2 else spent_evolve
                kind = ("手动" if manual else "自动") + ("超进化" if state >= 2 else "进化")
                card_id = canonical_card_id(card_id)
                self.recent_evolution_events.append((self.current_turn, card_id, kind))
                self._action_sequence += 1
                self.recent_actions.append((self.current_turn, self._action_sequence, card_id, kind))
        self._last_evolve_points = evolve_points if isinstance(evolve_points, int) else self._last_evolve_points
        self._last_super_evolve_points = super_evolve_points if isinstance(super_evolve_points, int) else self._last_super_evolve_points

    def _consume_destroy(self, card_id: int) -> None:
        effect = KNOWN_HAND_EFFECTS.get(canonical_card_id(card_id), {})
        self._add_effect(effect.get("on_destroy_add"))
        if not effect.get("on_destroy_add"):
            self._add_effect(inferred_hand_additions(card_id, "destroy"))
        if self._is_mage:
            self.magic_boost += magic_boost_amount(card_id, "destroy")

    def _add_effect(self, additions: object) -> None:
        """Record an explicitly public card or type-only draw.

        Registry entries use ``((card_or_type, count), ...)``.  A positive
        integer is an exact CardId; one of ``unknown_spell``,
        ``unknown_follower`` or ``unknown_amulet`` is a type-only draw.  This
        deliberately avoids inferring an identity for effects such as “draw a
        follower”.
        """
        if not isinstance(additions, (tuple, list)):
            return
        for value in additions:
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                continue
            card_or_type, amount = value
            if not isinstance(amount, int) or amount <= 0:
                continue
            if isinstance(card_or_type, int) and card_or_type > 0:
                # A public effect is only a prediction until the opponent's
                # hand actually grows. This prevents cards whose text merely
                # references a token (or whose optional branch was not chosen)
                # from polluting the known-hand ledger. Unit/integration
                # callers without hand snapshots retain the old behavior.
                delta = getattr(self, "_effect_hand_count_delta", None)
                if delta is not None and delta <= 0:
                    continue
                self.cards[canonical_card_id(card_or_type)] += amount
            elif isinstance(card_or_type, str) and card_or_type in UNKNOWN_CARD_TYPE_LABELS:
                self.cards[card_or_type] += amount

    @staticmethod
    def _card_type(card_id: int) -> int | None:
        from .card_effects import get_card_effect
        effect = get_card_effect(card_id)
        return effect.type if effect is not None else None

    @staticmethod
    def _yonghe_active(opponent: dict[str, object] | None) -> bool:
        if not isinstance(opponent, dict):
            return False
        field = opponent.get("field")
        if not isinstance(field, (list, tuple)):
            return False
        for card in field:
            if not isinstance(card, dict):
                continue
            value = card.get("base_card_id") or card.get("card_id")
            if isinstance(value, int) and canonical_card_id(value) == 10834120:
                return True
        return False


__all__ = ["KNOWN_HAND_EFFECTS", "OpponentKnownHand"]
