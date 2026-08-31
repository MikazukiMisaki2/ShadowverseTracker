"""Background, read-only battle-state polling service.

The service deliberately owns no debugger integration and exposes no process
write/injection operations.  A UI can start it once and receive snapshots while
the game continues normally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Callable

from .deck_ledger import DeckLedger
from .memory.battle import read_battle_model
from .memory.deck import DeckInfoSnapshot
from .memory.discovery import find_battle_models
from .memory.win32 import ProcessReader, find_process
from .versioning import verify_process_version


@dataclass(frozen=True)
class TrackerConfig:
    process_name: str = "ShadowverseWB.exe"
    model_address: int = 0
    pid: int | None = None
    interval: float = 0.25
    output_path: Path | None = None
    selected_deck: DeckInfoSnapshot | None = None
    selected_deck_key: str | None = None
    reveal_opponent_hand: bool = True


def without_addresses(value: object) -> object:
    """Remove managed-object addresses from a snapshot for stable comparison."""
    if isinstance(value, dict):
        return {
            key: without_addresses(item)
            for key, item in value.items()
            if key != "address"
        }
    if isinstance(value, list):
        return [without_addresses(item) for item in value]
    return value


class TrackerService:
    """Poll a BattleModel on a worker thread and publish semantic changes."""

    def __init__(
        self,
        config: TrackerConfig,
        *,
        on_snapshot: Callable[[dict[str, object]], None],
        on_error: Callable[[Exception], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_deck: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if config.interval <= 0:
            raise ValueError("interval must be positive")
        self.config = config
        self.on_snapshot = on_snapshot
        self.on_error = on_error
        self.on_status = on_status
        self.on_deck = on_deck
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._previous: object | None = None
        self._output_handle = None
        self._pid: int | None = None
        self._model_address = config.model_address
        self._deck_lock = threading.RLock()
        self._selected_deck = config.selected_deck
        self._selected_deck_key = config.selected_deck_key
        self._ledger = DeckLedger(config.selected_deck) if config.selected_deck else None
        self._last_result_code: int | None = None
        self._last_turn: int | None = None

    def set_selected_deck(self, deck: DeckInfoSnapshot | None, deck_key: str | None = None) -> None:
        """Switch the local ledger without interrupting battle-state polling."""
        with self._deck_lock:
            if self._selected_deck == deck:
                return
            self._selected_deck = deck
            self._selected_deck_key = deck_key
            self._ledger = DeckLedger(deck) if deck else None
            self._previous = None
        if self.on_deck:
            self.on_deck(deck.to_dict() if deck else {})
        if self.on_status:
            if deck:
                self.on_status(f"已切换牌组：{deck.deck_name}（{deck.total_cards} 张）")
            else:
                self.on_status("未选择本地牌组；对局状态仍会继续读取")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="svwb-reader", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        if self._output_handle is not None:
            self._output_handle.close()
            self._output_handle = None

    def _emit(self, snapshot: dict[str, object]) -> None:
        root = snapshot.get("root")
        if root is None:
            return
        semantic = without_addresses({
            "root": root,
            "deck_ledger": snapshot.get("deck_ledger"),
        })
        if semantic == self._previous:
            return
        self._previous = semantic
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": self._pid,
            "model": f"0x{self._model_address:016X}",
            "snapshot": snapshot,
        }
        if self._output_handle is not None:
            self._output_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._output_handle.flush()
        self.on_snapshot(snapshot)

    def _attach_deck_state(self, snapshot: dict[str, object]) -> None:
        root = snapshot.get("root")
        mine: dict[str, object] | None = None
        if isinstance(root, dict):
            players = root.get("players")
            if isinstance(players, (list, tuple)) and players and isinstance(players[0], dict):
                mine = players[0]
        with self._deck_lock:
            if mine is not None:
                turn = mine.get("turn")
                result_code = mine.get("result_code")
                is_new_match = (
                    isinstance(turn, int)
                    and self._last_turn is not None
                    and turn + 2 < self._last_turn
                ) or (
                    isinstance(result_code, int)
                    and result_code == 0
                    and self._last_result_code not in (None, 0)
                )
                if is_new_match and self._selected_deck is not None:
                    self._ledger = DeckLedger(self._selected_deck)
                self._last_turn = turn if isinstance(turn, int) else self._last_turn
                self._last_result_code = (
                    result_code if isinstance(result_code, int) else self._last_result_code
                )
            if self._selected_deck is not None:
                deck_info = self._selected_deck.to_dict()
                if self._selected_deck_key:
                    deck_info["deck_key"] = self._selected_deck_key
                snapshot["deck"] = deck_info
            if self._ledger is not None:
                snapshot["deck_ledger"] = self._ledger.update(snapshot)

    def _run(self) -> None:
        if self.config.output_path:
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_handle = (
            self.config.output_path.open("a", encoding="utf-8", buffering=1)
            if self.config.output_path
            else None
        )
        while not self._stop.is_set():
            try:
                pid = self.config.pid or find_process(self.config.process_name).pid
                self._pid = pid
                with ProcessReader(pid) as reader:
                    profile = verify_process_version(reader)
                    if self.on_status:
                        self.on_status(f"版本 {profile.game_version} 校验通过")
                    consecutive_errors = 0
                    while not self._stop.is_set():
                        if self._model_address <= 0:
                            if self.on_status:
                                self.on_status("正在自动寻找对局对象…")
                            models = find_battle_models(
                                reader,
                                class_pointer_rva=profile.battle_model_class_pointer_rva,
                            )
                            if not models:
                                if self.on_status:
                                    self.on_status("尚未进入对局，等待后自动重试")
                                self._stop.wait(2.0)
                                continue
                            self._model_address = models[-1]
                            self._previous = None
                            with self._deck_lock:
                                self._ledger = (
                                    DeckLedger(self._selected_deck) if self._selected_deck else None
                                )
                                self._last_turn = None
                                self._last_result_code = None
                            if self.on_status:
                                self.on_status(f"已自动连接 0x{self._model_address:X}")
                        try:
                            snapshot = read_battle_model(
                                reader,
                                self._model_address,
                                reveal_opponent_hand=self.config.reveal_opponent_hand,
                            )
                            self._attach_deck_state(snapshot)
                            self._emit(snapshot)
                            consecutive_errors = 0
                        except (OSError, ValueError, LookupError) as exc:
                            consecutive_errors += 1
                            if self.on_error:
                                self.on_error(exc)
                            if self.config.model_address <= 0 and consecutive_errors >= 4:
                                self._model_address = 0
                                consecutive_errors = 0
                        self._stop.wait(self.config.interval)
            except Exception as exc:
                if self.on_status:
                    self.on_status(f"等待游戏启动或重新连接：{exc}")
                self._model_address = 0 if self.config.model_address <= 0 else self.config.model_address
                self._stop.wait(2.0)
