from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.app import TrackerApp
from shadowverse_tracker.card_catalog import get_card_name


class AppFormattingTests(unittest.TestCase):
    def test_recent_history_contains_both_sides(self) -> None:
        value = TrackerApp._format_recent_history(
            {"played_card_ids": [(10953110, 0)]},
            {"played_card_ids": [(10851120, 0)]},
        )
        self.assertIn(get_card_name(10953110), value)
        self.assertIn(get_card_name(10851120), value)
        self.assertEqual(value.count("\n\n"), 1)


if __name__ == "__main__":
    unittest.main()
