from __future__ import annotations

import sys
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.tracker_service import TrackerConfig, TrackerService


class TrackerServiceRefreshTests(unittest.TestCase):
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
