from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.app import TrackerApp
from shadowverse_tracker.card_catalog import get_card_name
from shadowverse_tracker.opponent_hand import OpponentKnownHand


class AppFormattingTests(unittest.TestCase):
    def test_recent_history_contains_both_sides(self) -> None:
        value = TrackerApp._format_recent_history(
            {"played_card_ids": [(10953110, 0)]},
            {"played_card_ids": [(10851120, 0)]},
        )
        self.assertIn(get_card_name(10953110), value)
        self.assertIn(get_card_name(10851120), value)
        self.assertEqual(value.count("\n\n"), 1)

    def test_recent_history_includes_public_play_response(self) -> None:
        value = TrackerApp._format_recent_history(
            {"played_card_ids": [], "_event_played_cards": [{"turn": 1, "card_id": 10953110}]},
            {"played_card_ids": [], "_event_played_cards": [{"turn": 1, "card_id": 10851120}]},
        )
        self.assertIn(f"T1：{get_card_name(10953110)}", value)
        self.assertIn(f"T1：{get_card_name(10851120)}", value)

    def test_opponent_hand_drops_zero_value_placeholders(self) -> None:
        app = object.__new__(TrackerApp)
        app._opponent_known_hand = OpponentKnownHand()
        value = app._format_opponent_hand(
            {
                "hand": [
                    {"card_id": 0, "base_card_id": 0, "cost": 0},
                    {"card_id": 0, "base_card_id": 0, "cost": 0},
                ]
            }
        )
        self.assertEqual(value, ["（暂无已知明牌）"])

    def test_opponent_hand_keeps_resolved_cards(self) -> None:
        app = object.__new__(TrackerApp)
        app._opponent_known_hand = OpponentKnownHand()
        value = app._format_opponent_hand(
            {"hand": [{"card_id": 10052110, "base_card_id": 10052110, "cost": 1}]}
        )
        self.assertEqual(value, [f"1费 {get_card_name(10052110)}"])

    def test_terminal_result_is_detected_for_immediate_display_clear(self) -> None:
        self.assertTrue(TrackerApp._has_terminal_result(
            {"result_code": 101, "life": 12}, {"life": 7},
        ))
        self.assertTrue(TrackerApp._has_terminal_result(
            {"result_code": 106, "life": 12}, {"life": 7},
        ))
        self.assertFalse(TrackerApp._has_terminal_result(
            {"result_code": 0, "life": 12}, {"life": 7},
        ))

    def test_next_turn_key_projection_consumes_one_deck_card(self) -> None:
        self.assertEqual(TrackerApp._project_opponent_next_draw(29, 6), (28, 7))
        self.assertIsNone(TrackerApp._project_opponent_next_draw(0, 6))


if __name__ == "__main__":
    unittest.main()
