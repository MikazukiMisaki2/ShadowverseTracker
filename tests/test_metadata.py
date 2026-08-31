from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.metadata import IL2CPP_SANITY, parse_obfuscated_header, repair_header


class MetadataHeaderTests(unittest.TestCase):
    def test_parses_range_table_and_estimates_file_size(self) -> None:
        data = bytearray(0x100)
        struct.pack_into("<IIII", data, 0, 0x12345678, 0x9ABCDEF0, 0x20, 0x30)
        struct.pack_into("<II", data, 0x10, 0x50, 0x10)
        struct.pack_into("<II", data, 0x18, 0, 0)

        header = parse_obfuscated_header(bytes(data))

        self.assertEqual(header.header_size, 0x20)
        self.assertEqual(header.estimated_file_size, 0x60)
        self.assertEqual(header.encoded_sanity, 0x12345678)

    def test_repairs_only_first_eight_bytes(self) -> None:
        original = bytes(range(32))
        repaired = repair_header(original, 31)

        self.assertEqual(struct.unpack_from("<II", repaired), (IL2CPP_SANITY, 31))
        self.assertEqual(repaired[8:], original[8:])

    def test_rejects_implausible_first_offset(self) -> None:
        with self.assertRaises(ValueError):
            parse_obfuscated_header(struct.pack("<IIII", 1, 2, 0x21, 3))


if __name__ == "__main__":
    unittest.main()
