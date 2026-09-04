from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.tracker_service import TrackerConfig, TrackerService
from shadowverse_tracker.memory.win32 import ProcessInfo
from shadowverse_tracker.versioning import VersionProfile


class TrackerServiceRefreshTests(unittest.TestCase):
    def test_dynamic_profile_skips_blocking_server_data_scan(self) -> None:
        class Reader:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        profile = VersionProfile(
            game_version="test-cn",
            unity_version="test",
            process_name="MuMu模拟器x影之诗高清版.exe",
            module_name="GameAssembly.dll",
            gameassembly_sha256="TEST",
            battle_model_class_pointer_rva=0,
            deck_info_class_pointer_rva=0,
            practice_battle_model_class_pointer_rva=0,
            dynamic_discovery=True,
        )
        service = TrackerService(
            TrackerConfig(model_address=0x1234, interval=0.01),
            on_snapshot=lambda _snapshot: None,
        )
        service._attach_deck_state = lambda _snapshot: None
        service._emit = lambda _snapshot: service._stop.set()
        reader = Reader()
        with (
            patch.object(
                service,
                "_open_supported_reader",
                return_value=(reader, profile, ProcessInfo(42, profile.process_name)),
            ),
            patch("shadowverse_tracker.tracker_service.read_battle_model", return_value={}) as read_model,
            patch("shadowverse_tracker.tracker_service.find_battle_view_server_data") as find_server_data,
        ):
            service._run()

        find_server_data.assert_not_called()
        self.assertTrue(read_model.call_args.kwargs["read_root_legal_actions"])

    def test_legal_actions_are_part_of_semantic_refresh(self) -> None:
        seen: list[dict[str, object]] = []
        service = TrackerService(TrackerConfig(), on_snapshot=seen.append)
        root = {
            "address": "0xold",
            "is_ally_turn": True,
            "players": ({"address": "0x1", "hand": [], "field": []}, {"address": "0x2", "hand": [], "field": []}),
        }
        first = {
            "root": root,
            "current_turn": 3,
            "legal_actions": {"can_play_cards": [10], "attack_targets": {}},
        }
        service._emit(first)
        # Managed addresses are intentionally ignored, but a legal mode
        # change must produce a new callback for SnapshotAdapter/UI refresh.
        second = {
            "root": {**root, "address": "0xnew"},
            "current_turn": 3,
            "legal_actions": {"can_play_cards": [], "attack_targets": {}},
        }
        service._emit(second)
        service._emit(second)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]["legal_actions"]["can_play_cards"], [10])
        self.assertEqual(seen[1]["legal_actions"]["can_play_cards"], [])


if __name__ == "__main__":
    unittest.main()
