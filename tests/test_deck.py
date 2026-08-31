from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.deck import read_deck_info, select_matching_deck


class FakeReader:
    def __init__(self) -> None:
        self.bytes: dict[int, int] = {}

    def write(self, address: int, fmt: str, *values: int) -> None:
        for index, value in enumerate(struct.pack(fmt, *values)):
            self.bytes[address + index] = value

    def write_bytes(self, address: int, value: bytes) -> None:
        for index, byte in enumerate(value):
            self.bytes[address + index] = byte

    def read(self, address: int, size: int) -> bytes:
        return bytes(self.bytes.get(address + index, 0) for index in range(size))

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def read_c_string(self, address: int, maximum: int = 512) -> str:
        data = self.read(address, maximum)
        return data.split(b"\0", 1)[0].decode()


class DeckDecoderTests(unittest.TestCase):
    def test_reads_card_counts_from_deck_info(self) -> None:
        memory = FakeReader()
        deck, name, cards_list, items = 0x1000, 0x2000, 0x3000, 0x4000
        card_a, card_b = 0x5000, 0x6000
        memory.write(deck + 0x10, "<i", 6)
        memory.write(deck + 0x18, "<Q", name)
        memory.write(deck + 0x20, "<i", 5)
        memory.write(deck + 0x40, "<Q", cards_list)
        memory.write(deck + 0x50, "<i", 0)
        text = "测试牌组".encode("utf-16-le")
        memory.write(name + 0x10, "<i", len("测试牌组"))
        memory.write_bytes(name + 0x14, text)
        memory.write(cards_list + 0x10, "<Q", items)
        memory.write(cards_list + 0x18, "<i", 2)
        memory.write(items + 0x18, "<Q", 2)
        memory.write(items + 0x20, "<QQ", card_a, card_b)
        memory.write(card_a + 0x10, "<Ii", 10000110, 1)
        memory.write(card_b + 0x10, "<Ii", 10000210, 39)

        with self.assertRaisesRegex(ValueError, "invalid copy count"):
            read_deck_info(memory, deck)

        memory.write(card_a + 0x14, "<i", 20)
        memory.write(card_b + 0x14, "<i", 20)
        with self.assertRaisesRegex(ValueError, "invalid copy count"):
            read_deck_info(memory, deck)

        # A legal 40-card deck uses 14 distinct entries here.
        addresses = tuple(0x5000 + index * 0x100 for index in range(14))
        memory.write(cards_list + 0x18, "<i", len(addresses))
        memory.write(items + 0x18, "<Q", len(addresses))
        memory.write(items + 0x20, "<" + "Q" * len(addresses), *addresses)
        for index, address in enumerate(addresses):
            memory.write(address + 0x10, "<Ii", 10000110 + index * 10, 3 if index < 13 else 1)
        result = read_deck_info(memory, deck)
        self.assertEqual(result.deck_name, "测试牌组")
        self.assertEqual(result.total_cards, 40)

    def test_selects_only_unambiguous_matching_deck(self) -> None:
        # Reuse frozen dataclass construction through a small local import.
        from shadowverse_tracker.memory.deck import DeckCard, DeckInfoSnapshot

        first = DeckInfoSnapshot("0x1", 1, "A", 1, 0, (DeckCard(10000110, 3), DeckCard(10000210, 37)))
        second = DeckInfoSnapshot("0x2", 2, "B", 1, 0, (DeckCard(10000310, 3), DeckCard(10000410, 37)))
        selected, score, certain = select_matching_deck((first, second), (10000111,))
        self.assertEqual(selected, first)
        self.assertGreater(score, 0)
        self.assertTrue(certain)


if __name__ == "__main__":
    unittest.main()
