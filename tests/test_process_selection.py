from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.memory.win32 import ProcessInfo, find_process_candidates


class ProcessSelectionTests(unittest.TestCase):
    @patch(
        "shadowverse_tracker.memory.win32.iter_processes",
        return_value=(
            ProcessInfo(20, "MuMu模拟器x影之诗高清版.exe"),
            ProcessInfo(10, "ShadowverseWB.exe"),
        ),
    )
    def test_returns_all_supported_builds_in_preference_order(self, _iter) -> None:
        value = find_process_candidates(
            ("ShadowverseWB.exe", "MuMu模拟器x影之诗高清版.exe")
        )
        self.assertEqual(tuple(item.pid for item in value), (10, 20))

    @patch(
        "shadowverse_tracker.memory.win32.iter_processes",
        return_value=(ProcessInfo(20, "MuMu模拟器x影之诗高清版.exe"),),
    )
    def test_missing_names_raise_a_useful_error(self, _iter) -> None:
        with self.assertRaisesRegex(ProcessLookupError, "process not found"):
            find_process_candidates(("ShadowverseWB.exe",))

    @patch(
        "shadowverse_tracker.memory.win32.iter_processes",
        return_value=(
            ProcessInfo(20, "MuMu模拟器x影之诗高清版.exe"),
            ProcessInfo(21, "MuMu模拟器x影之诗高清版.exe"),
        ),
    )
    def test_duplicate_processes_still_require_explicit_pid(self, _iter) -> None:
        with self.assertRaisesRegex(ProcessLookupError, "multiple"):
            find_process_candidates(("MuMu模拟器x影之诗高清版.exe",))


if __name__ == "__main__":
    unittest.main()
