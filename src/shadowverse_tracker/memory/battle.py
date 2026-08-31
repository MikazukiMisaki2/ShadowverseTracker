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
    def read_u64(self, address: int) -> int: ...
    def read_u32(self, address: int) -> int: ...
    def read_i32(self, address: int) -> int: ...
    def read_c_string(self, address: int, maximum: int = 512) -> str: ...


MAX_PLAYERS = 2
MAX_HAND_CARDS = 16
MAX_FIELD_CARDS = 8
MAX_HISTORY_ITEMS = 512


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
    evolve_state: int
    has_guard: bool
    has_drain: bool
    has_cant_attack: bool


@dataclass(frozen=True)
class PlayerState:
    address: str
    deck_count: int
    life: int
    max_life: int
    pp: int
    max_pp: int
    turn: int
    evolve_points: int
    max_evolve_points: int
    super_evolve_points: int
    max_super_evolve_points: int
    cemetery_count: int
    is_first_side: bool
    result_code: int
    hand: tuple[HandCard, ...]
    field: tuple[FieldCard, ...]
    played_card_ids: tuple[tuple[int, int], ...]
    destroyed_card_ids: tuple[tuple[int, int], ...]


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
        base_card_id=reader.read_u32(address + 0x50),
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
        evolve_state=reader.read_i32(address + 0x40),
        has_drain=bool(reader.read_u32(address + 0x44) & 0xFF),
        has_guard=bool(reader.read_u32(address + 0x45) & 0xFF),
        has_cant_attack=bool(reader.read_u32(address + 0x55) & 0xFF),
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
    return PlayerState(
        address=f"0x{address:016X}",
        deck_count=reader.read_i32(address + 0x20),
        life=reader.read_i32(address + 0x24),
        max_life=reader.read_i32(address + 0x28),
        pp=reader.read_i32(address + 0x30),
        max_pp=reader.read_i32(address + 0x34),
        turn=reader.read_i32(address + 0x38),
        evolve_points=reader.read_i32(address + 0x3C),
        max_evolve_points=reader.read_i32(address + 0x40),
        super_evolve_points=reader.read_i32(address + 0x44),
        max_super_evolve_points=reader.read_i32(address + 0x48),
        cemetery_count=reader.read_i32(address + 0x58),
        is_first_side=bool(reader.read_u32(address + 0x98) & 0xFF),
        result_code=reader.read_i32(address + 0xB0),
        hand=hand,
        field=field,
        played_card_ids=played,
        destroyed_card_ids=destroyed,
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
        event.update(
            draw_num=reader.read_i32(address + 0x18),
            is_ally=bool(reader.read_u32(address + 0x1C) & 0xFF),
            change_card_flags=reader.read_i32(address + 0x28),
        )
    elif name == "BattleResponsePlayHide":
        # The object may contain a resolved card internally. Never expose it here.
        event.update(hidden=True, play_kind=reader.read_i32(address + 0x20))
    return event


def read_battle_model(
    reader: MemoryReader,
    address: int,
    *,
    reveal_opponent_hand: bool = False,
) -> dict[str, object]:
    if not address:
        raise ValueError("null BattleModel")
    root_property = reader.read_u64(address + 0x30)
    root_address = reader.read_u64(root_property + 0x20) if root_property else 0
    current_responses = reader.read_u64(address + 0x160)
    response_addresses = read_reference_collection(
        reader,
        current_responses,
        maximum=MAX_HISTORY_ITEMS,
    )
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
    return {
        "address": f"0x{address:016X}",
        "self_class_id": self_class_id,
        "opponent_class_id": opponent_class_id,
        "deck_format": deck_format,
        "root": (
            read_battle_root(reader, root_address).to_public_dict(
                reveal_opponent_hand=reveal_opponent_hand,
            )
            if root_address
            else None
        ),
        "events": [_read_battle_event(reader, event) for event in response_addresses if event],
    }
