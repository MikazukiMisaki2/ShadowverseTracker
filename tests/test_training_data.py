from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.training_data import TrainingMatchRecorder, compact_event_records


def _snapshot(*, fields=(), events=(), deck=None, turn=1) -> dict[str, object]:
    return {
        "current_turn": turn,
        "deck": deck,
        "battle_mode": "ranked",
        "root": {
            "is_ally_turn": True,
            "players": [
                {
                    "turn": turn,
                    "hand": [],
                    "field": list(fields),
                    "played_card_ids": [],
                    "life": 20,
                    "deck_count": 40,
                    "result_code": 0,
                },
                {
                    "turn": turn,
                    "hand": [],
                    "field": [],
                    "played_card_ids": [],
                    "life": 20,
                    "deck_count": 36,
                    "result_code": 0,
                },
            ],
        },
        "events": list(events),
    }


class TrainingDataTests(unittest.TestCase):
    def test_hidden_draw_keeps_count_without_private_card_ids(self) -> None:
        value = compact_event_records(
            {
                "type": "BattleResponseDrawHide",
                "sequence": 2,
                "is_ally": False,
                "draw_num": 2,
                "add_num": 2,
                "is_turn_start_draw": True,
            },
            4,
        )
        self.assertEqual(len(value), 1)
        self.assertEqual(value[0]["k"], "d")
        self.assertEqual(value[0]["s"], 1)
        self.assertEqual(value[0]["n"], 2)
        self.assertEqual(value[0]["h"], 1)
        self.assertEqual(value[0]["st"], 1)
        self.assertNotIn("c", value[0])

    def test_direct_deck_summon_and_generated_token_are_separately_classified(self) -> None:
        deck = {
            "deck_key": "deck-a",
            "deck_name": "Test deck",
            "class_id": 6,
            "deck_format": 1,
            "total_cards": 40,
            "cards": [{"card_id": 10000010, "count": 3}],
        }
        recorder = TrainingMatchRecorder()
        recorder.ingest(_snapshot(deck=deck, fields=()))
        recorder.ingest(
            _snapshot(
                deck=deck,
                fields=[
                    {"unique_id": 11, "base_card_id": 10000010, "card_id": 10000010},
                    {"unique_id": 12, "base_card_id": 10000010, "card_id": 10000010},
                ],
                events=[
                    {
                        "type": "BattleResponsePutCardFromDeck",
                        "sequence": 3,
                        "cards": [{"unique_id": 11, "base_card_id": 10000010}],
                    },
                    {
                        "type": "BattleResponsePutToken",
                        "sequence": 4,
                        "targets": [{"unique_id": 12, "base_card_id": 10000010}],
                    },
                ],
            )
        )
        self.assertIsNotNone(recorder._record)
        events = recorder._record["e"]  # type: ignore[index]
        direct = next(item for item in events if item.get("k") == "in" and item.get("u") == 11)
        token = next(item for item in events if item.get("k") == "in" and item.get("u") == 12)
        self.assertEqual(direct["src"], "deck")
        self.assertEqual(token["src"], "token")

    def test_public_token_flag_classifies_field_transition_without_response(self) -> None:
        recorder = TrainingMatchRecorder()
        recorder.ingest(_snapshot(fields=()))
        recorder.ingest(_snapshot(fields=[{
            "unique_id": 12,
            "base_card_id": 10000010,
            "card_id": 10000010,
            "is_same_name_token": True,
        }]))
        record = recorder.finish(complete=False)
        self.assertIsNotNone(record)
        event = next(item for item in record["e"] if item.get("k") == "in")  # type: ignore[index]
        self.assertEqual(event["src"], "token")

    def test_same_snapshot_event_is_recorded_once(self) -> None:
        event = {
            "type": "BattleResponseAttack",
            "address": "0x123",
            "sequence": 8,
            "is_ally": True,
            "from_unique_id": 11,
            "to_unique_id": 99,
            "from_damage": 3,
            "to_damage": 3,
        }
        recorder = TrainingMatchRecorder()
        snapshot = _snapshot(events=[event])
        recorder.ingest(snapshot)
        recorder.ingest(snapshot)
        record = recorder.finish(complete=False)
        self.assertIsNotNone(record)
        events = record["e"]  # type: ignore[index]
        attacks = [item for item in events if item.get("k") == "a"]
        self.assertEqual(len(attacks), 1)

    def test_nested_managed_address_change_is_not_a_second_event(self) -> None:
        first = {
            "type": "BattleResponseDrawOpen",
            "sequence": 9,
            "is_ally": True,
            "cards": [{"address": "0x1", "unique_id": 22, "base_card_id": 10000010}],
            "add_num": 1,
        }
        second = {
            **first,
            "address": "0x2",
            "cards": [{"address": "0x3", "unique_id": 22, "base_card_id": 10000010}],
        }
        recorder = TrainingMatchRecorder()
        recorder.ingest(_snapshot(events=[first]))
        recorder.ingest(_snapshot(events=[second]))
        record = recorder.finish(complete=False)
        self.assertIsNotNone(record)
        events = record["e"]  # type: ignore[index]
        draws = [item for item in events if item.get("k") == "d"]
        self.assertEqual(len(draws), 1)

    def test_checkpoint_keeps_turn_side_mode_and_resource_flags(self) -> None:
        recorder = TrainingMatchRecorder()
        snapshot = _snapshot(turn=3)
        snapshot["root"]["players"][0].update({
            "preparation_extra_pp": 1,
            "extra_pp_state": 2,
            "evolve_turn": 4,
            "super_evolve_turn": 7,
            "is_awakening": True,
            "is_evolved_this_turn": True,
        })
        recorder.ingest(snapshot)
        record = recorder.finish(complete=False)
        self.assertIsNotNone(record)
        checkpoint = record["s"][0]  # type: ignore[index]
        self.assertEqual(checkpoint["a"], 1)
        self.assertEqual(checkpoint["g"], "ranked")
        player = checkpoint["p"][0]
        self.assertEqual(player["pe"], 1)
        self.assertEqual(player["xs"], 2)
        self.assertEqual(player["et"], 4)
        self.assertEqual(player["st"], 7)
        self.assertTrue(player["x"] & (1 << 1))

    def test_super_evolve_blow_is_an_attack_with_target(self) -> None:
        value = compact_event_records(
            {
                "type": "BattleResponseSuperEvolveBlow",
                "sequence": 12,
                "is_ally": True,
                "from_unique_id": 21,
                "to_card_unique_id": 31,
                "damage": 4,
                "is_dead": True,
            },
            6,
        )
        self.assertEqual(value[0]["k"], "a")
        self.assertEqual(value[0]["u"], 21)
        self.assertEqual(value[0]["v"], 31)
        self.assertEqual(value[0]["d"], 4)
        self.assertEqual(value[0]["x"], 1)


if __name__ == "__main__":
    unittest.main()
