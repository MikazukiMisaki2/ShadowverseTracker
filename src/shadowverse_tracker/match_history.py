"""Local match history and per-deck opponent-class statistics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone, tzinfo
import json
import os
from pathlib import Path
from typing import Mapping

from .card_catalog import canonical_card_id


SCHEMA_VERSION = 5

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


def orient_player_order(
    players: object,
    *,
    self_class_id: object = None,
    opponent_class_id: object = None,
    expected_self_class_id: object = None,
) -> object:
    """Put the local player (BattleState player id ``1``) first.

    ``BattleRootMpo.players`` is usually emitted in local/opponent order, but
    a terminal response can briefly expose the two entries in server order.
    The player ``unique_id`` is stable across that transition and is the
    preferred ownership marker available in the public root snapshot.  Older
    logs may predate that field; when a selected deck class is available, the
    two BattleInfo class IDs provide a conservative fallback for those rows.
    Incomplete snapshots remain untouched so callers can still use their
    historical positional fallback.
    """
    if not isinstance(players, (list, tuple)) or len(players) != 2:
        return players

    def _unique_id(value: object) -> int | None:
        if not isinstance(value, Mapping):
            return None
        raw = value.get("unique_id")
        if isinstance(raw, bool) or raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    first_id = _unique_id(players[0])
    second_id = _unique_id(players[1])
    should_swap = second_id == 1 and first_id != 1
    if not should_swap:
        def _class_id(value: object) -> int | None:
            if isinstance(value, bool) or value is None:
                return None
            try:
                candidate = int(value)
            except (TypeError, ValueError):
                return None
            return candidate if 0 <= candidate <= 7 else None

        expected = _class_id(expected_self_class_id)
        current_self = _class_id(self_class_id)
        current_opponent = _class_id(opponent_class_id)
        should_swap = (
            expected is not None
            and current_self is not None
            and current_opponent == expected
            and current_self != expected
        )
    if not should_swap:
        return players
    ordered = (players[1], players[0])
    return list(ordered) if isinstance(players, list) else ordered


def format_timestamp_local(value: object, *, tz: tzinfo | None = None) -> str:
    """Format a stored ISO timestamp in the user's local time zone.

    New records are persisted as UTC-aware ISO strings.  Older records may be
    naive strings, so those are deliberately treated as already-local values
    instead of silently shifting them a second time.
    """
    raw = str(value or "").strip()
    if not raw:
        return "—"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return raw.replace("T", " ")[:16]
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz) if tz is not None else parsed.astimezone()
    return parsed.strftime("%Y-%m-%d %H:%M")


def orient_class_ids(
    self_class_id: object,
    opponent_class_id: object,
    expected_self_class_id: object = None,
) -> tuple[int | None, int | None]:
    """Orient the reader's two class IDs to the selected local deck.

    The BattleInfo user collection is not always ordered like the public
    player collection.  When the selected deck gives us an authoritative local
    class, use it to correct that occasional reversal while retaining the
    reader values as the fallback.
    """
    def _as_id(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            candidate = int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
        return candidate if candidate is not None and 0 <= candidate <= 7 else None

    current_self = _as_id(self_class_id)
    current_opponent = _as_id(opponent_class_id)
    expected = _as_id(expected_self_class_id)
    if expected is None:
        return current_self, current_opponent
    if current_opponent == expected and current_self != expected:
        return expected, current_self
    return expected, current_opponent


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
    # 105 is the opponent-surrender terminal result.  Both life totals can
    # remain positive, so it cannot be inferred from the board alone.
    if result_code == 105:
        return "胜利"
    # Shadowverse WB uses 106 for the local player's surrender result.  Life
    # totals remain non-zero in this case, so it must be handled explicitly.
    if result_code == 106:
        return "失败"
    return "结束"


def _normalise_played_card_ids(value: object) -> tuple[int, ...]:
    """Store public played-card observations in a compact stable shape."""
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[int] = []
    for item in value:
        raw: object = item
        if isinstance(item, dict):
            raw = item.get("base_card_id") or item.get("card_id")
        elif isinstance(item, (list, tuple)) and item:
            raw = item[0]
        try:
            card_id = canonical_card_id(int(raw))
        except (TypeError, ValueError):
            continue
        if card_id > 0:
            result.append(card_id)
    return tuple(result)


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
    opponent_deck_name: str = ""
    # Only public cards that the opponent has played are retained.  Hidden
    # cards are never inferred or persisted as if they were known.
    opponent_played_card_ids: tuple[int, ...] = ()


class MatchHistory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_history_path()
        self.records: list[MatchRecord] = []

    def load(self) -> "MatchHistory":
        if not self.path.exists():
            return self
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or int(value.get("schema_version", 0)) not in (1, 2, 3, 4, SCHEMA_VERSION):
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
                if result == "结束" and result_code in {105, 106}:
                    result = "胜利" if result_code == 105 else "失败"
                    migrated = True
                opponent_class_id = int(item["opponent_class_id"]) if item.get("opponent_class_id") is not None else None
                opponent_class = str(item.get("opponent_class") or "未知职业")
                canonical_opponent_class = class_name(opponent_class_id) if opponent_class_id is not None else opponent_class
                if opponent_class_id is not None and opponent_class != canonical_opponent_class:
                    migrated = True
                    opponent_class = canonical_opponent_class
                parsed.append(MatchRecord(
                    match_id=str(item["match_id"]),
                    timestamp=str(item["timestamp"]),
                    deck_key=str(item["deck_key"]),
                    deck_name=str(item["deck_name"]),
                    self_class_id=int(item["self_class_id"]) if item.get("self_class_id") is not None else None,
                    opponent_class_id=opponent_class_id,
                    opponent_class=opponent_class,
                    result=result,
                    result_code=result_code,
                    turn=int(item["turn"]) if item.get("turn") is not None else None,
                    is_first=bool(item["is_first"]) if item.get("is_first") is not None else None,
                    opponent_deck_name=str(
                        item.get("opponent_deck_name")
                        or item.get("opponent_deck")
                        or ""
                    ).strip(),
                    opponent_played_card_ids=_normalise_played_card_ids(
                        item.get("opponent_played_card_ids")
                        or item.get("opponent_observed_card_ids")
                        or ()
                    ),
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

    def update_opponent_deck(self, match_id: str, name: str) -> bool:
        """Persist the user-entered opponent deck label for one match."""
        clean_name = str(name or "").strip()
        for index, record in enumerate(self.records):
            if record.match_id != match_id:
                continue
            if record.opponent_deck_name == clean_name:
                return False
            self.records[index] = replace(record, opponent_deck_name=clean_name)
            self.save()
            return True
        return False

    def update_opponent_played_cards(self, match_id: str, card_ids: object) -> bool:
        """Persist public opponent cards without changing a manual label."""
        observed = _normalise_played_card_ids(card_ids)
        for index, record in enumerate(self.records):
            if record.match_id != match_id:
                continue
            if record.opponent_played_card_ids == observed:
                return False
            self.records[index] = replace(record, opponent_played_card_ids=observed)
            self.save()
            return True
        return False

    def reconcile_deck_class_ids(self, deck_class_ids: Mapping[str, object]) -> int:
        """Correct class orientation using the saved deck's known class.

        A BattleInfo snapshot can occasionally return its two class IDs in the
        opposite order from the public player list.  Saved deck metadata is a
        reliable local-side anchor, so swap only when the opponent slot holds
        that expected class; unrelated or unknown rows are left untouched.
        """
        changed = False
        updates = 0
        for index, record in enumerate(self.records):
            expected = deck_class_ids.get(record.deck_key)
            local_class_id, opponent_class_id = orient_class_ids(
                record.self_class_id,
                record.opponent_class_id,
                expected,
            )
            opponent_class = class_name(opponent_class_id)
            if (
                local_class_id == record.self_class_id
                and opponent_class_id == record.opponent_class_id
                and opponent_class == record.opponent_class
            ):
                continue
            self.records[index] = replace(
                record,
                self_class_id=local_class_id,
                opponent_class_id=opponent_class_id,
                opponent_class=opponent_class,
            )
            changed = True
            updates += 1
        if changed:
            self.save()
        return updates

    def auto_match_opponent_decks(
        self,
        matcher: object,
        observations: object = None,
    ) -> int:
        """Fill blank opponent-deck labels from public-card observations.

        ``matcher`` is intentionally duck-typed here to keep this persistence
        module independent of the optional meta-deck source.  User-entered
        labels are never overwritten.  ``observations`` may provide terminal
        match IDs from an older app-session log; the longest observation wins.
        The return value is the number of newly labelled rows.
        """
        external: dict[str, object] = observations if isinstance(observations, dict) else {}
        changed = False
        labels_added = 0
        for index, record in enumerate(self.records):
            observed = record.opponent_played_card_ids
            candidate = _normalise_played_card_ids(external.get(record.match_id))
            if len(candidate) > len(observed):
                observed = candidate
            updated = record
            if observed != record.opponent_played_card_ids:
                updated = replace(updated, opponent_played_card_ids=observed)
                changed = True
            if not updated.opponent_deck_name and observed:
                try:
                    match = matcher.match(observed, updated.opponent_class_id)
                except (AttributeError, TypeError, ValueError):
                    match = None
                label = str(getattr(match, "label", "") or "").strip() if match is not None else ""
                if label:
                    updated = replace(updated, opponent_deck_name=label)
                    changed = True
                    labels_added += 1
            if updated != record:
                self.records[index] = updated
        if changed:
            self.save()
        return labels_added

    def clear_deck(self, deck_key: str) -> int:
        """Delete all locally saved match records for one deck."""
        before = len(self.records)
        self.records = [record for record in self.records if record.deck_key != deck_key]
        removed = before - len(self.records)
        if removed:
            self.save()
        return removed

    def clear_all(self) -> int:
        """Delete all locally saved match records and return the count."""
        removed = len(self.records)
        if not removed:
            return 0
        self.records = []
        self.save()
        return removed

    def for_deck(self, deck_key: str) -> list[MatchRecord]:
        return [record for record in self.records if record.deck_key == deck_key]

    def stats(
        self,
        deck_key: str | None = None,
        opponent_class: str | None = None,
    ) -> dict[str, object]:
        # A record labelled ``结束`` is retained for diagnostics but is not a
        # completed result. In normal operation 105/106 are migrated above,
        # so all displayed games have a win or loss.
        records = [
            record for record in self.records
            if (deck_key is None or record.deck_key == deck_key)
            and (opponent_class is None or record.opponent_class == opponent_class)
            and record.result in {"胜利", "失败"}
        ]
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
    "format_timestamp_local",
    "orient_class_ids",
    "orient_player_order",
    "result_label",
    "terminal_match_id",
]
