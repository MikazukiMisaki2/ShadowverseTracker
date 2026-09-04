from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.deck_repository import DeckRepository
from shadowverse_tracker.memory.deck import DeckCard
from test_official_deck import test_hash
from shadowverse_tracker.official_deck import parse_official_deck


class DeckRepositoryTests(unittest.TestCase):
    def test_persists_import_selection_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decks.json"
            repository = DeckRepository(path)
            first = repository.add_official("测试牌组", parse_official_deck(test_hash()))
            loaded = DeckRepository(path).load()
            self.assertEqual(loaded.active(), first)
            self.assertEqual(loaded.active().to_snapshot().total_cards, 40)  # type: ignore[union-attr]
            loaded.delete(first.key)
            self.assertIsNone(DeckRepository(path).load().active())

    def test_edit_preserves_key_for_match_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decks.json"
            repository = DeckRepository(path)
            first = repository.add_official("测试牌组", parse_official_deck(test_hash()))
            cards = list(first.cards)
            cards[0] = DeckCard(cards[0].card_id, cards[0].count - 1)
            cards[-1] = DeckCard(cards[-1].card_id, cards[-1].count + 1)
            updated = repository.update_cards(first.key, tuple(cards))
            self.assertEqual(updated.key, first.key)
            self.assertEqual(updated.total_cards, 40)
            self.assertEqual(DeckRepository(path).load().active(), updated)

    def test_cover_card_persists_and_rejects_cards_outside_deck(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decks.json"
            repository = DeckRepository(path)
            first = repository.add_official("测试牌组", parse_official_deck(test_hash()))
            cover_id = first.cards[0].card_id
            updated = repository.set_cover(first.key, cover_id)
            self.assertEqual(updated.cover_card_id, cover_id)
            self.assertEqual(DeckRepository(path).load().active().cover_card_id, cover_id)  # type: ignore[union-attr]
            with self.assertRaises(ValueError):
                repository.set_cover(first.key, 99999999)


if __name__ == "__main__":
    unittest.main()
