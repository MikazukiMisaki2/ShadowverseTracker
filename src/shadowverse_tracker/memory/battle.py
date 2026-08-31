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
        )
    elif name == "BattleResponseDrawHide":
        event.update(
            draw_num=reader.read_i32(address + 0x18),
            add_num=reader.read_i32(address + 0x1C),
            is_turn_start_draw=bool(reader.read_u32(address + 0x20) & 0xFF),
        )
    elif name == "BattleResponsePlayOpen":
        event.update(
            is_ally=bool(reader.read_u32(address + 0x18) & 0xFF),
            unique_id=reader.read_u32(address + 0x1C),
            card_id=reader.read_i32(address + 0x20),
            card_style_id=reader.read_i32(address + 0x24),
            after_play_card_id=reader.read_i32(address + 0x28),
            play_kind=reader.read_i32(address + 0x30),
        )
    elif name == "BattleResponseMulligan":
        # ``change_card_flags`` is a bit mask (one bit for each of the four
        # opening cards), not a numeric card count.
        event.update(
            draw_num=reader.read_i32(address + 0x18),
            is_ally=bool(reader.read_u32(address + 0x1C) & 0xFF),
            change_card_flags=reader.read_u32(address + 0x28),
        )
    elif name == "BattleResponsePlayHide":
        # The object may contain a resolved card internally. Never expose it here.
        event.update(hidden=True, play_kind=reader.read_i32(address + 0x20))
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
        except (OSError, ValueError):
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
    events = [_read_battle_event(reader, event) for event in response_addresses if event]
    mulligan_selection = _read_mulligan_selection_response(reader, address, battle_root)
    if mulligan_selection is not None:
        events.append(mulligan_selection)
    public_root = (
        battle_root.to_public_dict(reveal_opponent_hand=reveal_opponent_hand)
        if battle_root
        else None
    )
    legal_actions = (
        read_battle_view_server_data(reader, battle_view_server_data_address)
        if battle_view_server_data_address
        else None
    )
    legal_actions_dict = asdict(legal_actions) if legal_actions is not None else None
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
