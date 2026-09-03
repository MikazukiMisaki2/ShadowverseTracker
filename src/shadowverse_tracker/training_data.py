"""Compact, replayable match records for model-training pipelines.

The normal ``app_session.jsonl`` file is intentionally a diagnostic stream and
contains a full snapshot envelope for every refresh.  This module builds a
second stream: one small record per match, with the deck embedded once and a
timeline of state checkpoints plus semantic events.  It never stores managed
memory addresses, process ids, or card names; card ids are stable categorical
features and keep the file small.

The format is deliberately JSONL rather than a Python-specific serialization so
it can be consumed by pandas, PyTorch, Rust, or a simple line reader.  Keys are
short because a long match can contain thousands of repeated state values::

    {"v":2,"id":"...","deck":{"k":"...","c":[[id,n],...]},
     "p":[{"c":5,"o":1},{"c":3,"o":0}],
     "m":{"i":[...],"r":[...],"f":[...],"o":2},
     "s":[{"t":1,"p":[...,...]}],
     "e":[{"t":1,"s":0,"k":"p","c":123,"u":7}]}

``s`` entries are complete checkpoints (not deltas), so replay code can seek
to any checkpoint without applying a long chain of patches.  ``e`` entries are
the event timeline and include attacks, effects, hand/deck draws, evolution,
and direct field placement.  Unknown event types are retained as ``x`` events
instead of being discarded.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import secrets
import urllib.error
import urllib.request

from .card_catalog import canonical_card_id
from .match_history import result_label


SCHEMA_VERSION = 2


def _without_addresses(value: object) -> object:
    """Return a JSON-compatible value without any managed-memory addresses.

    Response DTOs can contain nested ``Card`` objects.  Removing only the
    top-level response address is not enough for event de-duplication because
    the nested card object is often recreated at a different address on the
    next poll even though it represents the same draw/play.
    """
    if isinstance(value, dict):
        return {
            key: _without_addresses(item)
            for key, item in value.items()
            if key != "address"
        }
    if isinstance(value, list):
        return [_without_addresses(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_addresses(item) for item in value)
    return value


def _int(value: object, *, positive: bool = False) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if positive and value <= 0:
        return None
    return int(value)


def _card_id(value: object) -> int | None:
    value = _int(value, positive=True)
    return canonical_card_id(value) if value is not None else None


def _side(value: object) -> int:
    """Map ``is_ally`` to 0=self, 1=opponent, -1=unknown."""
    if isinstance(value, bool):
        return 0 if value else 1
    return -1


def _turn(snapshot: dict[str, object], players: tuple[object, ...] = ()) -> int:
    value = _int(snapshot.get("current_turn"), positive=True)
    if value is not None:
        return value
    # Recorder callers normally receive a full snapshot but do not otherwise
    # need to unpack the root just to label an event.  Fall back to the same
    # player collection used by ``_state_checkpoint`` so event timestamps do
    # not become ``T0`` when ``current_turn`` is omitted by a test adapter or
    # a root-only battle reader.
    if not players:
        root = snapshot.get("root")
        root_players = root.get("players") if isinstance(root, dict) else None
        if isinstance(root_players, (list, tuple)):
            players = tuple(root_players)
    for player in players:
        if isinstance(player, dict):
            value = _int(player.get("turn"), positive=True)
            if value is not None:
                return value
    return 0


def _clean_ids(value: object) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[int] = []
    for item in value:
        if isinstance(item, (list, tuple)) and item:
            item = item[0]
        card_id = _card_id(item)
        if card_id is not None:
            result.append(card_id)
    return result


def _clean_ints(value: object) -> list[int]:
    """Keep bounded integer choices such as option indexes/target UIDs."""
    if not isinstance(value, (list, tuple)):
        return []
    result: list[int] = []
    for item in value:
        number = _int(item, positive=True)
        if number is not None:
            result.append(number)
    return result


def _compact_card(card: object, *, field: bool) -> list[int] | None:
    if not isinstance(card, dict):
        return None
    uid = _int(card.get("unique_id"), positive=True) or 0
    base = _card_id(card.get("base_card_id") or card.get("card_id")) or 0
    runtime = _card_id(card.get("card_id")) or base
    # Hidden cards are represented by a zero id, while retaining the slot.  A
    # model can therefore learn hand size without accidentally receiving the
    # opponent's private card identity.
    if card.get("hidden") or (base <= 0 and runtime <= 0):
        base = runtime = 0
    cost = _int(card.get("cost"))
    attack = _int(card.get("attack"))
    life = _int(card.get("life"))
    card_type = _int(card.get("card_type"))
    style = _int(card.get("style_id"))
    if not field:
        # [uid, base id, runtime id, cost, attack, life, type, style]
        return [uid, base, runtime, cost if cost is not None else 0,
                attack if attack is not None else 0,
                life if life is not None else 0,
                card_type if card_type is not None else 0,
                style if style is not None else 0]
    max_life = _int(card.get("max_life"))
    evolve = _int(card.get("evolve_state"))
    countdown = _int(card.get("countdown"))
    stack = _int(card.get("stack"))
    # Status flags are packed into one integer.  The bit assignment is stable
    # and documented in ``STATUS_BITS`` below.
    flags = 0
    for bit, name in enumerate(STATUS_BITS):
        if bool(card.get(name)):
            flags |= 1 << bit
    # [uid, base id, runtime id, cost, atk, life, max life, type, evolve,
    #  countdown, stack, status flags, style]
    return [uid, base, runtime, cost if cost is not None else 0,
            attack if attack is not None else 0,
            life if life is not None else 0,
            max_life if max_life is not None else 0,
            card_type if card_type is not None else 0,
            evolve if evolve is not None else 0,
            countdown if countdown is not None else 0,
            stack if stack is not None else 0,
            flags,
            style if style is not None else 0]


# FieldCard status booleans.  Adding a flag is backwards compatible because
# the packed integer remains an opaque feature for older training consumers.
STATUS_BITS = (
    "has_guard", "has_drain", "has_sneak", "has_killer", "has_cant_be_attacked",
    "has_cant_select", "has_last_word", "is_earth_sigil", "has_spell_boost",
    "has_damage_cut", "has_cant_attack", "has_induction", "has_activation",
    "has_reduce_damage", "has_cant_destroy", "has_super_evolve_buff",
    "is_remove_field_at_turn_change", "has_temp_shield", "is_same_name_token",
)


def compact_deck(deck: object) -> dict[str, object] | None:
    """Return a stable deck identity and card multiset without local addresses."""
    if not isinstance(deck, dict) and hasattr(deck, "to_dict"):
        try:
            deck = deck.to_dict()  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            return None
    if not isinstance(deck, dict):
        return None
    cards: list[list[int]] = []
    raw_cards = deck.get("cards")
    if isinstance(raw_cards, (list, tuple)):
        for card in raw_cards:
            if not isinstance(card, dict):
                continue
            card_id = _card_id(card.get("card_id"))
            count = _int(card.get("count"))
            if card_id is not None and count is not None and count > 0:
                cards.append([card_id, count])
    cards.sort(key=lambda item: item[0])
    deck_key = deck.get("deck_key") or deck.get("key")
    result: dict[str, object] = {
        "k": str(deck_key or ""),
        "c": cards,
    }
    for source, target in (
        (("deck_id",), "i"),
        (("class_id",), "cl"),
        (("deck_format", "format_version"), "f"),
        (("total_cards",), "n"),
    ):
        value = next((_int(deck.get(name)) for name in source if _int(deck.get(name)) is not None), None)
        if value is not None:
            result[target] = value
    name = deck.get("deck_name") or deck.get("name")
    if isinstance(name, str) and name:
        # The name is useful for human inspection but is not required for
        # replay.  It is kept only when short to avoid unbounded user input.
        result["name"] = name[:128]
    return result


def _compact_player(player: object) -> dict[str, object]:
    if not isinstance(player, dict):
        return {}
    result: dict[str, object] = {}
    # Scalar state needed to replay decisions and outcomes.
    fields = (
        ("unique_id", "id"), ("deck_count", "d"), ("life", "hp"),
        ("max_life", "mh"), ("pp", "pp"), ("max_pp", "mp"),
        ("turn", "t"), ("evolve_points", "ep"), ("max_evolve_points", "me"),
        ("super_evolve_points", "sp"), ("max_super_evolve_points", "ms"),
        ("extra_pp", "xp"), ("preparation_extra_pp", "pe"),
        ("extra_pp_state", "xs"), ("cemetery_count", "cy"), ("rally", "ra"),
        ("evolve_turn", "et"), ("super_evolve_turn", "st"),
        ("restore_extra_pp_turn", "rt"), ("remaining_pp_until_awakening", "wa"),
        ("open_extra_pp_state", "oe"),
        ("evolve_count", "ec"), ("manual_evolve_count", "mc"),
        ("play_count", "pc"), ("result_code", "r"), ("total_damage", "dg"),
    )
    for source, target in fields:
        value = _int(player.get(source))
        if value is not None:
            result[target] = value
    if isinstance(player.get("is_first_side"), bool):
        result["1"] = bool(player["is_first_side"])
    player_flags = 0
    for bit, name in enumerate(
        (
            "is_end_mulligan", "is_awakening", "is_evolved_this_turn",
            "is_used_extra_pp_this_turn", "is_deck_out_win",
            "cant_fanfare_and_enhance_ally_follower",
        )
    ):
        if player.get(name) is True:
            player_flags |= 1 << bit
    if player_flags:
        result["x"] = player_flags

    def compact_instances(value: object, fields: tuple[tuple[str, str, str], ...]) -> list[dict[str, object]]:
        if not isinstance(value, (list, tuple)):
            return []
        rows: list[dict[str, object]] = []
        for instance in value:
            if not isinstance(instance, dict):
                continue
            row: dict[str, object] = {}
            for source, target, kind in fields:
                raw = instance.get(source)
                if kind == "card":
                    parsed = _card_id(raw)
                elif kind == "bool":
                    parsed = int(raw) if isinstance(raw, bool) else None
                else:
                    parsed = _int(raw)
                if parsed is not None and (parsed != 0 or kind == "bool"):
                    row[target] = parsed
            if row:
                rows.append(row)
        return rows

    crests = compact_instances(
        player.get("crests"),
        (("card_id", "c", "card"), ("unique_id", "u", "int"),
         ("countdown", "d", "int"), ("faith_value", "f", "int"),
         ("style_id", "st", "int")),
    )
    if crests:
        result["cr"] = crests
    extra_crests = compact_instances(
        player.get("extra_crests"),
        (("card_id", "c", "card"), ("unique_id", "u", "int"),
         ("countdown", "d", "int"), ("variable_x", "x", "int"),
         ("style_id", "st", "int")),
    )
    if extra_crests:
        result["xr"] = extra_crests
    boons = compact_instances(
        player.get("boons"),
        (("card_id", "c", "card"), ("unique_id", "u", "int")),
    )
    if boons:
        result["bo"] = boons
    special_actions = compact_instances(
        player.get("special_action_cards"),
        (("card_id", "c", "card"), ("unique_id", "u", "int"),
         ("state", "v", "int"), ("can_special_action_in_battle", "b", "bool")),
    )
    if special_actions:
        result["sa"] = special_actions
    related_styles = player.get("public_related_card_styles")
    if isinstance(related_styles, (list, tuple)):
        styles: list[list[int]] = []
        for pair in related_styles:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            card_id = _card_id(pair[0])
            style_id = _int(pair[1])
            if card_id is not None and style_id is not None:
                styles.append([card_id, style_id])
        if styles:
            result["rs"] = styles
    # Keep hand slots (including hidden slots) and complete public field card
    # status in a deterministic order.  A missing collection is represented by
    # an empty array, which is important for replaying a card leaving play.
    hand = player.get("hand")
    result["h"] = [item for item in (_compact_card(card, field=False) for card in hand)
                   if item is not None] if isinstance(hand, (list, tuple)) else []
    field = player.get("field")
    result["f"] = [item for item in (_compact_card(card, field=True) for card in field)
                    if item is not None] if isinstance(field, (list, tuple)) else []
    result["pl"] = _clean_ids(player.get("played_card_ids"))
    result["de"] = _clean_ids(player.get("destroyed_card_ids"))
    return result


def _compact_int_list(value: object) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    return [number for item in value if (number := _int(item, positive=True)) is not None]


def _compact_legal_actions(value: object) -> dict[str, object] | None:
    """Pack the action mask used by policy training into stable short keys."""
    if not isinstance(value, dict):
        return None
    mapping = (
        ("can_play_cards", "p"), ("can_play_cards_with_extra_pp", "px"),
        ("can_enhance_play_cards", "pe"), ("can_accelerate_play_cards", "pa"),
        ("can_crystal_play_cards", "pc"), ("can_attack_leader_cards", "al"),
        ("can_attack_field_cards", "af"), ("attacked_cards", "aa"),
        ("can_activation_field_cards", "ac"),
        ("can_activation_field_cards_with_extra_pp", "ax"),
        ("has_activation_field_cards", "ah"), ("can_evolve_cards", "ev"),
        ("can_super_evolve_cards", "se"),
        ("can_super_evolve_with_skill_cards", "sx"),
        ("can_fusion_cards", "fu"), ("has_fusion_hand_cards", "fh"),
        ("can_special_action_field_cards", "sf"),
        ("can_special_action_area_cards", "sa"),
        ("can_mode_skill_cards", "ms"),
        ("super_evolve_can_mode_skill_cards", "mx"),
        ("can_special_action_in_battle", "sb"),
    )
    result: dict[str, object] = {}
    for source, target in mapping:
        items = _compact_int_list(value.get(source))
        if items:
            result[target] = items
    target_map = value.get("attack_targets")
    if isinstance(target_map, dict):
        packed_targets: dict[str, list[int]] = {}
        for attacker, targets in target_map.items():
            attacker_id = _int(attacker, positive=True)
            target_ids = _compact_int_list(targets)
            if attacker_id is not None and target_ids:
                packed_targets[str(attacker_id)] = target_ids
        if packed_targets:
            result["at"] = packed_targets
    return result or None


def _compact_ledger(value: object) -> dict[str, object] | None:
    """Keep only changing deck counts; the full card multiset is in ``deck``."""
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    total = _int(value.get("authoritative_deck_count"))
    if total is not None:
        result["n"] = total
    rows = value.get("rows")
    compact_rows: list[list[int]] = []
    if isinstance(rows, (list, tuple)):
        for row in rows:
            if not isinstance(row, dict):
                continue
            card_id = _card_id(row.get("card_id"))
            initial = _int(row.get("initial"))
            remaining = _int(row.get("remaining"))
            if card_id is None or initial is None or remaining is None:
                continue
            # Unchanged rows can be reconstructed from the embedded deck.
            if remaining != initial:
                compact_rows.append([card_id, remaining])
    if compact_rows:
        result["r"] = compact_rows
    for source, target in (("unknown_removed", "u"), ("burned_cards", "b")):
        count = _int(value.get(source))
        if count is not None and count:
            result[target] = count
    burned_ids = _clean_ids(value.get("burned_card_ids"))
    if burned_ids:
        result["bi"] = burned_ids
    return result or None


def _state_checkpoint(snapshot: dict[str, object]) -> dict[str, object] | None:
    root = snapshot.get("root")
    players = root.get("players") if isinstance(root, dict) else None
    if not isinstance(players, (list, tuple)) or len(players) < 2:
        return None
    checkpoint: dict[str, object] = {
        "t": _turn(snapshot, tuple(players)),
        "p": [_compact_player(players[0]), _compact_player(players[1])],
    }
    root_dict = root if isinstance(root, dict) else {}
    if isinstance(root_dict.get("is_ally_turn"), bool):
        checkpoint["a"] = int(root_dict["is_ally_turn"])
    mode = snapshot.get("battle_mode") or root_dict.get("battle_mode")
    if isinstance(mode, str) and mode:
        checkpoint["g"] = mode[:32]
    legal = _compact_legal_actions(snapshot.get("legal_actions"))
    if legal is not None:
        checkpoint["l"] = legal
    ledger = _compact_ledger(snapshot.get("deck_ledger"))
    if ledger is not None:
        checkpoint["b"] = ledger
    return checkpoint


def _event_side(event: dict[str, object], *, fallback: int = -1) -> int:
    value = _side(event.get("is_ally"))
    if value < 0:
        # A few response DTOs name the actor flag differently.  Keeping this
        # alias handling here makes all event kinds use the same 0/1 side
        # encoding without duplicating it in each branch below.
        for key in ("is_act_ally", "is_from_ally", "is_from_ally_side"):
            value = _side(event.get(key))
            if value >= 0:
                break
    return value if value >= 0 else fallback


def _first_card_id(value: object) -> int | None:
    if isinstance(value, dict):
        return _card_id(value.get("base_card_id") or value.get("card_id"))
    return _card_id(value)


def _first_card_uid(value: object) -> int | None:
    if isinstance(value, dict):
        return _int(value.get("unique_id"), positive=True)
    return None


def _target_rows(
    value: object,
    fields: tuple[tuple[str, str, str], ...],
) -> list[dict[str, object]]:
    """Pack a list of decoder target dictionaries using short stable keys."""
    if not isinstance(value, (list, tuple)):
        return []
    rows: list[dict[str, object]] = []
    for target in value:
        if not isinstance(target, dict):
            continue
        row: dict[str, object] = {}
        for source, key, kind in fields:
            raw = target.get(source)
            if kind == "card":
                # Some response DTOs wrap the card identity in a compact
                # card dictionary (for example Bounce.Target.AfterCard).
                # Accept both that shape and a bare CardId without expanding
                # the replay vocabulary.
                result = _first_card_id(raw) if isinstance(raw, dict) else _card_id(raw)
            elif kind == "bool":
                result = int(raw) if isinstance(raw, bool) else None
            else:
                result = _int(raw)
            if result is not None:
                row[key] = result
        if row:
            rows.append(row)
    return rows


def _target_ids(value: object) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[int] = []
    for target in value:
        if isinstance(target, dict):
            target = target.get("unique_id") or target.get("card_id")
        elif isinstance(target, (list, tuple)):
            result.extend(_target_ids(target))
            continue
        target_id = _int(target, positive=True)
        if target_id is not None:
            result.append(target_id)
    return result


def _event_records(event: dict[str, object], turn: int) -> list[dict[str, object]]:
    """Normalize one decoder event to one or more compact training events."""
    event_type = str(event.get("type") or "Unknown")
    side = _event_side(event)
    sequence = _int(event.get("sequence"), positive=True)
    base: dict[str, object] = {"t": turn, "s": side}
    if sequence is not None:
        base["q"] = sequence
    result: list[dict[str, object]] = []

    if event_type in {"BattleResponsePlayOpen", "BattleResponsePlayHide"}:
        item = {**base, "k": "p"}
        card_id = _card_id(event.get("card_id") or event.get("base_card_id"))
        uid = _int(event.get("unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        # ``card_style_id`` distinguishes an alternate/accelerated card
        # presentation while ``after_play_card_style_id`` preserves the
        # resolved style when a play changes the card in-place.
        style = _int(event.get("card_style_id"))
        if style is not None and style != 0:
            item["st"] = style
        if _int(event.get("play_kind")) is not None:
            item["pk"] = int(event["play_kind"])
        if _card_id(event.get("after_play_card_id")) is not None:
            item["a"] = _card_id(event.get("after_play_card_id"))
        after_style = _int(event.get("after_play_card_style_id"))
        if after_style is not None and after_style != 0:
            item["as"] = after_style
        selected = _clean_ints(event.get("selected_indexes"))
        if selected:
            item["si"] = selected
        targets = _target_ids(event.get("target_unique_id_by_skills"))
        if targets:
            item["to"] = targets
        if event_type.endswith("Hide"):
            item["h"] = 1
        result.append(item)
    elif event_type in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect", "BattleResponseDrawHide", "BattleResponseHandToken"}:
        item = {**base, "k": "d" if event_type.startswith("BattleResponseDraw") else "ht"}
        cards = event.get("cards")
        ids = []
        if isinstance(cards, (list, tuple)):
            ids = [card_id for card_id in (_first_card_id(card) for card in cards) if card_id is not None]
        if ids:
            item["c"] = ids
        amount = _int(event.get("add_num")) or _int(event.get("draw_num"))
        if amount is not None and amount > 0:
            item["n"] = amount
        if event_type == "BattleResponseDrawOpenWithEffect":
            item["fx"] = 1
            effect_targets = _clean_ints(event.get("effect_targets"))
            if effect_targets:
                item["to"] = effect_targets
        if event_type == "BattleResponseDrawHide":
            # The hidden counterpart carries only a count.  Never infer card
            # IDs from it, but retain the marker so replay code can model a
            # private draw and its deck decrement.
            item["h"] = 1
        if event.get("is_super_evolve") is True:
            item["x"] = 1
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        if isinstance(event.get("is_turn_start_draw"), bool) and event["is_turn_start_draw"]:
            item["st"] = 1
        result.append(item)
    elif event_type in {
        "BattleResponseMulliganReady", "BattleResponseMulliganFinish",
        "BattleResponseTurnStart", "BattleResponseTurnStartEnd",
        "BattleResponseTurnEnd", "BattleResponseTurnEndSkillEnd",
        "BattleResponseActionEnd",
    }:
        item = {**base, "k": "phase", "n": event_type.removeprefix("BattleResponse")}
        phase_turn = _int(event.get("turn"), positive=True)
        if phase_turn is not None:
            item["tt"] = phase_turn
        if isinstance(event.get("is_force"), bool) and event["is_force"]:
            item["f"] = 1
        if isinstance(event.get("is_delay"), bool) and event["is_delay"]:
            item["d"] = 1
        result.append(item)
    elif event_type == "BattleResponseUpdatePP":
        item = {**base, "k": "res", "n": "pp"}
        values = (
            ("pp", "p"), ("max_pp", "m"), ("preparation_extra_pp", "x"),
            ("prev_pp", "pr"), ("skill_add_pp", "a"), ("skill_add_max_pp", "am"),
        )
        for source, key in values:
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        flags = 0
        for bit, source in enumerate(("is_super_evolve", "is_consume_extra_pp", "is_card_play")):
            if event.get(source) is True:
                flags |= 1 << bit
        if flags:
            item["f"] = flags
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        result.append(item)
    elif event_type == "BattleResponseUpdateEP":
        item = {**base, "k": "res", "n": "ep"}
        for source, key in (("ep", "p"), ("max_ep", "m"), ("sep", "x"), ("max_sep", "y")):
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        for source, key, card in (("skill_id", "sk", False), ("card_id", "c", True), ("style_id", "st", False)):
            value = _card_id(event.get(source)) if card else _int(event.get(source))
            if value is not None and (card or value != 0):
                item[key] = value
        result.append(item)
    elif event_type in {"BattleResponseExtraPP", "BattleResponseExtraPPRestore"}:
        item = {**base, "k": "res", "n": "extra_pp"}
        for source, key in (("pp", "p"), ("max_pp", "m")):
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        if event.get("is_cancel") is True:
            item["f"] = 1
        result.append(item)
    elif event_type == "BattleResponseMulligan" or event_type == "BattleModelMulliganSelection":
        item = {**base, "k": "m"}
        count = _int(event.get("replaced_count"))
        if count is None:
            flags = _int(event.get("change_card_flags")) or 0
            count = (flags & 0xF).bit_count()
        item["n"] = max(0, min(4, count))
        flags = _int(event.get("change_card_flags"))
        if flags:
            item["f"] = flags & 0xF
        hand_cards = event.get("hand_cards")
        hand_ids = [card_id for card_id in (_first_card_id(card) for card in hand_cards)
                    if card_id is not None] if isinstance(hand_cards, (list, tuple)) else []
        if hand_ids:
            # A local Mulligan response can carry the resolved post-change
            # hand.  Keep it on the event as an optional supplement to the
            # top-level ``m`` summary; the opponent remains hidden whenever
            # the client did not expose card identities.
            item["c"] = hand_ids
        if event.get("is_time_over") is True:
            item["x"] = 1
        result.append(item)
    elif event_type == "BattleResponseAttack":
        item = {**base, "k": "a"}
        for source, target in (
            ("from_unique_id", "u"), ("from_card_id", "c"),
            ("to_unique_id", "v"), ("to_card_id", "tc"),
            ("from_damage", "d"), ("to_damage", "td"),
            ("from_remove_type", "fr"), ("to_remove_type", "tr"),
            ("from_card_style_id", "fs"), ("to_card_style_id", "ts"),
        ):
            value = _int(event.get(source))
            if value is not None and (source.endswith("card_id") or source.endswith("unique_id") or value != 0):
                if source.endswith("card_id"):
                    value = _card_id(value)
                if value is not None:
                    item[target] = value
        for source, target in (("is_from_evolved", "fe"), ("is_to_evolved", "te"), ("is_super_evolve_blow", "sb")):
            if isinstance(event.get(source), bool) and event[source]:
                item[target] = 1
        result.append(item)
    elif event_type == "BattleResponseSuperEvolveBlow":
        # Super-evolution's collision/leader hit is reported separately from
        # the ordinary attack response. Keep its attacker and target in the
        # attack stream so a replay consumer does not lose this action.
        item = {**base, "k": "a", "n": "super_evolve_blow"}
        for source, target in (
            ("from_unique_id", "u"), ("to_card_unique_id", "v"),
            ("to_leader_unique_id", "l"), ("damage", "d"),
        ):
            value = _int(event.get(source), positive=source.endswith("unique_id"))
            if value is not None and (not source.endswith("unique_id") or value != 0):
                item[target] = value
        if event.get("is_dead") is True:
            item["x"] = 1
        result.append(item)
    elif event_type == "BattleResponseCancelAttack":
        item = {**base, "k": "a", "n": "cancel"}
        for source, target in (
            ("from_unique_id", "u"), ("to_unique_id", "v"),
            ("from_new_life", "fn"), ("to_new_life", "tn"),
        ):
            value = _int(event.get(source), positive=source.endswith("unique_id"))
            if value is not None and (not source.endswith("unique_id") or value != 0):
                item[target] = value
        result.append(item)
    elif event_type in {"BattleResponseSetAttackLimit", "BattleResponseAddModeSelectableCount", "BattleResponseIncreaseDamage"}:
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        card_id = _card_id(event.get("card_id"))
        if card_id is not None:
            item["c"] = card_id
        for source, key in (("unique_id", "u"), ("style_id", "st"), ("skill_id", "sk"), ("attack_limit", "l")):
            value = _int(event.get(source), positive=source == "unique_id")
            if value is not None and (source in {"unique_id", "attack_limit"} or value != 0):
                item[key] = value
        flags = 0
        for bit, source in enumerate(("is_evolved", "is_changed_ability")):
            if event.get(source) is True:
                flags |= 1 << bit
        if flags:
            item["f"] = flags
        result.append(item)
    elif event_type in {"BattleResponsePutCardFromDeck", "BattleResponsePutToken", "BattleResponsePutCardFromHand", "BattleResponseCastSpellFromHand"}:
        kind = {"BattleResponsePutCardFromDeck": "df", "BattleResponsePutToken": "tk",
                "BattleResponsePutCardFromHand": "fh", "BattleResponseCastSpellFromHand": "sp"}[event_type]
        item = {**base, "k": kind}
        cards = event.get("cards") or event.get("targets")
        if not cards and isinstance(event.get("card"), dict):
            cards = [event["card"]]
        ids: list[int] = []
        uids: list[int] = []
        if isinstance(cards, (list, tuple)):
            for card in cards:
                source_card = card.get("card") if isinstance(card, dict) and isinstance(card.get("card"), dict) else card
                card_id = _first_card_id(source_card)
                uid = _int(source_card.get("unique_id"), positive=True) if isinstance(source_card, dict) else None
                if card_id is not None:
                    ids.append(card_id)
                if uid is not None:
                    uids.append(uid)
        card_id = _card_id(event.get("card_id") or event.get("act_card_id"))
        if card_id is not None and not ids:
            ids.append(card_id)
        if ids:
            item["c"] = ids
        if uids:
            item["u"] = uids
        for source, key in (
            ("unique_id_before", "ub"),
            ("unique_id_before_accelerate", "ub"),
            ("enhance_index", "en"),
            ("skybound_art_state", "sa"),
            ("act_style_id", "st"),
        ):
            value = _int(event.get(source))
            if value is not None and value != 0:
                item[key] = value
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        if event.get("is_super_evolve") is True:
            item["x"] = 1
        if event.get("is_invocation"):
            item["iv"] = 1
        if event.get("is_overflow"):
            item["of"] = 1
        selected = _clean_ints(event.get("selected_indexes"))
        if selected:
            item["si"] = selected
        targets = _target_ids(event.get("target_unique_id_by_skills"))
        if targets:
            item["to"] = targets
        result.append(item)
    elif event_type == "BattleResponseFusion":
        item = {**base, "k": "fu"}
        fusion_card = event.get("fusion_card")
        fusion_id = _first_card_id(fusion_card)
        fusion_uid = _first_card_uid(fusion_card)
        if fusion_id is not None:
            item["c"] = fusion_id
        if fusion_uid is not None:
            item["u"] = fusion_uid
        materials = event.get("material_cards")
        material_ids = [
            card_id
            for card_id in (_first_card_id(card) for card in materials)
            if card_id is not None
        ] if isinstance(materials, (list, tuple)) else []
        if material_ids:
            item["m"] = material_ids
        if event.get("can_fusion_transform") is True:
            item["tr"] = 1
        result.append(item)
    elif event_type in {"BattleResponseTransformField", "BattleResponseTransformHand", "BattleResponseFusionTransform"}:
        item = {**base, "k": "xf", "n": event_type.removeprefix("BattleResponseTransform").removeprefix("BattleResponse")}
        before = _int(event.get("before_unique_id"), positive=True)
        if before is not None:
            item["u"] = before
        after = event.get("after_card")
        after_id = _first_card_id(after)
        after_uid = _first_card_uid(after)
        if after_id is not None:
            item["c"] = after_id
        if after_uid is not None:
            item["au"] = after_uid
        targets = _target_rows(
            event.get("targets"),
            (("unique_id", "u", "int"), ("is_ally", "s", "bool")),
        )
        if targets:
            item["tg"] = targets
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        result.append(item)
    elif event_type in {"BattleResponseBounce", "BattleResponseBounceIntoDeck", "BattleResponceReturnDeck"}:
        item = {**base, "k": "out", "n": event_type.removeprefix("BattleResponse").removeprefix("BattleResponce")}
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("after_card", "a", "card"), ("style_id", "st", "int"),
                ("is_ally", "s", "bool"), ("is_flood", "f", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        if event.get("is_super_evolve") is True or event.get("is_banish") is True:
            item["x"] = 1
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        if event.get("is_open") is True:
            item["o"] = 1
        result.append(item)
    elif event_type == "BattleResponseSetCountdown":
        item = {**base, "k": "fx", "n": "countdown"}
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("style_id", "st", "int"), ("count", "v", "int"),
                ("add_count", "a", "int"), ("count_sequence", "q", "int"),
                ("is_ally", "s", "bool"), ("is_by_turn_start", "b", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        result.append(item)
    elif event_type == "BattleResponseSpellBoost":
        item = {**base, "k": "fx", "n": "spell_boost"}
        targets = _target_rows(
            event.get("targets"),
            (("unique_id", "u", "int"), ("is_ally", "s", "bool")),
        )
        if targets:
            item["tg"] = targets
        amount = _int(event.get("add_count"))
        if amount is not None:
            item["a"] = amount
        if event.get("is_super_evolve") is True:
            item["x"] = 1
        result.append(item)
    elif event_type in {"BattleResponseActivation", "BattleResponseSpecialAction"}:
        # Activation (amulet/follower effect) and special-area actions are
        # distinct user choices even though both can carry target selections.
        item = {**base, "k": "ac" if event_type.endswith("Activation") else "sa"}
        card = event.get("card")
        card_id = _first_card_id(card) or _card_id(event.get("card_id") or event.get("act_card_id"))
        uid = _int(card.get("unique_id"), positive=True) if isinstance(card, dict) else _int(event.get("unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        selected = _clean_ints(event.get("selected_indexes"))
        if selected:
            item["si"] = selected
        targets = _target_ids(event.get("target_unique_id_by_skills"))
        if targets:
            item["to"] = targets
        result.append(item)
    elif event_type in {"BattleResponseEvolve", "BattleResponseSkillEvolve"}:
        item = {**base, "k": "ev"}
        card = event.get("evolved_card") or event.get("card")
        card_id = _first_card_id(card) or _card_id(event.get("card_id") or event.get("act_card_id"))
        uid = _int(card.get("unique_id"), positive=True) if isinstance(card, dict) else _int(event.get("unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        if event.get("is_super") or event.get("is_super_evolve"):
            item["x"] = 1
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        targets = _target_ids(event.get("targets") or event.get("target_unique_id_by_skills"))
        if targets:
            item["to"] = targets
        result.append(item)
    elif event_type in {"BattleResponseStartSelect", "BattleResponseDecideSelect", "BattleResponseCancelSelect"}:
        item = {**base, "k": "sel"}
        if event_type.endswith("StartSelect"):
            mode = _int(event.get("select_mode"))
            select_type = _int(event.get("select_type"))
            source = _int(event.get("source_unique_id"), positive=True)
            if mode is not None:
                item["m"] = mode
            if select_type is not None:
                item["y"] = select_type
            if source is not None:
                item["u"] = source
        elif event_type.endswith("DecideSelect"):
            card = _int(event.get("decide_card"), positive=True)
            ids = _clean_ints(event.get("decide_ids"))
            if card is not None:
                item["u"] = card
            if ids:
                item["i"] = ids
            if isinstance(event.get("decide_bool"), bool):
                item["b"] = int(event["decide_bool"])
        else:
            item["x"] = 1
        result.append(item)
    elif event_type == "BattleResponseSetStatusField":
        item = {**base, "k": "fx", "n": "SetStatusField"}
        if event.get("is_set") is True:
            item["x"] = 1
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        targets = _target_rows(
            event.get("targets"),
            (
                ("card_id", "c", "card"), ("unique_id", "u", "int"),
                ("atk", "a", "int"), ("life", "h", "int"),
                ("max_life", "m", "int"), ("add_atk", "aa", "int"),
                ("add_life", "al", "int"), ("add_max_life", "am", "int"),
                ("is_ally", "s", "bool"), ("is_evolved", "e", "bool"),
                ("style_id", "st", "int"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type == "BattleResponseSetStatusHand":
        item = {**base, "k": "fx", "n": "SetStatusHand"}
        for source, key in (("skill_id", "sk"),):
            value = _int(event.get(source))
            if value is not None and value != 0:
                item[key] = value
        flags = 0
        for bit, source in enumerate(("is_super_evolve", "is_spell_boost", "is_reset")):
            if event.get(source) is True:
                flags |= 1 << bit
        if flags:
            item["f"] = flags
        targets = _target_rows(
            event.get("targets"),
            (
                ("card_id", "c", "card"), ("unique_id", "u", "int"),
                ("card_type", "ty", "int"), ("cost", "co", "int"),
                ("atk", "a", "int"), ("life", "h", "int"),
                ("add_cost", "ac", "int"), ("added_cost", "dc", "int"),
                ("added_atk", "aa", "int"), ("added_life", "al", "int"),
                ("is_ally", "s", "bool"), ("style_id", "st", "int"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type == "BattleResponseSetStatusLeader":
        item = {**base, "k": "fx", "n": "SetStatusLeader"}
        running = _int(event.get("skill_running_number"), positive=True)
        if running is not None:
            item["sr"] = running
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("life", "h", "int"),
                ("max_life", "m", "int"), ("add_max_life", "a", "int"),
                ("is_ally", "s", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type in {"BattleResponseAttachSkillField", "BattleResponseAttachSkillHand", "BattleResponseAttachSkillLeaderArea", "BattleResponseAttachSkillExtraCrestArea"}:
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("style_id", "st", "int"), ("is_evolved", "e", "bool"),
                ("is_ally", "s", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type == "BattleResponseAffectDeck":
        item = {**base, "k": "fx", "n": "AffectDeck"}
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        result.append(item)
    elif event_type in {"BattleResponseSkillDamage", "BattleResponseSkillHeal", "BattleResponseHeal", "BattleResponseSkillEffect", "BattleResponseSkillEffectEach", "BattleResponseSkillEffectPrev"}:
        item = {**base, "k": "fx"}
        card_id = _card_id(event.get("from_card_id") or event.get("act_card_id") or event.get("card_id"))
        uid = _int(event.get("from_unique_id") or event.get("act_card_unique_id") or event.get("unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        skill = _int(event.get("skill_id") or event.get("skil_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        effect = _int(event.get("effect"))
        sub = _int(event.get("sub_effect"))
        if effect is not None and effect != 0:
            item["ef"] = effect
        if sub is not None and sub != 0:
            item["se"] = sub
        targets = _target_ids(event.get("target_unique_ids") or event.get("targets"))
        if targets:
            item["to"] = targets
        # Keep the per-target result as well as the flattened UID list.  The
        # latter is convenient for policy features; the former preserves
        # damage/heal/death/style information needed for deterministic replay.
        target_fields: tuple[tuple[str, str, str], ...]
        if event_type == "BattleResponseSkillDamage":
            target_fields = (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("damage", "d", "int"), ("is_ally", "s", "bool"),
                ("is_dead", "x", "bool"), ("is_evolved", "e", "bool"),
                ("style_id", "st", "int"),
            )
        elif event_type in {"BattleResponseSkillHeal", "BattleResponseHeal"}:
            target_fields = (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("healed", "h", "int"), ("is_ally", "s", "bool"),
                ("is_evolved", "e", "bool"), ("style_id", "st", "int"),
            )
        else:
            target_fields = (
                ("unique_id", "u", "int"), ("is_ally", "s", "bool"),
            )
        target_rows = _target_rows(event.get("targets"), target_fields)
        if target_rows:
            item["tg"] = target_rows
        damage = _int(event.get("damage")) or _int(event.get("healed"))
        if damage is not None and damage != 0:
            item["n"] = damage
        result.append(item)
    elif event_type == "BattleResponseBattleEnd":
        item = {**base, "k": "end"}
        codes = _clean_ints(event.get("result_codes"))
        if codes:
            item["r"] = codes
        heal = event.get("heal_result")
        if isinstance(heal, dict):
            row: dict[str, object] = {}
            for source, key in (("is_executed", "x"), ("healed", "h"), ("battle_start_max_life", "m")):
                value = heal.get(source)
                if isinstance(value, bool):
                    row[key] = int(value)
                elif isinstance(value, int):
                    row[key] = value
            if row:
                item["hr"] = row
        result.append(item)
    elif event_type in {"BattleResponseAddExtraCrest", "BattleResponseCantAddCrest", "BattleResponseCantAddExtraCrest", "BattleResponseChangeExtraCrestCount", "BattleResponseRemoveExtraCrest"}:
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        card_id = _card_id(event.get("card_id"))
        if card_id is not None:
            item["c"] = card_id
        uid = _int(event.get("unique_id"), positive=True)
        if uid is not None:
            item["u"] = uid
        for source, key in (("countdown", "cd"), ("style_id", "st"), ("faith_value", "fv"), ("skill_id", "sk")):
            value = _int(event.get(source))
            if value is not None and (value != 0 or source in {"countdown", "faith_value"}):
                item[key] = value
        if event_type in {"BattleResponseAddExtraCrest", "BattleResponseChangeExtraCrestCount"}:
            for source, key in (("count", "v"), ("add_count", "a")):
                value = _int(event.get(source))
                if value is not None:
                    item[key] = value
        if event.get("is_super_evolve") is True or event.get("is_banish") is True:
            item["x"] = 1
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("style_id", "st", "int"), ("count", "v", "int"),
                ("add_count", "a", "int"), ("is_ally", "s", "bool"),
                ("created_by_evolved", "e", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type in {"BattleResponseAddCrest", "BattleResponseReinforceFaith", "BattleResponseRemoveCrest", "BattleResponseChangeLeaderAreaCount"}:
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        card_id = _card_id(event.get("card_id"))
        if card_id is not None:
            item["c"] = card_id
        uid = _int(event.get("unique_id"), positive=True)
        if uid is not None:
            item["u"] = uid
        for source, key in (("countdown", "cd"), ("faith_value", "fv"), ("add", "a"), ("skill_id", "sk")):
            value = _int(event.get(source))
            if value is not None and (value != 0 or source in {"countdown", "faith_value"}):
                item[key] = value
        if event.get("is_super_evolve") is True or event.get("is_banish") is True:
            item["x"] = 1
        if event.get("is_battle_start") is True:
            item["b"] = 1
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("style_id", "st", "int"), ("count", "v", "int"),
                ("add_count", "a", "int"), ("is_ally", "s", "bool"),
                ("created_by_evolved", "e", "bool"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type in {"BattleResponseStack", "BattleResponseContentUhT9MJ"}:
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        values = (("unique_id", "u", False), ("card_id", "c", True), ("style_id", "st", False),
                  ("stack", "v", False), ("content", "v", False), ("add", "a", False),
                  ("skill_id", "sk", False))
        for source, key, card in values:
            value = _card_id(event.get(source)) if card else _int(event.get(source), positive=True if source == "unique_id" else False)
            if value is not None and (card or value != 0):
                item[key] = value
        flags = 0
        for bit, source in enumerate(("is_super_evolve", "is_destroy")):
            if event.get(source) is True:
                flags |= 1 << bit
        if flags:
            item["f"] = flags
        result.append(item)
    elif event_type in {"BattleResponsePushDeck", "BattleResponsePushDeckHide", "BattleResponseReplaceDeck"}:
        item = {**base, "k": "deck", "n": event_type.removeprefix("BattleResponse")}
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("style_id", "st", "int"), ("cost", "co", "int"),
                ("attack", "a", "int"), ("life", "h", "int"),
            ),
        )
        if targets:
            item["tg"] = targets
        for source, key in (("push_num", "n"), ("deck_count", "d"), ("skill_id", "sk")):
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        result.append(item)
    elif event_type in {"BattleResponseAddPlayCount", "BattleResponseAddCemeteryCount"}:
        item = {**base, "k": "res", "n": event_type.removeprefix("BattleResponse")}
        for source, key in (("add", "a"), ("skill_id", "sk")):
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        result.append(item)
    elif event_type == "BattleResponseEmote":
        item = {**base, "k": "sa", "n": "Emote"}
        for source, key in (("emote_type", "e"), ("timing", "g")):
            value = _int(event.get(source))
            if value is not None:
                item[key] = value
        result.append(item)
    elif event_type == "BattleResponseAddSkyboundArtCount":
        item = {**base, "k": "res", "n": "skybound_art"}
        targets = _target_rows(
            event.get("targets"),
            (("unique_id", "u", "int"), ("is_ally", "s", "bool")),
        )
        if targets:
            item["tg"] = targets
        if event.get("from_super_evolve_boost_skill") is True:
            item["x"] = 1
        result.append(item)
    elif event_type == "BattleResponseRandomAllocate":
        item = {**base, "k": "fx", "n": "random_allocate"}
        for source, key, card in (("card_id", "c", True), ("style_id", "st", False), ("skill_id", "sk", False)):
            value = _card_id(event.get(source)) if card else _int(event.get(source))
            if value is not None and (card or value != 0):
                item[key] = value
        values = _clean_ints(event.get("values"))
        if values:
            item["v"] = values
        result.append(item)
    elif event_type in {"BattleResponseSendArrow", "BattleResponseSendTouchCard", "BattleResponseTurnTimerStart", "BattleResponseMulliganSelect"}:
        item = {**base, "k": "sel", "n": event_type.removeprefix("BattleResponse")}
        targets = _clean_ints(event.get("target_unique_ids"))
        if targets:
            item["to"] = targets
        touched = _int(event.get("card_unique_id"), positive=True)
        if touched is not None:
            item["u"] = touched
        changed = _clean_ints(event.get("change_card_unique_ids"))
        if changed:
            item["i"] = changed
            item["n"] = len(changed)
        arrow_type = _int(event.get("arrow_type"))
        if arrow_type is not None and arrow_type != 0:
            item["a"] = arrow_type
        timer_turn = _int(event.get("turn"), positive=True)
        if event_type == "BattleResponseTurnTimerStart" and timer_turn is not None:
            item["tt"] = timer_turn
        result.append(item)
    elif event_type.startswith("BattleResponseActivate"):
        # Keyword/status activations (guard, rush, induction, last word, …)
        # are effects rather than a hand play.  Preserve their actor/card and
        # active state in the same compact vocabulary.
        item = {**base, "k": "fx", "n": event_type.removeprefix("BattleResponse")}
        card_id = _card_id(event.get("card_id"))
        uid = _int(event.get("unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        if isinstance(event.get("is_active"), bool):
            item["on"] = int(event["is_active"])
        if isinstance(event.get("is_evolved"), bool) and event["is_evolved"]:
            item["ev"] = 1
        result.append(item)
    elif event_type == "BattleResponseRemoveCard":
        item = {**base, "k": "out", "n": "RemoveCard"}
        card_id = _card_id(event.get("act_card_id"))
        uid = _int(event.get("act_card_unique_id"), positive=True)
        if card_id is not None:
            item["c"] = card_id
        if uid is not None:
            item["u"] = uid
        skill = _int(event.get("skill_id"))
        if skill is not None and skill != 0:
            item["sk"] = skill
        if event.get("is_skill_destroy_or_banish") is True or event.get("is_super_evolve") is True:
            item["x"] = 1
        targets = _target_rows(
            event.get("targets"),
            (
                ("unique_id", "u", "int"), ("card_id", "c", "card"),
                ("is_ally", "s", "bool"), ("is_evolved", "e", "bool"),
                ("remove_type", "rt", "int"), ("attack_card_id", "ac", "card"),
            ),
        )
        if targets:
            item["tg"] = targets
        result.append(item)
    elif event_type.startswith("BattleResponse"):
        # Preserve every other response (status changes, crest changes, turn
        # boundaries, PP updates, etc.).  Exact names make the stream useful
        # for future feature extraction even before a dedicated decoder is
        # added.  Strip the common prefix for a compact categorical value.
        item = {**base, "k": "x", "n": event_type.removeprefix("BattleResponse")}
        card_id = _card_id(event.get("card_id") or event.get("act_card_id"))
        if card_id is not None:
            item["c"] = card_id
        scalar_fields = (
            ("unique_id", "u", True), ("act_card_unique_id", "au", True),
            ("skill_id", "sk", False), ("style_id", "st", False),
            ("card_style_id", "st", False), ("play_kind", "pk", False),
            ("effect", "ef", False), ("sub_effect", "se", False),
            ("add_num", "n", False), ("draw_num", "d", False),
            ("damage", "dg", False), ("healed", "h", False),
            ("deck_count", "dc", False), ("pp", "p", False),
            ("max_pp", "mp", False), ("ep", "ep", False),
            ("sep", "sp", False),
        )
        for source, key, positive in scalar_fields:
            value = _int(event.get(source), positive=positive)
            if value is not None and (value != 0 or source in {"unique_id", "act_card_unique_id", "card_id"}):
                item[key] = value
        flags = 0
        for bit, source in enumerate(("is_evolved", "is_super_evolve", "is_active", "is_dead", "is_time_over")):
            if event.get(source) is True:
                flags |= 1 << bit
        if flags:
            item["f"] = flags
        target_ids = _target_ids(
            event.get("target_unique_ids") or event.get("target_unique_id_by_skills")
        )
        if target_ids:
            item["to"] = target_ids
        result.append(item)
    else:
        result.append({**base, "k": "x", "n": event_type})
    return result


def compact_event_records(event: dict[str, object], turn: int) -> list[dict[str, object]]:
    """Public wrapper used by the live UI to render the same event vocabulary."""
    return _event_records(event, turn)


def _field_cards(snapshot: dict[str, object]) -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]]:
    root = snapshot.get("root")
    players = root.get("players") if isinstance(root, dict) else None
    values: list[dict[int, tuple[int, int]]] = []
    if isinstance(players, (list, tuple)):
        for player in players[:2]:
            cards: dict[int, tuple[int, int]] = {}
            if isinstance(player, dict) and isinstance(player.get("field"), (list, tuple)):
                for card in player["field"]:
                    if not isinstance(card, dict):
                        continue
                    uid = _int(card.get("unique_id"), positive=True)
                    card_id = _card_id(card.get("base_card_id") or card.get("card_id"))
                    if uid is not None and card_id is not None:
                        cards[uid] = (card_id, _int(card.get("card_id")) or card_id)
            values.append(cards)
    while len(values) < 2:
        values.append({})
    return values[0], values[1]


def _public_token_uids(snapshot: dict[str, object]) -> set[int]:
    """Collect token-marked field UIDs when the response stream is gone."""
    root = snapshot.get("root")
    players = root.get("players") if isinstance(root, dict) else None
    result: set[int] = set()
    if not isinstance(players, (list, tuple)):
        return result
    for player in players[:2]:
        field = player.get("field") if isinstance(player, dict) else None
        if not isinstance(field, (list, tuple)):
            continue
        for card in field:
            if not isinstance(card, dict) or card.get("is_same_name_token") is not True:
                continue
            uid = _int(card.get("unique_id"), positive=True)
            if uid is not None:
                result.add(uid)
    return result


def _field_event_provenance(
    events: object,
) -> tuple[dict[int, str], dict[int, str], bool]:
    """Map newly visible field cards to the response that created them.

    A single response batch may contain a real direct summon and one or more
    generated tokens.  Classifying the whole batch from its event *types*
    therefore loses information (and can incorrectly charge a token to the
    selected deck).  Prefer the target UID supplied by each response; the
    card-id fallback is used only when token provenance is complete.
    """
    by_uid: dict[int, str] = {}
    by_card: dict[int, str] = {}
    if not isinstance(events, (list, tuple)):
        return by_uid, by_card, False
    unknown_token = False
    type_sources = {
        "BattleResponsePutCardFromDeck": "deck",
        "BattleResponsePutToken": "token",
        "BattleResponsePutCardFromHand": "hand",
        "BattleResponseCastSpellFromHand": "hand",
    }
    # If a target UID is missing, card-id fallback still needs a deterministic
    # precedence.  A generated token is the weakest evidence; a direct deck
    # result should win even when it appears later in the same response batch.
    source_priority = {"token": 0, "hand": 1, "deck": 2}
    for event in events:
        if not isinstance(event, dict):
            continue
        source = type_sources.get(str(event.get("type")))
        if source is None:
            continue
        values = event.get("cards") or event.get("targets")
        if not values and isinstance(event.get("card"), dict):
            values = [event["card"]]
        found = False
        if isinstance(values, (list, tuple)):
            for value in values:
                card = value.get("card") if isinstance(value, dict) and isinstance(value.get("card"), dict) else value
                if not isinstance(card, dict):
                    continue
                uid = _int(card.get("unique_id"), positive=True)
                card_id = _card_id(card.get("base_card_id") or card.get("card_id"))
                if uid is not None:
                    by_uid[uid] = source
                    found = True
                if card_id is not None:
                    previous = by_card.get(card_id)
                    if previous is None or source_priority.get(source, 0) > source_priority.get(previous, 0):
                        by_card[card_id] = source
        if source == "token" and not found:
            unknown_token = True
    return by_uid, by_card, unknown_token


@dataclass
class TrainingMatchRecorder:
    """Incrementally collect one compact replayable match."""

    match_id: str | None = None
    _record: dict[str, object] | None = None
    _previous_checkpoint: dict[str, object] | None = None
    _previous_fields: tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]] | None = None
    _seen_events: set[tuple[object, ...]] | None = None
    _next_event_index: int = 0

    def reset(self) -> None:
        self.match_id = None
        self._record = None
        self._previous_checkpoint = None
        self._previous_fields = None
        self._seen_events = set()
        self._next_event_index = 0

    @property
    def active(self) -> bool:
        return self._record is not None

    def _ensure_started(self, snapshot: dict[str, object]) -> None:
        if self._record is not None:
            return
        self.match_id = secrets.token_hex(12)
        root = snapshot.get("root")
        players = root.get("players") if isinstance(root, dict) else ()
        self._record = {
            "v": SCHEMA_VERSION,
            "id": self.match_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "deck": compact_deck(snapshot.get("deck")),
            "p": [
                {"c": snapshot.get("self_class_id")},
                {"c": snapshot.get("opponent_class_id")},
            ],
            "m": {},
            "s": [],
            "e": [],
        }
        mode = snapshot.get("battle_mode")
        if isinstance(mode, str) and mode:
            self._record["g"] = mode[:32]
        deck = self._record.get("deck")
        if isinstance(deck, dict):
            self._record["dk"] = deck.get("k", "")
        if isinstance(players, (list, tuple)) and len(players) >= 2:
            for index, player in enumerate(players[:2]):
                if not isinstance(player, dict):
                    continue
                is_first = player.get("is_first_side")
                if isinstance(is_first, bool):
                    self._record["p"][index]["o"] = int(is_first)  # type: ignore[index]

    def ingest(self, snapshot: dict[str, object]) -> None:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("root"), dict):
            return
        self._ensure_started(snapshot)
        assert self._record is not None
        deck = compact_deck(snapshot.get("deck"))
        if self._record.get("deck") is None and deck is not None:
            self._record["deck"] = deck
            self._record["dk"] = deck.get("k", "")
        training = snapshot.get("training_observation")
        mulligan = training.get("mulligan") if isinstance(training, dict) else None
        if isinstance(mulligan, dict):
            compact_mulligan: dict[str, object] = {}
            for source, target in (("self_initial_hand", "i"), ("self_replaced_cards", "r"), ("self_final_starting_hand", "f"), ("opponent_replaced_count", "o")):
                value = mulligan.get(source)
                if source == "opponent_replaced_count":
                    if isinstance(value, int):
                        compact_mulligan[target] = value
                elif isinstance(value, (list, tuple)) and value:
                    compact_mulligan[target] = _clean_ids(value)
            if compact_mulligan:
                self._record["m"] = compact_mulligan

        turn = _turn(snapshot)
        events = snapshot.get("events")
        if isinstance(events, (list, tuple)):
            if self._seen_events is None:
                self._seen_events = set()
            seen = self._seen_events
            for event in events:
                if not isinstance(event, dict):
                    continue
                # A sequence number is unique within a response stream.  The
                # type and a compact value fingerprint protect against the
                # same sequence being reused for both mulligan sides.
                fingerprint = json.dumps(
                    _without_addresses(event),
                    ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"),
                )
                # Managed response objects can be copied/recreated between
                # polls, so their address is not a stable event identity.
                # Keep the semantic response fingerprint instead; sequence 0
                # is still safe because the fingerprint includes the side and
                # selected card flags for mulligan responses.
                token = (event.get("type"), event.get("sequence"), fingerprint)
                if token in seen:
                    continue
                seen.add(token)
                compact_events = _event_records(event, turn)
                for item in compact_events:
                    # ``q`` is the game's response sequence and can reset
                    # between batches.  ``i`` is our monotonic replay order.
                    item["i"] = self._next_event_index
                    self._next_event_index += 1
                self._record["e"].extend(compact_events)  # type: ignore[union-attr]

        checkpoint = _state_checkpoint(snapshot)
        if checkpoint is not None and checkpoint != self._previous_checkpoint:
            self._record["s"].append(checkpoint)  # type: ignore[union-attr]
            self._previous_checkpoint = checkpoint

        # A state transition is still useful when a response object was too
        # short-lived for the decoder.  Mark every new/removed field card and
        # classify direct deck/token placement from the same response batch.
        current_fields = _field_cards(snapshot)
        previous_fields = self._previous_fields
        if previous_fields is not None:
            source_by_uid, source_by_card, unknown_token = _field_event_provenance(events)
            public_token_uids = _public_token_uids(snapshot)
            for side, (before, after) in enumerate(zip(previous_fields, current_fields)):
                for uid, (card_id, _runtime) in after.items():
                    if uid not in before:
                        source = source_by_uid.get(uid)
                        if source is None and uid in public_token_uids:
                            source = "token"
                        if source is None and not unknown_token:
                            source = source_by_card.get(card_id)
                        self._record["e"].append({"i": self._next_event_index, "t": turn, "s": side, "k": "in", "u": uid, "c": card_id, "src": source or "effect"})  # type: ignore[union-attr]
                        self._next_event_index += 1
                for uid, (card_id, _runtime) in before.items():
                    if uid not in after:
                        self._record["e"].append({"i": self._next_event_index, "t": turn, "s": side, "k": "out", "u": uid, "c": card_id})  # type: ignore[union-attr]
                        self._next_event_index += 1
        self._previous_fields = current_fields

        root = snapshot.get("root")
        players = root.get("players") if isinstance(root, dict) else ()
        if isinstance(players, (list, tuple)) and players and isinstance(players[0], dict):
            mine = players[0]
            opponent = players[1] if len(players) > 1 and isinstance(players[1], dict) else {}
            code = _int(mine.get("result_code")) or 0
            result = result_label(code, _int(mine.get("life")), _int(opponent.get("life")))
            self._record["r"] = {"c": code, "v": result, "t": turn}

    def finish(self, snapshot: dict[str, object] | None = None, *, complete: bool | None = None) -> dict[str, object] | None:
        if snapshot is not None:
            self.ingest(snapshot)
        if self._record is None:
            return None
        record = deepcopy(self._record)
        result = record.get("r")
        if complete is None:
            complete = isinstance(result, dict) and result.get("v") in {"胜利", "失败"}
        record["z"] = 1 if complete else 0
        record["end"] = datetime.now(timezone.utc).isoformat()
        self.reset()
        return record


class TrainingUploadQueue:
    """Persist completed records and optionally POST them to a user endpoint.

    Uploading is opt-in.  A queue line is retained until the server returns a
    2xx response, so temporary network failures never lose a match.  The queue
    contains the same address-free compact object as the training file.
    """

    def __init__(
        self,
        path: Path,
        *,
        endpoint: str | None = None,
        enabled: bool = False,
        token: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.endpoint = endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None
        self.enabled = bool(enabled and self.endpoint)
        self.token = token.strip() if isinstance(token, str) and token.strip() else None
        self.timeout = max(0.5, float(timeout))

    def enqueue(self, record: dict[str, object]) -> bool:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(payload + "\n")
        except OSError:
            return False
        if self.enabled:
            self.flush()
        return True

    def flush(self) -> int:
        if not self.enabled or self.endpoint is None or not self.path.is_file():
            return 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        remaining: list[str] = []
        uploaded = 0
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                body = line.encode("utf-8")
                request = urllib.request.Request(
                    self.endpoint,
                    data=body,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
                    },
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", 200))
                if 200 <= status < 300:
                    uploaded += 1
                else:
                    remaining.append(line)
            except (OSError, ValueError, urllib.error.URLError):
                remaining.append(line)
                # Preserve order and avoid hammering an unavailable endpoint.
                remaining.extend(lines[index + 1:])
                break
        try:
            if remaining:
                self.path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                self.path.unlink(missing_ok=True)
        except OSError:
            pass
        return uploaded


def default_upload_queue_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "ShadowverseTracker" / "training_upload_queue.jsonl"
    return Path.home() / ".shadowverse_tracker" / "training_upload_queue.jsonl"


__all__ = [
    "SCHEMA_VERSION", "TrainingMatchRecorder", "TrainingUploadQueue",
    "compact_deck", "compact_event_records", "default_upload_queue_path",
]
