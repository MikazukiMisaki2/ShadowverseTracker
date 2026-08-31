from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_battle_root, read_battle_view_server_data


class FakeReader:
    def __init__(self) -> None:
        self.bytes: dict[int, int] = {}

    def write(self, address: int, fmt: str, *values: int) -> None:
        for index, value in enumerate(struct.pack(fmt, *values)):
            self.bytes[address + index] = value

    def write_bytes(self, address: int, value: bytes) -> None:
        for index, item in enumerate(value):
            self.bytes[address + index] = item

    def write_ref_array(self, address: int, values: tuple[int, ...]) -> None:
        self.write(address + 0x18, "<Q", len(values))
        if values:
            self.write(address + 0x20, "<" + "Q" * len(values), *values)

    def write_i32_array(self, address: int, values: tuple[int, ...]) -> None:
        self.write(address + 0x18, "<Q", len(values))
        if values:
            self.write(address + 0x20, "<" + "i" * len(values), *values)

    def write_managed_string(self, address: int, value: str) -> None:
        encoded = value.encode("utf-16-le")
        self.write(address + 0x10, "<i", len(value))
        self.write_bytes(address + 0x14, encoded)

    def write_string_i32_dictionary(
        self,
        address: int,
        entries: int,
        key_address: int,
        key: str,
        value: int,
    ) -> None:
        self.write(address + 0x18, "<Q", entries)
        self.write(address + 0x20, "<i", 1)
        self.write(entries + 0x18, "<Q", 1)
        self.write(entries + 0x20, "<iiQi", 1, -1, key_address, value)
        self.write_managed_string(key_address, key)

    def write_i32_hash_set(
        self,
        address: int,
        slots: int,
        values: tuple[int, ...],
    ) -> None:
        self.write(address + 0x18, "<Q", slots)
        self.write(address + 0x20, "<ii", len(values), len(values))
        self.write(slots + 0x18, "<Q", max(len(values), 1))
        for index, value in enumerate(values):
            self.write(slots + 0x20 + index * 0x0C, "<iii", value, -1, value)

    def write_i32_hash_set_dictionary(
        self,
        address: int,
        entries: int,
        items: tuple[tuple[int, int], ...],
    ) -> None:
        self.write(address + 0x18, "<Q", entries)
        self.write(address + 0x20, "<i", len(items))
        self.write(entries + 0x18, "<Q", max(len(items), 1))
        for index, (key, value_address) in enumerate(items):
            self.write(
                entries + 0x20 + index * 0x18,
                "<iiiIQ",
                key,
                -1,
                key,
                0,
                value_address,
            )

    def read(self, address: int, size: int) -> bytes:
        return bytes(self.bytes.get(address + index, 0) for index in range(size))

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]


class BattleDecoderTests(unittest.TestCase):
    def test_decodes_root_players_and_list_backed_hand(self) -> None:
        memory = FakeReader()
        root, players_array = 0x1000, 0x2000
        ally, opponent = 0x3000, 0x4000
        hand_list, hand_items, card = 0x5000, 0x6000, 0x7000

        memory.write(root + 0x10, "<Q", players_array)
        memory.write(root + 0x18, "<I", 1)
        memory.write(players_array + 0x18, "<Q", 2)
        memory.write(players_array + 0x20, "<QQ", ally, opponent)

        memory.write(ally + 0x10, "<Q", hand_list)
        memory.write(ally + 0x20, "<iii", 36, 20, 20)
        memory.write(ally + 0x30, "<iii", 1, 1, 1)
        memory.write(ally + 0x58, "<i", 0)
        memory.write(ally + 0x98, "<I", 1)
        memory.write(opponent + 0x20, "<iii", 36, 20, 20)

        memory.write(hand_list + 0x10, "<Q", hand_items)
        memory.write(hand_list + 0x18, "<i", 1)
        memory.write(hand_items + 0x18, "<Q", 1)
        memory.write(hand_items + 0x20, "<Q", card)
        memory.write(card + 0x10, "<IIiiii", 123, 101001, 2, 3, 4, 1)
        memory.write(card + 0x50, "<I", 101001)

        result = read_battle_root(memory, root)

        self.assertTrue(result.is_ally_turn)
        self.assertEqual(result.players[0].deck_count, 36)
        self.assertEqual(result.players[0].hand[0].card_id, 101001)
        self.assertEqual(result.players[0].hand[0].unique_id, 123)
        self.assertEqual(result.players[1].hand, ())
        self.assertEqual(result.to_public_dict()["players"][0]["hand"][0]["card_id"], 101001)

    def test_public_dict_can_reveal_local_practice_hand(self) -> None:
        memory = FakeReader()
        root, players_array = 0x1000, 0x2000
        ally, opponent = 0x3000, 0x4000
        hand_list, hand_items, card = 0x5000, 0x6000, 0x7000
        memory.write(root + 0x10, "<Q", players_array)
        memory.write(players_array + 0x18, "<Q", 2)
        memory.write(players_array + 0x20, "<QQ", ally, opponent)
        memory.write(ally + 0x10, "<Q", hand_list)
        memory.write(opponent + 0x10, "<Q", hand_list)
        memory.write(hand_list + 0x10, "<Q", hand_items)
        memory.write(hand_list + 0x18, "<i", 1)
        memory.write(hand_items + 0x18, "<Q", 1)
        memory.write(hand_items + 0x20, "<Q", card)
        memory.write(card + 0x10, "<IIiiii", 123, 10052110, 1, 1, 1, 1)
        memory.write(card + 0x50, "<I", 10052110)
        result = read_battle_root(memory, root)
        self.assertEqual(
            result.to_public_dict(reveal_opponent_hand=True)["players"][1]["hand"][0]["card_id"],
            10052110,
        )

    def test_decodes_lethal_search_state_extensions(self) -> None:
        memory = FakeReader()
        root, players_array = 0x1000, 0x2000
        ally, opponent = 0x3000, 0x4000
        hand_array, hand = 0x5000, 0x6000
        field_array, field = 0x7000, 0x8000
        attack_targets = 0x9000
        enhance, accelerate, crystal, tribes = 0xA000, 0xA100, 0xA200, 0xA300
        fusion_outer, fusion_inner = 0xA400, 0xA500
        hand_buff, buff_sources, buff_source, add_tribes = 0xB000, 0xB100, 0xB200, 0xB300
        hand_info, hand_entries, hand_key = 0xB400, 0xB500, 0xB600
        player_buff, player_sources = 0xC000, 0xC100
        crest_array, crest, crest_buff = 0xD000, 0xD100, 0xD200
        crest_info, crest_entries, crest_key = 0xD300, 0xD400, 0xD500
        random_indexes = 0xD600

        memory.write(root + 0x10, "<Q", players_array)
        memory.write(root + 0x18, "<B", 1)
        memory.write_ref_array(players_array, (ally, opponent))
        memory.write(ally + 0x10, "<Q", hand_array)
        memory.write(ally + 0x18, "<Q", field_array)
        memory.write_ref_array(hand_array, (hand,))
        memory.write_ref_array(field_array, (field,))

        memory.write(hand + 0x10, "<IIiiii", 101, 10999991, 4, 6, 7, 1)
        memory.write(hand + 0x28, "<Q", enhance)
        memory.write(hand + 0x30, "<B", 1)
        memory.write(hand + 0x34, "<i", 5)
        memory.write(hand + 0x38, "<Q", accelerate)
        memory.write(hand + 0x40, "<Q", crystal)
        memory.write(hand + 0x48, "<Q", fusion_outer)
        memory.write(hand + 0x50, "<I", 10999990)
        memory.write(hand + 0x58, "<Q", tribes)
        memory.write(hand + 0x60, "<Q", hand_buff)
        memory.write(hand + 0x68, "<i", 12)
        memory.write(hand + 0x70, "<Q", hand_info)
        memory.write(hand + 0x78, "<i", 5)
        memory.write(hand + 0x7C, "<B", 1)
        memory.write(hand + 0x80, "<i", 3)
        memory.write(hand + 0x84, "<B", 1)
        memory.write(hand + 0x90, "<i", 2)
        memory.write(hand + 0x94, "<B", 1)
        memory.write(hand + 0x98, "<i", 4)
        memory.write_i32_array(enhance, (7, 9))
        memory.write_i32_array(accelerate, (1,))
        memory.write_i32_array(crystal, (2,))
        memory.write_ref_array(fusion_outer, (fusion_inner,))
        memory.write_i32_array(fusion_inner, (1, 2))
        memory.write_i32_array(tribes, (5, 23))
        memory.write_string_i32_dictionary(hand_info, hand_entries, hand_key, "boost", 3)

        memory.write(hand_buff + 0x10, "<Q", buff_sources)
        memory.write(hand_buff + 0x18, "<iii", -2, 3, 4)
        memory.write(hand_buff + 0x24, "<BBB", 1, 1, 1)
        memory.write(hand_buff + 0x28, "<i", 2)
        memory.write(hand_buff + 0x2C, "<B", 1)
        memory.write(hand_buff + 0x30, "<Q", add_tribes)
        memory.write_ref_array(buff_sources, (buff_source,))
        memory.write(buff_source + 0x10, "<iiBB", 10777770, 8, 1, 1)
        memory.write(buff_source + 0x1C, "<i", 2)
        memory.write_i32_array(add_tribes, (14,))

        memory.write(field + 0x10, "<IIiiiii", 201, 10888881, 3, 8, 9, 10, 1)
        memory.write(field + 0x30, "<Q", attack_targets)
        memory.write(field + 0x38, "<ii", 2, 4)
        memory.write(field + 0x40, "<i", 2)
        memory.write(field + 0x44, "<BBBBBBBBB", 1, 1, 1, 1, 1, 1, 1, 1, 1)
        memory.write(field + 0x50, "<i", 6)
        memory.write(field + 0x54, "<BBBBBBB", 1, 0, 1, 1, 1, 1, 1)
        memory.write(field + 0x60, "<Q", hand_buff)
        memory.write(field + 0x80, "<i", 8)
        memory.write(field + 0x84, "<BB", 1, 1)
        memory.write(field + 0x90, "<iii", 11, 12, 2)
        memory.write(field + 0x9C, "<BB", 1, 1)
        memory.write(field + 0xA0, "<i", 13)
        memory.write_i32_array(attack_targets, (999, 301))

        memory.write(ally + 0x20, "<iiiIiii", 25, 16, 22, 901, 5, 8, 8)
        memory.write(ally + 0x3C, "<iiiiiii", 1, 2, 1, 2, 1, 0, 2)
        memory.write(ally + 0x58, "<iB", 12, 1)
        memory.write(ally + 0x60, "<iiii", 14, 4, 6, 9)
        memory.write(ally + 0x94, "<i", 18)
        memory.write(ally + 0x98, "<B", 1)
        memory.write(ally + 0xA0, "<Q", player_buff)
        memory.write(ally + 0xA8, "<Q", crest_array)
        memory.write(ally + 0xB4, "<iBB", 2, 1, 1)
        memory.write(ally + 0xBC, "<iB", 3, 1)
        memory.write(ally + 0xC4, "<i", 2)
        memory.write(ally + 0xC8, "<iB", 1, 1)
        memory.write(ally + 0xD0, "<iB", 4, 1)

        memory.write(player_buff + 0x10, "<Q", player_sources)
        memory.write(player_buff + 0x18, "<iB", 25, 1)
        memory.write(player_buff + 0x20, "<ii", 2, 1)
        memory.write_ref_array(player_sources, (buff_source,))

        memory.write_ref_array(crest_array, (crest,))
        memory.write(crest + 0x10, "<iiiiQ", 10614120, 3, 17, 6, crest_buff)
        memory.write(crest + 0x28, "<Q", crest_info)
        memory.write(crest + 0x30, "<iI", 4, 501)
        memory.write(crest + 0x40, "<Q", random_indexes)
        memory.write(crest + 0x48, "<iB", 2, 1)
        memory.write(crest + 0x50, "<i", 5)
        memory.write(crest_buff + 0x10, "<Q", buff_sources)
        memory.write_string_i32_dictionary(crest_info, crest_entries, crest_key, "faith", 17)
        memory.write_i32_array(random_indexes, (0, 2))

        result = read_battle_root(memory, root)
        player = result.players[0]

        self.assertEqual(player.unique_id, 901)
        self.assertEqual(player.extra_pp, 1)
        self.assertEqual(player.extra_pp_state, 2)
        self.assertEqual(player.rally, 14)
        self.assertEqual(player.play_count, 3)
        self.assertTrue(player.is_awakening)
        self.assertEqual(player.buff.damage_cut, 2)
        self.assertEqual(player.buff.increase_damage, 1)
        self.assertEqual(player.crests[0].faith_value, 17)
        self.assertEqual(player.crests[0].supplement_info, {"faith": 17})
        self.assertEqual(player.hand[0].enhance_costs, (7, 9))
        self.assertEqual(player.hand[0].fusion_list, ((1, 2),))
        self.assertEqual(player.hand[0].spell_boost_count, 3)
        self.assertTrue(player.hand[0].buff.quick)
        self.assertEqual(player.hand[0].buff.sources[0].card_id, 10777770)
        self.assertEqual(player.hand[0].supplement_info, {"boost": 3})
        self.assertEqual(player.field[0].attack_targets, (999, 301))
        self.assertTrue(player.field[0].has_cant_destroy)
        self.assertEqual(player.field[0].attack_limit, 2)

        public = result.to_public_dict()
        self.assertEqual(public["players"][0]["rally"], 14)
        self.assertEqual(public["players"][0]["field"][0]["attack_targets"], (999, 301))

    def test_decodes_client_legal_actions_and_attack_target_map(self) -> None:
        memory = FakeReader()
        server_data = 0x1000
        can_play, can_play_slots = 0x2000, 0x2100
        can_face, can_face_slots = 0x2200, 0x2300
        can_field, can_field_slots = 0x2400, 0x2500
        target_map, target_entries = 0x2600, 0x2700
        target_set, target_slots = 0x2800, 0x2900

        memory.write(server_data + 0x18, "<Q", can_play)
        memory.write(server_data + 0x40, "<Q", can_face)
        memory.write(server_data + 0x48, "<Q", can_field)
        memory.write(server_data + 0x70, "<Q", target_map)
        memory.write_i32_hash_set(can_play, can_play_slots, (84, 85, 22, 25))
        memory.write_i32_hash_set(can_face, can_face_slots, (5, 27))
        memory.write_i32_hash_set(can_field, can_field_slots, (5, 27))
        memory.write_i32_hash_set(target_set, target_slots, (59,))
        memory.write_i32_hash_set_dictionary(target_map, target_entries, ((5, target_set),))

        result = read_battle_view_server_data(memory, server_data)

        self.assertEqual(result.can_play_cards, (84, 85, 22, 25))
        self.assertEqual(result.can_attack_leader_cards, (5, 27))
        self.assertEqual(result.can_attack_field_cards, (5, 27))
        self.assertEqual(result.attack_targets, {5: (59,)})


if __name__ == "__main__":
    unittest.main()
