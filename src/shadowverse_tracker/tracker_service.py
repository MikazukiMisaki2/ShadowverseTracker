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
from .opponent_hand import OpponentKnownHand
from .card_catalog import canonical_card_id
from .match_history import result_label
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
        self._opponent_known_hand = OpponentKnownHand()
        self._self_action_tracker = OpponentKnownHand()
        self._last_result_code: int | None = None
        self._last_turn: int | None = None
        self._played_history_lengths = [0, 0]
        self._played_history_turns: list[list[int]] = [[], []]
        self._training_initial_hands: list[list[int] | None] = [None, None]
        self._training_final_hands: list[list[int] | None] = [None, None]
        self._training_initial_self_cards_by_uid: dict[int, int] | None = None
        self._training_final_self_uids: set[int] | None = None
        self._training_self_selected_uids: set[int] = set()
        self._training_self_replaced: list[int] = []
        self._training_opponent_replaced_count: int | None = None
        self._training_opponent_mulligan_seen = False
        self._training_mulligan_events: list[dict[str, object]] = []
        self._training_seen_event_tokens: set[tuple[object, ...]] = set()
        self._event_play_history: list[list[dict[str, int]]] = [[], []]
        self._seen_play_event_tokens: set[tuple[object, ...]] = set()
        self._last_self_deck_count: int | None = None
        self._last_self_hand_size: int | None = None
        self._last_self_hand_uids: set[int] | None = None
        self._self_draw_history: list[dict[str, object]] = []
        self._seen_self_draw_event_tokens: set[tuple[object, ...]] = set()

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
            "opponent_hand_knowledge": snapshot.get("opponent_hand_knowledge"),
            "training_observation": snapshot.get("training_observation"),
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
                if is_new_match:
                    if self._selected_deck is not None:
                        self._ledger = DeckLedger(self._selected_deck)
                    self._opponent_known_hand.reset()
                    self._self_action_tracker.reset()
                    self._played_history_lengths = [0, 0]
                    self._played_history_turns = [[], []]
                    self._training_initial_hands = [None, None]
                    self._training_final_hands = [None, None]
                    self._training_initial_self_cards_by_uid = None
                    self._training_final_self_uids = None
                    self._training_self_selected_uids = set()
                    self._training_self_replaced = []
                    self._training_opponent_replaced_count = None
                    self._training_opponent_mulligan_seen = False
                    self._training_mulligan_events = []
                    self._training_seen_event_tokens = set()
                    self._event_play_history = [[], []]
                    self._seen_play_event_tokens = set()
                    self._last_self_deck_count = None
                    self._last_self_hand_size = None
                    self._last_self_hand_uids = None
                    self._self_draw_history = []
                    self._seen_self_draw_event_tokens = set()
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
            if isinstance(root, dict):
                players = root.get("players")
                if (
                    isinstance(players, (list, tuple))
                    and len(players) >= 2
                    and isinstance(players[1], dict)
                ):
                    for index, player in enumerate(players[:2]):
                        if not isinstance(player, dict):
                            continue
                        history = player.get("played_card_ids", ())
                        items = list(history) if isinstance(history, (list, tuple)) else []
                        if len(items) < self._played_history_lengths[index]:
                            self._played_history_lengths[index] = 0
                            self._played_history_turns[index] = []
                        turn = player.get("turn")
                        if not isinstance(turn, int) or turn <= 0:
                            turn = snapshot.get("current_turn", 0)
                        for _item in items[self._played_history_lengths[index]:]:
                            self._played_history_turns[index].append(turn if isinstance(turn, int) else 0)
                        self._played_history_lengths[index] = len(items)
                        player["_played_card_turns"] = list(self._played_history_turns[index])
                    if isinstance(players[0], dict) and isinstance(players[0].get("turn"), int):
                        snapshot["current_turn"] = players[0]["turn"]
                    self._capture_public_play_events(snapshot, players)
                    self._self_action_tracker.update(snapshot, players[0])
                    mine_actions = self._self_action_tracker.to_training_dict().get("recent_actions", [])
                    players[0]["_recent_actions"] = mine_actions
                    self._opponent_known_hand.update(snapshot, players[1])
                    snapshot["opponent_hand_knowledge"] = self._opponent_known_hand.to_training_dict()
                    players[1]["opponent_hand_knowledge"] = snapshot["opponent_hand_knowledge"]
                    self._update_training_observation(snapshot, players)
                    self._capture_self_draws_and_burns(snapshot, players[0])
                    if self._ledger is not None:
                        snapshot["deck_ledger"] = self._ledger.to_dict()

    def _capture_self_draws_and_burns(self, snapshot: dict[str, object], mine: dict[str, object]) -> None:
        hand = mine.get("hand")
        hand_size = len(hand) if isinstance(hand, (list, tuple)) else None
        deck_count = mine.get("deck_count")
        turn = mine.get("turn")
        if not isinstance(turn, int) or turn <= 0:
            turn = snapshot.get("current_turn", 0)
        current_cards = {
            int(card["unique_id"]): card
            for card in hand if isinstance(card, dict) and isinstance(card.get("unique_id"), int) and int(card["unique_id"]) > 0
        } if isinstance(hand, (list, tuple)) else {}
        current_uids = set(current_cards)
        deck_drop = (
            self._last_self_deck_count - deck_count
            if isinstance(deck_count, int)
            and isinstance(self._last_self_deck_count, int)
            and deck_count < self._last_self_deck_count
            else 0
        )
        if deck_drop:
            draws = deck_drop
            gained = max(0, (hand_size or 0) - (self._last_self_hand_size or 0))
            burned = max(0, draws - gained) if (self._last_self_hand_size or 0) >= 9 else 0

            # The latest BattleEvents ReactiveProperty retains the public draw
            # response even after the short-lived current-response list is
            # cleared.  A card absent from a full hand is the overdrawn card.
            named_burns = 0
            burned_card_ids: list[int] = []
            recorded_draw_uids: set[int] = set()
            events = snapshot.get("events", ())
            if isinstance(events, (list, tuple)):
                for event in events:
                    if (
                        not isinstance(event, dict)
                        or not event.get("is_ally")
                        or event.get("type") not in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect"}
                    ):
                        continue
                    cards = event.get("cards", ())
                    if not isinstance(cards, (list, tuple)):
                        continue
                    for card in cards:
                        if not isinstance(card, dict):
                            continue
                        uid = card.get("unique_id")
                        card_id = card.get("base_card_id") or card.get("card_id")
                        if not isinstance(uid, int) or not isinstance(card_id, int) or card_id <= 0:
                            continue
                        token = (event.get("address"), event.get("sequence"), uid)
                        if token in self._seen_self_draw_event_tokens:
                            continue
                        if uid not in current_uids and named_burns < burned:
                            self._seen_self_draw_event_tokens.add(token)
                            named_burns += 1
                            burned_card_ids.append(canonical_card_id(card_id))
                            self._self_draw_history.append({
                                "turn": turn,
                                "kind": "爆牌",
                                "card_id": canonical_card_id(card_id),
                                "count": 1,
                            })
                        elif uid in current_uids:
                            self._seen_self_draw_event_tokens.add(token)
                            # Cards inserted by the opening redraw belong to
                            # the final four-card baseline, not to T1 draws.
                            if not (
                                turn <= 1
                                and self._training_final_self_uids is not None
                                and uid in self._training_final_self_uids
                            ):
                                recorded_draw_uids.add(uid)
                                self._self_draw_history.append({
                                    "turn": turn,
                                    "kind": "抽取",
                                    "card_id": canonical_card_id(card_id),
                                })
            if burned > named_burns:
                self._self_draw_history.append({"turn": turn, "kind": "爆牌", "count": burned - named_burns})
            if burned and self._ledger is not None:
                self._ledger.record_burn(burned, tuple(burned_card_ids))

            # Fall back to hand-UID differences when a public draw response is
            # genuinely unavailable.  On T1, subtract the post-mulligan four
            # card baseline before doing that comparison.
            if self._last_self_hand_uids is not None:
                new_uids = current_uids - self._last_self_hand_uids
                if turn <= 1 and self._training_final_self_uids is not None:
                    new_uids -= self._training_final_self_uids
                remaining_draws = max(0, draws - burned - len(recorded_draw_uids))
                for uid in list(new_uids - recorded_draw_uids)[:remaining_draws]:
                    card = current_cards.get(uid)
                    card_id = card.get("base_card_id") or card.get("card_id") if isinstance(card, dict) else None
                    if isinstance(card_id, int) and card_id > 0:
                        self._self_draw_history.append({
                            "turn": turn,
                            "kind": "抽取",
                            "card_id": canonical_card_id(card_id),
                        })
        if isinstance(deck_count, int):
            self._last_self_deck_count = deck_count
        if isinstance(hand_size, int):
            self._last_self_hand_size = hand_size
        self._last_self_hand_uids = current_uids
        mine["_draw_history"] = list(self._self_draw_history)

    @staticmethod
    def _hand_ids(player: dict[str, object]) -> list[int]:
        hand = player.get("hand")
        if not isinstance(hand, (list, tuple)):
            return []
        values: list[int] = []
        for card in hand:
            if not isinstance(card, dict):
                continue
            value = card.get("base_card_id") or card.get("card_id")
            if isinstance(value, int) and value > 0:
                values.append(canonical_card_id(value))
        return values

    def _update_training_observation(self, snapshot: dict[str, object], players: list[object] | tuple[object, ...]) -> None:
        player_dicts = [player for player in players[:2] if isinstance(player, dict)]
        if len(player_dicts) < 2:
            return
        mine_turn = player_dicts[0].get("turn")
        mine_hand = player_dicts[0].get("hand")
        mine_cards = [card for card in mine_hand if isinstance(card, dict)] if isinstance(mine_hand, (list, tuple)) else []
        current_mine = self._hand_ids(player_dicts[0])
        current_uids = {
            int(card["unique_id"])
            for card in mine_cards
            if isinstance(card.get("unique_id"), int) and int(card["unique_id"]) > 0
        }
        if (
            self._training_initial_hands[0] is None
            and mine_turn == 0
            and len(current_mine) == 4
            and len(current_uids) == 4
        ):
            self._training_initial_hands[0] = list(current_mine)
            self._training_initial_self_cards_by_uid = {
                int(card["unique_id"]): canonical_card_id(int(card.get("base_card_id") or card.get("card_id")))
                for card in mine_cards
                if isinstance(card.get("unique_id"), int)
                and isinstance(card.get("base_card_id") or card.get("card_id"), int)
            }
        events = snapshot.get("events", ())
        if isinstance(events, (list, tuple)):
            for event in events:
                if (
                    not isinstance(event, dict)
                    or event.get("type") not in {"BattleResponseMulligan", "BattleModelMulliganSelection"}
                ):
                    continue
                # The game commonly gives both mulligan responses sequence 0.
                # Sequence-only de-duplication therefore discarded one side.
                fingerprint_token = event.get("selection_fingerprint")
                if isinstance(fingerprint_token, list):
                    fingerprint_token = tuple(fingerprint_token)
                token = (
                    event.get("address"), event.get("type"), event.get("sequence"),
                    event.get("is_ally"), event.get("change_card_flags"), fingerprint_token,
                )
                if token in self._training_seen_event_tokens:
                    continue
                self._training_seen_event_tokens.add(token)
                explicit_count = event.get("replaced_count")
                changed = event.get("change_card_flags")
                if isinstance(explicit_count, int) and 0 <= explicit_count <= 4:
                    count = explicit_count
                elif isinstance(changed, int) and changed:
                    count = bin(int(changed) & 0xF).count("1")
                else:
                    draw_num = event.get("draw_num")
                    count = int(draw_num) if isinstance(draw_num, int) and 0 < draw_num <= 4 else 0
                is_ally = bool(event.get("is_ally"))
                item = {"side": "self" if is_ally else "opponent", "replaced_count": count}
                self._training_mulligan_events.append(item)
                if is_ally:
                    fingerprint = event.get("selection_fingerprint")
                    if isinstance(fingerprint, (list, tuple)):
                        self._training_self_selected_uids = {
                            int(value) for value in fingerprint if isinstance(value, int) and value > 0
                        }
                else:
                    self._training_opponent_mulligan_seen = True
                    self._training_opponent_replaced_count = count
                if not is_ally and self._training_final_hands[1] is None:
                    self._training_final_hands[1] = self._hand_ids(player_dicts[1])

        def finalize_self_opening(cards: list[dict[str, object]]) -> None:
            if len(cards) != 4:
                return
            final_ids: list[int] = []
            final_uids: set[int] = set()
            for card in cards:
                uid = card.get("unique_id")
                card_id = card.get("base_card_id") or card.get("card_id")
                if not isinstance(uid, int) or uid <= 0 or not isinstance(card_id, int) or card_id <= 0:
                    return
                final_uids.add(uid)
                final_ids.append(canonical_card_id(card_id))
            self._training_final_self_uids = final_uids
            self._training_final_hands[0] = final_ids
            initial_by_uid = self._training_initial_self_cards_by_uid or {}
            replaced = [
                card_id
                for uid, card_id in initial_by_uid.items()
                if uid in self._training_self_selected_uids
            ]
            if not replaced and self._training_self_selected_uids:
                # Defensive fallback for snapshots that lacked UIDs in the
                # first opening-hand read.
                remaining = list(final_ids)
                for card_id in self._training_initial_hands[0] or []:
                    if card_id in remaining:
                        remaining.remove(card_id)
                    else:
                        replaced.append(card_id)
            self._training_self_replaced = replaced

        if self._training_initial_hands[0] is not None and self._training_final_hands[0] is None:
            if mine_turn == 0 and len(mine_cards) == 4:
                initial_uids = set(self._training_initial_self_cards_by_uid or {})
                selection_finished = (
                    not self._training_self_selected_uids
                    or self._training_self_selected_uids.isdisjoint(current_uids)
                )
                if current_uids != initial_uids and selection_finished:
                    finalize_self_opening(mine_cards)
            elif isinstance(mine_turn, int) and mine_turn >= 1 and len(mine_cards) >= 5:
                turn_draw_uids: set[int] = set()
                if isinstance(events, (list, tuple)):
                    for event in events:
                        if (
                            isinstance(event, dict)
                            and event.get("is_ally")
                            and event.get("type") in {"BattleResponseDrawOpen", "BattleResponseDrawOpenWithEffect"}
                            and event.get("is_turn_start_draw")
                        ):
                            cards = event.get("cards", ())
                            if isinstance(cards, (list, tuple)):
                                turn_draw_uids.update(
                                    int(card["unique_id"])
                                    for card in cards
                                    if isinstance(card, dict) and isinstance(card.get("unique_id"), int)
                                )
                opening_cards = [card for card in mine_cards if card.get("unique_id") not in turn_draw_uids]
                if len(opening_cards) != 4 and mine_turn == 1:
                    # Hand order retains the four redraw results and appends the
                    # ordinary first-turn draw.  This recovers cleanly even if
                    # the tracker attached after the draw response was cleared.
                    opening_cards = mine_cards[:4]
                finalize_self_opening(opening_cards)
        player_dicts[0]["mulligan_summary"] = {
            "initial_hand": self._training_initial_hands[0] or [],
            "replaced_cards": self._training_self_replaced,
            "final_hand": self._training_final_hands[0] or (current_mine if mine_turn == 0 else []),
        }
        player_dicts[1]["mulligan_summary"] = {
            "replaced_count": self._training_opponent_replaced_count if self._training_opponent_mulligan_seen else None,
        }
        snapshot["training_observation"] = self._build_training_observation(snapshot, player_dicts)

    def _capture_public_play_events(self, snapshot: dict[str, object], players: list[object] | tuple[object, ...]) -> None:
        """Keep public play responses for the recent-record panel.

        The model's permanent play-history list is sometimes populated only
        after an animation has completed.  The public response is available at
        the moment the card is used, so retaining it prevents the UI from
        missing a card in that interval.
        """
        events = snapshot.get("events")
        if not isinstance(events, (list, tuple)):
            return
        turn = snapshot.get("current_turn")
        if not isinstance(turn, int) or turn <= 0:
            turn = 0
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "BattleResponsePlayOpen":
                continue
            card_id = event.get("card_id")
            if not isinstance(card_id, int) or card_id <= 0:
                continue
            token = (event.get("address"), event.get("sequence"), card_id, event.get("is_ally"))
            if token in self._seen_play_event_tokens:
                continue
            self._seen_play_event_tokens.add(token)
            side = 0 if bool(event.get("is_ally")) else 1
            self._event_play_history[side].append({"turn": turn, "card_id": canonical_card_id(card_id)})
        for index, player in enumerate(players[:2]):
            if isinstance(player, dict):
                player["_event_played_cards"] = list(self._event_play_history[index])

    def _build_training_observation(self, snapshot: dict[str, object], players: list[dict[str, object]]) -> dict[str, object]:
        mine, opponent = players[0], players[1]
        result_code = mine.get("result_code") if isinstance(mine.get("result_code"), int) else 0
        result = result_label(result_code, mine.get("life") if isinstance(mine.get("life"), int) else None, opponent.get("life") if isinstance(opponent.get("life"), int) else None)
        return {
            "schema_version": 1,
            "turn": mine.get("turn"),
            "self_class_id": snapshot.get("self_class_id"),
            "opponent_class_id": snapshot.get("opponent_class_id"),
            "is_first": mine.get("is_first_side"),
            "result": result,
            "result_code": result_code,
            "mulligan": {
                "self_initial_hand": self._training_initial_hands[0] or [],
                "self_replaced_cards": self._training_self_replaced,
                "self_final_starting_hand": self._training_final_hands[0] or (
                    self._hand_ids(mine) if mine.get("turn") == 0 else []
                ),
                "opponent_replaced_count": self._training_opponent_replaced_count,
                "events": list(self._training_mulligan_events),
            },
            "played_card_turns": {
                "self": [
                    {"turn": turn, "card_id": item[0] if isinstance(item, (list, tuple)) and item else item}
                    for turn, item in zip(self._played_history_turns[0], list(mine.get("played_card_ids", ())))
                ],
                "opponent": [
                    {"turn": turn, "card_id": item[0] if isinstance(item, (list, tuple)) and item else item}
                    for turn, item in zip(self._played_history_turns[1], list(opponent.get("played_card_ids", ())))
                ],
            },
            "recent_history": {
                "self_played": [item[0] if isinstance(item, (list, tuple)) and item else item for item in mine.get("played_card_ids", ())] if isinstance(mine.get("played_card_ids"), (list, tuple)) else [],
                "opponent_played": [item[0] if isinstance(item, (list, tuple)) and item else item for item in opponent.get("played_card_ids", ())] if isinstance(opponent.get("played_card_ids"), (list, tuple)) else [],
                "self_destroyed": [item[0] if isinstance(item, (list, tuple)) and item else item for item in mine.get("destroyed_card_ids", ())] if isinstance(mine.get("destroyed_card_ids"), (list, tuple)) else [],
                "opponent_destroyed": [item[0] if isinstance(item, (list, tuple)) and item else item for item in opponent.get("destroyed_card_ids", ())] if isinstance(opponent.get("destroyed_card_ids"), (list, tuple)) else [],
                "opponent_evolutions": (snapshot.get("opponent_hand_knowledge") or {}).get("recent_evolution_events", []) if isinstance(snapshot.get("opponent_hand_knowledge"), dict) else [],
            },
            "opponent_hand_knowledge": snapshot.get("opponent_hand_knowledge"),
        }

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
                                self._opponent_known_hand.reset()
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
