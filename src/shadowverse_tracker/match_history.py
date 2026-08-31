"""Local match history and per-deck opponent-class statistics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path


SCHEMA_VERSION = 2

# The order used by the official deck format.  Keep the numeric ID in records
# as well, so an updated translation can be applied without losing history.
CLASS_NAMES = {
    0: "中立",
    1: "精灵",
    2: "皇家护卫",
    3: "巫师",
    4: "龙族",
    5: "梦魇",
    6: "主教",
    7: "超越者",
}


def default_history_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "ShadowverseTracker" / "matches.json"
    return Path.home() / ".shadowverse_tracker" / "matches.json"


def class_name(class_id: int | None) -> str:
    if class_id is None:
        return "未知职业"
    return CLASS_NAMES.get(int(class_id), f"职业 {class_id}")


def result_label(result_code: int, self_life: int | None, opponent_life: int | None) -> str:
    """Classify terminal snapshots conservatively.

    Life reaching zero or the known victory code is conclusive.  Other
    non-zero codes are retained as ``结束`` until their meaning is confirmed,
    rather than silently polluting win-rate statistics.
    """
    if opponent_life is not None and opponent_life <= 0:
        return "胜利"
    if self_life is not None and self_life <= 0:
        return "失败"
    if result_code == 101:
        return "胜利"
    # Shadowverse WB uses 106 for the local player's surrender result.  Life
    # totals remain non-zero in this case, so it must be handled explicitly.
    if result_code == 106:
        return "失败"
    return "结束"


def terminal_match_id(
    model_address: str,
    result_code: int,
    turn: int | None,
    self_life: int | None,
    opponent_life: int | None,
    deck_count: int | None,
    cemetery_count: int | None,
    played_count: int,
    destroyed_count: int,
) -> str:
    """Build a stable identity for one terminal BattleModel snapshot."""
    return (
        f"terminal:{model_address}:{result_code}:{turn}:{self_life}:"
        f"{opponent_life}:{deck_count}:{cemetery_count}:{played_count}:{destroyed_count}"
    )


@dataclass(frozen=True)
class MatchRecord:
    match_id: str
    timestamp: str
    deck_key: str
    deck_name: str
    self_class_id: int | None
    opponent_class_id: int | None
    opponent_class: str
    result: str
    result_code: int
    turn: int | None
    is_first: bool | None = None


class MatchHistory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_history_path()
        self.records: list[MatchRecord] = []

    def load(self) -> "MatchHistory":
        if not self.path.exists():
            return self
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or int(value.get("schema_version", 0)) not in (1, SCHEMA_VERSION):
            raise ValueError("不支持的对局记录格式")
        migrated = int(value.get("schema_version", 0)) != SCHEMA_VERSION
        records = value.get("records", ())
        if not isinstance(records, list):
            raise ValueError("本地对局记录已损坏")
        parsed: list[MatchRecord] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            try:
                result_code = int(item.get("result_code", 0))
                result = str(item["result"])
                if result_code == 106 and result == "结束":
                    result = "失败"
                    migrated = True
                parsed.append(MatchRecord(
                    match_id=str(item["match_id"]),
                    timestamp=str(item["timestamp"]),
                    deck_key=str(item["deck_key"]),
                    deck_name=str(item["deck_name"]),
                    self_class_id=int(item["self_class_id"]) if item.get("self_class_id") is not None else None,
                    opponent_class_id=int(item["opponent_class_id"]) if item.get("opponent_class_id") is not None else None,
                    opponent_class=str(item.get("opponent_class") or "未知职业"),
                    result=result,
                    result_code=result_code,
                    turn=int(item["turn"]) if item.get("turn") is not None else None,
                    is_first=bool(item["is_first"]) if item.get("is_first") is not None else None,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        self.records = parsed
        if migrated:
            self.save()
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "records": [asdict(record) for record in self.records],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def add(self, record: MatchRecord) -> bool:
        if any(existing.match_id == record.match_id for existing in self.records):
            return False
        self.records.append(record)
        self.save()
        return True

    def for_deck(self, deck_key: str) -> list[MatchRecord]:
        return [record for record in self.records if record.deck_key == deck_key]

    def stats(self, deck_key: str) -> dict[str, object]:
        records = self.for_deck(deck_key)
        grouped: dict[str, dict[str, int | float | dict[str, int | float]]] = {}
        for record in records:
            group = grouped.setdefault(record.opponent_class, {
                "total": 0, "wins": 0, "losses": 0, "finished": 0,
                "first": {"total": 0, "wins": 0, "losses": 0, "finished": 0},
                "second": {"total": 0, "wins": 0, "losses": 0, "finished": 0},
            })
            group["total"] += 1
            order = group["first"] if record.is_first else group["second"] if record.is_first is False else None
            if order is not None:
                order["total"] += 1
            if record.result == "胜利":
                group["wins"] += 1
                group["finished"] += 1
                if order is not None:
                    order["wins"] += 1
                    order["finished"] += 1
            elif record.result == "失败":
                group["losses"] += 1
                group["finished"] += 1
                if order is not None:
                    order["losses"] += 1
                    order["finished"] += 1
        for group in grouped.values():
            finished = int(group["finished"])
            group["win_rate"] = round(int(group["wins"]) * 100 / finished, 1) if finished else 0.0
            for key in ("first", "second"):
                order = group[key]
                finished = int(order["finished"])
                order["win_rate"] = round(int(order["wins"]) * 100 / finished, 1) if finished else 0.0
        wins = sum(int(group["wins"]) for group in grouped.values())
        losses = sum(int(group["losses"]) for group in grouped.values())
        finished = wins + losses
        orders = {}
        for key in ("first", "second"):
            order_wins = sum(int(group[key]["wins"]) for group in grouped.values())
            order_losses = sum(int(group[key]["losses"]) for group in grouped.values())
            order_finished = order_wins + order_losses
            orders[key] = {
                "wins": order_wins,
                "losses": order_losses,
                "finished": order_finished,
                "win_rate": round(order_wins * 100 / order_finished, 1) if order_finished else 0.0,
            }
        return {
            "total": len(records),
            "wins": wins,
            "losses": losses,
            "finished": finished,
            "win_rate": round(wins * 100 / finished, 1) if finished else 0.0,
            "first": orders["first"],
            "second": orders["second"],
            "by_class": grouped,
        }


__all__ = [
    "CLASS_NAMES",
    "MatchHistory",
    "MatchRecord",
    "class_name",
    "default_history_path",
    "result_label",
    "terminal_match_id",
]
