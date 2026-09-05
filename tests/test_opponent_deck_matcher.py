from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.meta_deck_source import MetaDeckSourceError, parse_wbarts_deck_payload
from shadowverse_tracker.opponent_deck_matcher import (
    MetaDeckProfile,
    OpponentDeckMatcher,
    load_meta_deck_profiles,
    save_meta_deck_profiles,
)


def profile(profile_id: str, name: str, cards: dict[int, int]) -> MetaDeckProfile:
    return MetaDeckProfile(profile_id, name, 5, cards)


class OpponentDeckMatcherTests(unittest.TestCase):
    def test_requires_enough_public_evidence(self) -> None:
        matcher = OpponentDeckMatcher((profile("a", "构筑 A", {10000110: 3, 10000210: 3, 10000310: 3}),))
        self.assertIsNone(matcher.match([10000111, 10000111], 5))
        result = matcher.match([10000111, 10000111, 10000211, 10000311], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.label, "构筑 A")
        self.assertTrue(result.accepted)

    def test_margin_keeps_shared_opening_cards_unknown(self) -> None:
        matcher = OpponentDeckMatcher((
            profile("a", "构筑 A", {10000110: 3, 10000210: 3, 10000310: 3}),
            profile("b", "构筑 B", {10000110: 3, 10000210: 3, 10000410: 3}),
        ))
        self.assertIsNone(matcher.match([10000111, 10000211, 10000111], 5))
        result = matcher.match([10000111, 10000211, 10000311], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.label, "构筑 A")
        self.assertGreaterEqual(result.margin, 0.08)

    def test_class_filter_and_canonical_style_ids(self) -> None:
        matcher = OpponentDeckMatcher((
            profile("nightmare", "梦魇构筑", {10052110: 3, 10452130: 3, 10552110: 3}),
            MetaDeckProfile("dragon", "龙族构筑", 4, {10042110: 3, 10442130: 3}),
        ))
        result = matcher.match([10052111, 10452131, 10452131, 10552111], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.profile.profile_id, "nightmare")
        self.assertEqual(matcher.rank([10052111, 10452131], 4)[0].profile.profile_id, "dragon")

    def test_cache_round_trip(self) -> None:
        profiles = (profile("a", "构筑 A", {10000110: 3, 10000210: 3}),)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_decks.json"
            save_meta_deck_profiles(profiles, path)
            loaded = load_meta_deck_profiles(path)
        self.assertEqual(loaded[0].name, "构筑 A")
        self.assertEqual(loaded[0].total_cards, 6)

    def test_wbarts_payload_validation(self) -> None:
        payload = {
            "deck": {
                "id": 77,
                "name": "中速梦",
                "class_id": 5,
                "format": "rotation",
                "cards": {str(10000000 + index * 100): 1 for index in range(1, 41)},
            }
        }
        parsed = parse_wbarts_deck_payload(payload)
        self.assertEqual(parsed.profile_id, "wbarts-77")
        self.assertEqual(parsed.total_cards, 40)
        with self.assertRaises(MetaDeckSourceError):
            parse_wbarts_deck_payload({"deck": {"id": 77, "class_id": 5, "cards": {}}})


if __name__ == "__main__":
    unittest.main()
