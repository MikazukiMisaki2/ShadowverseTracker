import math
import unittest

from opponent_key_probability import calculate_key_probability


class KeyProbabilityTests(unittest.TestCase):
    def test_unknown_policy_matches_hypergeometric_baseline(self) -> None:
        result = calculate_key_probability(
            deck_remaining=30,
            hand_size=6,
            mulligan_swapped=4,
            keep1_types=0,
            keep2_types=0,
            seen_keep1=0,
            seen_keep2=0,
            key_copies=3,
            strategy="unknown",
        )
        expected = 1.0 - math.comb(30, 3) / math.comb(36, 3)
        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.probability, expected, places=12)

    def test_unknown_policy_ignores_mulligan_count(self) -> None:
        values = []
        for swapped in range(5):
            result = calculate_key_probability(
                deck_remaining=30,
                hand_size=6,
                mulligan_swapped=swapped,
                keep1_types=8,
                keep2_types=2,
                seen_keep1=4,
                seen_keep2=1,
                key_copies=3,
                strategy="unknown",
            )
            self.assertTrue(result.valid)
            values.append(result.probability)
        self.assertTrue(all(value == values[0] for value in values))

    def test_unknown_opening_turn_examples_are_independent_of_mulligan_count(self) -> None:
        # Opening four plus one regular draw each turn: T4/T5 see 8/9 cards.
        # T6/T7 in the extra-draw case see 11/12 cards.
        expected = {
            8: 0.4979757085020243,
            9: 0.5450404858299596,
            11: 0.6301619433198381,
            12: 0.6684210526315789,
        }
        for seen_cards, probability in expected.items():
            values = []
            for swapped in range(4):
                result = calculate_key_probability(
                    deck_remaining=40 - seen_cards,
                    hand_size=seen_cards,
                    mulligan_swapped=swapped,
                    keep1_types=0,
                    keep2_types=0,
                    seen_keep1=0,
                    seen_keep2=0,
                    key_copies=3,
                    key_keep_limit=1,
                    key_seen=0,
                    strategy="unknown",
                )
                self.assertTrue(result.valid, result.reason)
                self.assertAlmostEqual(result.probability, probability, places=12)
                values.append(result.probability)
            self.assertTrue(all(value == values[0] for value in values))

    def test_all_key_copies_seen_returns_zero(self) -> None:
        result = calculate_key_probability(
            deck_remaining=25,
            hand_size=5,
            mulligan_swapped=2,
            keep1_types=1,
            keep2_types=0,
            seen_keep1=3,
            seen_keep2=0,
            key_copies=3,
            key_seen=3,
            key_keep_limit=1,
            strategy="known",
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.probability, 0.0)

    def test_known_policy_full_keep_is_more_informative_than_full_swap(self) -> None:
        probabilities = []
        for swapped in (4, 0):
            result = calculate_key_probability(
                deck_remaining=36,
                hand_size=4,
                mulligan_swapped=swapped,
                keep1_types=5,
                keep2_types=1,
                seen_keep1=0,
                seen_keep2=0,
                key_copies=3,
                strategy="known",
                key_keep_limit=1,
            )
            self.assertTrue(result.valid, result.reason)
            probabilities.append(result.probability)
        self.assertLess(probabilities[0], probabilities[1])

    def test_known_policy_reference_case(self) -> None:
        result = calculate_key_probability(
            deck_remaining=29,
            hand_size=6,
            mulligan_swapped=2,
            keep1_types=5,
            keep2_types=1,
            seen_keep1=2,
            seen_keep2=1,
            key_copies=3,
            strategy="known",
            key_keep_limit=1,
        )
        self.assertTrue(result.valid, result.reason)
        self.assertAlmostEqual(result.probability, 0.6850386395951014, places=12)

    def test_impossible_evidence_is_reported_not_silently_fallback(self) -> None:
        result = calculate_key_probability(
            deck_remaining=36,
            hand_size=4,
            mulligan_swapped=4,
            keep1_types=1,
            keep2_types=0,
            seen_keep1=3,
            seen_keep2=0,
            key_copies=3,
            strategy="known",
            key_keep_limit=1,
        )
        self.assertFalse(result.valid)
        self.assertIsNone(result.probability)

    def test_key_type_must_be_in_corresponding_total(self) -> None:
        result = calculate_key_probability(
            deck_remaining=30,
            hand_size=6,
            mulligan_swapped=2,
            keep1_types=0,
            keep2_types=1,
            seen_keep1=0,
            seen_keep2=0,
            key_copies=3,
            strategy="known",
            key_keep_limit=1,
        )
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()
