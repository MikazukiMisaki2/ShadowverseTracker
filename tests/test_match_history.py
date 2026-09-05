from __future__ import annotations

from pathlib import Path
from datetime import timedelta, timezone
import json
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.match_history import (
    MatchHistory,
    MatchRecord,
    format_timestamp_local,
    orient_class_ids,
    orient_player_order,
    result_label,
    terminal_match_id,
)
from shadowverse_tracker.opponent_deck_matcher import MetaDeckProfile, OpponentDeckMatcher


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
    def test_formats_aware_timestamp_in_requested_local_timezone(self) -> None:
        local = timezone(timedelta(hours=8))
        self.assertEqual(
            format_timestamp_local("2026-09-05T07:02:45+00:00", tz=local),
            "2026-09-05 15:02",
        )
        # Legacy naive timestamps are already local and must not shift.
        self.assertEqual(
            format_timestamp_local("2026-09-05T07:02:45", tz=local),
            "2026-09-05 07:02",
        )

    def test_orients_reversed_reader_classes_to_selected_deck(self) -> None:
        self.assertEqual(orient_class_ids(1, 5, 5), (5, 1))
        self.assertEqual(orient_class_ids(5, 1, 5), (5, 1))
        self.assertEqual(orient_class_ids(None, 1, 5), (5, 1))

    def test_orients_reversed_root_players_by_local_unique_id(self) -> None:
        reversed_players = [
            {"unique_id": 2, "result_code": 106},
            {"unique_id": 1, "result_code": 105},
        ]
        self.assertEqual(
            [player["unique_id"] for player in orient_player_order(reversed_players)],
            [1, 2],
        )
        legacy_reversed = [{"result_code": 106}, {"result_code": 105}]
        self.assertEqual(
            [player["result_code"] for player in orient_player_order(
                legacy_reversed,
                self_class_id=1,
                opponent_class_id=5,
                expected_self_class_id=5,
            )],
            [105, 106],
        )
        # Legacy snapshots without the ownership marker keep positional order.
        legacy = [{"result_code": 101}, {"result_code": 102}]
        self.assertIs(orient_player_order(legacy), legacy)

    def test_reconciles_existing_reversed_class_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            history.add(MatchRecord(
                match_id="m1",
                timestamp="2026-08-30T00:00:00+00:00",
                deck_key="deck-a",
                deck_name="中速梦",
                self_class_id=1,
                opponent_class_id=5,
                opponent_class="梦魇",
                result="失败",
                result_code=106,
                turn=10,
            ))
            self.assertEqual(history.reconcile_deck_class_ids({"deck-a": 5}), 1)
            restored = MatchHistory(history.path).load()
            self.assertEqual(restored.records[0].self_class_id, 5)
            self.assertEqual(restored.records[0].opponent_class_id, 1)
            self.assertEqual(restored.records[0].opponent_class, "精灵")

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
            filtered = restored.stats("deck-a", "精灵")
            self.assertEqual(filtered["total"], 2)
            self.assertEqual(filtered["first"]["win_rate"], 100.0)
            self.assertEqual(filtered["second"]["win_rate"], 0.0)

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

    def test_clear_all_removes_every_deck_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            history.add(record("m1", 1, "胜利"))
            history.add(MatchRecord(**{**record("m2", 2, "失败").__dict__, "deck_key": "deck-b"}))
            self.assertEqual(history.clear_all(), 2)
            self.assertEqual(history.stats()["total"], 0)
            self.assertEqual(MatchHistory(history.path).load().records, [])
            self.assertEqual(history.clear_all(), 0)

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

    def test_auto_matches_saved_public_cards_without_overwriting_manual_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = MatchHistory(Path(directory) / "matches.json")
            observed = MatchRecord(
                **{
                    **record("m1", 1, "胜利").__dict__,
                    "opponent_played_card_ids": (10000111, 10000211, 10000311),
                }
            )
            manual = MatchRecord(
                **{
                    **record("m2", 1, "失败").__dict__,
                    "opponent_deck_name": "手动标注",
                    "opponent_played_card_ids": (10000111,),
                }
            )
            history.add(observed)
            history.add(manual)
            matcher = OpponentDeckMatcher((
                MetaDeckProfile(
                    "profile-a",
                    "精灵构筑",
                    1,
                    {10000110: 3, 10000210: 3, 10000310: 3},
                ),
            ))
            self.assertEqual(history.auto_match_opponent_decks(matcher), 1)
            restored = MatchHistory(history.path).load()
            self.assertEqual(restored.records[0].opponent_deck_name, "精灵构筑")
            self.assertEqual(restored.records[0].opponent_played_card_ids, (10000110, 10000210, 10000310))
            self.assertEqual(restored.records[1].opponent_deck_name, "手动标注")

    def test_schema_four_records_migrate_with_empty_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.json"
            path.write_text(
                '{"schema_version": 4, "records": [{'
                '"match_id":"m1","timestamp":"t","deck_key":"d",'
                '"deck_name":"牌组","self_class_id":5,"opponent_class_id":1,'
                '"opponent_class":"精灵","result":"胜利","result_code":101,"turn":1}]}',
                encoding="utf-8",
            )
            history = MatchHistory(path).load()
            self.assertEqual(history.records[0].opponent_played_card_ids, ())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 5)


if __name__ == "__main__":
    unittest.main()
