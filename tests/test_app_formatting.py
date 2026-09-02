from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.app import TrackerApp
from shadowverse_tracker.card_catalog import get_card_name
from shadowverse_tracker.opponent_hand import OpponentKnownHand


class AppFormattingTests(unittest.TestCase):
    class _TextBuffer:
        def __init__(self) -> None:
            self.value = ""

        def configure(self, **_kwargs: object) -> None:
            pass

        def delete(self, *_args: object) -> None:
            self.value = ""

        def insert(self, _where: str, value: str, *_args: object) -> None:
            self.value += value

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

    def test_lethal_panel_shows_max_damage_resources_and_targets(self) -> None:
        app = object.__new__(TrackerApp)
        app.lethal_text = self._TextBuffer()
        app._lethal_status_message = ""
        state = SimpleNamespace(
            pp=4, max_pp=6, extra_pp=1, ep=2, sep=1, rally=7, play_count=3,
            cemetery=6, is_awakening=True, faith=10, faith_instances=[{}],
            active_crests=[1, 2], crest_instances=[], earth_sigil=2,
            skybound_art=1, super_skybound_art=2, destroyed_this_match=[{}],
            turn_number=3, evolve_turn=5, super_evolve_turn=7,
            hand=[SimpleNamespace(unique_id=11, name="Fire", card_id=1)],
            my_board=[], enemy_board=[], enemy_leader_uid=99,
        )
        view = SimpleNamespace(
            status="NO_LETHAL", trusted=True, usable=True, is_ally_turn=True,
            probability=0.0, max_damage=7,
            max_damage_sequence=("Fire deals 7",), sequence=(),
            state=state, available_modes={11: ("normal", "enhance")},
            attack_targets={11: (99,)}, legal_actions={"can_play_hand": [11]},
            trust_reasons=(), warnings=(),
        )
        app._lethal_bridge = SimpleNamespace(refresh=lambda _snapshot: view)
        app._render_lethal({})
        self.assertIn("当前回合最高理论伤害：7 点", app.lethal_text.value)
        self.assertIn("PP 4/6", app.lethal_text.value)
        self.assertIn("可用模式", app.lethal_text.value)
        self.assertIn("对手主战者 [99]", app.lethal_text.value)
        self.assertIn("超进化 T7（未解锁）", app.lethal_text.value)

    def test_field_format_shows_amulet_countdown_and_keywords(self) -> None:
        lines = TrackerApp._format_field([
            {
                "card_id": 90021210,
                "card_type": 2,
                "cost": 1,
                "countdown": 5,
                "attack": 0,
                "life": 0,
            },
            {
                "card_id": 10021110,
                "card_type": 1,
                "cost": 1,
                "attack": 1,
                "life": 1,
                "evolve_state": 0,
                "has_guard": True,
                "has_last_word": True,
                "has_killer": True,
                "has_cant_be_attacked": True,
                "has_cant_select": True,
                "buff": {"quick": True, "rush": True},
            },
        ])
        self.assertIn("护符", lines[0])
        self.assertIn("倒数=5", lines[0])
        self.assertNotIn("0/0", lines[0])
        for keyword in ("守护", "谢幕曲", "必杀", "无法被攻击", "无法被选中为目标", "突进", "疾驰"):
            self.assertIn(keyword, lines[1])


if __name__ == "__main__":
    unittest.main()
