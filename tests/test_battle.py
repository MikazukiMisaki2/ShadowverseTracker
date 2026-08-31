from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.battle import read_battle_root


class FakeReader:
    def __init__(self) -> None:
        self.bytes: dict[int, int] = {}

    def write(self, address: int, fmt: str, *values: int) -> None:
        for index, value in enumerate(struct.pack(fmt, *values)):
            self.bytes[address + index] = value

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


if __name__ == "__main__":
    unittest.main()
