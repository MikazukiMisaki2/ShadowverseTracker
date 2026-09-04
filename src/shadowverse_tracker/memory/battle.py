"""Decode the small IL2CPP object graph needed by the tracker prototype.

Offsets in this module are fields of version-specific managed classes, not global
addresses.  The root address is captured from BattleModel.ExecuteRootUpdated while
validating a new game version; the production discovery mechanism will replace that
manual validation step.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


class MemoryReader(Protocol):
    def read(self, address: int, size: int) -> bytes: ...
    def read_u64(self, address: int) -> int: ...
    def read_u32(self, address: int) -> int: ...
    def read_i32(self, address: int) -> int: ...
    def read_c_string(self, address: int, maximum: int = 512) -> str: ...


MAX_PLAYERS = 2
MAX_HAND_CARDS = 16
MAX_FIELD_CARDS = 8
MAX_HISTORY_ITEMS = 512
MAX_CARD_COUNTERS = 64
MAX_CARD_TRAITS = 32
MAX_BUFF_SOURCES = 64
MAX_CRESTS = 32
MAX_SPECIAL_ACTIONS = 32
MAX_LEGAL_ACTION_CARDS = 64


@dataclass(frozen=True)
class BuffSource:
    card_id: int
    style_id: int
    is_ally: bool
    is_evolve: bool
    evolve_state: int


@dataclass(frozen=True)
class CardBuff:
    sources: tuple[BuffSource, ...]
    cost: int
    attack: int
    max_life_diff: int
    quick: bool
    rush: bool
    temp_shield: bool
    attack_limit: int
    add_dead_by_reanimate: bool
    add_tribes: tuple[int, ...]


@dataclass(frozen=True)
class PlayerBuff:
    sources: tuple[BuffSource, ...]
    max_life: int
    temp_shield: bool
    damage_cut: int
    increase_damage: int


@dataclass(frozen=True)
class CrestBuff:
    sources: tuple[BuffSource, ...]


@dataclass(frozen=True)
class Crest:
    card_id: int
    countdown: int
    faith_value: int
    variable_x: int
    buff: CrestBuff | None
    supplement_info: dict[str, int]
    style_id: int
    unique_id: int
    activated_random_once_indexes: tuple[int, ...]
    current_run_in_order_count: int
    is_run_in_order_no_loop: bool
    run_in_order_amount: int


@dataclass(frozen=True)
class ExtraCrest:
    card_id: int
    countdown: int
    variable_x: int
    buff: CrestBuff | None
    supplement_info: dict[str, int]
    style_id: int
    unique_id: int
    activated_random_once_indexes: tuple[int, ...]
    current_run_in_order_count: int
    is_run_in_order_no_loop: bool
    run_in_order_amount: int


@dataclass(frozen=True)
class Boon:
    card_id: int
    unique_id: int
    supplement_info: dict[str, int]
    activated_random_once_indexes: tuple[int, ...]
    current_run_in_order_count: int
    is_run_in_order_no_loop: bool
    run_in_order_amount: int


@dataclass(frozen=True)
class SpecialActionCard:
    card_id: int
    unique_id: int
    supplement_info: dict[str, int]
    state: int
    can_special_action_in_battle: bool


@dataclass(frozen=True)
class LegalActions:
    can_play_cards: tuple[int, ...]
    can_play_cards_with_extra_pp: tuple[int, ...]
    can_enhance_play_cards: tuple[int, ...]
    can_accelerate_play_cards: tuple[int, ...]
    can_crystal_play_cards: tuple[int, ...]
    can_attack_leader_cards: tuple[int, ...]
    can_attack_field_cards: tuple[int, ...]
    attacked_cards: tuple[int, ...]
    can_activation_field_cards: tuple[int, ...]
    can_activation_field_cards_with_extra_pp: tuple[int, ...]
    has_activation_field_cards: tuple[int, ...]
    attack_targets: dict[int, tuple[int, ...]]
    can_evolve_cards: tuple[int, ...]
    can_super_evolve_cards: tuple[int, ...]
    can_super_evolve_with_skill_cards: tuple[int, ...]
    can_fusion_cards: tuple[int, ...]
    has_fusion_hand_cards: tuple[int, ...]
    can_special_action_field_cards: tuple[int, ...]
    can_special_action_area_cards: tuple[int, ...]


@dataclass(frozen=True)
class HandCard:
    address: str
    unique_id: int
    card_id: int
    base_card_id: int
    cost: int
    attack: int
    life: int
    card_type: int
    enhance_costs: tuple[int, ...]
    has_spell_boost: bool
    variable_x: int
    accelerate_costs: tuple[int, ...]
    crystal_costs: tuple[int, ...]
    fusion_list: tuple[tuple[int, ...], ...]
    tribes: tuple[int, ...]
    buff: CardBuff | None
    style_id: int
    supplement_info: dict[str, int]
    cant_action_type: int
    is_changed_ability: bool
    spell_boost_count: int
    can_enhance: bool
    activated_random_once_indexes: tuple[int, ...]
    current_run_in_order_count: int
    is_run_in_order_no_loop: bool
    run_in_order_amount: int


@dataclass(frozen=True)
class FieldCard:
    """A public card currently on a player's field."""

    address: str
    unique_id: int
    card_id: int
    cost: int
    attack: int
    life: int
    max_life: int
    card_type: int
    attack_targets: tuple[int, ...]
    countdown: int
    stack: int
    evolve_state: int
    has_guard: bool
    has_drain: bool
    has_sneak: bool
    has_killer: bool
    has_cant_be_attacked: bool
    has_cant_select: bool
    has_last_word: bool
    is_earth_sigil: bool
    has_spell_boost: bool
    enhanced_cost: int
    has_damage_cut: bool
    has_cant_attack: bool
    has_induction: bool
    has_activation: bool
    has_reduce_damage: bool
    has_cant_destroy: bool
    has_super_evolve_buff: bool
    buff: CardBuff | None
    style_id: int
    fusion_list: tuple[tuple[int, ...], ...]
    supplement_info: dict[str, int]
    cant_action_type: int
    is_remove_field_at_turn_change: bool
    has_temp_shield: bool
    activated_random_once_indexes: tuple[int, ...]
    content_counter: int
    current_run_in_order_count: int
    attack_limit: int
    is_same_name_token: bool
    is_run_in_order_no_loop: bool
    run_in_order_amount: int


@dataclass(frozen=True)
class PlayerState:
    address: str
    deck_count: int
    life: int
    max_life: int
    unique_id: int
    pp: int
    max_pp: int
    turn: int
    evolve_points: int
    max_evolve_points: int
    super_evolve_points: int
    max_super_evolve_points: int
    extra_pp: int
    preparation_extra_pp: int
    extra_pp_state: int
    cemetery_count: int
    is_end_mulligan: bool
    rally: int
    evolve_turn: int
    super_evolve_turn: int
    restore_extra_pp_turn: int
    is_first_side: bool
    result_code: int
    hand: tuple[HandCard, ...]
    field: tuple[FieldCard, ...]
    played_card_ids: tuple[tuple[int, int], ...]
    destroyed_card_ids: tuple[tuple[int, int], ...]
    total_damage: int
    buff: PlayerBuff | None
    crests: tuple[Crest, ...]
    remaining_pp_until_awakening: int
    is_awakening: bool
    is_evolved_this_turn: bool
    play_count: int
    is_used_extra_pp_this_turn: bool
    manual_evolve_count: int
    open_extra_pp_state: int
    is_deck_out_win: bool
    evolve_count: int
    cant_fanfare_and_enhance_ally_follower: bool
    boons: tuple[Boon, ...]
    extra_crests: tuple[ExtraCrest, ...]
    special_action_cards: tuple[SpecialActionCard, ...]
    public_related_card_styles: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BattleRoot:
    address: str
    is_ally_turn: bool
    players: tuple[PlayerState, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_public_dict(self, *, reveal_opponent_hand: bool = False) -> dict[str, object]:
        """Return tracker output, optionally retaining local AI hand identities.

        The default remains privacy-safe for discovery and online-compatible
        callers.  The desktop tracker enables this only for the user's local
        practice-mode reader.
        """
        result = self.to_dict()
        players = result["players"]
        if not reveal_opponent_hand and isinstance(players, (list, tuple)) and len(players) >= 2:
            opponent = players[1]
            if isinstance(opponent, dict):
                hidden_count = len(opponent.get("hand", []))
                opponent["hand"] = [{"hidden": True} for _ in range(hidden_count)]
        return result


def _read_managed_array_pointers(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int,
) -> tuple[int, ...]:
    if not address:
        return ()
    length = reader.read_u64(address + 0x18)
    if length > maximum:
        raise ValueError(f"implausible managed array length {length} at 0x{address:X}")
    return tuple(reader.read_u64(address + 0x20 + index * 8) for index in range(length))


def _read_i32_array(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int,
) -> tuple[int, ...]:
    if not address:
        return ()
    length = reader.read_u64(address + 0x18)
    if length > maximum:
        raise ValueError(f"implausible int array length {length} at 0x{address:X}")
    return tuple(reader.read_i32(address + 0x20 + index * 4) for index in range(length))


def _read_i32_collection(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int,
) -> tuple[int, ...]:
    """Read either ``int[]`` or ``List<int>``/an enum equivalent."""
    if not address:
        return ()
    items = reader.read_u64(address + 0x10)
    size = reader.read_i32(address + 0x18)
    if items and 0 <= size <= maximum:
        capacity = reader.read_u64(items + 0x18)
        if size <= capacity <= max(maximum, size):
            return tuple(reader.read_i32(items + 0x20 + index * 4) for index in range(size))
    return _read_i32_array(reader, address, maximum=maximum)


def _read_jagged_i32_array(
    reader: MemoryReader,
    address: int,
    *,
    maximum_outer: int = MAX_CARD_TRAITS,
    maximum_inner: int = MAX_CARD_COUNTERS,
) -> tuple[tuple[int, ...], ...]:
    arrays = _read_managed_array_pointers(reader, address, maximum=maximum_outer)
    return tuple(
        _read_i32_array(reader, item, maximum=maximum_inner) if item else ()
        for item in arrays
    )


def _read_managed_string(reader: MemoryReader, address: int, *, maximum: int = 256) -> str:
    if not address:
        return ""
    length = reader.read_i32(address + 0x10)
    if length < 0 or length > maximum:
        raise ValueError(f"implausible managed string length {length} at 0x{address:X}")
    return reader.read(address + 0x14, length * 2).decode("utf-16-le", errors="replace")


def _read_string_i32_dictionary(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int = MAX_CARD_COUNTERS,
) -> dict[str, int]:
    """Decode the IL2CPP ``Dictionary<string, int>`` used by SupplementInfo."""
    if not address:
        return {}
    entries = reader.read_u64(address + 0x18)
    count = reader.read_i32(address + 0x20)
    if count < 0 or count > maximum:
        raise ValueError(f"implausible dictionary count {count} at 0x{address:X}")
    if not entries or count == 0:
        return {}
    capacity = reader.read_u64(entries + 0x18)
    if capacity < count or capacity > maximum:
        raise ValueError(f"implausible dictionary capacity {capacity} at 0x{entries:X}")
    result: dict[str, int] = {}
    # Entry<string, int> is 24 bytes on 64-bit IL2CPP: hash, next, key, value.
    for index in range(count):
        entry = entries + 0x20 + index * 0x18
        hash_code = reader.read_i32(entry)
        key_address = reader.read_u64(entry + 0x08)
        if hash_code < 0 or not key_address:
            continue
        key = _read_managed_string(reader, key_address)
        if key:
            result[key] = reader.read_i32(entry + 0x10)
    return result


def _read_i32_hash_set(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int = MAX_LEGAL_ACTION_CARDS,
) -> tuple[int, ...]:
    """Decode the Unity/IL2CPP ``HashSet<int>`` used by battle legality state."""
    if not address:
        return ()
    slots = reader.read_u64(address + 0x18)
    count = reader.read_i32(address + 0x20)
    last_index = reader.read_i32(address + 0x24)
    if count < 0 or count > maximum or last_index < 0 or last_index > maximum:
        raise ValueError(f"implausible hash set size at 0x{address:X}")
    if not slots or count == 0:
        return ()
    capacity = reader.read_u64(slots + 0x18)
    if last_index > capacity or capacity > maximum:
        raise ValueError(f"implausible hash set capacity {capacity} at 0x{slots:X}")
    values: list[int] = []
    for index in range(last_index):
        slot = slots + 0x20 + index * 0x0C
        if reader.read_i32(slot) >= 0:
            values.append(reader.read_i32(slot + 0x08))
    return tuple(values)


def _read_i32_hash_set_dictionary(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int = MAX_LEGAL_ACTION_CARDS,
) -> dict[int, tuple[int, ...]]:
    if not address:
        return {}
    entries = reader.read_u64(address + 0x18)
    count = reader.read_i32(address + 0x20)
    if count < 0 or count > maximum:
        raise ValueError(f"implausible target-map count {count} at 0x{address:X}")
    if not entries or count == 0:
        return {}
    capacity = reader.read_u64(entries + 0x18)
    if capacity < count or capacity > maximum:
        raise ValueError(f"implausible target-map capacity {capacity} at 0x{entries:X}")
    result: dict[int, tuple[int, ...]] = {}
    # Entry<int, HashSet<int>> is 24 bytes: hash, next, key, padding, value pointer.
    for index in range(count):
        entry = entries + 0x20 + index * 0x18
        if reader.read_i32(entry) < 0:
            continue
        key = reader.read_i32(entry + 0x08)
        value = reader.read_u64(entry + 0x10)
        if value:
            result[key] = _read_i32_hash_set(reader, value, maximum=maximum)
    return result


def _read_i32_dictionary_keys(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int = MAX_LEGAL_ACTION_CARDS,
) -> tuple[int, ...]:
    """Read keys from a ``Dictionary<int, TValue>``.

    Several ``BattleRootMpo`` legality projections are dictionaries whose
    values contain mode/cost metadata.  The action contract only needs the
    card UIDs, so decoding the keys avoids making assumptions about the value
    type while still validating the managed dictionary layout.
    """
    if not address:
        return ()
    entries = reader.read_u64(address + 0x18)
    count = reader.read_i32(address + 0x20)
    if count < 0 or count > maximum:
        raise ValueError(f"implausible dictionary count {count} at 0x{address:X}")
    if not entries or count == 0:
        return ()
    capacity = reader.read_u64(entries + 0x18)
    if capacity < count or capacity > maximum:
        raise ValueError(f"implausible dictionary capacity {capacity} at 0x{entries:X}")
    result: list[int] = []
    for index in range(count):
        entry = entries + 0x20 + index * 0x18
        if reader.read_i32(entry) < 0:
            continue
        result.append(reader.read_i32(entry + 0x08))
    return tuple(result)


def read_battle_root_legal_actions(reader: MemoryReader, address: int) -> dict[str, object]:
    """Decode legality projections embedded in ``BattleRootMpo``.

    The regular ``BattleViewServerData`` object is not created in puzzle /
    teaching battles, but the root carries the same projections.  Offsets are
    the fields of the current ``BattleRootMpo`` layout and are intentionally
    kept in one place so a version change fails closed in the caller.
    """
    if not address:
        raise ValueError("null BattleRootMpo")

    # These six projections are present even when empty in a live root.  A
    # null pointer here means the object layout is not the expected version;
    # fail closed so SnapshotAdapter keeps the result INCOMPLETE.
    required_offsets = (0x20, 0x28, 0x30, 0x38, 0x40, 0x48)
    if any(reader.read_u64(address + offset) == 0 for offset in required_offsets):
        raise ValueError("BattleRootMpo legality fields are unavailable")

    def hash_set(offset: int) -> tuple[int, ...]:
        return _read_i32_hash_set(reader, reader.read_u64(address + offset))

    def dictionary_keys(offset: int) -> tuple[int, ...]:
        return _read_i32_dictionary_keys(reader, reader.read_u64(address + offset))

    return {
        "can_play_cards": hash_set(0x20),
        # Root does not expose the extra-PP projection separately.
        "can_play_cards_with_extra_pp": (),
        "can_attack_leader_cards": hash_set(0x28),
        "can_attack_field_cards": hash_set(0x30),
        "attack_targets": _read_i32_hash_set_dictionary(reader, reader.read_u64(address + 0x38)),
        "can_evolve_cards": hash_set(0x40),
        "can_super_evolve_cards": hash_set(0x48),
        "can_super_evolve_with_skill_cards": hash_set(0x70),
        "can_enhance_play_cards": dictionary_keys(0x58),
        "can_activation_field_cards": dictionary_keys(0x60),
        "can_activation_field_cards_with_extra_pp": (),
        "has_activation_field_cards": (),
        "can_mode_skill_cards": hash_set(0x68),
        "super_evolve_can_mode_skill_cards": hash_set(0x70),
        "can_accelerate_play_cards": dictionary_keys(0x78),
        "can_crystal_play_cards": dictionary_keys(0x80),
        "can_fusion_cards": hash_set(0x88),
        "has_fusion_hand_cards": hash_set(0x90),
        "can_special_action_field_cards": hash_set(0x98),
        "can_special_action_area_cards": hash_set(0xA0),
        "can_special_action_in_battle": hash_set(0xA8),
        "source": "BattleRootMpo",
    }


def read_battle_view_server_data(reader: MemoryReader, address: int) -> LegalActions:
    """Read client-derived legal actions for the current local-player state."""
    if not address:
        raise ValueError("null BattleViewServerData")

    def read_set(offset: int) -> tuple[int, ...]:
        return _read_i32_hash_set(reader, reader.read_u64(address + offset))

    return LegalActions(
        can_play_cards=read_set(0x18),
        can_play_cards_with_extra_pp=read_set(0x20),
        can_enhance_play_cards=read_set(0x28),
        can_accelerate_play_cards=read_set(0x30),
        can_crystal_play_cards=read_set(0x38),
        can_attack_leader_cards=read_set(0x40),
        can_attack_field_cards=read_set(0x48),
        attacked_cards=read_set(0x50),
        can_activation_field_cards=read_set(0x58),
        can_activation_field_cards_with_extra_pp=read_set(0x60),
        has_activation_field_cards=read_set(0x68),
        attack_targets=_read_i32_hash_set_dictionary(
            reader, reader.read_u64(address + 0x70)
        ),
        can_evolve_cards=read_set(0x78),
        can_super_evolve_cards=read_set(0x80),
        can_super_evolve_with_skill_cards=read_set(0x88),
        can_fusion_cards=read_set(0x98),
        has_fusion_hand_cards=read_set(0xA0),
        can_special_action_field_cards=read_set(0x130),
        can_special_action_area_cards=read_set(0x138),
    )


def read_reference_collection(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int,
) -> tuple[int, ...]:
    """Read either T[] or List<T>, the two runtime IReadOnlyList implementations used here."""
    if not address:
        return ()

    first_field = reader.read_u64(address + 0x10)
    possible_length = reader.read_u64(address + 0x18)
    if first_field == 0 and possible_length <= maximum:
        return _read_managed_array_pointers(reader, address, maximum=maximum)

    size = reader.read_i32(address + 0x18)
    if 0 <= size <= maximum and first_field:
        capacity = reader.read_u64(first_field + 0x18)
        if size <= capacity <= max(maximum, size):
            return tuple(reader.read_u64(first_field + 0x20 + index * 8) for index in range(size))

    # Some zero-length arrays have a non-null bounds pointer. Try the array layout last.
    if possible_length <= maximum:
        return _read_managed_array_pointers(reader, address, maximum=maximum)
    raise ValueError(f"unsupported reference collection at 0x{address:X}")


def _read_value_tuple_i32_array(
    reader: MemoryReader,
    address: int,
    *,
    maximum: int,
) -> tuple[tuple[int, int], ...]:
    if not address:
        return ()
    length = reader.read_u64(address + 0x18)
    if length > maximum:
        raise ValueError(f"implausible tuple array length {length} at 0x{address:X}")
    return tuple(
        (reader.read_i32(address + 0x20 + index * 8), reader.read_i32(address + 0x24 + index * 8))
        for index in range(length)
    )


def _read_buff_sources(reader: MemoryReader, address: int) -> tuple[BuffSource, ...]:
    if not address:
        return ()
    sources = _read_managed_array_pointers(reader, address, maximum=MAX_BUFF_SOURCES)
    return tuple(
        BuffSource(
            card_id=reader.read_i32(source + 0x10),
            style_id=reader.read_i32(source + 0x14),
            is_ally=bool(reader.read_u32(source + 0x18) & 0xFF),
            is_evolve=bool(reader.read_u32(source + 0x19) & 0xFF),
            evolve_state=reader.read_i32(source + 0x1C),
        )
        for source in sources
        if source
    )


def read_card_buff(reader: MemoryReader, address: int) -> CardBuff | None:
    if not address:
        return None
    return CardBuff(
        sources=_read_buff_sources(reader, reader.read_u64(address + 0x10)),
        cost=reader.read_i32(address + 0x18),
        attack=reader.read_i32(address + 0x1C),
        max_life_diff=reader.read_i32(address + 0x20),
        quick=bool(reader.read_u32(address + 0x24) & 0xFF),
        rush=bool(reader.read_u32(address + 0x25) & 0xFF),
        temp_shield=bool(reader.read_u32(address + 0x26) & 0xFF),
        attack_limit=reader.read_i32(address + 0x28),
        add_dead_by_reanimate=bool(reader.read_u32(address + 0x2C) & 0xFF),
        add_tribes=_read_i32_array(
            reader,
            reader.read_u64(address + 0x30),
            maximum=MAX_CARD_TRAITS,
        ),
    )


def read_player_buff(reader: MemoryReader, address: int) -> PlayerBuff | None:
    if not address:
        return None
    return PlayerBuff(
        sources=_read_buff_sources(reader, reader.read_u64(address + 0x10)),
        max_life=reader.read_i32(address + 0x18),
        temp_shield=bool(reader.read_u32(address + 0x1C) & 0xFF),
        damage_cut=reader.read_i32(address + 0x20),
        increase_damage=reader.read_i32(address + 0x24),
    )


def read_crest_buff(reader: MemoryReader, address: int) -> CrestBuff | None:
    if not address:
        return None
    return CrestBuff(sources=_read_buff_sources(reader, reader.read_u64(address + 0x10)))


def read_crest(reader: MemoryReader, address: int) -> Crest:
    return Crest(
        card_id=reader.read_i32(address + 0x10),
        countdown=reader.read_i32(address + 0x14),
        faith_value=reader.read_i32(address + 0x18),
        variable_x=reader.read_i32(address + 0x1C),
        buff=read_crest_buff(reader, reader.read_u64(address + 0x20)),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x28)),
        style_id=reader.read_i32(address + 0x30),
        unique_id=reader.read_u32(address + 0x34),
        activated_random_once_indexes=_read_i32_array(
            reader, reader.read_u64(address + 0x40), maximum=MAX_CARD_COUNTERS
        ),
        current_run_in_order_count=reader.read_i32(address + 0x48),
        is_run_in_order_no_loop=bool(reader.read_u32(address + 0x4C) & 0xFF),
        run_in_order_amount=reader.read_i32(address + 0x50),
    )


def read_extra_crest(reader: MemoryReader, address: int) -> ExtraCrest:
    return ExtraCrest(
        card_id=reader.read_i32(address + 0x10),
        countdown=reader.read_i32(address + 0x14),
        variable_x=reader.read_i32(address + 0x18),
        buff=read_crest_buff(reader, reader.read_u64(address + 0x20)),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x28)),
        style_id=reader.read_i32(address + 0x30),
        unique_id=reader.read_u32(address + 0x34),
        activated_random_once_indexes=_read_i32_array(
            reader, reader.read_u64(address + 0x40), maximum=MAX_CARD_COUNTERS
        ),
        current_run_in_order_count=reader.read_i32(address + 0x48),
        is_run_in_order_no_loop=bool(reader.read_u32(address + 0x4C) & 0xFF),
        run_in_order_amount=reader.read_i32(address + 0x50),
    )


def read_boon(reader: MemoryReader, address: int) -> Boon:
    return Boon(
        card_id=reader.read_i32(address + 0x10),
        unique_id=reader.read_u32(address + 0x14),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x18)),
        activated_random_once_indexes=_read_i32_array(
            reader, reader.read_u64(address + 0x20), maximum=MAX_CARD_COUNTERS
        ),
        current_run_in_order_count=reader.read_i32(address + 0x28),
        is_run_in_order_no_loop=bool(reader.read_u32(address + 0x2C) & 0xFF),
        run_in_order_amount=reader.read_i32(address + 0x30),
    )


def read_special_action_card(reader: MemoryReader, address: int) -> SpecialActionCard:
    return SpecialActionCard(
        card_id=reader.read_i32(address + 0x10),
        unique_id=reader.read_u32(address + 0x14),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x18)),
        state=reader.read_i32(address + 0x20),
        can_special_action_in_battle=bool(reader.read_u32(address + 0x24) & 0xFF),
    )


def read_hand_card(reader: MemoryReader, address: int) -> HandCard:
    if not address:
        raise ValueError("null BattleHandCardMpo")
    return HandCard(
        address=f"0x{address:016X}",
        unique_id=reader.read_u32(address + 0x10),
        card_id=reader.read_u32(address + 0x14),
        cost=reader.read_i32(address + 0x18),
        attack=reader.read_i32(address + 0x1C),
        life=reader.read_i32(address + 0x20),
        card_type=reader.read_i32(address + 0x24),
        enhance_costs=_read_i32_array(
            reader, reader.read_u64(address + 0x28), maximum=MAX_CARD_COUNTERS
        ),
        has_spell_boost=bool(reader.read_u32(address + 0x30) & 0xFF),
        variable_x=reader.read_i32(address + 0x34),
        accelerate_costs=_read_i32_array(
            reader, reader.read_u64(address + 0x38), maximum=MAX_CARD_COUNTERS
        ),
        crystal_costs=_read_i32_array(
            reader, reader.read_u64(address + 0x40), maximum=MAX_CARD_COUNTERS
        ),
        fusion_list=_read_jagged_i32_array(reader, reader.read_u64(address + 0x48)),
        base_card_id=reader.read_u32(address + 0x50),
        tribes=_read_i32_array(
            reader, reader.read_u64(address + 0x58), maximum=MAX_CARD_TRAITS
        ),
        buff=read_card_buff(reader, reader.read_u64(address + 0x60)),
        style_id=reader.read_i32(address + 0x68),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x70)),
        cant_action_type=reader.read_i32(address + 0x78),
        is_changed_ability=bool(reader.read_u32(address + 0x7C) & 0xFF),
        spell_boost_count=reader.read_i32(address + 0x80),
        can_enhance=bool(reader.read_u32(address + 0x84) & 0xFF),
        activated_random_once_indexes=_read_i32_array(
            reader, reader.read_u64(address + 0x88), maximum=MAX_CARD_COUNTERS
        ),
        current_run_in_order_count=reader.read_i32(address + 0x90),
        is_run_in_order_no_loop=bool(reader.read_u32(address + 0x94) & 0xFF),
        run_in_order_amount=reader.read_i32(address + 0x98),
    )


def read_field_card(reader: MemoryReader, address: int) -> FieldCard:
    if not address:
        raise ValueError("null BattleFieldCardMpo")
    return FieldCard(
        address=f"0x{address:016X}",
        unique_id=reader.read_u32(address + 0x10),
        card_id=reader.read_u32(address + 0x14),
        cost=reader.read_i32(address + 0x18),
        attack=reader.read_i32(address + 0x1C),
        life=reader.read_i32(address + 0x20),
        max_life=reader.read_i32(address + 0x24),
        card_type=reader.read_i32(address + 0x28),
        attack_targets=_read_i32_collection(
            reader, reader.read_u64(address + 0x30), maximum=MAX_FIELD_CARDS + 2
        ),
        countdown=reader.read_i32(address + 0x38),
        stack=reader.read_i32(address + 0x3C),
        evolve_state=reader.read_i32(address + 0x40),
        has_drain=bool(reader.read_u32(address + 0x44) & 0xFF),
        has_guard=bool(reader.read_u32(address + 0x45) & 0xFF),
        has_sneak=bool(reader.read_u32(address + 0x46) & 0xFF),
        has_killer=bool(reader.read_u32(address + 0x47) & 0xFF),
        has_cant_be_attacked=bool(reader.read_u32(address + 0x48) & 0xFF),
        has_cant_select=bool(reader.read_u32(address + 0x49) & 0xFF),
        has_last_word=bool(reader.read_u32(address + 0x4A) & 0xFF),
        is_earth_sigil=bool(reader.read_u32(address + 0x4B) & 0xFF),
        has_spell_boost=bool(reader.read_u32(address + 0x4C) & 0xFF),
        enhanced_cost=reader.read_i32(address + 0x50),
        has_damage_cut=bool(reader.read_u32(address + 0x54) & 0xFF),
        has_cant_attack=bool(reader.read_u32(address + 0x55) & 0xFF),
        has_induction=bool(reader.read_u32(address + 0x56) & 0xFF),
        has_activation=bool(reader.read_u32(address + 0x57) & 0xFF),
        has_reduce_damage=bool(reader.read_u32(address + 0x58) & 0xFF),
        has_cant_destroy=bool(reader.read_u32(address + 0x59) & 0xFF),
        has_super_evolve_buff=bool(reader.read_u32(address + 0x5A) & 0xFF),
        buff=read_card_buff(reader, reader.read_u64(address + 0x60)),
        style_id=reader.read_i32(address + 0x68),
        fusion_list=_read_jagged_i32_array(reader, reader.read_u64(address + 0x70)),
        supplement_info=_read_string_i32_dictionary(reader, reader.read_u64(address + 0x78)),
        cant_action_type=reader.read_i32(address + 0x80),
        is_remove_field_at_turn_change=bool(reader.read_u32(address + 0x84) & 0xFF),
        has_temp_shield=bool(reader.read_u32(address + 0x85) & 0xFF),
        activated_random_once_indexes=_read_i32_array(
            reader, reader.read_u64(address + 0x88), maximum=MAX_CARD_COUNTERS
        ),
        content_counter=reader.read_i32(address + 0x90),
        current_run_in_order_count=reader.read_i32(address + 0x94),
        attack_limit=reader.read_i32(address + 0x98),
        is_same_name_token=bool(reader.read_u32(address + 0x9C) & 0xFF),
        is_run_in_order_no_loop=bool(reader.read_u32(address + 0x9D) & 0xFF),
        run_in_order_amount=reader.read_i32(address + 0xA0),
    )


def read_player_state(reader: MemoryReader, address: int) -> PlayerState:
    if not address:
        raise ValueError("null BattleStatePlayerMpo")
    hand_collection = reader.read_u64(address + 0x10)
    hand_addresses = read_reference_collection(
        reader,
        hand_collection,
        maximum=MAX_HAND_CARDS,
    )
    hand = tuple(read_hand_card(reader, card) for card in hand_addresses if card)
    field_collection = reader.read_u64(address + 0x18)
    field_addresses = read_reference_collection(
        reader,
        field_collection,
        maximum=MAX_FIELD_CARDS,
    )
    field = tuple(read_field_card(reader, card) for card in field_addresses if card)
    played = _read_value_tuple_i32_array(
        reader,
        reader.read_u64(address + 0x70),
        maximum=MAX_HISTORY_ITEMS,
    )
    destroyed = _read_value_tuple_i32_array(
        reader,
        reader.read_u64(address + 0x78),
        maximum=MAX_HISTORY_ITEMS,
    )
    crest_addresses = read_reference_collection(
        reader, reader.read_u64(address + 0xA8), maximum=MAX_CRESTS
    )
    boon_addresses = read_reference_collection(
        reader, reader.read_u64(address + 0xD8), maximum=MAX_CRESTS
    )
    extra_crest_addresses = read_reference_collection(
        reader, reader.read_u64(address + 0xE0), maximum=MAX_CRESTS
    )
    special_action_addresses = read_reference_collection(
        reader, reader.read_u64(address + 0xE8), maximum=MAX_SPECIAL_ACTIONS
    )
    return PlayerState(
        address=f"0x{address:016X}",
        deck_count=reader.read_i32(address + 0x20),
        life=reader.read_i32(address + 0x24),
        max_life=reader.read_i32(address + 0x28),
        unique_id=reader.read_u32(address + 0x2C),
        pp=reader.read_i32(address + 0x30),
        max_pp=reader.read_i32(address + 0x34),
        turn=reader.read_i32(address + 0x38),
        evolve_points=reader.read_i32(address + 0x3C),
        max_evolve_points=reader.read_i32(address + 0x40),
        super_evolve_points=reader.read_i32(address + 0x44),
        max_super_evolve_points=reader.read_i32(address + 0x48),
        extra_pp=reader.read_i32(address + 0x4C),
        preparation_extra_pp=reader.read_i32(address + 0x50),
        extra_pp_state=reader.read_i32(address + 0x54),
        cemetery_count=reader.read_i32(address + 0x58),
        is_end_mulligan=bool(reader.read_u32(address + 0x5C) & 0xFF),
        rally=reader.read_i32(address + 0x60),
        evolve_turn=reader.read_i32(address + 0x64),
        super_evolve_turn=reader.read_i32(address + 0x68),
        restore_extra_pp_turn=reader.read_i32(address + 0x6C),
        is_first_side=bool(reader.read_u32(address + 0x98) & 0xFF),
        result_code=reader.read_i32(address + 0xB0),
        hand=hand,
        field=field,
        played_card_ids=played,
        destroyed_card_ids=destroyed,
        total_damage=reader.read_i32(address + 0x94),
        buff=read_player_buff(reader, reader.read_u64(address + 0xA0)),
        crests=tuple(read_crest(reader, crest) for crest in crest_addresses if crest),
        remaining_pp_until_awakening=reader.read_i32(address + 0xB4),
        is_awakening=bool(reader.read_u32(address + 0xB8) & 0xFF),
        is_evolved_this_turn=bool(reader.read_u32(address + 0xB9) & 0xFF),
        play_count=reader.read_i32(address + 0xBC),
        is_used_extra_pp_this_turn=bool(reader.read_u32(address + 0xC0) & 0xFF),
        manual_evolve_count=reader.read_i32(address + 0xC4),
        open_extra_pp_state=reader.read_i32(address + 0xC8),
        is_deck_out_win=bool(reader.read_u32(address + 0xCC) & 0xFF),
        evolve_count=reader.read_i32(address + 0xD0),
        cant_fanfare_and_enhance_ally_follower=bool(reader.read_u32(address + 0xD4) & 0xFF),
        boons=tuple(read_boon(reader, boon) for boon in boon_addresses if boon),
        extra_crests=tuple(
            read_extra_crest(reader, crest) for crest in extra_crest_addresses if crest
        ),
        special_action_cards=tuple(
            read_special_action_card(reader, card) for card in special_action_addresses if card
        ),
        public_related_card_styles=_read_value_tuple_i32_array(
            reader, reader.read_u64(address + 0xF0), maximum=MAX_HISTORY_ITEMS
        ),
    )


def read_battle_root(reader: MemoryReader, address: int) -> BattleRoot:
    if not address:
        raise ValueError("null BattleRootMpo")
    players_array = reader.read_u64(address + 0x10)
    player_addresses = _read_managed_array_pointers(reader, players_array, maximum=MAX_PLAYERS)
    if len(player_addresses) != MAX_PLAYERS:
        raise ValueError(f"expected two players, found {len(player_addresses)}")
    return BattleRoot(
        address=f"0x{address:016X}",
        is_ally_turn=bool(reader.read_u32(address + 0x18) & 0xFF),
        players=tuple(read_player_state(reader, player) for player in player_addresses),
    )


def read_il2cpp_type_name(reader: MemoryReader, object_address: int) -> str:
    if not object_address:
        return ""
    klass = reader.read_u64(object_address)
    if not klass:
        return ""
    name = reader.read_c_string(reader.read_u64(klass + 0x10))
    namespace = reader.read_c_string(reader.read_u64(klass + 0x18))
    return f"{namespace}.{name}" if namespace else name


def _event_card_summary(reader: MemoryReader, address: int, *, field: bool) -> dict[str, object] | None:
    """Decode the identity/status subset carried by a response card.

    Response objects are short-lived and some game versions omit optional
    nested cards.  Callers deliberately treat a failed nested read as an
    absent annotation instead of dropping the entire battle snapshot.
    """
    if not address:
        return None
    try:
        value = asdict(read_field_card(reader, address) if field else read_hand_card(reader, address))
    except (OSError, ValueError, LookupError):
        return None
    keep = (
        ("unique_id", "card_id", "cost", "attack", "life", "max_life", "card_type", "evolve_state", "style_id")
        if field
        else ("unique_id", "card_id", "base_card_id", "cost", "attack", "life", "card_type", "style_id")
    )
    return {key: value[key] for key in keep if key in value}


def _event_cards(reader: MemoryReader, collection_address: int, *, field: bool, maximum: int) -> list[dict[str, object]]:
    if not collection_address:
        return []
    try:
        addresses = read_reference_collection(reader, collection_address, maximum=maximum)
    except (OSError, ValueError, LookupError):
        return []
    return [
        summary
        for address in addresses
        if (summary := _event_card_summary(reader, address, field=field)) is not None
    ]


def _event_int_values(reader: MemoryReader, collection_address: int, *, maximum: int) -> list[int]:
    if not collection_address:
        return []
    try:
        return list(_read_i32_collection(reader, collection_address, maximum=maximum))
    except (OSError, ValueError, LookupError):
        return []


def _event_nested_int_values(
    reader: MemoryReader,
    collection_address: int,
    *,
    maximum_outer: int,
    maximum_inner: int,
) -> list[list[int]]:
    """Read the nested target-id lists carried by card selections.

    ``PutCardFromHand``, ``CastSpellFromHand`` and ``Activation`` all use a
    ``List<List<BattleCardUniqueId>>`` for their selectable targets.  The
    outer collection is a managed ``List`` in the live client, while each
    inner value is either an array or a ``List<int>``.  Keep this helper
    best-effort so an animation object released between polls never makes the
    entire battle snapshot unreadable.
    """
    if not collection_address:
        return []
    try:
        outer = read_reference_collection(reader, collection_address, maximum=maximum_outer)
    except (OSError, ValueError, LookupError):
        return []
    result: list[list[int]] = []
    for inner_address in outer:
        if not inner_address:
            result.append([])
            continue
        try:
            result.append(list(_read_i32_collection(reader, inner_address, maximum=maximum_inner)))
        except (OSError, ValueError, LookupError):
            result.append([])
    return result


def _event_field_card_targets(
    reader: MemoryReader,
    collection_address: int,
    *,
    maximum: int,
    include_is_ally: bool = True,
) -> list[dict[str, object]]:
    """Decode response target records whose first field is a FieldCard."""
    if not collection_address:
        return []
    try:
        target_addresses = read_reference_collection(reader, collection_address, maximum=maximum)
    except (OSError, ValueError, LookupError):
        return []
    result: list[dict[str, object]] = []
    for target_address in target_addresses:
        if not target_address:
            continue
        try:
            card = _event_card_summary(reader, reader.read_u64(target_address + 0x10), field=True)
            if card is None:
                continue
            # Most target DTOs carry ``IsAlly`` immediately after the card
            # pointer.  PutToken.Target is the exception: that byte is
            # ``IsOverflow`` and the side lives on the parent response.
            if include_is_ally:
                card["is_ally"] = bool(reader.read_u32(target_address + 0x18) & 0xFF)
            result.append(card)
        except (OSError, ValueError, LookupError):
            continue
    return result


def _event_scalar_targets(
    reader: MemoryReader,
    collection_address: int,
    *,
    kind: str,
    maximum: int,
) -> list[dict[str, object]]:
    """Decode compact target DTOs used by non-damage responses.

    The server protocol uses several tiny target classes (countdown changes,
    leader-area/crest changes, deck pushes, and field transforms).  They are
    deliberately decoded into plain dictionaries so the training normalizer
    can retain the choice without coupling it to a particular IL2CPP class.
    """
    if not collection_address:
        return []
    try:
        addresses = read_reference_collection(reader, collection_address, maximum=maximum)
    except (OSError, ValueError, LookupError):
        return []
    result: list[dict[str, object]] = []
    for target_address in addresses:
        if not target_address:
            continue
        try:
            if kind == "set_countdown":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "count": reader.read_i32(target_address + 0x1C),
                    "add_count": reader.read_i32(target_address + 0x20),
                    "count_sequence": reader.read_i32(target_address + 0x24),
                    "is_ally": bool(reader.read_u32(target_address + 0x28) & 0xFF),
                    "is_by_turn_start": bool(reader.read_u32(target_address + 0x29) & 0xFF),
                }
            elif kind == "spell_boost":
                values = {
                    "is_ally": bool(reader.read_u32(target_address + 0x10) & 0xFF),
                    "unique_id": reader.read_u32(target_address + 0x14),
                }
            elif kind == "change_leader":
                values = {
                    "is_ally": bool(reader.read_u32(target_address + 0x10) & 0xFF),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "count": reader.read_i32(target_address + 0x1C),
                    "add_count": reader.read_i32(target_address + 0x20),
                    "created_by_evolved": bool(reader.read_u32(target_address + 0x24) & 0xFF),
                }
            elif kind in {"remove_crest", "remove_extra"}:
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "created_by_evolved": bool(reader.read_u32(target_address + 0x1C) & 0xFF),
                    "is_ally": bool(reader.read_u32(target_address + 0x1D) & 0xFF),
                }
            elif kind == "push_deck":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "cost": reader.read_i32(target_address + 0x1C),
                    "attack": reader.read_i32(target_address + 0x20),
                    "life": reader.read_i32(target_address + 0x24),
                }
            elif kind == "transform_field":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "after_card": _event_card_summary(reader, reader.read_u64(target_address + 0x18), field=True),
                    "is_ally": bool(reader.read_u32(target_address + 0x20) & 0xFF),
                }
            elif kind == "skybound":
                values = {
                    "is_ally": bool(reader.read_u32(target_address + 0x10) & 0xFF),
                    "unique_id": reader.read_u32(target_address + 0x14),
                }
            elif kind == "leader_status":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "life": reader.read_i32(target_address + 0x14),
                    "max_life": reader.read_i32(target_address + 0x18),
                    "add_max_life": reader.read_i32(target_address + 0x1C),
                    "is_ally": bool(reader.read_u32(target_address + 0x20) & 0xFF),
                }
            elif kind == "attach_field":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "is_evolved": bool(reader.read_u32(target_address + 0x1C) & 0xFF),
                    "is_ally": bool(reader.read_u32(target_address + 0x1D) & 0xFF),
                }
            elif kind in {"attach_hand", "attach_leader", "attach_extra"}:
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "is_ally": bool(reader.read_u32(target_address + 0x1C) & 0xFF),
                }
            elif kind == "extra_count":
                values = {
                    "is_ally": bool(reader.read_u32(target_address + 0x10) & 0xFF),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "count": reader.read_i32(target_address + 0x1C),
                    "add_count": reader.read_i32(target_address + 0x20),
                    "created_by_evolved": bool(reader.read_u32(target_address + 0x24) & 0xFF),
                }
            elif kind == "bounce":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "after_card": _event_card_summary(reader, reader.read_u64(target_address + 0x18), field=False),
                    "is_ally": bool(reader.read_u32(target_address + 0x20) & 0xFF),
                    "is_flood": bool(reader.read_u32(target_address + 0x21) & 0xFF),
                }
            elif kind == "bounce_deck":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                    "is_ally": bool(reader.read_u32(target_address + 0x1C) & 0xFF),
                }
            elif kind == "return_deck":
                values = {
                    "unique_id": reader.read_u32(target_address + 0x10),
                    "card_id": reader.read_i32(target_address + 0x14),
                    "style_id": reader.read_i32(target_address + 0x18),
                }
            else:
                continue
        except (OSError, ValueError, LookupError):
            continue
        if any(int(values.get(key, 0) or 0) for key in ("unique_id", "card_id")):
            result.append(values)
    return result


def _event_target_summaries(reader: MemoryReader, collection_address: int, *, kind: str) -> list[dict[str, object]]:
    """Decode the small target records used by damage/status responses."""
    if not collection_address:
        return []
    try:
        addresses = read_reference_collection(reader, collection_address, maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS)
    except (OSError, ValueError, LookupError):
        return []
    result: list[dict[str, object]] = []
    for address in addresses:
        if not address:
            continue
        try:
            if kind == "damage":
                values = {
                    "unique_id": reader.read_u32(address + 0x10),
                    "card_id": reader.read_i32(address + 0x14),
                    "damage": reader.read_i32(address + 0x18),
                    "is_ally": bool(reader.read_u32(address + 0x1C) & 0xFF),
                    "is_dead": bool(reader.read_u32(address + 0x1D) & 0xFF),
                    "is_evolved": bool(reader.read_u32(address + 0x1E) & 0xFF),
                    "style_id": reader.read_i32(address + 0x20),
                }
            elif kind == "heal":
                values = {
                    "unique_id": reader.read_u32(address + 0x10),
                    "card_id": reader.read_i32(address + 0x14),
                    "is_ally": bool(reader.read_u32(address + 0x18) & 0xFF),
                    "is_evolved": bool(reader.read_u32(address + 0x19) & 0xFF),
                    "healed": reader.read_i32(address + 0x1C),
                    "style_id": reader.read_i32(address + 0x20),
                }
            elif kind == "field_status":
                values = {
                    "card_id": reader.read_i32(address + 0x10),
                    "unique_id": reader.read_u32(address + 0x14),
                    "atk": reader.read_i32(address + 0x18),
                    "life": reader.read_i32(address + 0x1C),
                    "max_life": reader.read_i32(address + 0x20),
                    "add_atk": reader.read_i32(address + 0x24),
                    "add_life": reader.read_i32(address + 0x28),
                    "add_max_life": reader.read_i32(address + 0x2C),
                    "is_ally": bool(reader.read_u32(address + 0x30) & 0xFF),
                    "is_evolved": bool(reader.read_u32(address + 0x31) & 0xFF),
                    "style_id": reader.read_i32(address + 0x34),
                }
            elif kind == "hand_status":
                values = {
                    "card_id": reader.read_i32(address + 0x10),
                    "unique_id": reader.read_u32(address + 0x14),
                    "card_type": reader.read_i32(address + 0x18),
                    "cost": reader.read_i32(address + 0x1C),
                    "atk": reader.read_i32(address + 0x20),
                    "life": reader.read_i32(address + 0x24),
                    "add_cost": reader.read_i32(address + 0x28),
                    "added_cost": reader.read_i32(address + 0x2C),
                    "added_atk": reader.read_i32(address + 0x30),
                    "added_life": reader.read_i32(address + 0x34),
                    "is_ally": bool(reader.read_u32(address + 0x38) & 0xFF),
                    "style_id": reader.read_i32(address + 0x3C),
                }
            elif kind == "remove":
                values = {
                    "unique_id": reader.read_u32(address + 0x10),
                    "card_id": reader.read_i32(address + 0x14),
                    "is_ally": bool(reader.read_u32(address + 0x18) & 0xFF),
                    "is_evolved": bool(reader.read_u32(address + 0x19) & 0xFF),
                    "remove_type": reader.read_i32(address + 0x24),
                    "attack_card_id": reader.read_i32(address + 0x28),
                }
            else:
                continue
        except (OSError, ValueError, LookupError):
            continue
        # Zero IDs are placeholders, not actual cards.  Keep non-card scalar
        # fields only when a valid identity was decoded.
        if int(values.get("unique_id", 0) or 0) or int(values.get("card_id", 0) or 0):
            result.append(values)
    return result


def _read_battle_event(reader: MemoryReader, address: int) -> dict[str, object]:
    full_name = read_il2cpp_type_name(reader, address)
    name = full_name.rsplit(".", 1)[-1]
    event: dict[str, object] = {
        "address": f"0x{address:016X}",
        "type": name,
        "sequence": reader.read_i32(address + 0x10),
    }

    if name in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect"}:
        card_list = reader.read_u64(address + 0x20)
        cards = read_reference_collection(reader, card_list, maximum=MAX_HAND_CARDS)
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            cards=[asdict(read_hand_card(reader, card)) for card in cards if card],
            add_num=reader.read_i32(address + 0x28),
            is_turn_start_draw=bool(reader.read_u32(address + 0x2C) & 0xFF),
            is_super_evolve=bool(reader.read_u32(address + 0x2D) & 0xFF),
            skill_id=reader.read_i32(address + 0x30),
        )
        if name == "BattleResponseDrawOpenWithEffect":
            event["effect_targets"] = _event_int_values(reader, reader.read_u64(address + 0x38), maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS)
    elif name == "BattleResponseDrawHide":
        event.update(
            draw_num=reader.read_i32(address + 0x18),
            add_num=reader.read_i32(address + 0x1C),
            is_turn_start_draw=bool(reader.read_u32(address + 0x20) & 0xFF),
            is_super_evolve=bool(reader.read_u32(address + 0x21) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
        )
    elif name in {"BattleResponseMulliganReady", "BattleResponseMulliganFinish"}:
        # These responses mark the opening-hand phase.  The root pointer in
        # the ready/finish DTO is intentionally not followed; the root
        # snapshot is already captured separately and is the authoritative
        # replay state.
        if name == "BattleResponseMulliganReady":
            event["is_ally"] = bool(reader.read_u32(address + 0x18) & 0xFF)
        event["phase"] = "mulligan_ready" if name.endswith("Ready") else "mulligan_finish"
    elif name in {"BattleResponseTurnStart", "BattleResponseTurnStartEnd"}:
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            turn=reader.read_i32(address + 0x1C),
            phase="turn_start" if name.endswith("TurnStart") else "turn_start_end",
        )
    elif name == "BattleResponseTurnEnd":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            is_force=bool(reader.read_u32(address + 0x19) & 0xFF),
            phase="turn_end",
        )
    elif name == "BattleResponseTurnEndSkillEnd":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            phase="turn_end_skill_end",
        )
    elif name == "BattleResponseActionEnd":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            is_delay=bool(reader.read_u32(address + 0x19) & 0xFF),
            phase="action_end",
        )
    elif name == "BattleResponsePlayOpen":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            unique_id=reader.read_u32(address + 0x1C),
            card_id=reader.read_i32(address + 0x20),
            card_style_id=reader.read_i32(address + 0x24),
            after_play_card_id=reader.read_i32(address + 0x28),
            after_play_card_style_id=reader.read_i32(address + 0x2C),
            play_kind=reader.read_i32(address + 0x30),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x38), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x40), maximum=MAX_CARD_COUNTERS,
            ),
        )
    elif name == "BattleResponseUpdatePP":
        event.update(
            pp=reader.read_i32(address + 0x18),
            max_pp=reader.read_i32(address + 0x1C),
            preparation_extra_pp=reader.read_i32(address + 0x20),
            is_ally=bool(reader.read_u32(address + 0x24) & 0xFF),
            skill_id=reader.read_i32(address + 0x28),
            skill_add_pp=reader.read_i32(address + 0x2C),
            skill_add_max_pp=reader.read_i32(address + 0x30),
            is_super_evolve=bool(reader.read_u32(address + 0x34) & 0xFF),
            is_consume_extra_pp=bool(reader.read_u32(address + 0x35) & 0xFF),
            prev_pp=reader.read_i32(address + 0x38),
            is_card_play=bool(reader.read_u32(address + 0x3C) & 0xFF),
        )
    elif name == "BattleResponseSetAttackLimit":
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            card_id=reader.read_i32(address + 0x1C),
            style_id=reader.read_i32(address + 0x20),
            is_evolved=bool(reader.read_u32(address + 0x24) & 0xFF),
            is_ally=bool(reader.read_u32(address + 0x25) & 0xFF),
            skill_id=reader.read_i32(address + 0x28),
            is_changed_ability=bool(reader.read_u32(address + 0x2C) & 0xFF),
            attack_limit=reader.read_i32(address + 0x30),
        )
    elif name in {"BattleResponseAddModeSelectableCount", "BattleResponseIncreaseDamage"}:
        event.update(
            card_id=reader.read_i32(address + 0x18),
            style_id=reader.read_i32(address + 0x1C),
            is_evolved=bool(reader.read_u32(address + 0x20) & 0xFF),
            is_ally=bool(reader.read_u32(address + 0x21) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
        )
    elif name == "BattleResponsePutCardFromHand":
        event.update(
            card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=True),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            unique_id_before=reader.read_u32(address + 0x24),
            enhance_index=reader.read_i32(address + 0x28),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x30), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x38), maximum=MAX_CARD_COUNTERS,
            ),
            skybound_art_state=reader.read_i32(address + 0x40),
        )
    elif name == "BattleResponseCastSpellFromHand":
        event.update(
            card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=True),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            unique_id_before_accelerate=reader.read_u32(address + 0x24),
            enhance_index=reader.read_i32(address + 0x28),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x30), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x38), maximum=MAX_CARD_COUNTERS,
            ),
            skybound_art_state=reader.read_i32(address + 0x40),
        )
    elif name == "BattleResponseActivation":
        event.update(
            card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=True),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x28), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x30), maximum=MAX_CARD_COUNTERS,
            ),
        )
    elif name == "BattleResponseFusion":
        event.update(
            fusion_card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=False),
            material_cards=_event_cards(
                reader, reader.read_u64(address + 0x20), field=False, maximum=MAX_HAND_CARDS,
            ),
            is_ally=bool(reader.read_u32(address + 0x28) & 0xFF),
            can_fusion_transform=bool(reader.read_u32(address + 0x29) & 0xFF),
        )
    elif name == "BattleResponseAttack":
        event.update(
            from_unique_id=reader.read_u32(address + 0x18),
            from_card_id=reader.read_i32(address + 0x1C),
            from_damage=reader.read_i32(address + 0x20),
            from_remove_type=reader.read_i32(address + 0x24),
            is_from_evolved=bool(reader.read_u32(address + 0x28) & 0xFF),
            to_unique_id=reader.read_u32(address + 0x2C),
            to_card_id=reader.read_i32(address + 0x30),
            to_damage=reader.read_i32(address + 0x34),
            to_remove_type=reader.read_i32(address + 0x38),
            is_to_evolved=bool(reader.read_u32(address + 0x3C) & 0xFF),
            is_ally=bool(reader.read_u32(address + 0x3D) & 0xFF),
            from_card_style_id=reader.read_i32(address + 0x40),
            to_card_style_id=reader.read_i32(address + 0x44),
            is_super_evolve_blow=bool(reader.read_u32(address + 0x48) & 0xFF),
        )
    elif name == "BattleResponseSuperEvolveBlow":
        event.update(
            from_unique_id=reader.read_u32(address + 0x18),
            to_card_unique_id=reader.read_u32(address + 0x1C),
            to_leader_unique_id=reader.read_u32(address + 0x20),
            damage=reader.read_i32(address + 0x24),
            is_ally=bool(reader.read_u32(address + 0x28) & 0xFF),
            is_dead=bool(reader.read_u32(address + 0x29) & 0xFF),
        )
    elif name == "BattleResponseCancelAttack":
        event.update(
            from_unique_id=reader.read_u32(address + 0x18),
            from_new_life=reader.read_i32(address + 0x1C),
            to_unique_id=reader.read_u32(address + 0x20),
            to_new_life=reader.read_i32(address + 0x24),
        )
    elif name == "BattleResponseMulligan":
        # ``change_card_flags`` is a bit mask (one bit for each of the four
        # opening cards), not a numeric card count.
        event.update(
            draw_num=reader.read_i32(address + 0x18),
            is_ally=bool(reader.read_u32(address + 0x1C) & 0xFF),
            change_card_flags=reader.read_u32(address + 0x28),
            hand_cards=_event_cards(reader, reader.read_u64(address + 0x20), field=False, maximum=MAX_HAND_CARDS),
            is_time_over=bool(reader.read_u32(address + 0x2C) & 0xFF),
        )
    elif name == "BattleResponseEvolve":
        event.update(
            evolved_card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=True),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            new_ep=reader.read_i32(address + 0x24),
            new_ep_max=reader.read_i32(address + 0x28),
            new_sep=reader.read_i32(address + 0x2C),
            is_super=bool(reader.read_u32(address + 0x30) & 0xFF),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x38), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x40), maximum=MAX_CARD_COUNTERS,
            ),
        )
    elif name == "BattleResponseSkillEvolve":
        event.update(
            act_card_unique_id=reader.read_u32(address + 0x18),
            act_card_id=reader.read_i32(address + 0x1C),
            targets=_event_field_card_targets(
                reader, reader.read_u64(address + 0x20), maximum=MAX_FIELD_CARDS,
            ),
            skill_id=reader.read_i32(address + 0x28),
            act_card_style_id=reader.read_i32(address + 0x2C),
            is_super_evolve_timing=bool(reader.read_u32(address + 0x30) & 0xFF),
            is_super_evolve=bool(reader.read_u32(address + 0x31) & 0xFF),
        )
    elif name == "BattleResponseUpdateEP":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            max_ep=reader.read_i32(address + 0x1C),
            ep=reader.read_i32(address + 0x20),
            max_sep=reader.read_i32(address + 0x24),
            sep=reader.read_i32(address + 0x28),
            skill_id=reader.read_i32(address + 0x2C),
            card_id=reader.read_i32(address + 0x30),
            style_id=reader.read_i32(address + 0x34),
        )
    elif name == "BattleResponsePutCardFromDeck":
        event.update(
            cards=_event_cards(reader, reader.read_u64(address + 0x18), field=True, maximum=MAX_FIELD_CARDS),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
            is_super_evolve=bool(reader.read_u32(address + 0x28) & 0xFF),
            is_invocation=bool(reader.read_u32(address + 0x29) & 0xFF),
            act_card_id=reader.read_i32(address + 0x2C),
            act_style_id=reader.read_i32(address + 0x30),
        )
    elif name == "BattleResponsePutToken":
        targets = _event_field_card_targets(
            reader, reader.read_u64(address + 0x18), maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS,
            include_is_ally=False,
        )
        # PutToken.Target has one extra flag beyond the common card/side
        # fields.  Read it separately when the target record is available.
        try:
            target_addresses = read_reference_collection(
                reader, reader.read_u64(address + 0x18), maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS,
            )
        except (OSError, ValueError, LookupError):
            target_addresses = ()
        for index, target_address in enumerate(target_addresses[:len(targets)]):
            try:
                targets[index]["is_overflow"] = bool(reader.read_u32(target_address + 0x18) & 0xFF)
            except (OSError, ValueError, LookupError):
                pass
        event.update(
            targets=targets,
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
            is_super_evolve=bool(reader.read_u32(address + 0x28) & 0xFF),
            act_card_id=reader.read_i32(address + 0x2C),
            act_style_id=reader.read_i32(address + 0x30),
        )
    elif name == "BattleResponseSetCountdown":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="set_countdown", maximum=MAX_FIELD_CARDS + MAX_CRESTS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseSpellBoost":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="spell_boost", maximum=MAX_HAND_CARDS,
            ),
            is_super_evolve=bool(reader.read_u32(address + 0x20) & 0xFF),
            add_count=reader.read_i32(address + 0x24),
        )
    elif name == "BattleResponseExtraPP":
        event.update(
            pp=reader.read_i32(address + 0x18),
            max_pp=reader.read_i32(address + 0x1C),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            is_cancel=bool(reader.read_u32(address + 0x21) & 0xFF),
        )
    elif name == "BattleResponseExtraPPRestore":
        event["is_ally"] = bool(reader.read_u32(address + 0x18) & 0xFF)
    elif name == "BattleResponseTransformField":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="transform_field", maximum=MAX_FIELD_CARDS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name in {"BattleResponseTransformHand", "BattleResponseFusionTransform"}:
        event.update(
            before_unique_id=reader.read_u32(address + 0x18),
            after_card=_event_card_summary(reader, reader.read_u64(address + 0x20), field=False),
            is_ally=bool(reader.read_u32(address + 0x28) & 0xFF),
            skill_id=reader.read_i32(address + 0x2C),
        )
    elif name == "BattleResponseBounce":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="bounce", maximum=MAX_FIELD_CARDS,
            ),
            is_super_evolve=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
        )
    elif name == "BattleResponseBounceIntoDeck":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="bounce_deck", maximum=MAX_FIELD_CARDS,
            ),
            is_super_evolve=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
        )
    elif name == "BattleResponceReturnDeck":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="return_deck", maximum=MAX_FIELD_CARDS,
            ),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
            is_open=bool(reader.read_u32(address + 0x28) & 0xFF),
        )
    elif name == "BattleResponseSpecialAction":
        event.update(
            card=_event_card_summary(reader, reader.read_u64(address + 0x18), field=True),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            target_unique_id_by_skills=_event_nested_int_values(
                reader, reader.read_u64(address + 0x28), maximum_outer=MAX_CARD_COUNTERS,
                maximum_inner=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
            ),
            selected_indexes=_event_int_values(
                reader, reader.read_u64(address + 0x30), maximum=MAX_CARD_COUNTERS,
            ),
        )
    elif name == "BattleResponseSkillDamage":
        event.update(
            act_card_unique_id=reader.read_u32(address + 0x18),
            act_card_id=reader.read_i32(address + 0x1C),
            skill_id=reader.read_i32(address + 0x20),
            is_act_ally=bool(reader.read_u32(address + 0x24) & 0xFF),
            targets=_event_target_summaries(reader, reader.read_u64(address + 0x28), kind="damage"),
            act_card_style_id=reader.read_i32(address + 0x30),
            is_super_evolve=bool(reader.read_u32(address + 0x34) & 0xFF),
        )
    elif name == "BattleResponseSkillHeal":
        event.update(
            skill_id=reader.read_i32(address + 0x18),
            targets=_event_target_summaries(reader, reader.read_u64(address + 0x20), kind="heal"),
            card_id=reader.read_i32(address + 0x28),
            style_id=reader.read_i32(address + 0x2C),
            is_super_evolve=bool(reader.read_u32(address + 0x30) & 0xFF),
        )
    elif name == "BattleResponseHeal":
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            healed=reader.read_i32(address + 0x1C),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseSkillEffect":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            skill_id=reader.read_i32(address + 0x1C),
            from_unique_id=reader.read_u32(address + 0x20),
            from_card_id=reader.read_i32(address + 0x24),
            is_evolved_from=bool(reader.read_u32(address + 0x28) & 0xFF),
            target_unique_ids=_event_int_values(reader, reader.read_u64(address + 0x30), maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2),
            effect=reader.read_i32(address + 0x38),
            sub_effect=reader.read_i32(address + 0x3C),
            from_card_style_id=reader.read_i32(address + 0x40),
            is_super_evolve=bool(reader.read_u32(address + 0x44) & 0xFF),
        )
    elif name == "BattleResponseSkillEffectEach":
        targets_address = reader.read_u64(address + 0x30)
        targets: list[dict[str, object]] = []
        try:
            target_addresses = read_reference_collection(reader, targets_address, maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2)
        except (OSError, ValueError, LookupError):
            target_addresses = ()
        for target_address in target_addresses:
            try:
                targets.append({"unique_id": reader.read_u32(target_address + 0x10), "is_ally": bool(reader.read_u32(target_address + 0x14) & 0xFF)})
            except (OSError, ValueError, LookupError):
                continue
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            skill_id=reader.read_i32(address + 0x1C),
            from_unique_id=reader.read_u32(address + 0x20),
            from_card_id=reader.read_i32(address + 0x24),
            from_card_style_id=reader.read_i32(address + 0x28),
            targets=targets,
            is_super_evolve=bool(reader.read_u32(address + 0x38) & 0xFF),
        )
    elif name == "BattleResponseSkillEffectPrev":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            skill_ids=_event_int_values(reader, reader.read_u64(address + 0x20), maximum=MAX_CARD_COUNTERS),
            unique_id=reader.read_u32(address + 0x28),
            card_id=reader.read_i32(address + 0x2C),
            style_id=reader.read_i32(address + 0x30),
            is_evolved=bool(reader.read_u32(address + 0x34) & 0xFF),
            effect=reader.read_i32(address + 0x38),
            sub_effect=reader.read_i32(address + 0x3C),
            crest_card_id=reader.read_i32(address + 0x40),
            extra_crest_card_id=reader.read_i32(address + 0x44),
            is_induction=bool(reader.read_u32(address + 0x48) & 0xFF),
        )
    elif name == "BattleResponseBattleEnd":
        result_codes = _read_i32_array(
            reader, reader.read_u64(address + 0x18), maximum=MAX_PLAYERS,
        )
        heal_address = reader.read_u64(address + 0x20)
        heal_result: dict[str, object] | None = None
        if heal_address:
            try:
                heal_result = {
                    "is_executed": bool(reader.read_u32(heal_address + 0x10) & 0xFF),
                    "healed": reader.read_i32(heal_address + 0x14),
                    "battle_start_max_life": reader.read_i32(heal_address + 0x18),
                }
            except (OSError, ValueError, LookupError):
                heal_result = None
        event.update(result_codes=list(result_codes), heal_result=heal_result)
    elif name == "BattleResponseAddCrest":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            card_id=reader.read_i32(address + 0x1C),
            unique_id=reader.read_u32(address + 0x20),
            countdown=reader.read_i32(address + 0x24),
            skill_id=reader.read_i32(address + 0x28),
            faith_value=reader.read_i32(address + 0x2C),
            is_super_evolve=bool(reader.read_u32(address + 0x30) & 0xFF),
            style_id=reader.read_i32(address + 0x34),
            is_battle_start=bool(reader.read_u32(address + 0x38) & 0xFF),
        )
    elif name in {"BattleResponseCantAddCrest", "BattleResponseCantAddExtraCrest"}:
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            card_id=reader.read_i32(address + 0x1C),
        )
    elif name == "BattleResponseAddExtraCrest":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            card_id=reader.read_i32(address + 0x1C),
            unique_id=reader.read_u32(address + 0x20),
            countdown=reader.read_i32(address + 0x24),
            skill_id=reader.read_i32(address + 0x28),
            is_super_evolve=bool(reader.read_u32(address + 0x2C) & 0xFF),
            style_id=reader.read_i32(address + 0x30),
            is_battle_start=bool(reader.read_u32(address + 0x34) & 0xFF),
        )
    elif name == "BattleResponseChangeExtraCrestCount":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="extra_count", maximum=MAX_CRESTS,
            ),
            is_super_evolve=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseRemoveExtraCrest":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="remove_extra", maximum=MAX_CRESTS,
            ),
            is_banish=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseRemoveCrest":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="remove_crest", maximum=MAX_CRESTS,
            ),
            is_banish=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseReinforceFaith":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            card_id=reader.read_i32(address + 0x1C),
        )
    elif name == "BattleResponseChangeLeaderAreaCount":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="change_leader", maximum=MAX_CRESTS,
            ),
            is_super_evolve=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseAffectDeck":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            skill_id=reader.read_i32(address + 0x1C),
        )
    elif name == "BattleResponseSetStatusLeader":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="leader_status", maximum=MAX_PLAYERS,
            ),
            skill_running_number=reader.read_u32(address + 0x20),
        )
    elif name == "BattleResponseStack":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            unique_id=reader.read_u32(address + 0x1C),
            card_id=reader.read_i32(address + 0x20),
            style_id=reader.read_i32(address + 0x24),
            stack=reader.read_i32(address + 0x28),
            add=reader.read_i32(address + 0x2C),
            skill_id=reader.read_i32(address + 0x30),
            is_super_evolve=bool(reader.read_u32(address + 0x34) & 0xFF),
            is_destroy=bool(reader.read_u32(address + 0x35) & 0xFF),
        )
    elif name == "BattleResponseContentUhT9MJ":
        # The generated class name is present in the protocol (it represents
        # a card content counter update).  Keep the opaque counter instead of
        # reducing this response to the generic unknown-event bucket.
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            unique_id=reader.read_u32(address + 0x1C),
            card_id=reader.read_i32(address + 0x20),
            style_id=reader.read_i32(address + 0x24),
            content=reader.read_i32(address + 0x28),
            add=reader.read_i32(address + 0x2C),
            skill_id=reader.read_i32(address + 0x30),
            is_super_evolve=bool(reader.read_u32(address + 0x34) & 0xFF),
            is_destroy=bool(reader.read_u32(address + 0x35) & 0xFF),
        )
    elif name == "BattleResponsePushDeck":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="push_deck", maximum=MAX_HAND_CARDS,
            ),
            is_ally=bool(reader.read_u32(address + 0x20) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
            is_super_evolve=bool(reader.read_u32(address + 0x28) & 0xFF),
        )
    elif name == "BattleResponsePushDeckHide":
        event.update(
            push_num=reader.read_i32(address + 0x18),
            is_ally=bool(reader.read_u32(address + 0x1C) & 0xFF),
            skill_id=reader.read_i32(address + 0x20),
            is_super_evolve=bool(reader.read_u32(address + 0x24) & 0xFF),
        )
    elif name == "BattleResponseReplaceDeck":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            deck_count=reader.read_i32(address + 0x1C),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name in {"BattleResponseAddPlayCount", "BattleResponseAddCemeteryCount"}:
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            add=reader.read_i32(address + 0x1C),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseEmote":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            emote_type=reader.read_i32(address + 0x1C),
            timing=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseAddSkyboundArtCount":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="skybound", maximum=MAX_PLAYERS,
            ),
            from_super_evolve_boost_skill=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponseRandomAllocate":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            card_id=reader.read_i32(address + 0x1C),
            style_id=reader.read_i32(address + 0x20),
            values=list(_read_i32_array(reader, reader.read_u64(address + 0x28), maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS)),
            skill_id=reader.read_i32(address + 0x30),
        )
    elif name == "BattleResponseSetStatusField":
        event.update(
            skill_id=reader.read_i32(address + 0x18),
            targets=_event_target_summaries(reader, reader.read_u64(address + 0x20), kind="field_status"),
            is_set=bool(reader.read_u32(address + 0x28) & 0xFF),
        )
    elif name == "BattleResponseSetStatusHand":
        event.update(
            skill_id=reader.read_i32(address + 0x18),
            targets=_event_target_summaries(reader, reader.read_u64(address + 0x20), kind="hand_status"),
            is_super_evolve=bool(reader.read_u32(address + 0x28) & 0xFF),
            is_spell_boost=bool(reader.read_u32(address + 0x29) & 0xFF),
            is_reset=bool(reader.read_u32(address + 0x2A) & 0xFF),
        )
    elif name == "BattleResponseAttachSkillField":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="attach_field", maximum=MAX_FIELD_CARDS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseAttachSkillHand":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="attach_hand", maximum=MAX_HAND_CARDS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseAttachSkillLeaderArea":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="attach_leader", maximum=MAX_PLAYERS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseAttachSkillExtraCrestArea":
        event.update(
            targets=_event_scalar_targets(
                reader, reader.read_u64(address + 0x18), kind="attach_extra", maximum=MAX_CRESTS,
            ),
            skill_id=reader.read_i32(address + 0x20),
        )
    elif name == "BattleResponseHandToken":
        event.update(
            cards=_event_cards(reader, reader.read_u64(address + 0x18), field=False, maximum=MAX_HAND_CARDS),
            add_num=reader.read_i32(address + 0x20),
            is_ally=bool(reader.read_u32(address + 0x24) & 0xFF),
            is_open=bool(reader.read_u32(address + 0x25) & 0xFF),
            skill_id=reader.read_i32(address + 0x28),
            is_super_evolve=bool(reader.read_u32(address + 0x2C) & 0xFF),
        )
    elif name == "BattleResponseRemoveCard":
        event.update(
            act_card_unique_id=reader.read_u32(address + 0x18),
            act_card_id=reader.read_i32(address + 0x1C),
            targets=_event_target_summaries(reader, reader.read_u64(address + 0x20), kind="remove"),
            skill_id=reader.read_i32(address + 0x28),
            is_skill_destroy_or_banish=bool(reader.read_u32(address + 0x2C) & 0xFF),
            act_card_style_id=reader.read_i32(address + 0x30),
            is_super_evolve=bool(reader.read_u32(address + 0x34) & 0xFF),
        )
    elif name in {
        "BattleResponseActivateGuard", "BattleResponseActivateQuick",
        "BattleResponseActivateRush", "BattleResponseActivateSneak",
        "BattleResponseActivateTempShield",
        "BattleResponseActivateCantAttack", "BattleResponseActivateCantBeAttack",
        "BattleResponseActivateCantSelect", "BattleResponseActivateKiller",
        "BattleResponseActivateDrain", "BattleResponseActivateDamageCut",
        "BattleResponseActivateCantDestroy",
    }:
        # These keyword effects share the same response layout in the 1.9.x
        # client.  Keeping the source event name lets a trainer distinguish
        # guard/rush/etc. while the common fields provide the actor identity.
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            card_id=reader.read_i32(address + 0x1C),
            is_evolved=bool(reader.read_u32(address + 0x20) & 0xFF),
            is_active=bool(reader.read_u32(address + 0x21) & 0xFF),
            is_ally=bool(reader.read_u32(address + 0x22) & 0xFF),
            skill_id=reader.read_i32(address + 0x24),
            style_id=reader.read_i32(address + 0x28),
            is_changed_ability=bool(reader.read_u32(address + 0x2C) & 0xFF),
        )
    elif name == "BattleResponseActivateLastword":
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            card_id=reader.read_i32(address + 0x1C),
            style_id=reader.read_i32(address + 0x20),
            is_ally=bool(reader.read_u32(address + 0x24) & 0xFF),
            is_active=bool(reader.read_u32(address + 0x25) & 0xFF),
            skill_id=reader.read_i32(address + 0x28),
        )
    elif name in {"BattleResponseActivateLostSkill", "BattleResponseRemoveGuard"}:
        # Lost-skill/remove-guard use the same compact identity and place the
        # evolved/ally flags at the same offsets.
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            card_id=reader.read_i32(address + 0x1C),
            style_id=reader.read_i32(address + 0x20),
            is_evolved=bool(reader.read_u32(address + 0x24) & 0xFF),
            is_ally=bool(reader.read_u32(address + 0x25) & 0xFF),
            skill_id=reader.read_i32(address + 0x28),
        )
    elif name in {
        "BattleResponseActivateActivation", "BattleResponseActivateInduction",
        "BattleResponseActivateRemoveFieldAtTurnChange", "BattleResponseActivateSuperEvolveBuff",
    }:
        event.update(
            unique_id=reader.read_u32(address + 0x18),
            is_active=bool(reader.read_u32(address + 0x1C) & 0xFF),
        )
    elif name in {
        "BattleResponseActivateKakusei", "BattleResponseActivateCantFanfareAndEnhanceAllyFollower",
    }:
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            is_active=bool(reader.read_u32(address + 0x19) & 0xFF),
        )
    elif name == "BattleResponseSetDeckOutWin":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            is_active=bool(reader.read_u32(address + 0x19) & 0xFF),
            skill_id=reader.read_i32(address + 0x1C),
        )
    elif name == "BattleResponseStartSelect":
        response = reader.read_u64(address + 0x18)
        event.update(
            source_unique_id=reader.read_u32(response + 0x10) if response else 0,
            select_mode=reader.read_i32(response + 0x14) if response else 0,
            select_type=reader.read_i32(response + 0x18) if response else 0,
            select_client_id=reader.read_u64(response + 0x20) if response else 0,
            select_sequence=reader.read_i32(response + 0x28) if response else 0,
        )
    elif name == "BattleResponseDecideSelect":
        response = reader.read_u64(address + 0x18)
        decide_ids = _event_int_values(reader, reader.read_u64(response + 0x18), maximum=MAX_CARD_COUNTERS) if response else []
        event.update(
            decide_card=reader.read_u32(response + 0x10) if response else 0,
            decide_ids=decide_ids,
            decide_bool=bool(reader.read_u32(response + 0x20) & 0xFF) if response else False,
        )
    elif name == "BattleResponseCancelSelect":
        event["cancelled"] = True
    elif name == "BattleResponseSendArrow":
        response = reader.read_u64(address + 0x18)
        event.update(
            arrow_type=reader.read_i32(response + 0x18) if response else 0,
            target_unique_ids=(
                _event_int_values(
                    reader, reader.read_u64(response + 0x20),
                    maximum=MAX_FIELD_CARDS + MAX_HAND_CARDS + 2,
                ) if response else []
            ),
        )
    elif name == "BattleResponseSendTouchCard":
        response = reader.read_u64(address + 0x18)
        event["card_unique_id"] = reader.read_u32(response + 0x18) if response else 0
    elif name == "BattleResponseTurnTimerStart":
        response = reader.read_u64(address + 0x18)
        event["turn"] = reader.read_i32(response + 0x18) if response else 0
    elif name == "BattleResponseMulliganSelect":
        response = reader.read_u64(address + 0x18)
        changed = (
            _event_int_values(reader, reader.read_u64(response + 0x18), maximum=MAX_HAND_CARDS)
            if response else []
        )
        event.update(
            change_card_unique_ids=changed,
            replaced_count=len(changed),
        )
    elif name == "BattleResponsePlayHide":
        # The object may contain a resolved card internally. Never expose it here.
        event.update(
            hidden=True,
            play_kind=reader.read_i32(address + 0x20),
            after_play_card_id=reader.read_i32(address + 0x24),
            after_play_card_style_id=reader.read_i32(address + 0x28),
        )
    return event


def _read_mulligan_selection_response(
    reader: MemoryReader,
    battle_model_address: int,
    root: BattleRoot | None,
) -> dict[str, object] | None:
    """Read the persistent mulligan-selection response.

    The transient response queue is normally empty by the time the first turn
    begins.  ``BattleModel`` retains the local player's
    ``MulliganSelectResponse`` at +0x58.  Its ``BattleCardUniqueId[]`` is the
    list of selected (returned) cards.
    """
    property_address = reader.read_u64(battle_model_address + 0x58)
    response_address = reader.read_u64(property_address + 0x20) if property_address else 0
    if not response_address or not read_il2cpp_type_name(reader, response_address).endswith("MulliganSelectResponse"):
        return None
    unique_ids_address = reader.read_u64(response_address + 0x18)
    if not unique_ids_address:
        return None
    length = reader.read_u64(unique_ids_address + 0x18)
    if length == 0 or length > MAX_HAND_CARDS:
        return None
    unique_ids = tuple(
        reader.read_u32(unique_ids_address + 0x20 + index * 4)
        for index in range(length)
    )
    return {
        "address": f"0x{response_address:016X}",
        "type": "BattleModelMulliganSelection",
        "is_ally": True,
        "replaced_count": length,
        # Keeps a new local selection distinct without exposing IDs.
        "selection_fingerprint": tuple(unique_ids),
    }


def read_battle_model(
    reader: MemoryReader,
    address: int,
    *,
    reveal_opponent_hand: bool = False,
    battle_view_server_data_address: int | None = None,
    read_root_legal_actions: bool = False,
) -> dict[str, object]:
    if not address:
        raise ValueError("null BattleModel")
    root_property = reader.read_u64(address + 0x30)
    root_address = reader.read_u64(root_property + 0x20) if root_property else 0
    # ``_currentResponseList`` is cleared as soon as presentation finishes a
    # response batch.  At the normal 20 Hz tracker poll that makes short-lived
    # events (mulligan and, importantly, an overdraw) very easy to miss.
    # ``_battleEvents`` is a ReactiveProperty whose current value keeps the
    # latest batch alive until the next batch arrives.  Read both collections
    # and de-duplicate their object addresses.
    response_addresses: list[int] = []
    battle_events_property = reader.read_u64(address + 0x28)
    latest_responses = reader.read_u64(battle_events_property + 0x20) if battle_events_property else 0
    current_responses = reader.read_u64(address + 0x160)
    for collection in (latest_responses, current_responses):
        if not collection:
            continue
        try:
            addresses = read_reference_collection(
                reader,
                collection,
                maximum=MAX_HISTORY_ITEMS,
            )
        except (OSError, ValueError, LookupError):
            continue
        for response_address in addresses:
            if response_address and response_address not in response_addresses:
                response_addresses.append(response_address)
    self_class_id: int | None = None
    opponent_class_id: int | None = None
    deck_format: int | None = None
    try:
        battle_info_property = reader.read_u64(address + 0x20)
        battle_info = reader.read_u64(battle_info_property + 0x20) if battle_info_property else 0
        if battle_info:
            users_array = reader.read_u64(battle_info + 0x10)
            users = _read_managed_array_pointers(reader, users_array, maximum=MAX_PLAYERS)
            if users and users[0]:
                self_class_id = reader.read_i32(users[0] + 0x40)
            if len(users) >= 2 and users[1]:
                opponent_class_id = reader.read_i32(users[1] + 0x40)
            deck_format = reader.read_i32(battle_info + 0xD4)
    except (OSError, ValueError):
        # Root state remains useful if ancillary BattleInfo has already been released.
        pass
    battle_root = read_battle_root(reader, root_address) if root_address else None
    # A response can be released between the two collection reads above.  A
    # stale pointer must not make the complete board snapshot unreadable (and
    # consequently lose the match record); skip only that response and keep
    # the root/state checkpoint.
    events: list[dict[str, object]] = []
    for response_address in response_addresses:
        if not response_address:
            continue
        try:
            events.append(_read_battle_event(reader, response_address))
        except (OSError, ValueError, LookupError, IndexError, TypeError):
            continue
    try:
        mulligan_selection = _read_mulligan_selection_response(reader, address, battle_root)
    except (OSError, ValueError, LookupError, IndexError, TypeError):
        # The persistent selection response is replaced immediately after the
        # mulligan animation.  Treat a released pointer like any other missed
        # response; the root checkpoint and the transient event stream remain
        # usable for the rest of the match.
        mulligan_selection = None
    if mulligan_selection is not None:
        events.append(mulligan_selection)
    public_root = (
        battle_root.to_public_dict(reveal_opponent_hand=reveal_opponent_hand)
        if battle_root
        else None
    )
    legal_actions: LegalActions | dict[str, object] | None = None
    if battle_view_server_data_address:
        legal_actions = read_battle_view_server_data(reader, battle_view_server_data_address)
    elif read_root_legal_actions and root_address:
        # The China client does not expose a stable presentation-layer pointer
        # for BattleViewServerData.  Its BattleRootMpo already carries the same
        # legality projections, so use those directly instead of forcing a
        # full-process pointer scan in the polling thread.
        try:
            legal_actions = read_battle_root_legal_actions(reader, root_address)
        except (OSError, ValueError, LookupError):
            # Root state remains useful when a legality collection is released
            # during an animation or when an older client lacks the projection.
            legal_actions = None
    legal_actions_dict = (
        asdict(legal_actions) if isinstance(legal_actions, LegalActions) else legal_actions
    )
    if legal_actions is not None and isinstance(public_root, dict):
        players = public_root.get("players")
        ally = players[0] if isinstance(players, (list, tuple)) and players else None
        opponent = players[1] if isinstance(players, (list, tuple)) and len(players) >= 2 else None
        hand = ally.get("hand") if isinstance(ally, dict) else None
        field = ally.get("field") if isinstance(ally, dict) else None
        enemy_field = opponent.get("field") if isinstance(opponent, dict) else None
        hand_ids = {
            card.get("unique_id")
            for card in hand
            if isinstance(hand, (list, tuple)) and isinstance(card, dict)
        } if isinstance(hand, (list, tuple)) else set()
        field_ids = {
            card.get("unique_id")
            for card in field
            if isinstance(field, (list, tuple)) and isinstance(card, dict)
        } if isinstance(field, (list, tuple)) else set()
        target_ids = {
            card.get("unique_id")
            for card in enemy_field
            if isinstance(enemy_field, (list, tuple)) and isinstance(card, dict)
        } if isinstance(enemy_field, (list, tuple)) else set()
        if isinstance(opponent, dict):
            target_ids.add(opponent.get("unique_id"))
        hand_ids.discard(None)
        field_ids.discard(None)
        target_ids.discard(None)
        is_ally_turn = bool(public_root.get("is_ally_turn"))
        if isinstance(legal_actions_dict, dict):
            hand_action_keys = (
                "can_play_cards",
                "can_play_cards_with_extra_pp",
                "can_enhance_play_cards",
                "can_accelerate_play_cards",
                "can_crystal_play_cards",
                "can_fusion_cards",
                "has_fusion_hand_cards",
            )
            field_action_keys = (
                "can_attack_leader_cards",
                "can_attack_field_cards",
                "attacked_cards",
                "can_activation_field_cards",
                "can_activation_field_cards_with_extra_pp",
                "has_activation_field_cards",
                "can_evolve_cards",
                "can_super_evolve_cards",
                "can_super_evolve_with_skill_cards",
                "can_special_action_field_cards",
            )
            for key in hand_action_keys:
                values = legal_actions_dict.get(key, ())
                legal_actions_dict[key] = tuple(value for value in values if value in hand_ids) if is_ally_turn else ()
            for key in field_action_keys:
                values = legal_actions_dict.get(key, ())
                legal_actions_dict[key] = tuple(value for value in values if value in field_ids) if is_ally_turn else ()
            target_map = legal_actions_dict.get("attack_targets")
            legal_actions_dict["attack_targets"] = {
                int(attacker): tuple(target for target in targets if target in target_ids)
                for attacker, targets in target_map.items()
                if is_ally_turn and int(attacker) in field_ids
            } if isinstance(target_map, dict) else {}
            if not is_ally_turn:
                legal_actions_dict["can_special_action_area_cards"] = ()
        if isinstance(field, (list, tuple)):
            can_leader = set(legal_actions_dict.get("can_attack_leader_cards", ()))
            can_field = set(legal_actions_dict.get("can_attack_field_cards", ()))
            attacked = set(legal_actions_dict.get("attacked_cards", ()))
            target_map = legal_actions_dict.get("attack_targets", {})
            for card in field:
                if not isinstance(card, dict):
                    continue
                unique_id = card.get("unique_id")
                if not isinstance(unique_id, int):
                    continue
                card["attack_targets"] = target_map.get(unique_id, ())
                card["can_attack_leader"] = unique_id in can_leader
                card["can_attack_field"] = unique_id in can_field
                card["has_attacked"] = unique_id in attacked
    return {
        "address": f"0x{address:016X}",
        "self_class_id": self_class_id,
        "opponent_class_id": opponent_class_id,
        "deck_format": deck_format,
        "root": public_root,
        "legal_actions": legal_actions_dict,
        "events": events,
    }


def read_battle_root_snapshot(
    reader: MemoryReader,
    address: int,
    *,
    reveal_opponent_hand: bool = False,
) -> dict[str, object]:
    """Build the public snapshot envelope directly from a BattleRootMpo.

    Puzzle/teaching battles can keep a valid root while exposing no regular
    ``BattleModel`` instance.  The root still carries the server's legality
    projections, so decode those directly.  Ancillary class ids and response
    events remain unknown; the adapter only trusts fields it can validate.
    """
    root = read_battle_root(reader, address)
    try:
        legal_actions: dict[str, object] | None = read_battle_root_legal_actions(reader, address)
    except (OSError, ValueError):
        legal_actions = None
    public_root = root.to_public_dict(reveal_opponent_hand=reveal_opponent_hand)
    # The root-level target map is authoritative in puzzle mode.  Project it
    # onto field cards as well, matching the regular BattleModel reader and
    # keeping the UI/adapter views identical.
    if isinstance(public_root, dict) and isinstance(legal_actions, dict):
        players = public_root.get("players")
        if isinstance(players, (list, tuple)) and players:
            mine = players[0] if isinstance(players[0], dict) else None
            opponent = players[1] if len(players) > 1 and isinstance(players[1], dict) else None
            hand = mine.get("hand", ()) if isinstance(mine, dict) else ()
            field = mine.get("field", ()) if isinstance(mine, dict) else ()
            enemy_field = opponent.get("field", ()) if isinstance(opponent, dict) else ()
            hand_ids = {int(card["unique_id"]) for card in hand if isinstance(card, dict) and isinstance(card.get("unique_id"), int)}
            field_ids = {int(card["unique_id"]) for card in field if isinstance(card, dict) and isinstance(card.get("unique_id"), int)}
            target_ids = {int(card["unique_id"]) for card in enemy_field if isinstance(card, dict) and isinstance(card.get("unique_id"), int)}
            if isinstance(opponent, dict) and isinstance(opponent.get("unique_id"), int):
                target_ids.add(int(opponent["unique_id"]))
            hand_keys = ("can_play_cards", "can_play_cards_with_extra_pp", "can_enhance_play_cards", "can_accelerate_play_cards", "can_crystal_play_cards", "can_fusion_cards", "has_fusion_hand_cards")
            field_keys = ("can_attack_leader_cards", "can_attack_field_cards", "attacked_cards", "can_activation_field_cards", "can_activation_field_cards_with_extra_pp", "has_activation_field_cards", "can_evolve_cards", "can_super_evolve_cards", "can_super_evolve_with_skill_cards", "can_special_action_field_cards")
            for key in hand_keys:
                legal_actions[key] = tuple(value for value in legal_actions.get(key, ()) if value in hand_ids)
            for key in field_keys:
                legal_actions[key] = tuple(value for value in legal_actions.get(key, ()) if value in field_ids)
            raw_target_map = legal_actions.get("attack_targets", {})
            legal_actions["attack_targets"] = {
                int(attacker): tuple(target for target in targets if target in target_ids)
                for attacker, targets in raw_target_map.items()
                if int(attacker) in field_ids
            } if isinstance(raw_target_map, dict) else {}
            if isinstance(mine, dict) and isinstance(mine.get("field"), (list, tuple)):
                target_map = legal_actions.get("attack_targets", {})
                leader_ids = set(legal_actions.get("can_attack_leader_cards", ()))
                field_ids = set(legal_actions.get("can_attack_field_cards", ()))
                attacked_ids = set(legal_actions.get("attacked_cards", ()))
                for card in mine["field"]:
                    if not isinstance(card, dict) or not isinstance(card.get("unique_id"), int):
                        continue
                    uid = int(card["unique_id"])
                    card["attack_targets"] = target_map.get(uid, ()) if isinstance(target_map, dict) else ()
                    card["can_attack_leader"] = uid in leader_ids
                    card["can_attack_field"] = uid in field_ids
                    card["has_attacked"] = uid in attacked_ids
    return {
        "address": f"0x{address:016X}",
        "self_class_id": None,
        "opponent_class_id": None,
        "deck_format": None,
        "battle_mode": "puzzle",
        "root": public_root,
        "legal_actions": legal_actions,
        "events": [],
    }
