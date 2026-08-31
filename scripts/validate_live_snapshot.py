#!/usr/bin/env python3
"""Continuously validate expanded battle snapshots across multiple matches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from shadowverse_tracker.tracker_service import TrackerConfig, TrackerService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=1800.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "logs" / "live_snapshot_validation.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    finished = threading.Event()
    last_status = ""
    last_summary: tuple[object, ...] | None = None
    snapshot_count = 0
    issue_count = 0

    def status(message: str) -> None:
        nonlocal last_status
        if message != last_status:
            print(f"STATUS {message}", flush=True)
            last_status = message

    def error(exc: Exception) -> None:
        nonlocal issue_count
        issue_count += 1
        print(f"ERROR {type(exc).__name__}: {exc}", flush=True)

    def snapshot(value: dict[str, object]) -> None:
        nonlocal snapshot_count, issue_count, last_summary
        snapshot_count += 1
        root = value.get("root")
        players = root.get("players") if isinstance(root, dict) else None
        if not isinstance(players, (list, tuple)) or len(players) != 2:
            issue_count += 1
            print("ISSUE missing two-player root", flush=True)
            return
        mine, opponent = players
        if not isinstance(mine, dict) or not isinstance(opponent, dict):
            return
        hand = mine.get("hand")
        field = mine.get("field")
        enemy_field = opponent.get("field")
        def unique_ids(cards: object) -> set[object]:
            if not isinstance(cards, (list, tuple)):
                return set()
            return {
                card.get("unique_id")
                for card in cards
                if isinstance(card, dict)
            }

        hand_ids = unique_ids(hand)
        field_ids = unique_ids(field)
        enemy_ids = unique_ids(enemy_field)
        valid_target_ids = set(enemy_ids)
        valid_target_ids.add(opponent.get("unique_id"))
        valid_target_ids.discard(None)
        legal = value.get("legal_actions")
        issues: list[str] = []
        if not isinstance(legal, dict):
            issues.append("legal_actions unavailable")
        else:
            for key in (
                "can_play_cards",
                "can_play_cards_with_extra_pp",
                "can_enhance_play_cards",
                "can_accelerate_play_cards",
                "can_crystal_play_cards",
                "can_fusion_cards",
                "has_fusion_hand_cards",
            ):
                unknown = set(legal.get(key, ())) - hand_ids
                if unknown:
                    issues.append(f"{key} outside hand: {sorted(unknown)}")
            for key in (
                "can_attack_leader_cards",
                "can_attack_field_cards",
                "attacked_cards",
                "can_activation_field_cards",
                "has_activation_field_cards",
                "can_evolve_cards",
                "can_super_evolve_cards",
            ):
                unknown = set(legal.get(key, ())) - field_ids
                if unknown:
                    issues.append(f"{key} outside field: {sorted(unknown)}")
            target_map = legal.get("attack_targets")
            if isinstance(target_map, dict):
                for attacker, targets in target_map.items():
                    try:
                        attacker_id = int(attacker)
                    except (TypeError, ValueError):
                        issues.append(f"invalid attacker key: {attacker!r}")
                        continue
                    if attacker_id not in field_ids:
                        issues.append(f"attack target source outside field: {attacker_id}")
                    unknown_targets = set(targets) - valid_target_ids
                    if unknown_targets:
                        issues.append(
                            f"attack targets outside enemy field: {sorted(unknown_targets)}"
                        )
        if issues:
            issue_count += len(issues)
            print("ISSUE " + " | ".join(issues), flush=True)
        summary = (
            value.get("address"),
            mine.get("turn"),
            root.get("is_ally_turn") if isinstance(root, dict) else None,
            mine.get("pp"),
            mine.get("rally"),
            mine.get("play_count"),
            tuple(sorted(hand_ids - {None})),
            tuple(sorted(field_ids - {None})),
            tuple(sorted(enemy_ids - {None})),
            tuple(issues),
        )
        if summary != last_summary:
            print(
                "SNAPSHOT "
                + json.dumps(
                    {
                        "model": value.get("address"),
                        "turn": mine.get("turn"),
                        "ally_turn": root.get("is_ally_turn") if isinstance(root, dict) else None,
                        "pp": mine.get("pp"),
                        "rally": mine.get("rally"),
                        "play_count": mine.get("play_count"),
                        "hand": len(hand_ids - {None}),
                        "field": len(field_ids - {None}),
                        "enemy_field": len(enemy_ids - {None}),
                        "legal_actions": isinstance(legal, dict),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_summary = summary

    service = TrackerService(
        TrackerConfig(output_path=args.output, reveal_opponent_hand=False),
        on_snapshot=snapshot,
        on_error=error,
        on_status=status,
    )
    service.start()
    try:
        finished.wait(args.duration)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
    print(f"DONE snapshots={snapshot_count} issues={issue_count} output={args.output}", flush=True)
    return 0 if issue_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
