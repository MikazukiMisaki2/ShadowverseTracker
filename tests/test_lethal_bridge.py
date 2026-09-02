from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.lethal_bridge import create_lethal_bridge


class LethalBridgeTests(unittest.TestCase):
    def test_loads_sibling_calculator_and_generated_sources(self) -> None:
        calculator = Path(r"D:\Github\LethalCalculator")
        if not (calculator / "tracker_integration.py").is_file():
            self.skipTest("sibling LethalCalculator checkout is unavailable")
        bridge, message = create_lethal_bridge(root=calculator, max_depth=2)
        self.assertIsNotNone(bridge, message)
        assert bridge is not None
        self.assertEqual(bridge.root, calculator.resolve())
        self.assertTrue(hasattr(bridge.session, "refresh"))
        self.assertIn("LethalCalculator", message)
        fixture = calculator / "fixtures" / "tracker_snapshots" / "complete.json"
        if fixture.is_file():
            view = bridge.refresh(json.loads(fixture.read_text(encoding="utf-8")))
            self.assertIn(view.status, {"CONFIRMED", "PROBABILISTIC", "NO_LETHAL", "INCOMPLETE"})

    def test_missing_root_fails_closed_with_ui_message(self) -> None:
        bridge, message = create_lethal_bridge(root=REPO_ROOT / "does-not-exist")
        self.assertIsNone(bridge)
        self.assertTrue(message)


if __name__ == "__main__":
    unittest.main()
