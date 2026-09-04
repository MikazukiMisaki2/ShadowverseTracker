from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.faith_probability import calculate_faith_damage_probability


class FaithProbabilityTests(unittest.TestCase):
    def test_single_point_is_split_equally(self) -> None:
        self.assertAlmostEqual(calculate_faith_damage_probability(1, 1), 1 / 3)

    def test_binomial_tail(self) -> None:
        # P(Z >= 3) for N=5 is (40 + 10 + 1) / 243.
        self.assertAlmostEqual(
            calculate_faith_damage_probability(5, 3),
            float(Fraction(51, 243)),
        )

    def test_threshold_edges(self) -> None:
        self.assertEqual(calculate_faith_damage_probability(0, 0), 1.0)
        self.assertEqual(calculate_faith_damage_probability(0, 1), 0.0)
        self.assertEqual(calculate_faith_damage_probability(8, 0), 1.0)
        self.assertEqual(calculate_faith_damage_probability(8, 9), 0.0)

    def test_rejects_negative_inputs(self) -> None:
        with self.assertRaises(ValueError):
            calculate_faith_damage_probability(-1, 0)
        with self.assertRaises(ValueError):
            calculate_faith_damage_probability(1, -1)


if __name__ == "__main__":
    unittest.main()
