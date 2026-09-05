from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.match_history import MatchHistory, MatchRecord, result_label, terminal_match_id


def record(match_id: str, opponent_class_id: int, result: str, *, is_first: bool | None = None) -> MatchRecord:
    return MatchRecord(
        match_id=match_id,
        timestamp="2026-08-30T00:00:00+00:00",
        deck_key="deck-a",
        deck_name="测试卡组",
        self_class_id=5,
        opponent_class_id=opponent_class_id,
        opponent_class={1: "精灵", 2: "皇家护卫"}[opponent_class_id],
        result=result,
        result_code=101 if result == "胜利" else 102,
        turn=6,
        is_first=is_first,
    )


class MatchHistoryTests(unittest.TestCase):
    def test_persists_and_groups_stats_by_opponent_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            self.assertTrue(history.add(record("m1", 1, "胜利", is_first=True)))
            self.assertTrue(history.add(record("m2", 1, "失败", is_first=False)))
            self.assertTrue(history.add(record("m3", 2, "胜利", is_first=False)))
            self.assertFalse(history.add(record("m3", 2, "胜利")))

            restored = MatchHistory(history.path).load()
            stats = restored.stats("deck-a")
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["wins"], 2)
            self.assertEqual(stats["losses"], 1)
            self.assertEqual(stats["win_rate"], 66.7)
            self.assertEqual(stats["first"]["win_rate"], 100.0)
            self.assertEqual(stats["second"]["win_rate"], 50.0)
            self.assertEqual(stats["by_class"]["精灵"]["win_rate"], 50.0)
            self.assertEqual(stats["by_class"]["皇家护卫"]["wins"], 1)

    def test_result_classification_is_conservative(self) -> None:
        self.assertEqual(result_label(101, 20, 10), "胜利")
        self.assertEqual(result_label(105, 20, 10), "胜利")
        self.assertEqual(result_label(999, 20, 0), "胜利")
        self.assertEqual(result_label(999, 0, 20), "失败")
        self.assertEqual(result_label(106, 20, 10), "失败")

    def test_migrates_saved_surrender_to_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.json"
            path.write_text(
                '{"schema_version": 1, "records": [{'
                '"match_id":"m1","timestamp":"t","deck_key":"d",'
                '"deck_name":"牌组","self_class_id":5,"opponent_class_id":1,'
                '"opponent_class":"精灵","result":"结束","result_code":106,"turn":1}]}',
                encoding="utf-8",
            )
            history = MatchHistory(path).load()
            self.assertEqual(history.records[0].result, "失败")
            self.assertEqual(MatchHistory(path).load().records[0].result, "失败")

    def test_migrates_opponent_surrender_to_win(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.json"
            path.write_text(
                '{"schema_version": 2, "records": [{'
                '"match_id":"m1","timestamp":"t","deck_key":"d",'
                '"deck_name":"牌组","self_class_id":5,"opponent_class_id":1,'
                '"opponent_class":"精灵","result":"结束","result_code":105,"turn":1}]}',
                encoding="utf-8",
            )
            history = MatchHistory(path).load()
            self.assertEqual(history.records[0].result, "胜利")
            self.assertEqual(history.stats("d")["wins"], 1)

    def test_clear_deck_removes_only_that_decks_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            history.add(record("m1", 1, "胜利"))
            other = MatchRecord(**{**record("m2", 2, "失败").__dict__, "deck_key": "deck-b"})
            history.add(other)
            self.assertEqual(history.clear_deck("deck-a"), 1)
            self.assertEqual(history.stats("deck-a")["total"], 0)
            self.assertEqual(history.stats("deck-b")["total"], 1)

    def test_overall_stats_and_opponent_deck_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            history.add(record("m1", 1, "胜利", is_first=True))
            second = MatchRecord(**{**record("m2", 2, "失败", is_first=False).__dict__, "deck_key": "deck-b"})
            history.add(second)
            self.assertEqual(history.stats()["total"], 2)
            self.assertTrue(history.update_opponent_deck("m2", "快攻龙"))
            restored = MatchHistory(history.path).load()
            self.assertEqual(restored.records[-1].opponent_deck_name, "快攻龙")

    def test_terminal_id_is_stable(self) -> None:
        first = terminal_match_id("0xabc", 101, 11, 3, -2, 22, 4, 10, 8)
        second = terminal_match_id("0xabc", 101, 11, 3, -2, 22, 4, 10, 8)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
