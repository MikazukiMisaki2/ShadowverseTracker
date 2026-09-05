from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import sys
import tempfile
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.meta_deck_source import (
    META_REFRESH_VERSION,
    MetaDeckSourceError,
    fetch_wbarts_meta_decks,
    _meta_list_urls,
    parse_wbarts_deck_payload,
    refresh_wbarts_meta_cache_daily,
)
from shadowverse_tracker.opponent_deck_matcher import (
    META_ARCHETYPE_ORDER,
    MetaDeckProfile,
    OpponentDeckMatcher,
    canonicalize_meta_deck_labels,
    load_session_opponent_observations,
    load_meta_deck_profiles,
    meta_profile_from_saved_deck,
    meta_archetype_sort_key,
    meta_tier_label,
    save_meta_deck_profiles,
)


def profile(profile_id: str, name: str, cards: dict[int, int]) -> MetaDeckProfile:
    return MetaDeckProfile(profile_id, name, 5, cards)


class OpponentDeckMatcherTests(unittest.TestCase):
    def test_meta_archetype_sort_key_matches_wbarts_tier_order(self) -> None:
        names = ("疾驰教", "中速皇", "魔神梦", "进化妖")
        self.assertEqual(
            sorted(names, key=lambda value: meta_archetype_sort_key(value)),
            ["进化妖", "中速皇", "魔神梦", "疾驰教"],
        )
        self.assertEqual(META_ARCHETYPE_ORDER[0:2], ("中速梦", "跳费龙"))
        self.assertEqual(meta_tier_label("unranked"), "其他")
        self.assertEqual(meta_tier_label("其他", "财宝皇"), "T3")

    def test_requires_enough_public_evidence(self) -> None:
        matcher = OpponentDeckMatcher((profile("a", "构筑 A", {10000110: 3, 10000210: 3, 10000310: 3}),))
        self.assertIsNone(matcher.match([10000111, 10000111], 5))
        result = matcher.match([10000111, 10000111, 10000211, 10000311], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.label, "构筑 A")
        self.assertTrue(result.accepted)

    def test_accepted_match_uses_canonical_archetype_label(self) -> None:
        matcher = OpponentDeckMatcher((
            MetaDeckProfile(
                "a",
                "作者样本 A",
                5,
                {10000110: 3, 10000210: 3, 10000310: 3},
                archetype="中速梦",
            ),
        ))
        result = matcher.match([10000111, 10000211, 10000311], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.label, "中速梦")
        self.assertEqual(result.profile.tier, "T1")

    def test_local_archetype_id_uses_reference_chinese_label(self) -> None:
        reference = MetaDeckProfile(
            "reference",
            "中速梦·构筑 A",
            5,
            {10000110: 3, 10000210: 3, 10000310: 3},
            archetype="中速梦",
        )
        local = MetaDeckProfile(
            "local-build",
            "local:99",
            5,
            reference.cards,
        )
        labelled = canonicalize_meta_deck_labels((local,), (reference,))[0]
        self.assertEqual(labelled.display_name, "中速梦")

    def test_known_wbarts_local_id_is_translated_without_card_reference(self) -> None:
        profile = MetaDeckProfile("local-build", "local:13", 2, {10000110: 40})
        self.assertEqual(profile.display_name, "财宝皇")

    def test_saved_deck_is_available_as_local_meta_profile(self) -> None:
        deck = SimpleNamespace(
            key="private-1",
            name="我的精灵",
            class_id=1,
            format_version=1,
            cards=tuple(SimpleNamespace(card_id=10001000 + index * 100, count=1) for index in range(40)),
        )
        profile = meta_profile_from_saved_deck(deck)
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.profile_id, "local-deck:private-1")
        self.assertEqual(profile.display_name, "我的精灵")
        self.assertEqual(profile.format, "rotation")
        self.assertEqual(profile.total_cards, 40)

    def test_meta_fetch_requests_three_recommendations_per_class(self) -> None:
        calls: list[int | None] = []

        def fake_list(*, timeout: float, class_id: int | None = None):
            calls.append(class_id)
            assert class_id is not None
            cards = {str(10000000 + class_id * 100000 + offset * 100): 1 for offset in range(40)}
            return tuple(
                {
                    "id": class_id * 100 + index,
                    "name": f"class-{class_id}-{index}",
                    "class_id": class_id,
                    "format": "rotation",
                    "archetype": f"type-{class_id}",
                    "cards": cards,
                }
                for index in range(5)
            )

        with patch("shadowverse_tracker.meta_deck_source._fetch_meta_deck_list", side_effect=fake_list):
            profiles = fetch_wbarts_meta_decks(
                timeout=0.1,
                max_profiles=6,
                recommended_per_class=3,
                class_ids=(1, 2),
            )
        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(profiles), 6)
        self.assertEqual(
            {class_id: sum(1 for profile in profiles if profile.class_id == class_id) for class_id in (1, 2)},
            {1: 3, 2: 3},
        )

    def test_meta_list_url_contains_site_class_filter_and_limit(self) -> None:
        urls = _meta_list_urls(4)
        self.assertTrue(urls)
        self.assertTrue(all("class_id=4" in url and "limit=3" in url for url in urls))

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

    def test_shared_builds_fall_back_to_common_archetype(self) -> None:
        matcher = OpponentDeckMatcher((
            MetaDeckProfile("a", "中速梦·构筑 A", 5, {10000110: 3, 10000210: 3, 10000310: 3}, archetype="中速梦"),
            MetaDeckProfile("b", "中速梦·构筑 B", 5, {10000110: 3, 10000210: 3, 10000310: 3}, archetype="中速梦"),
            MetaDeckProfile("c", "快攻梦", 5, {10000110: 3, 10000410: 3, 10000510: 3}, archetype="快攻梦"),
        ))
        result = matcher.match([10000111, 10000211, 10000311], 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.label, "中速梦")

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
                "archetype": "中速梦",
                "tier": 1,
                "cards": {str(10000000 + index * 100): 1 for index in range(1, 41)},
            }
        }
        parsed = parse_wbarts_deck_payload(payload)
        self.assertEqual(parsed.profile_id, "wbarts-77")
        self.assertEqual(parsed.total_cards, 40)
        self.assertEqual(parsed.tier, "T1")
        with self.assertRaises(MetaDeckSourceError):
            parse_wbarts_deck_payload({"deck": {"id": 77, "class_id": 5, "cards": {}}})

    def test_list_card_entries_preserve_counts(self) -> None:
        parsed = parse_wbarts_deck_payload({
            "deck": {
                "id": 78,
                "name": "列表格式",
                "class_id": 5,
                "cards": [
                    {"card_id": 10000110, "count": 3},
                    {"baseCardId": 10000210, "quantity": 2},
                ] + [
                    {"card_id": 10001010 + index * 100, "count": 1}
                    for index in range(35)
                ],
            }
        })
        self.assertEqual(parsed.cards[10000110], 3)
        self.assertEqual(parsed.cards[10000210], 2)

    def test_meta_refresh_is_once_per_day(self) -> None:
        original = profile("old", "旧构筑", {10000110: 3})
        replacement = profile("new", "新构筑", {10000210: 3})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_decks.json"
            save_meta_deck_profiles(
                (original,),
                path,
                checked_at="2026-09-05T00:05:00+00:00",
                refresh_version=META_REFRESH_VERSION,
            )
            with patch("shadowverse_tracker.meta_deck_source.fetch_wbarts_meta_decks") as fetch:
                profiles, status = refresh_wbarts_meta_cache_daily(
                    path=path,
                    now=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
                )
            fetch.assert_not_called()
            self.assertEqual(status, "skipped")
            self.assertEqual(profiles[0].profile_id, "old")

            with patch(
                "shadowverse_tracker.meta_deck_source.fetch_wbarts_meta_decks",
                return_value=(replacement,),
            ) as fetch:
                profiles, status = refresh_wbarts_meta_cache_daily(
                    path=path,
                    now=datetime(2026, 9, 6, 12, tzinfo=timezone.utc),
                )
            fetch.assert_called_once()
            self.assertEqual(status, "updated")
            self.assertIn("new", {item.profile_id for item in profiles})

    def test_meta_refresh_rechecks_cache_from_previous_strategy(self) -> None:
        original = profile("old", "旧构筑", {10000110: 3})
        replacement = profile("new", "新构筑", {10000210: 3})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_decks.json"
            save_meta_deck_profiles(
                (original,),
                path,
                checked_at="2026-09-05T00:05:00+00:00",
                refresh_version="",
            )
            with patch(
                "shadowverse_tracker.meta_deck_source.fetch_wbarts_meta_decks",
                return_value=(replacement,),
            ) as fetch:
                profiles, status = refresh_wbarts_meta_cache_daily(
                    path=path,
                    now=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
                )
            fetch.assert_called_once()
            self.assertEqual(status, "updated")
            self.assertEqual(profiles[0].profile_id, "new")

    def test_session_observation_uses_terminal_match_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_session.jsonl"
            snapshot = {
                "address": "0xabc",
                "opponent_class_id": 5,
                "root": {
                    "players": [
                        {
                            "result_code": 101,
                            "turn": 6,
                            "life": 20,
                            "deck_count": 30,
                            "cemetery_count": 4,
                            "played_card_ids": [[10000110, 0]],
                            "destroyed_card_ids": [],
                        },
                        {
                            "life": 0,
                            "played_card_ids": [[10000211, 0], [10000311, 0]],
                        },
                    ],
                },
            }
            path.write_text(json.dumps({"model": "0xabc", "snapshot": snapshot}) + "\n", encoding="utf-8")
            observations = load_session_opponent_observations(path)
        self.assertEqual(
            observations["terminal:0xabc:101:6:20:0:30:4:1:0"],
            (10000210, 10000310),
        )

    def test_session_observation_repairs_legacy_reversed_terminal_players(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app_session.jsonl"
            snapshot = {
                "address": "0xdef",
                # Older snapshots have no player unique_id.  The selected
                # Nightmare deck plus the 1/5 class pair still identifies the
                # reversed terminal frame conservatively.
                "self_class_id": 1,
                "opponent_class_id": 5,
                "deck": {"class_id": 5},
                "root": {
                    "players": [
                        {
                            "result_code": 106,
                            "turn": 10,
                            "life": 7,
                            "deck_count": 29,
                            "cemetery_count": 4,
                            "played_card_ids": [[10000211, 0]],
                            "destroyed_card_ids": [],
                        },
                        {
                            "result_code": 105,
                            "turn": 10,
                            "life": 14,
                            "deck_count": 28,
                            "cemetery_count": 5,
                            "played_card_ids": [[10000311, 0], [10000411, 0]],
                            "destroyed_card_ids": [],
                        },
                    ],
                },
            }
            path.write_text(json.dumps({"model": "0xdef", "snapshot": snapshot}) + "\n", encoding="utf-8")
            observations = load_session_opponent_observations(path)
        self.assertEqual(
            observations["terminal:0xdef:105:10:14:7:28:5:2:0"],
            (10000210,),
        )


if __name__ == "__main__":
    unittest.main()
