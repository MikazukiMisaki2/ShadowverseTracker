from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.official_deck import (
    OfficialDeckError,
    SHORTCODE_ALPHABET,
    parse_official_deck,
)


def encode_shortcode(card_id: int) -> str:
    return "".join(
        SHORTCODE_ALPHABET[(card_id >> shift) & 0x3F]
        for shift in (18, 12, 6, 0)
    )


def test_hash() -> str:
    cards = []
    for index in range(13):
        cards.extend([10_000_110 + index * 10] * 3)
    cards.append(10_000_990)
    return "1.5." + ".".join(encode_shortcode(card_id) for card_id in cards)


class OfficialDeckTests(unittest.TestCase):
    def test_parses_official_url_into_counted_cards(self) -> None:
        value = parse_official_deck(
            "https://shadowverse-wb.com/web/Deck/detail?hash=" + test_hash()
        )
        self.assertEqual(value.class_id, 5)
        self.assertEqual(value.total_cards, 40)
        self.assertEqual(len(value.cards), 14)
        self.assertEqual(value.cards[0].count, 3)

    def test_rejects_non_official_url(self) -> None:
        with self.assertRaisesRegex(OfficialDeckError, "只支持"):
            parse_official_deck("https://example.com/deck/detail?hash=" + test_hash())

    def test_rejects_short_deck(self) -> None:
        with self.assertRaisesRegex(OfficialDeckError, "40"):
            parse_official_deck("1.5." + encode_shortcode(10_000_110))


if __name__ == "__main__":
    unittest.main()
