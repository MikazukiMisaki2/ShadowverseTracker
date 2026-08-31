from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.opponent_hand import OpponentKnownHand


class OpponentKnownHandTests(unittest.TestCase):
    def test_known_last_words_and_unknown_spell(self) -> None:
        tracker = OpponentKnownHand()
        opponent = {
            "deck_count": 10,
            "played_card_ids": [(10052110, 0), (10574120, 0)],
            "destroyed_card_ids": [(10052110, 0)],
        }
        tracker.update({}, opponent)
        self.assertEqual(tracker.cards[90051120], 1)
        self.assertEqual(tracker.cards["unknown_spell"], 1)

    def test_self_replacing_last_words_token(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {},
            {
                "played_card_ids": [(10941110, 0)],
                "destroyed_card_ids": [(10941110, 0)],
            },
        )
        self.assertEqual(tracker.cards[10941110], 1)

    def test_public_draw_event_is_recorded_but_hidden_draw_is_not(self) -> None:
        tracker = OpponentKnownHand()
        tracker.update(
            {
                "events": [
                    {
                        "type": "BattleResponseDrawOpen",
                        "sequence": 7,
                        "is_ally": False,
                        "cards": [{"base_card_id": 90051120}],
                    },
                    {
                        "type": "BattleResponseDrawHide",
                        "sequence": 8,
                        "is_ally": False,
                        "draw_num": 1,
                    },
                ]
            },
            {"deck_count": 10},
        )
        self.assertEqual(tracker.cards[90051120], 1)
        self.assertNotIn("unknown_spell", tracker.cards)


if __name__ == "__main__":
    unittest.main()
