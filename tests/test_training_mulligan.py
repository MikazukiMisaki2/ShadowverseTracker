from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.tracker_service import TrackerConfig, TrackerService


class TrainingMulliganTests(unittest.TestCase):
    @staticmethod
    def card(uid: int, card_id: int) -> dict[str, int]:
        return {"unique_id": uid, "base_card_id": card_id}

    def test_two_same_sequence_mulligan_events_keep_both_sides(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        players = [
            {"hand": [{"base_card_id": 10052110}], "turn": 1},
            {"hand": [], "turn": 1},
        ]
        # 0b0011 means two selected opening cards.  Both game responses can
        # carry sequence 0, so they must not be de-duplicated by sequence alone.
        snapshot = {
            "events": [
                {"address": "0x1", "type": "BattleResponseMulligan", "sequence": 0, "is_ally": False, "change_card_flags": 3},
                {"address": "0x2", "type": "BattleResponseMulligan", "sequence": 0, "is_ally": True, "change_card_flags": 3},
            ]
        }
        service._update_training_observation(snapshot, players)
        self.assertEqual(players[1]["mulligan_summary"]["replaced_count"], 2)
        self.assertEqual(snapshot["training_observation"]["mulligan"]["opponent_replaced_count"], 2)
        self.assertEqual(len(snapshot["training_observation"]["mulligan"]["events"]), 2)

    def test_persistent_selection_response_uses_explicit_pair_count(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        players = [{"hand": [], "turn": 1}, {"hand": [], "turn": 1}]
        snapshot = {
            "events": [{
                "address": "0x55",
                "type": "BattleModelMulliganSelection",
                "is_ally": False,
                "replaced_count": 4,
                "selection_fingerprint": (11, 12, 13, 14, 15, 16, 17, 18),
            }]
        }
        service._update_training_observation(snapshot, players)
        self.assertEqual(players[1]["mulligan_summary"]["replaced_count"], 4)

    def test_finish_event_does_not_overwrite_opponent_count(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        players = [{"hand": [], "turn": 1}, {"hand": [], "turn": 1}]
        snapshot = {
            "events": [
                {"address": "0x1", "type": "BattleResponseMulligan", "sequence": 3, "is_ally": False, "change_card_flags": 7},
                {"address": "0x2", "type": "BattleResponseMulliganFinish", "sequence": 4},
            ]
        }
        service._update_training_observation(snapshot, players)
        self.assertEqual(players[1]["mulligan_summary"]["replaced_count"], 3)

    def test_mulligan_response_with_new_managed_address_is_not_counted_twice(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        players = [{"hand": [], "turn": 0}, {"hand": [], "turn": 0}]
        first = {
            "events": [{
                "address": "0x1", "type": "BattleResponseMulligan", "sequence": 0,
                "is_ally": False, "change_card_flags": 7,
            }]
        }
        second = {
            "events": [{
                "address": "0x2", "type": "BattleResponseMulligan", "sequence": 0,
                "is_ally": False, "change_card_flags": 7,
            }]
        }
        service._update_training_observation(first, players)
        service._update_training_observation(second, players)
        self.assertEqual(len(first["training_observation"]["mulligan"]["events"]), 1)
        self.assertEqual(second["training_observation"]["mulligan"]["opponent_replaced_count"], 3)

    def test_t1_draw_is_separated_from_three_mulligan_replacements(self) -> None:
        service = TrackerService(TrackerConfig(), on_snapshot=lambda _snapshot: None)
        initial = [
            self.card(1, 10052110),
            self.card(2, 10252110),
            self.card(3, 10252110),
            self.card(4, 10352110),
        ]
        players = [{"hand": initial, "turn": 0, "deck_count": 36}, {"hand": [], "turn": 0}]
        opening_snapshot = {
            "current_turn": 0,
            "events": [{
                "address": "0x10",
                "type": "BattleModelMulliganSelection",
                "is_ally": True,
                "replaced_count": 3,
                "selection_fingerprint": (1, 2, 3),
            }],
        }
        service._update_training_observation(opening_snapshot, players)
        service._capture_self_draws_and_burns(opening_snapshot, players[0])

        final_four = [
            self.card(11, 10452110),
            self.card(12, 10552110),
            self.card(13, 10652110),
            self.card(4, 10352110),
        ]
        turn_draw = self.card(14, 10752110)
        players = [{"hand": [*final_four, turn_draw], "turn": 1, "deck_count": 35}, {"hand": [], "turn": 1}]
        turn_snapshot = {
            "current_turn": 1,
            "events": [{
                "address": "0x20",
                "type": "BattleResponseDrawOpen",
                "sequence": 10,
                "is_ally": True,
                "is_turn_start_draw": True,
                "cards": [turn_draw],
            }],
        }
        service._update_training_observation(turn_snapshot, players)
        service._capture_self_draws_and_burns(turn_snapshot, players[0])

        summary = players[0]["mulligan_summary"]
        # Both same-name copies remain listed even when one replacement has
        # that same card name; replacement identity is UID-based, not a name
        # multiset difference.
        self.assertEqual(summary["replaced_cards"], [10052110, 10252110, 10252110])
        self.assertEqual(summary["final_hand"], [10452110, 10552110, 10652110, 10352110])
        self.assertEqual(players[0]["_draw_history"], [{"turn": 1, "kind": "抽取", "card_id": 10752110}])


if __name__ == "__main__":
    unittest.main()
