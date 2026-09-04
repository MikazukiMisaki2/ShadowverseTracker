"""Minimal desktop shell for the external read-only tracker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from functools import lru_cache
import math
import os
from pathlib import Path
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
try:
    from PIL import Image, ImageTk
except ImportError:  # image support remains optional for source runs
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]

from .card_catalog import (
    canonical_card_id,
    get_card_metadata,
    get_card_name,
    is_card_allowed,
    latest_card_pack,
    load_card_catalog,
)
from .deck_repository import DeckRepository, SavedDeck
from .faith_probability import calculate_faith_damage_probability
from .memory.deck import DeckCard
from .official_deck import OfficialDeck, OfficialDeckError, import_deck_code, parse_official_deck
from .match_history import CLASS_NAMES, MatchHistory, MatchRecord, class_name, result_label, terminal_match_id
from .opponent_hand import UNKNOWN_CARD_TYPE_LABELS, OpponentKnownHand
from .opponent_key_probability import calculate_key_probability
from .tracker_service import TrackerConfig, TrackerService


class TrackerApp(tk.Tk):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.title("Shadowverse Tracker")
        self._app_icon: object | None = None
        self._set_application_icon()
        self.geometry("1280x760")
        self.minsize(1000, 620)
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._service: TrackerService | None = None
        self._startup_pid: int | None = getattr(args, "pid", None)
        self._repository = DeckRepository()
        self._repository_error = ""
        try:
            self._repository.load()
        except (OSError, ValueError) as exc:
            self._repository_error = str(exc)
        self._match_history = MatchHistory()
        self._match_history_error = ""
        try:
            self._match_history.load()
        except (OSError, ValueError) as exc:
            self._match_history_error = str(exc)
        self._match_sequence = 0
        self._match_id: str | None = None
        self._match_deck_key: str | None = None
        self._last_model_address: str | None = None
        self._last_render_turn: int | None = None
        self._last_render_result: int | None = None
        self._deck_choice_keys: list[str] = []
        self._opponent_known_hand = OpponentKnownHand()
        self._last_snapshot: dict[str, object] | None = None
        self._overlay: tk.Toplevel | None = None
        self._overlay_canvas: tk.Canvas | None = None
        self._overlay_drag_origin: tuple[int, int] | None = None
        self._overlay_resize_origin: tuple[int, int, int, int] | None = None
        self._overlay_images: dict[tuple[int, int], object] = {}
        self._probability_window: tk.Toplevel | None = None
        self._card_image_paths: dict[int, Path | None] = {}
        self._card_image_roots = self._find_card_image_roots()
        self._build_ui(args)
        self.after(100, self._drain_events)
        # Reading runs automatically; the manual address/button remain
        # available only through the settings/debug build, not the main UI.
        self.after(300, self._connect)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self, args: argparse.Namespace) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#dfe7f0")
        style.configure("TLabelframe", background="#eaf0f6", foreground="#182635", bordercolor="#9aabbd", relief="flat")
        style.configure("TLabelframe.Label", background="#eaf0f6", foreground="#182635", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background="#eaf0f6", foreground="#182635")
        style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
        style.configure("TCheckbutton", background="#eaf0f6", foreground="#182635")
        style.map("TCheckbutton", background=[("active", "#d6e1ec")])
        style.configure("TEntry", fieldbackground="#f6f8fb", foreground="#182635", insertcolor="#182635")
        style.configure("TSpinbox", fieldbackground="#f6f8fb", foreground="#182635", insertcolor="#182635")
        style.configure("TCombobox", fieldbackground="#f6f8fb", background="#d4e0ec", foreground="#182635")
        style.configure("TPanedwindow", background="#dfe7f0")

        root = ttk.Frame(self, padding=12, style="App.TFrame")
        root.pack(fill="both", expand=True)

        decks = ttk.LabelFrame(root, text="本地牌组仓库", padding=8)
        decks.pack(fill="x")
        decks.columnconfigure(1, weight=1)
        ttk.Label(decks, text="当前牌组").grid(row=0, column=0, sticky="w")
        self.deck_choice_var = tk.StringVar()
        self.deck_choice = ttk.Combobox(
            decks,
            textvariable=self.deck_choice_var,
            state="readonly",
            width=48,
        )
        self.deck_choice.grid(row=0, column=1, padx=6, sticky="ew")
        self.deck_choice.bind("<<ComboboxSelected>>", self._select_deck)
        ttk.Button(decks, text="删除牌组", command=self._delete_deck).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(decks, text="清空当前牌组", command=self._clear_deck_selection).grid(
            row=0, column=3, padx=(6, 0)
        )
        # Match recording is opt-in and is started manually by the checkbox.
        self.record_matches_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            decks,
            text="启用胜负统计（本地）",
            variable=self.record_matches_var,
            command=self._toggle_match_recording,
        ).grid(row=0, column=4, padx=(12, 0))
        ttk.Button(decks, text="对局统计", command=self._show_match_stats).grid(
            row=0, column=5, padx=(6, 0)
        )
        ttk.Button(decks, text="编辑当前卡组", command=self._edit_current_deck).grid(
            row=0, column=6, padx=(6, 0)
        )
        self.overlay_button = ttk.Button(
            decks, text="打开悬浮记牌器", command=self._toggle_overlay
        )
        self.overlay_button.grid(row=0, column=7, padx=(6, 0))
        ttk.Button(decks, text="概率计算", command=self._open_probability_window).grid(
            row=0, column=8, padx=(6, 0)
        )

        active_deck = self._active_saved_deck()
        default_class = class_name(active_deck.class_id) if active_deck else class_name(1)
        default_mode = "轮换" if active_deck is None or active_deck.format_version == 1 else "无限"
        ttk.Label(decks, text="登记职业").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.import_class_var = tk.StringVar(value=default_class)
        self.import_class_choice = ttk.Combobox(
            decks,
            textvariable=self.import_class_var,
            values=[CLASS_NAMES[index] for index in sorted(CLASS_NAMES)],
            state="readonly",
            width=14,
        )
        self.import_class_choice.grid(row=1, column=1, padx=6, pady=(8, 0), sticky="w")
        ttk.Label(decks, text="模式").grid(row=1, column=2, sticky="e", pady=(8, 0))
        self.import_mode_var = tk.StringVar(value=default_mode)
        ttk.Combobox(
            decks,
            textvariable=self.import_mode_var,
            values=("轮换", "无限"),
            state="readonly",
            width=10,
        ).grid(row=1, column=3, padx=6, pady=(8, 0), sticky="w")
        ttk.Label(
            decks,
            text="新增卡牌仅显示所选职业与中立；轮换为最新六个卡包",
        ).grid(row=1, column=4, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(decks, text="链接 / 四位牌组码").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.deck_url_var = tk.StringVar()
        ttk.Entry(decks, textvariable=self.deck_url_var).grid(
            row=2, column=1, columnspan=4, padx=6, pady=(8, 0), sticky="ew"
        )
        ttk.Button(decks, text="导入并保存", command=self._import_deck).grid(
            row=2, column=5, padx=(6, 0), pady=(8, 0)
        )
        self.deck_status_var = tk.StringVar()
        ttk.Label(decks, textvariable=self.deck_status_var).grid(
            row=3, column=0, columnspan=6, sticky="w", pady=(8, 0)
        )

        connection = ttk.LabelFrame(root, text="只读连接", padding=8)
        connection.pack(fill="x", pady=(10, 0))
        self.model_label = ttk.Label(connection, text="BattleModel 地址")
        self.model_label.grid(row=0, column=0, sticky="w")
        self.model_var = tk.StringVar(value=f"0x{args.model:X}" if args.model else "")
        self.model_entry = ttk.Entry(connection, textvariable=self.model_var, width=22)
        self.model_entry.grid(row=0, column=1, padx=6)
        self.model_hint = ttk.Label(connection, text="（留空自动发现）")
        self.model_hint.grid(row=0, column=2, sticky="w")
        self.connect_button = ttk.Button(connection, text="开始读取", command=self._connect)
        self.connect_button.grid(row=0, column=3, padx=(12, 0))
        self.status_var = tk.StringVar(value="未连接（自动寻找 Steam / 国服客户端）")
        ttk.Label(connection, textvariable=self.status_var).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.model_label.grid_remove()
        self.model_entry.grid_remove()
        self.model_hint.grid_remove()
        self.connect_button.grid_remove()
        self.opponent_counter_var = tk.StringVar(value="通用计数器：等待对局数据")
        self.class_counter_var = tk.StringVar(value="职业计数器：等待对局数据")
        counter_frame = ttk.LabelFrame(connection, text="通用计数器")
        counter_frame.grid(row=0, column=5, rowspan=4, padx=(18, 0), sticky="nsew")
        ttk.Label(counter_frame, textvariable=self.opponent_counter_var, justify="left", anchor="nw").pack(
            fill="both", expand=True, padx=8, pady=6
        )
        class_frame = ttk.LabelFrame(connection, text="对手职业计数器")
        class_frame.grid(row=0, column=6, rowspan=4, padx=(8, 0), sticky="nsew")
        ttk.Label(class_frame, textvariable=self.class_counter_var, justify="left", anchor="nw").pack(
            fill="both", expand=True, padx=8, pady=6
        )
        connection.columnconfigure(5, weight=1)
        connection.columnconfigure(6, weight=1)

        details = ttk.PanedWindow(root, orient="horizontal")
        details.pack(fill="both", expand=True, pady=(10, 0))
        self.hand_text = self._overview_panel(details)
        self.deck_text = self._text_panel(details, "剩余牌库")
        self.field_text = self._text_panel(details, "目前对局")
        self.history_text = self._text_panel(details, "最近记录")
        self.deck_text.tag_configure("deck_header", font=("Segoe UI", 14, "bold"))
        self.deck_text.tag_configure("deck_section", font=("Segoe UI", 10, "bold"), foreground="#24527a")
        self._build_probability_window()
        self._refresh_deck_choices()
        self._update_stats_summary()

    def _build_probability_window(self) -> None:
        """Create the optional calculator window and keep it hidden by default."""
        if self._probability_window is not None and self._probability_window.winfo_exists():
            return

        window = tk.Toplevel(self)
        window.title("Shadowverse Tracker - 概率计算")
        window.geometry("1000x430")
        window.minsize(760, 360)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        window.columnconfigure(0, weight=1)
        body = ttk.Frame(window, padding=10, style="App.TFrame")
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        draw_frame = ttk.LabelFrame(body, text="抽牌概率", padding=6)
        draw_frame.grid(row=0, column=0, sticky="ew")
        draw_frame.columnconfigure(1, weight=1)
        ttk.Label(draw_frame, text="目标卡牌").grid(row=0, column=0, sticky="w")
        self.probability_card_var = tk.StringVar()
        self.probability_card_choice = ttk.Combobox(
            draw_frame,
            textvariable=self.probability_card_var,
            state="readonly",
            width=42,
        )
        self.probability_card_choice.grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Label(draw_frame, text="未来抽牌").grid(row=0, column=2, sticky="e")
        self.probability_draws_var = tk.StringVar(value="1")
        ttk.Entry(draw_frame, textvariable=self.probability_draws_var, width=6).grid(
            row=0, column=3, padx=(6, 0), sticky="w"
        )
        self.probability_result_var = tk.StringVar(value="选择牌库中的卡牌后计算")
        ttk.Button(draw_frame, text="计算", command=self._calculate_draw_probability).grid(
            row=0, column=4, padx=(8, 0), sticky="w"
        )
        ttk.Label(draw_frame, textvariable=self.probability_result_var).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(6, 0)
        )
        self._probability_cards: dict[str, tuple[int, int, int]] = {}

        # Opponent key-card probability. Deck/hand/swap values are filled from
        # Tracker snapshots; only mulligan policy and the queried key
        # assumptions need to be supplied by the user.
        key_frame = ttk.LabelFrame(
            body,
            text="对手关键牌概率（固定首回合抽1张，起手换4张模型）",
            padding=6,
        )
        key_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.key_strategy_var = tk.StringVar(value="unknown")
        ttk.Label(key_frame, text="策略").grid(row=0, column=0, sticky="w")
        strategy_choice = ttk.Combobox(
            key_frame,
            textvariable=self.key_strategy_var,
            values=("known", "unknown"),
            state="readonly",
            width=9,
        )
        strategy_choice.grid(row=0, column=1, padx=4)
        self.key_keep1_var = tk.StringVar(value="0")
        self.key_keep2_var = tk.StringVar(value="0")
        self.key_seen1_var = tk.StringVar(value="0")
        self.key_seen2_var = tk.StringVar(value="0")
        self.key_copies_var = tk.StringVar(value="3")
        self.key_limit_var = tk.StringVar(value="1")
        self.key_seen_var = tk.StringVar(value="0")
        self._key_policy_entries: list[ttk.Entry] = []
        for column, label, variable in (
            (2, "留1类型", self.key_keep1_var),
            (4, "留2类型", self.key_keep2_var),
            (6, "已见留1", self.key_seen1_var),
            (8, "已见留2", self.key_seen2_var),
        ):
            ttk.Label(key_frame, text=label).grid(
                row=0, column=column, padx=(8, 2), sticky="e"
            )
            entry = ttk.Entry(key_frame, textvariable=variable, width=5)
            entry.grid(row=0, column=column + 1, padx=2)
            self._key_policy_entries.append(entry)
        self.key_deck_remaining_var = tk.StringVar(value="—")
        self.key_hand_size_var = tk.StringVar(value="—")
        self.key_mulligan_var = tk.StringVar(value="—")
        for column, label, variable in (
            (10, "牌库剩余", self.key_deck_remaining_var),
            (12, "未知手牌", self.key_hand_size_var),
            (14, "对手换牌数", self.key_mulligan_var),
        ):
            ttk.Label(key_frame, text=label).grid(
                row=0, column=column, padx=(8, 2), sticky="e"
            )
            ttk.Label(
                key_frame,
                textvariable=variable,
                width=5,
                relief="sunken",
                anchor="center",
            ).grid(row=0, column=column + 1, padx=2)
        for column, label, variable in (
            (0, "Key投入", self.key_copies_var),
            (3, "Key留牌上限", self.key_limit_var),
            (6, "Key已见", self.key_seen_var),
        ):
            ttk.Label(key_frame, text=label).grid(
                row=1, column=column, padx=(8, 2), pady=(5, 0), sticky="e"
            )
            entry = ttk.Entry(key_frame, textvariable=variable, width=5)
            entry.grid(row=1, column=column + 1, padx=2, pady=(5, 0))
            if variable is self.key_limit_var:
                self._key_policy_entries.append(entry)
        self.key_probability_result_var = tk.StringVar(value="等待对手对局数据")
        ttk.Button(
            key_frame,
            text="计算对手Key概率",
            command=self._calculate_opponent_key_probability,
        ).grid(row=1, column=8, columnspan=3, padx=6, pady=(5, 0), sticky="w")
        ttk.Button(
            key_frame,
            text="计算对手下回合Key概率",
            command=self._calculate_opponent_next_turn_key_probability,
        ).grid(row=1, column=11, columnspan=4, padx=6, pady=(5, 0), sticky="w")
        ttk.Label(key_frame, textvariable=self.key_probability_result_var).grid(
            row=2, column=0, columnspan=17, sticky="w", pady=(5, 0)
        )
        strategy_choice.bind("<<ComboboxSelected>>", self._sync_key_strategy_inputs)

        faith_frame = ttk.LabelFrame(
            body,
            text="天晶深渊伤害概率（X/Y/Z 独立逐点分配）",
            padding=6,
        )
        faith_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(faith_frame, text="信仰总值 X+Y+Z").grid(
            row=0, column=0, sticky="w"
        )
        self.faith_total_var = tk.StringVar(value="")
        ttk.Entry(faith_frame, textvariable=self.faith_total_var, width=7).grid(
            row=0, column=1, padx=(6, 16)
        )
        ttk.Label(faith_frame, text="需要 Z ≥").grid(row=0, column=2, sticky="e")
        self.faith_min_z_var = tk.StringVar(value="")
        ttk.Entry(faith_frame, textvariable=self.faith_min_z_var, width=7).grid(
            row=0, column=3, padx=6
        )
        self.faith_probability_result_var = tk.StringVar(
            value="每个信仰点以 1/3 概率分配给 X、Y、Z"
        )
        ttk.Button(
            faith_frame,
            text="计算天晶深渊概率",
            command=self._calculate_faith_damage_probability,
        ).grid(row=0, column=4, padx=(6, 12), sticky="w")
        ttk.Label(
            faith_frame,
            textvariable=self.faith_probability_result_var,
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(5, 0))

        self._probability_window = window
        self._sync_key_strategy_inputs()
        window.withdraw()

    def _open_probability_window(self) -> None:
        """Show the calculator window from the main toolbar."""
        self._build_probability_window()
        window = self._probability_window
        if window is None:
            return
        window.deiconify()
        window.lift()
        window.focus_force()

    @staticmethod
    def _app_asset_path(name: str) -> Path | None:
        """Locate bundled UI assets in both source and PyInstaller runs."""
        package_root = Path(__file__).resolve().parent
        roots = [package_root / "assets"]
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            roots.insert(0, Path(frozen_root) / "shadowverse_tracker" / "assets")
        return next((root / name for root in roots if (root / name).is_file()), None)

    def _set_application_icon(self) -> None:
        """Use Kandima artwork for the title bar, taskbar, and app icon."""
        icon_ico = self._app_asset_path("kandima_icon.ico")
        if icon_ico is not None:
            try:
                self.iconbitmap(default=str(icon_ico))
            except tk.TclError:
                pass
        icon_png = self._app_asset_path("kandima_icon.png")
        if icon_png is not None:
            try:
                self._app_icon = tk.PhotoImage(file=str(icon_png))
                self.iconphoto(True, self._app_icon)
            except tk.TclError:
                pass

    def _toggle_overlay(self) -> None:
        """Show or hide the lightweight Canvas overlay."""
        if self._overlay is not None and self._overlay.winfo_exists():
            self._overlay.destroy()
            self._overlay = None
            self._overlay_canvas = None
            self.overlay_button.configure(text="打开悬浮记牌器")
            return
        overlay = tk.Toplevel(self)
        overlay.title("Shadowverse 悬浮记牌器")
        overlay.geometry("430x1080+40+40")
        overlay.minsize(360, 520)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="#00ff00")
        try:
            overlay.overrideredirect(True)
            overlay.wm_attributes("-transparentcolor", "#00ff00")
        except tk.TclError:
            # Non-Windows platforms simply retain the solid Canvas background.
            overlay.configure(bg="#e9eef4")
        canvas = tk.Canvas(
            overlay, bg="#00ff00", highlightthickness=0, borderwidth=0
        )
        canvas.pack(fill="both", expand=True)
        self._overlay = overlay
        self._overlay_canvas = canvas
        self.overlay_button.configure(text="关闭悬浮记牌器")
        canvas.bind("<ButtonPress-1>", self._overlay_press)
        canvas.bind("<B1-Motion>", self._overlay_drag)
        canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_overlay_resize_origin", None))
        canvas.tag_bind("resize_handle", "<ButtonPress-1>", self._overlay_resize_press)
        canvas.tag_bind("resize_handle", "<B1-Motion>", self._overlay_resize_drag)
        overlay.bind("<Configure>", lambda _event: self.after_idle(lambda: self._render_overlay(self._last_snapshot)), add="+")
        overlay.bind("<Escape>", lambda _event: self._toggle_overlay())
        overlay.protocol("WM_DELETE_WINDOW", self._toggle_overlay)
        self._render_overlay(self._last_snapshot)

    @staticmethod
    def _find_card_image_roots() -> list[Path]:
        """Find an optional card-image pack placed beside the repository."""
        project_root = Path(__file__).resolve().parents[2]
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if getattr(sys, "frozen", False) else project_root
        roots = [
            runtime_root / "SV_WB_Cards",
            runtime_root / "SV_WB_Cards" / "SV_WB_Cards",
            project_root / "SV_WB_Cards",
            project_root / "SV_WB_Cards" / "SV_WB_Cards",
            Path(__file__).resolve().parents[3] / "SV_WB_Cards",
            Path(__file__).resolve().parents[3] / "SV_WB_Cards" / "SV_WB_Cards",
            Path.cwd() / "SV_WB_Cards",
            Path.cwd() / "SV_WB_Cards" / "SV_WB_Cards",
        ]
        return list(dict.fromkeys(path for path in roots if path.is_dir()))

    def _card_image(self, card_id: object, height: int = 38) -> object | None:
        if not isinstance(card_id, int) or card_id <= 0 or Image is None or ImageTk is None:
            return None
        cache_key = (card_id, height)
        cached = self._overlay_images.get(cache_key)
        if cached is not None:
            return cached
        path = self._card_image_paths.get(card_id)
        if path is None and card_id not in self._card_image_paths:
            path = None
            token = str(card_id)
            for root in self._card_image_roots:
                candidates = list(root.rglob("*.webp")) + list(root.rglob("*.png"))
                matches = [
                    item for item in candidates
                    if re.search(rf"(?:^|_){re.escape(token)}(?:_|@|$)", item.stem)
                ]
                if matches:
                    # Prefer the base illustration over an evolution/style variant.
                    path = next((item for item in matches if "_evo" not in item.stem and "@" not in item.stem), matches[0])
                    break
            self._card_image_paths[card_id] = path
        if path is None:
            return None
        try:
            image = Image.open(path).convert("RGBA")
            ratio = height / max(image.height, 1)
            image = image.resize((max(1, int(image.width * ratio)), height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._overlay_images[cache_key] = photo
            return photo
        except (OSError, ValueError, tk.TclError):
            return None

    def _overlay_press(self, event: tk.Event) -> None:
        if self._overlay_resize_origin is not None:
            return
        self._overlay_drag_origin = (event.x_root, event.y_root)

    def _overlay_drag(self, event: tk.Event) -> None:
        if self._overlay_resize_origin is not None:
            return
        if self._overlay is None or self._overlay_drag_origin is None:
            return
        old_x, old_y = self._overlay_drag_origin
        x = self._overlay.winfo_x() + event.x_root - old_x
        y = self._overlay.winfo_y() + event.y_root - old_y
        self._overlay.geometry(f"+{x}+{y}")
        self._overlay_drag_origin = (event.x_root, event.y_root)

    def _overlay_resize_press(self, event: tk.Event) -> None:
        if self._overlay is None:
            return
        self._overlay_resize_origin = (
            event.x_root,
            event.y_root,
            self._overlay.winfo_width(),
            self._overlay.winfo_height(),
        )

    def _overlay_resize_drag(self, event: tk.Event) -> None:
        if self._overlay is None or self._overlay_resize_origin is None:
            return
        old_x, old_y, old_width, old_height = self._overlay_resize_origin
        width = max(260, old_width + event.x_root - old_x)
        height = max(360, old_height + event.y_root - old_y)
        self._overlay.geometry(f"{width}x{height}")

    def _render_overlay(self, snapshot: dict[str, object] | None) -> None:
        canvas = self._overlay_canvas
        if canvas is None or self._overlay is None or not self._overlay.winfo_exists():
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 520)
        panel = "#e9eef4"
        border = "#91a4b8"
        text = "#172536"
        muted = "#40576d"
        canvas.create_rectangle(8, 8, width - 8, height - 8, fill=panel, outline=border, width=1)
        # Keep the three win-rate values and their game counts on one compact
        # line even at the default narrow overlay width.
        canvas.create_text(20, 16, anchor="nw", text=self._overlay_win_rate_summary(), fill=text, font=("Segoe UI", 8, "bold"))
        if not isinstance(snapshot, dict):
            active = self._active_saved_deck()
            if active is None:
                canvas.create_text(24, 42, anchor="nw", text="等待对局数据…", fill=text, font=("Segoe UI", 13, "bold"))
                canvas.create_text(24, 70, anchor="nw", text="拖动此窗口可调整位置，Esc 关闭", fill=muted, font=("Segoe UI", 10))
                return
            snapshot = {
                "root": {"players": [{"deck_count": active.total_cards}, {}]},
                "deck_ledger": {
                    "deck_name": active.name,
                    "authoritative_deck_count": active.total_cards,
                    "rows": [
                        {"card_id": card.card_id, "initial": card.count, "remaining": card.count}
                        for card in active.cards
                    ],
                },
            }
        root = snapshot.get("root")
        players = root.get("players", []) if isinstance(root, dict) else []
        if not isinstance(players, (list, tuple)) or len(players) < 2 or not all(isinstance(p, dict) for p in players[:2]):
            canvas.create_text(24, 42, anchor="nw", text="等待对局数据…", fill=text, font=("Segoe UI", 13, "bold"))
            return
        mine, opponent = players[0], players[1]
        canvas.create_text(20, 38, anchor="nw", text="剩余牌库", fill=text, font=("Segoe UI", 16, "bold"))
        ledger = snapshot.get("deck_ledger")
        deck_name = str(ledger.get("deck_name") or "当前牌组") if isinstance(ledger, dict) else "当前牌组"
        deck_count = ledger.get("authoritative_deck_count", mine.get("deck_count", "?")) if isinstance(ledger, dict) else mine.get("deck_count", "?")
        initial = sum(int(row.get("initial", 0)) for row in ledger.get("rows", ()) if isinstance(row, dict)) if isinstance(ledger, dict) else 40
        canvas.create_text(20, 67, anchor="nw", text=f"{deck_name}    {deck_count} / {initial}", fill=text, font=("Segoe UI", 12, "bold"))
        canvas.create_line(18, 96, width - 18, 96, fill=border)
        ledger = snapshot.get("deck_ledger")
        rows = ledger.get("rows", []) if isinstance(ledger, dict) else []
        rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get("remaining"), int)]
        # Keep depleted cards visible at the end of the overlay rather than
        # making them disappear from the player's mental deck list.
        rows = sorted(rows, key=lambda row: (row.get("remaining", 0) <= 0, self._card_sort_key(row)))
        if not rows:
            canvas.create_text(20, 114, anchor="nw", text="等待牌库数据…", fill=muted, font=("Segoe UI", 10))
        else:
            usable_width = width - 28
            usable_height = height - 126
            # Select the grid that gives each card the largest proportional
            # thumbnail while keeping every remaining card inside the window.
            best_columns, best_card_h = 1, 1.0
            image_ratio = 530 / 687
            for columns in range(1, len(rows) + 1):
                grid_rows = (len(rows) + columns - 1) // columns
                tile_width = usable_width / columns
                tile_height = usable_height / grid_rows
                card_height = min(tile_height - 6, (tile_width - 10) / image_ratio)
                if card_height > best_card_h:
                    best_columns, best_card_h = columns, card_height
            columns = best_columns
            grid_rows = (len(rows) + columns - 1) // columns
            col_width = usable_width / columns
            row_height = usable_height / grid_rows
            card_w = int(col_width - 8)
            card_h = max(22, int(best_card_h))
            for index, row in enumerate(rows):
                line, col = divmod(index, columns)
                x = 14 + col * col_width
                y = 106 + line * row_height
                value = row.get("card_id")
                depleted = row.get("remaining", 0) <= 0
                photo = self._card_image(value, card_h)
                if photo is not None:
                    canvas.create_image(x + card_w // 2, y, image=photo, anchor="n")
                    if depleted and hasattr(photo, "width"):
                        image_width = int(photo.width())
                        canvas.create_rectangle(
                            x + card_w // 2 - image_width // 2 - 2,
                            y - 2,
                            x + card_w // 2 + image_width // 2 + 2,
                            y + card_h + 2,
                            outline="#c93636",
                            width=3,
                        )
                    badge_w = max(34, min(44, card_w // 2))
                    badge_fill = "#ffe7e7" if depleted else "#f4f7fb"
                    badge_border = "#c93636" if depleted else "#50657a"
                    badge_text = "#9f1e1e" if depleted else "#172536"
                    canvas.create_rectangle(x + 2, y + card_h - 21, x + 2 + badge_w, y + card_h - 2, fill=badge_fill, outline=badge_border)
                    canvas.create_text(x + 6, y + card_h - 12, anchor="w", text=f"{row.get('remaining')}/{row.get('initial')}", fill=badge_text, font=("Segoe UI", max(7, min(10, card_h // 11)), "bold"))
                else:
                    name = self._card_label(value)
                    cost = get_card_metadata(value).cost if isinstance(value, int) and get_card_metadata(value) else "?"
                    canvas.create_rectangle(x, y, x + card_w, y + card_h, fill="#d9e2ec", outline="#c93636" if depleted else border, width=3 if depleted else 1)
                    canvas.create_text(x + 6, y + 8, anchor="nw", text=f"{cost}费 {name}\n{row.get('remaining')}/{row.get('initial')}", fill=text, font=("Segoe UI", 9), width=card_w - 12)
        canvas.create_polygon(width - 18, height - 8, width - 8, height - 18, width - 8, height - 8, fill="#50657a", outline="", tags="resize_handle")

    def _overlay_win_rate_summary(self) -> str:
        active = self._active_saved_deck()
        if active is None:
            return "当前卡组胜率：暂无已选牌组"
        stats = self._match_history.stats(active.key)
        first = stats["first"]
        second = stats["second"]
        return (
            f"总胜率 {float(stats['win_rate']):.1f}%（{int(stats['finished'])}局）    "
            f"先手胜率 {float(first['win_rate']):.1f}%（{int(first['finished'])}局）    "
            f"后手胜率 {float(second['win_rate']):.1f}%（{int(second['finished'])}局）"
        )

    @staticmethod
    def _text_panel(parent: ttk.PanedWindow, title: str, *, wrap: str = "none") -> tk.Text:
        frame = ttk.LabelFrame(parent, text=title, padding=5)
        text = tk.Text(
            frame,
            height=16,
            width=30,
            state="disabled",
            wrap=wrap,
            background="#f6f8fb",
            foreground="#182635",
            insertbackground="#182635",
            relief="flat",
            borderwidth=0,
            padx=7,
            pady=7,
            font=("Segoe UI", 10),
        )
        text.pack(fill="both", expand=True)
        parent.add(frame, weight=1)
        return text

    def _overview_panel(self, parent: ttk.PanedWindow) -> tk.Text:
        frame = ttk.LabelFrame(parent, text="对局概览", padding=5)
        self.summary_var = tk.StringVar(value="等待读取")
        ttk.Label(
            frame,
            textvariable=self.summary_var,
            justify="left",
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, 4))
        self.stats_var = tk.StringVar(value="对局记录未启用")
        ttk.Label(
            frame,
            textvariable=self.stats_var,
            justify="left",
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, 4))
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(0, 4))
        ttk.Label(frame, text="我的手牌").pack(anchor="w")
        text = tk.Text(
            frame,
            height=16,
            width=30,
            state="disabled",
            wrap="none",
            background="#f6f8fb",
            foreground="#182635",
            insertbackground="#182635",
            relief="flat",
            borderwidth=0,
            padx=7,
            pady=7,
            font=("Segoe UI", 10),
        )
        text.pack(fill="both", expand=True)
        parent.add(frame, weight=1)
        return text

    def _connect(self) -> None:
        if self._service and self._service.running:
            self._service.stop()
            self.connect_button.configure(text="开始读取")
            self.status_var.set("已停止")
            return
        raw_model = self.model_var.get().strip()
        try:
            model = int(raw_model, 0) if raw_model else 0
        except ValueError:
            messagebox.showerror("地址格式错误", "请输入类似 0x20B0CFEBC40 的地址。")
            return
        self._service = TrackerService(
            TrackerConfig(
                model_address=model,
                pid=self._startup_pid,
                # Opening mulligan responses can be replaced in quick
                # succession. Poll at 20 Hz so the opponent response is seen
                # before the local response overwrites it.
                interval=0.05,
                output_path=Path("logs") / "app_session.jsonl",
                training_output_path=Path("logs") / "training_matches.jsonl",
                training_upload_queue_path=(
                    Path("logs") / "training_upload_queue.jsonl"
                    if os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_URL")
                    else None
                ),
                training_upload_url=os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_URL"),
                training_upload_enabled=os.environ.get(
                    "SHADOWVERSE_TRACKER_UPLOAD_ENABLED", ""
                ).strip().casefold() in {"1", "true", "yes", "on"},
                training_upload_token=os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_TOKEN"),
                # Keep opponent private cards out of the UI and training
                # stream unless a caller explicitly opts into local practice
                # reveals through TrackerConfig.
                reveal_opponent_hand=False,
                selected_deck=self._active_deck_snapshot(),
                selected_deck_key=self._active_saved_deck().key if self._active_saved_deck() else None,
            ),
            on_snapshot=lambda value: self._events.put(("snapshot", value)),
            on_error=lambda value: self._events.put(("error", value)),
            on_status=lambda value: self._events.put(("status", value)),
            on_deck=lambda value: self._events.put(("deck", value)),
        )
        self._service.start()
        self.connect_button.configure(text="停止读取")
        self.status_var.set("正在后台读取（不会暂停游戏）")

    def _refresh_probability_choices(self, ledger: dict[str, object]) -> None:
        rows = ledger.get("rows", ())
        choices: dict[str, tuple[int, int, int]] = {}
        if isinstance(rows, (list, tuple)):
            for row in sorted((item for item in rows if isinstance(item, dict)), key=self._card_sort_key):
                card_id = row.get("card_id")
                remaining = row.get("remaining")
                initial = row.get("initial")
                if not isinstance(card_id, int) or not isinstance(remaining, int) or remaining <= 0:
                    continue
                if not isinstance(initial, int):
                    initial = remaining
                metadata = get_card_metadata(card_id)
                cost = metadata.cost if metadata is not None else "?"
                label = f"{cost}费 {self._card_label(card_id)}（剩余 {remaining}）"
                choices[label] = (card_id, remaining, initial)
        previous = self.probability_card_var.get()
        self._probability_cards = choices
        self.probability_card_choice.configure(values=tuple(choices))
        if previous not in choices:
            self.probability_card_var.set(next(iter(choices), ""))

    def _calculate_draw_probability(self) -> None:
        selected = self._probability_cards.get(self.probability_card_var.get())
        if selected is None:
            self.probability_result_var.set("当前牌库中没有可计算的卡牌")
            return
        try:
            draws = int(self.probability_draws_var.get())
        except ValueError:
            self.probability_result_var.set("抽牌次数请输入正整数")
            return
        if draws <= 0:
            self.probability_result_var.set("抽牌次数请输入正整数")
            return
        snapshot = self._last_snapshot or {}
        ledger = snapshot.get("deck_ledger") if isinstance(snapshot, dict) else None
        total = ledger.get("authoritative_deck_count") if isinstance(ledger, dict) else None
        if not isinstance(total, int) or total <= 0:
            self.probability_result_var.set("尚未取得有效的剩余牌库数量")
            return
        _card_id, remaining, _initial = selected
        actual_draws = min(draws, total)
        misses = math.comb(total - remaining, actual_draws) / math.comb(total, actual_draws) if actual_draws <= total - remaining else 0.0
        chance = (1.0 - misses) * 100
        self.probability_result_var.set(
            f"未来 {actual_draws} 抽至少抽到 1 张：{chance:.1f}%（该牌剩余 {remaining}/{total}）"
        )

    def _calculate_opponent_key_probability(self) -> None:
        self._calculate_opponent_key_probability_for_state(after_next_draw=False)

    def _calculate_opponent_next_turn_key_probability(self) -> None:
        """Project the opponent's hidden hand through their next turn-start draw."""
        self._calculate_opponent_key_probability_for_state(after_next_draw=True)

    def _calculate_faith_damage_probability(self) -> None:
        try:
            faith_total = int(self.faith_total_var.get().strip())
            minimum_damage = int(self.faith_min_z_var.get().strip())
        except (AttributeError, ValueError):
            self.faith_probability_result_var.set("信仰总值和 Z 下限请输入整数")
            return
        try:
            probability = calculate_faith_damage_probability(faith_total, minimum_damage)
        except ValueError as exc:
            self.faith_probability_result_var.set(f"无法计算：{exc}")
            return
        self.faith_probability_result_var.set(
            f"P(Z≥{minimum_damage})：{probability * 100:.2f}%（N={faith_total}，Z~Binomial(N, 1/3)）"
        )

    @staticmethod
    def _project_opponent_next_draw(deck_remaining: int, hand_size: int) -> tuple[int, int] | None:
        if deck_remaining <= 0:
            return None
        return deck_remaining - 1, hand_size + 1

    def _calculate_opponent_key_probability_for_state(self, *, after_next_draw: bool) -> None:
        snapshot = self._last_snapshot or {}
        root = snapshot.get("root") if isinstance(snapshot, dict) else None
        players = root.get("players", ()) if isinstance(root, dict) else ()
        if not isinstance(players, (list, tuple)) or len(players) < 2 or not isinstance(players[1], dict):
            self.key_probability_result_var.set("尚未读取到对手牌库/手牌数据")
            return
        opponent = players[1]
        def integer(variable: tk.StringVar, label: str) -> int | None:
            try:
                value = int(variable.get().strip())
            except ValueError:
                self.key_probability_result_var.set(f"{label}请输入整数")
                return None
            return value
        values = [(self.key_keep1_var, "留1类型"), (self.key_keep2_var, "留2类型"), (self.key_seen1_var, "已见留1"),
                  (self.key_seen2_var, "已见留2"), (self.key_copies_var, "Key投入"), (self.key_limit_var, "Key留牌上限"), (self.key_seen_var, "Key已见")]
        parsed = [integer(variable, label) for variable, label in values]
        if any(value is None for value in parsed):
            return
        keep1, keep2, seen1, seen2, copies, limit, key_seen = [int(value) for value in parsed]
        hand = opponent.get("hand", ())
        hand_size = len(hand) if isinstance(hand, (list, tuple)) else 0
        knowledge = snapshot.get("opponent_hand_knowledge")
        if isinstance(knowledge, dict):
            generated = sum(int(item.get("count", 0)) for item in knowledge.get("known_cards", ()) if isinstance(item, dict))
            generated += sum(int(item.get("count", 0)) for item in knowledge.get("known_types", ()) if isinstance(item, dict))
            hand_size = max(0, hand_size - generated)
        mulligan = snapshot.get("training_observation", {})
        mulligan_data = mulligan.get("mulligan", {}) if isinstance(mulligan, dict) else {}
        swapped = self._resolved_opponent_mulligan(mulligan_data, default=None)
        strategy = self.key_strategy_var.get() if self.key_strategy_var.get() in ("known", "unknown") else "known"
        if swapped is None and strategy == "known":
            self.key_probability_result_var.set("无法计算：尚未读取到对手换牌数量")
            return
        calculation_swapped = swapped if isinstance(swapped, int) else 0
        deck_remaining = opponent.get("deck_count", 36)
        if not isinstance(deck_remaining, int):
            deck_remaining = 36
        deck_remaining = min(36, max(0, deck_remaining))
        if after_next_draw:
            projected = self._project_opponent_next_draw(deck_remaining, hand_size)
            if projected is None:
                self.key_probability_result_var.set("无法计算：对手牌库为空，无法进行下一回合抽牌")
                return
            deck_remaining, hand_size = projected
        result = calculate_key_probability(
            deck_remaining=deck_remaining, hand_size=hand_size, mulligan_swapped=calculation_swapped,
            keep1_types=keep1, keep2_types=keep2, seen_keep1=seen1, seen_keep2=seen2,
            key_copies=copies, key_keep_limit=limit, key_seen=key_seen,
            strategy=strategy,
        )
        if result.valid and result.percent is not None:
            mulligan_label = swapped if isinstance(swapped, int) else "未知"
            label = "对手下回合 Key 概率" if after_next_draw else "Key概率"
            self.key_probability_result_var.set(f"{label}：{result.percent:.2f}%（牌库{deck_remaining}，未知手牌{hand_size}，换牌{mulligan_label}）")
        else:
            self.key_probability_result_var.set(f"无法计算：{result.reason}")

    def _sync_key_strategy_inputs(self, _event: object = None) -> None:
        """Known-policy fields are irrelevant, and therefore read-only, in unknown mode."""
        state = "disabled" if self.key_strategy_var.get() == "unknown" else "normal"
        for entry in self._key_policy_entries:
            entry.configure(state=state)

    def _resolved_opponent_mulligan(self, mulligan: object, *, default: int | None) -> int | None:
        value = mulligan.get("opponent_replaced_count", default) if isinstance(mulligan, dict) else default
        return value if isinstance(value, int) and 0 <= value <= 4 else default

    def _update_opponent_probability_inputs(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        deck_remaining = opponent.get("deck_count")
        if not isinstance(deck_remaining, int):
            deck_remaining = 36
        self.key_deck_remaining_var.set(str(max(0, deck_remaining)))
        hand = opponent.get("hand", ())
        hand_size = len(hand) if isinstance(hand, (list, tuple)) else 0
        knowledge = snapshot.get("opponent_hand_knowledge")
        if isinstance(knowledge, dict):
            generated = sum(int(item.get("count", 0)) for item in knowledge.get("known_cards", ()) if isinstance(item, dict))
            generated += sum(int(item.get("count", 0)) for item in knowledge.get("known_types", ()) if isinstance(item, dict))
            hand_size = max(0, hand_size - generated)
        self.key_hand_size_var.set(str(hand_size))
        training = snapshot.get("training_observation")
        mulligan = training.get("mulligan", {}) if isinstance(training, dict) else {}
        swapped = self._resolved_opponent_mulligan(mulligan, default=None)
        self.key_mulligan_var.set(str(swapped) if isinstance(swapped, int) else "—")

    def _toggle_match_recording(self) -> None:
        if self.record_matches_var.get():
            self.status_var.set("已开启胜负统计（仅保存到本机）；训练记录始终自动保存")
        else:
            self.status_var.set("已关闭胜负统计；训练记录仍会自动保存")
        self._update_stats_summary()

    def _drain_events(self) -> None:
        latest_snapshot: dict[str, object] | None = None
        status_after_snapshot: str | None = None
        while True:
            try:
                kind, value = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                message = f"读取错误：{value}"
                self.status_var.set(message)
                if latest_snapshot is not None:
                    status_after_snapshot = message
                continue
            if kind == "status":
                message = str(value)
                self.status_var.set(message)
                if latest_snapshot is not None:
                    status_after_snapshot = message
                continue
            if kind == "deck":
                self._render_deck_info(value)  # type: ignore[arg-type]
                continue
            if kind == "snapshot" and isinstance(value, dict):
                # The memory reader can produce several snapshots between UI
                # ticks.  Rendering only the newest one keeps the window
                # responsive; the tracker only renders the latest snapshot.
                latest_snapshot = value
                status_after_snapshot = None
                continue
            if isinstance(value, dict):
                latest_snapshot = value
        if latest_snapshot is not None:
            self._render(latest_snapshot)
            if status_after_snapshot is not None:
                self.status_var.set(status_after_snapshot)
        self.after(100, self._drain_events)

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    @staticmethod
    def _set_rich_text(widget: tk.Text, segments: list[tuple[str, str | None]]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for value, tag in segments:
            widget.insert("end", value, tag or ())
        widget.configure(state="disabled")

    def _render(self, snapshot: dict[str, object]) -> None:
        self._last_snapshot = snapshot
        self._render_overlay(snapshot)
        root = snapshot.get("root")
        if not isinstance(root, dict):
            return
        address = snapshot.get("address")
        if isinstance(address, str):
            self.model_var.set(address)
        self.status_var.set("已连接，正在后台读取（不会暂停游戏）")
        players = root.get("players", [])
        if not isinstance(players, (list, tuple)) or len(players) < 2:
            return
        mine, opponent = players[0], players[1]
        if not isinstance(mine, dict) or not isinstance(opponent, dict):
            return
        self._update_opponent_probability_inputs(snapshot, opponent)
        self._track_match(snapshot, mine, opponent)
        if self._has_terminal_result(mine, opponent):
            self._clear_completed_match_display()
            return
        self._opponent_known_hand.update(snapshot, opponent)
        self.summary_var.set(
            f"回合 {mine.get('turn', '?')}    "
            f"我方生命 {mine.get('life', '?')} / 对手 {opponent.get('life', '?')}    "
            f"我方牌库 {mine.get('deck_count', '?')}    "
            f"PP {mine.get('pp', '?')}/{mine.get('max_pp', '?')}"
        )
        hand = mine.get("hand", [])
        hand_lines = [
            self._format_card_line(card)
            for card in hand if isinstance(card, dict)
        ] if isinstance(hand, (list, tuple)) else []
        self._set_text(self.hand_text, "\n".join(hand_lines))
        ledger = snapshot.get("deck_ledger")
        if isinstance(ledger, dict):
            self._refresh_probability_choices(ledger)
            deck_name = str(ledger.get("deck_name") or "未命名牌组")
            deck_count = ledger.get("authoritative_deck_count", "?")
            initial_total = sum(
                int(row.get("initial", 0))
                for row in ledger.get("rows", ())
                if isinstance(row, dict) and isinstance(row.get("initial"), int)
            ) if isinstance(ledger.get("rows"), (list, tuple)) else "?"
            deck_segments: list[tuple[str, str | None]] = [
                (f"{deck_name}\n", "deck_header"),
                (f"剩余牌库：{deck_count} / {initial_total} 张\n", "deck_header"),
            ]
            unknown = ledger.get("unknown_removed", 0)
            if isinstance(unknown, int) and unknown:
                deck_segments.append((f"未识别离开牌库：{unknown} 张\n", "deck_section"))
            burned = ledger.get("burned_cards", 0)
            if isinstance(burned, int) and burned:
                burned_ids = ledger.get("burned_card_ids", ())
                names = [self._card_label(card_id) for card_id in burned_ids if isinstance(card_id, int)] if isinstance(burned_ids, (list, tuple)) else []
                detail = "、".join(names) if names else f"{burned} 张"
                deck_segments.append((f"爆牌：{detail}\n", "deck_section"))
            rows = ledger.get("rows", ())
            if isinstance(rows, (list, tuple)):
                valid_rows = [row for row in rows if isinstance(row, dict)]
                remaining = [row for row in valid_rows if isinstance(row.get("remaining"), int) and row.get("remaining", 0) > 0]
                depleted = [row for row in valid_rows if isinstance(row.get("remaining"), int) and row.get("remaining", 0) <= 0]
                deck_segments.append(("\n未抽空\n", "deck_section"))
                for row in sorted(remaining, key=self._card_sort_key):
                    deck_segments.append((self._format_deck_row(row) + "\n", None))
                deck_segments.append(("\n已抽空\n", "deck_section"))
                if depleted:
                    for row in sorted(depleted, key=self._card_sort_key):
                        deck_segments.append((self._format_deck_row(row) + "\n", None))
                else:
                    deck_segments.append(("（暂无）\n", None))
            self._set_rich_text(self.deck_text, deck_segments)
        else:
            if snapshot.get("battle_mode") == "puzzle":
                self._set_text(self.deck_text, "特殊/解密对局：当前牌组为空（不使用本地牌库）")
            else:
                self._set_text(self.deck_text, "请从本地牌组仓库选择牌组")
        # Keep hand knowledge and other extra information in the upper part;
        # the current board is separated below for quick scanning.
        lines = ["对手手牌："]
        lines.extend(self._format_opponent_hand(opponent))
        if snapshot.get("opponent_class_id") == 3:
            lines.append(f"\n对手魔力增幅：{self._opponent_known_hand.magic_boost}")
        lines.append("\n────────────────")
        lines.append("我方场面：")
        lines.extend(self._format_field(mine.get("field", [])))
        lines.append("\n对手场面：")
        lines.extend(self._format_field(opponent.get("field", [])))
        self.opponent_counter_var.set(self._format_general_counters(snapshot))
        self.class_counter_var.set(self._format_class_counters(snapshot))
        self._set_text(self.field_text, "\n".join(lines))
        self._set_text(self.history_text, self._format_recent_history(mine, opponent))

    def _render_lethal(self, snapshot: dict[str, object]) -> None:
        """Record a fresh snapshot without automatically running the solver."""
        if self._lethal_bridge is None:
            self._set_text(self.lethal_text, self._lethal_status_message or "斩杀计算器不可用")
            return

        # A few formatting/unit callers construct ``TrackerApp`` with
        # ``object.__new__`` and only provide the widgets they exercise. Keep
        # that supported by retaining a synchronous compatibility path when
        # the Tk runtime fields have not been initialized.
        if "_lethal_lock" not in object.__getattribute__(self, "__dict__"):
            try:
                view = self._lethal_bridge.refresh(snapshot)
            except Exception as exc:
                view = exc
            self._render_lethal_view(snapshot, view)
            return

        with self._lethal_lock:
            self._lethal_generation += 1
            self._lethal_latest_snapshot = snapshot
            self._lethal_view = None
            self._lethal_view_generation = -1
            self._lethal_dirty = True
            # A board update invalidates an in-flight result, but must not
            # trigger another search until the user explicitly clicks.
            self._lethal_restart_requested = False
        self._set_text(self.lethal_text, "盘面已更新，请点击“计算本回合斩杀”")

    def _calculate_lethal(self) -> None:
        """Start one explicit search using the newest tracker snapshot."""
        if self._lethal_bridge is None:
            self._set_text(self.lethal_text, self._lethal_status_message or "斩杀计算器不可用")
            return
        snapshot = self._last_snapshot
        if not isinstance(snapshot, dict):
            self._set_text(self.lethal_text, "等待对局快照；暂时无法计算")
            return
        with self._lethal_lock:
            self._lethal_generation += 1
            self._lethal_latest_snapshot = snapshot
            self._lethal_view = None
            self._lethal_view_generation = -1
            self._lethal_dirty = False
            if self._lethal_pending:
                # Do not run two sessions concurrently.  The current worker
                # will publish a stale result, after which the requested
                # calculation is started from the latest snapshot.
                self._lethal_restart_requested = True
                should_start = False
            else:
                self._lethal_pending = True
                self._lethal_restart_requested = False
                should_start = True
        if should_start:
            threading.Thread(target=self._lethal_worker, name="lethal-solver", daemon=True).start()
        self._set_text(self.lethal_text, "斩杀计算中…")

    def _lethal_worker(self) -> None:
        """Run one serialized solve in a daemon thread, never touching Tk."""
        with self._lethal_lock:
            snapshot = self._lethal_latest_snapshot
            generation = self._lethal_generation
        if self._lethal_bridge is None or not isinstance(snapshot, dict):
            result: object = RuntimeError("lethal bridge unavailable")
        else:
            try:
                result = self._lethal_bridge.refresh(snapshot)
            except Exception as exc:  # optional UI integration must fail closed
                result = exc
        self._events.put(("lethal_view", (generation, result)))

    def _render_lethal_view(self, snapshot: dict[str, object], view: object) -> None:
        """Render a completed solver view.  This method runs on Tk's thread."""
        if isinstance(view, Exception):
            self._set_text(
                self.lethal_text,
                "状态：INCOMPLETE\n斩杀计算器刷新失败："
                f"{type(view).__name__}: {view}",
            )
            return

        status = str(getattr(view, "status", "INCOMPLETE"))
        status_labels = {
            "CONFIRMED": "确认斩杀",
            "PROBABILISTIC": "概率斩杀",
            "NO_LETHAL": "本回合无法斩杀",
            "INCOMPLETE": "计算不完整",
        }
        lines = [f"状态：{status_labels.get(status, status)} ({status})"]
        trusted = bool(getattr(view, "trusted", False))
        usable = bool(getattr(view, "usable", False))
        ally_turn = bool(getattr(view, "is_ally_turn", False))
        lines.append(
            f"快照：{'可信' if trusted else '不可信'}    "
            f"可计算：{'是' if usable else '否'}    "
            f"回合：{'我方' if ally_turn else '对手'}"
        )

        state = getattr(view, "state", None)
        if state is not None:
            def _state_int(name: str, fallback: object = "?") -> object:
                value = getattr(state, name, fallback)
                return value if isinstance(value, int) and not isinstance(value, bool) else fallback

            def _state_count(name: str) -> int:
                value = getattr(state, name, ())
                return len(value) if isinstance(value, (list, tuple, set, dict)) else 0

            lines.append(f"对手当前生命：{_state_int('enemy_hp')}")
            lines.append(
                "资源："
                f"PP {_state_int('pp')}/{_state_int('max_pp')}"
                f" (+{_state_int('extra_pp', 0)} Extra)；"
                f"EP {_state_int('ep')} / SEP {_state_int('sep')}；"
                f"Rally {_state_int('rally', 0)}；"
                f"PlayCount {_state_int('play_count', 0)}；"
                f"墓地 {_state_int('cemetery', 0)}；"
                f"觉醒 {'是' if bool(getattr(state, 'is_awakening', False)) else '否'}；"
                f"本回合已攻击 {_state_count('attacked_card_uids')}"
            )
            unlocks = []
            evolve_turn = getattr(state, "evolve_turn", None)
            super_evolve_turn = getattr(state, "super_evolve_turn", None)
            current_turn = getattr(state, "turn_number", None)
            if isinstance(evolve_turn, int) and not isinstance(evolve_turn, bool):
                suffix = (
                    "未知"
                    if not isinstance(current_turn, int) or isinstance(current_turn, bool)
                    else ("已解锁" if current_turn >= evolve_turn else "未解锁")
                )
                unlocks.append(f"进化 T{evolve_turn}（{suffix}）")
            if isinstance(super_evolve_turn, int) and not isinstance(super_evolve_turn, bool):
                suffix = (
                    "未知"
                    if not isinstance(current_turn, int) or isinstance(current_turn, bool)
                    else ("已解锁" if current_turn >= super_evolve_turn else "未解锁")
                )
                unlocks.append(f"超进化 T{super_evolve_turn}（{suffix}）")
            if unlocks:
                lines.append("解锁限制：" + "；".join(unlocks))
            crest_instances = getattr(state, "crest_instances", ()) or ()
            active_crests = getattr(state, "active_crests", ()) or ()
            crest_instance_count = _state_count("crest_instances")
            crest_count = crest_instance_count if crest_instance_count else (
                len(active_crests) if isinstance(active_crests, (list, tuple, set)) else _state_int("active_crests", 0)
            )
            lines.append(
                "额外资源："
                f"Faith {_state_int('faith', 0)}"
                f"（{_state_count('faith_instances')}实例）；"
                f"Crest {crest_count}"
                f"（{crest_instance_count}实例）；"
                f"土之印 {_state_int('earth_sigil', 0)}；"
                f"奥义 {_state_int('skybound_art', 0)}"
                f"/解放 {_state_int('super_skybound_art', 0)}；"
                f"毁坏池 {_state_count('destroyed_this_match')}"
            )
            faith_details = getattr(state, "faith_instances", ()) or ()
            if isinstance(faith_details, (list, tuple)) and faith_details:
                rendered_faith = []
                for item in faith_details:
                    if isinstance(item, dict):
                        source = item.get("source_card_id") or item.get("unique_id") or "?"
                        rendered_faith.append(f"{source}={item.get('value', 0)}")
                if rendered_faith:
                    lines.append("Faith实例：" + "、".join(rendered_faith))
            if isinstance(crest_instances, (list, tuple)) and crest_instances:
                rendered_crests = []
                for item in crest_instances:
                    if isinstance(item, dict):
                        identity = item.get("unique_id") or item.get("card_id") or "?"
                        countdown = item.get("countdown")
                        rendered_crests.append(f"{identity}({countdown if countdown is not None else '∞'})")
                if rendered_crests:
                    lines.append("Crest实例：" + "、".join(rendered_crests))

        probability = getattr(view, "probability", 0.0)
        try:
            probability_value = max(0.0, min(1.0, float(probability)))
        except (TypeError, ValueError):
            probability_value = 0.0
        if status == "PROBABILISTIC" or probability_value > 0.0:
            lines.append(f"斩杀概率：{probability_value * 100:.2f}%")

        if status in {"NO_LETHAL", "INCOMPLETE"}:
            if usable:
                max_damage = getattr(view, "max_damage", 0)
                try:
                    max_damage_value = max(0, int(max_damage))
                except (TypeError, ValueError):
                    max_damage_value = 0
                qualifier = "当前回合最高理论伤害"
                if status == "INCOMPLETE":
                    qualifier = "当前已知最高理论伤害（结果不完整）"
                suffix = ""
                enemy_hp = getattr(state, "enemy_hp", None)
                if isinstance(enemy_hp, int) and not isinstance(enemy_hp, bool):
                    suffix = f"（预计剩余生命 {max(0, enemy_hp - max_damage_value)}）"
                lines.append(f"{qualifier}：{max_damage_value} 点{suffix}")
                max_sequence = tuple(getattr(view, "max_damage_sequence", ()) or ())
                if max_sequence:
                    lines.append("最高伤害路线：")
                    lines.extend(f"  {index}. {step}" for index, step in enumerate(max_sequence, 1))
            else:
                lines.append("最高伤害：无法计算（快照缺少关键字段）")

        sequence = tuple(getattr(view, "sequence", ()) or ())
        if sequence and status in {"CONFIRMED", "PROBABILISTIC", "INCOMPLETE"}:
            lines.append("斩杀路线：")
            lines.extend(f"  {index}. {step}" for index, step in enumerate(sequence, 1))

        # Show the live legality projections so the user can verify why an
        # action/target is or is not considered by the solver.
        entity_names: dict[int, str] = {}
        if state is not None:
            for collection_name in ("hand", "my_board", "enemy_board"):
                collection = getattr(state, collection_name, ()) or ()
                if not isinstance(collection, (list, tuple, set)):
                    continue
                for entity in collection:
                    uid = getattr(entity, "unique_id", None)
                    if isinstance(uid, int):
                        name = getattr(entity, "name", None)
                        card_id = getattr(entity, "card_id", None)
                        entity_names[uid] = str(name or self._card_label(card_id))
            leader_uid = getattr(state, "enemy_leader_uid", None)
            if isinstance(leader_uid, int):
                entity_names[leader_uid] = "对手主战者"

        modes = getattr(view, "available_modes", {})
        if isinstance(modes, dict) and modes:
            lines.append("可用模式：")
            for uid, values in sorted(modes.items(), key=lambda item: str(item[0])):
                raw_values = values if isinstance(values, (list, tuple, set)) else ()
                mode_values = tuple(str(value) for value in raw_values)
                if mode_values:
                    label = entity_names.get(int(uid), str(uid)) if str(uid).lstrip('-').isdigit() else str(uid)
                    lines.append(f"  {label} [{uid}]：{'、'.join(mode_values)}")
        attack_targets = getattr(view, "attack_targets", {})
        if isinstance(attack_targets, dict) and attack_targets:
            lines.append("AttackTargets：")
            for uid, values in sorted(attack_targets.items(), key=lambda item: str(item[0])):
                raw_values = values if isinstance(values, (list, tuple, set)) else ()
                rendered_values = [
                    f"{entity_names.get(value, value)} [{value}]" if isinstance(value, int) else str(value)
                    for value in raw_values
                ]
                rendered = "、".join(rendered_values) or "（无）"
                attacker = entity_names.get(int(uid), str(uid)) if str(uid).lstrip('-').isdigit() else str(uid)
                lines.append(f"  {attacker} [{uid}] → {rendered}")

        legal_actions = getattr(view, "legal_actions", None)
        if isinstance(legal_actions, dict):
            populated = []
            for action, values in legal_actions.items():
                if isinstance(values, (list, tuple, set)) and values:
                    populated.append(f"{action}={len(values)}")
                elif action in {"can_attack_leader_cards", "can_attack_field_cards"} and isinstance(values, (list, tuple, set)):
                    # Explicit zeroes make it clear that an attack was
                    # checked and found illegal, rather than omitted from
                    # the snapshot or the UI.
                    populated.append(f"{action}=0")
            if populated:
                lines.append("合法操作：" + "；".join(sorted(populated)))

        reasons = tuple(getattr(view, "trust_reasons", ()) or ())
        warnings = tuple(getattr(view, "warnings", ()) or ())
        if reasons:
            lines.append("快照原因：")
            lines.extend(f"  - {reason}" for reason in reasons)
        if warnings:
            lines.append("提示：")
            lines.extend(f"  - {warning}" for warning in warnings)
        self._set_text(self.lethal_text, "\n".join(lines))

    @staticmethod
    def _has_terminal_result(mine: dict[str, object], opponent: dict[str, object]) -> bool:
        """Return true only for a confirmed local victory or defeat."""
        result_code = mine.get("result_code")
        if not isinstance(result_code, int):
            return False
        return result_label(
            result_code,
            mine.get("life") if isinstance(mine.get("life"), int) else None,
            opponent.get("life") if isinstance(opponent.get("life"), int) else None,
        ) in {"胜利", "失败"}

    def _clear_completed_match_display(self) -> None:
        """Immediately remove finished-match data while keeping saved results."""
        self._last_snapshot = None
        self._opponent_known_hand.reset()
        self.status_var.set("本局已结束，等待下一局")
        self.summary_var.set("本局已结束，等待下一局数据")
        self.opponent_counter_var.set("通用计数器：等待下一局")
        self.class_counter_var.set("对手职业计数器：等待下一局")
        self.key_deck_remaining_var.set("—")
        self.key_hand_size_var.set("—")
        self.key_mulligan_var.set("—")
        self.key_probability_result_var.set("等待下一局对手数据")
        self._set_text(self.hand_text, "等待下一局")
        self._render_active_deck_full()
        self._set_text(self.field_text, "等待下一局")
        self._set_text(self.history_text, "等待下一局")
        self._render_overlay(None)

    def _track_match(
        self,
        snapshot: dict[str, object],
        mine: dict[str, object],
        opponent: dict[str, object],
    ) -> None:
        model_address = str(snapshot.get("address") or "unknown")
        turn = mine.get("turn") if isinstance(mine.get("turn"), int) else None
        result_code = mine.get("result_code") if isinstance(mine.get("result_code"), int) else 0
        is_new_match = (
            self._match_id is None
            or model_address != self._last_model_address
            or (
                result_code == 0
                and self._last_render_result not in (None, 0)
            )
            or (
                result_code != 0
                and self._last_render_result not in (None, 0, result_code)
            )
            or (
                turn is not None
                and self._last_render_turn is not None
                and turn + 2 < self._last_render_turn
            )
        )
        if is_new_match:
            self._match_sequence += 1
            self._match_id = f"{model_address}:{os.getpid()}:{self._match_sequence}"
            self._opponent_known_hand.reset()
            deck = snapshot.get("deck")
            self._match_deck_key = (
                str(deck.get("deck_key"))
                if isinstance(deck, dict) and deck.get("deck_key")
                else None
            )
            if self._match_deck_key is None:
                active = self._active_saved_deck()
                self._match_deck_key = active.key if active else None
        terminal_result = result_label(
            result_code,
            mine.get("life") if isinstance(mine.get("life"), int) else None,
            opponent.get("life") if isinstance(opponent.get("life"), int) else None,
        )
        if (
            self.record_matches_var.get()
            and self._match_id is not None
            and terminal_result in {"胜利", "失败"}
            and self._match_deck_key
        ):
            deck = snapshot.get("deck")
            deck_name = str(deck.get("deck_name") or "未命名牌组") if isinstance(deck, dict) else "未命名牌组"
            opponent_class_id = snapshot.get("opponent_class_id")
            if not isinstance(opponent_class_id, int):
                opponent_class_id = None
            try:
                self._match_history_error = ""
                model_match_id = terminal_match_id(
                    model_address,
                    result_code,
                    turn,
                    mine.get("life") if isinstance(mine.get("life"), int) else None,
                    opponent.get("life") if isinstance(opponent.get("life"), int) else None,
                    mine.get("deck_count") if isinstance(mine.get("deck_count"), int) else None,
                    mine.get("cemetery_count") if isinstance(mine.get("cemetery_count"), int) else None,
                    len(mine.get("played_card_ids", ())) if isinstance(mine.get("played_card_ids"), (list, tuple)) else 0,
                    len(mine.get("destroyed_card_ids", ())) if isinstance(mine.get("destroyed_card_ids"), (list, tuple)) else 0,
                )
                added = self._match_history.add(MatchRecord(
                    match_id=model_match_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    deck_key=self._match_deck_key,
                    deck_name=deck_name,
                    self_class_id=(snapshot.get("self_class_id") if isinstance(snapshot.get("self_class_id"), int) else None),
                    opponent_class_id=opponent_class_id,
                    opponent_class=class_name(opponent_class_id),
                    result=terminal_result,
                    result_code=result_code,
                    turn=turn,
                    is_first=mine.get("is_first_side") if isinstance(mine.get("is_first_side"), bool) else None,
                ))
            except (OSError, ValueError) as exc:
                self._match_history_error = str(exc)
                self.stats_var.set(f"对局记录保存失败：{exc}")
                added = False
            if added:
                self.stats_var.set("本局已保存；" + self._stats_summary_for_key(self._match_deck_key))
        elif self.record_matches_var.get() and terminal_result in {"胜利", "失败"} and not self._match_deck_key:
            self.stats_var.set("本局未保存：请先选择本地牌组")
        self._last_model_address = model_address
        self._last_render_turn = turn
        self._last_render_result = result_code
        self._update_stats_summary()

    def _stats_summary_for_key(self, deck_key: str) -> str:
        stats = self._match_history.stats(deck_key)
        return (
            f"当前卡组：{stats['wins']} 胜 / {stats['losses']} 负，"
            f"胜率 {float(stats['win_rate']):.1f}%（共 {stats['total']} 局）"
        )

    def _update_stats_summary(self) -> None:
        if not self.record_matches_var.get():
            self.stats_var.set("胜负统计未启用（训练记录仍自动保存）")
            return
        if self._match_history_error:
            self.stats_var.set(f"对局记录保存失败：{self._match_history_error}")
            return
        active = self._active_saved_deck()
        if active is None:
            self.stats_var.set("对局记录已启用；请选择本地牌组")
            return
        self.stats_var.set(self._stats_summary_for_key(active.key))

    def _show_match_stats(self) -> None:
        active = self._active_saved_deck()
        if active is None:
            messagebox.showinfo("对局统计", "请先从本地牌组仓库选择牌组。", parent=self)
            return
        stats = self._match_history.stats(active.key)
        window = tk.Toplevel(self)
        window.title(f"对局统计 - {active.name}")
        window.geometry("620x420")
        buttons = ttk.Frame(window, padding=(12, 0, 12, 10))
        buttons.pack(fill="x", side="bottom")
        ttk.Button(
            buttons,
            text="重置当前牌组胜率",
            command=lambda: self._reset_match_stats(active, window),
        ).pack(side="right")
        text = tk.Text(window, wrap="none", state="normal", padx=12, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("end", f"{active.name}\n", "title")
        text.insert("end", f"总计：{stats['total']} 局    {stats['wins']} 胜 / {stats['losses']} 负    胜率 {float(stats['win_rate']):.1f}%\n\n", "title")
        text.insert("end", "对手职业\n", "section")
        groups = stats["by_class"]
        if isinstance(groups, dict) and groups:
            for name in sorted(groups):
                group = groups[name]
                text.insert(
                    "end",
                    f"{name}：{group['wins']} 胜 / {group['losses']} 负    "
                    f"胜率 {float(group['win_rate']):.1f}%（{group['total']} 局）\n",
                )
                first = group.get("first") if isinstance(group, dict) else None
                second = group.get("second") if isinstance(group, dict) else None
                if isinstance(first, dict) and isinstance(second, dict):
                    text.insert(
                        "end",
                        f"    先手 {first['wins']}/{first['total']}  胜率 {float(first['win_rate']):.1f}%    "
                        f"后手 {second['wins']}/{second['total']}  胜率 {float(second['win_rate']):.1f}%\n",
                    )
        else:
            text.insert("end", "暂无已记录对局\n")
        text.configure(state="disabled")
        text.tag_configure("title", font=("Segoe UI", 14, "bold"))
        text.tag_configure("section", font=("Segoe UI", 11, "bold"), foreground="#24527a")

    def _reset_match_stats(self, active: SavedDeck, window: tk.Toplevel) -> None:
        stats = self._match_history.stats(active.key)
        if not messagebox.askyesno(
            "重置胜率",
            f"确定清除“{active.name}”的 {stats['total']} 局胜负统计吗？\n此操作不可恢复。",
            parent=window,
        ):
            return
        try:
            removed = self._match_history.clear_deck(active.key)
        except OSError as exc:
            messagebox.showerror("重置失败", str(exc), parent=window)
            return
        self._update_stats_summary()
        window.destroy()
        messagebox.showinfo("对局统计", f"已清除 {removed} 局对局记录。", parent=self)

    def _edit_current_deck(self) -> None:
        deck = self._active_saved_deck()
        if deck is None:
            messagebox.showinfo("编辑卡组", "请先从本地牌组仓库选择牌组。", parent=self)
            return
        editor = tk.Toplevel(self)
        editor.title(f"编辑卡组 - {deck.name}")
        # Keep the save bar visible even on a 720p screen.  The card table
        # receives the flexible middle area instead of imposing 20 fixed rows.
        editor.geometry("760x680")
        editor.minsize(620, 520)
        editor.transient(self)

        counts = {card.card_id: card.count for card in deck.cards}
        selected_id: int | None = None
        total_var = tk.StringVar()
        count_var = tk.IntVar(value=1)
        catalog = load_card_catalog()
        search_var = tk.StringVar()
        choice_var = tk.StringVar()
        option_ids: dict[str, int] = {}

        ttk.Label(
            editor,
            text="选择牌组中的卡牌后修改数量；添加新卡时先选择卡牌再点击“添加”。总数必须保持 40 张。",
        ).pack(anchor="w", padx=12, pady=(12, 6))
        buttons = ttk.Frame(editor, padding=(12, 0, 12, 12))
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="保存修改", command=lambda: save_changes()).pack(side="right")
        ttk.Button(buttons, text="取消", command=editor.destroy).pack(side="right", padx=(0, 8))

        controls = ttk.Frame(editor, padding=12)
        controls.pack(fill="x", side="bottom")
        table = ttk.Treeview(editor, columns=("cost", "name", "count"), show="headings", height=12)
        table.heading("cost", text="费用")
        table.heading("name", text="卡牌名称")
        table.heading("count", text="数量")
        table.column("cost", width=70, anchor="center")
        table.column("name", width=420)
        table.column("count", width=80, anchor="center")
        table.pack(fill="both", expand=True, padx=12)
        ttk.Label(controls, text="选中数量").grid(row=0, column=0, sticky="w")
        count_spin = ttk.Spinbox(controls, from_=0, to=3, textvariable=count_var, width=6)
        count_spin.grid(row=0, column=1, padx=(6, 12), sticky="w")
        ttk.Button(controls, text="应用数量", command=lambda: apply_count()).grid(row=0, column=2, padx=(0, 18))
        ttk.Label(controls, textvariable=total_var).grid(row=0, column=3, rowspan=3, sticky="e")
        ttk.Label(controls, text="搜索卡牌").grid(row=1, column=0, pady=(10, 0), sticky="w")
        search_entry = ttk.Entry(controls, textvariable=search_var, width=24)
        search_entry.grid(row=1, column=1, columnspan=2, padx=(6, 18), pady=(10, 0), sticky="ew")
        ttk.Label(
            controls,
            text=self._deck_restriction_text(deck.class_id, deck.format_version),
        ).grid(row=2, column=0, columnspan=3, pady=(6, 0), sticky="w")
        choice = ttk.Combobox(controls, textvariable=choice_var, state="readonly", width=42)
        choice.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="ew")
        ttk.Button(controls, text="添加新卡", command=lambda: add_card()).grid(row=3, column=2, pady=(10, 0), padx=(0, 18))
        controls.columnconfigure(1, weight=1)

        def refresh() -> None:
            table.delete(*table.get_children())
            for card_id, card_count in sorted(
                counts.items(),
                key=lambda item: (
                    get_card_metadata(item[0]).cost if get_card_metadata(item[0]) else 999,
                    get_card_name(item[0]),
                ),
            ):
                metadata = get_card_metadata(card_id)
                name = metadata.name if metadata else get_card_name(card_id)
                cost = metadata.cost if metadata else "?"
                table.insert("", "end", iid=str(card_id), values=(f"{cost}费", name, card_count))
            total_var.set(f"当前总数：{sum(counts.values())} / 40")
            refresh_options()

        def refresh_options(*_args: object) -> None:
            query = search_var.get().strip().casefold()
            option_ids.clear()
            labels: list[str] = []
            duplicate_counts: dict[str, int] = {}
            for card in sorted(catalog.values(), key=lambda value: (value.cost, value.name, value.card_id)):
                if card.card_id in counts:
                    continue
                if not is_card_allowed(card.card_id, deck.class_id, deck.format_version):
                    continue
                if query and query not in card.name.casefold() and query not in str(card.card_id):
                    continue
                base = f"{card.cost}费 {card.name}"
                duplicate_counts[base] = duplicate_counts.get(base, 0) + 1
                label = base
                if label in option_ids:
                    label = f"{base}（{duplicate_counts[base]}）"
                option_ids[label] = card.card_id
                labels.append(label)
            choice.configure(values=labels)
            if choice_var.get() not in option_ids:
                choice_var.set("")

        def on_select(_event: object = None) -> None:
            nonlocal selected_id
            selection = table.selection()
            if not selection:
                selected_id = None
                return
            selected_id = int(selection[0])
            count_var.set(counts[selected_id])

        def apply_count() -> None:
            nonlocal selected_id
            if selected_id is None:
                messagebox.showinfo("编辑卡组", "请先选中一张卡牌。", parent=editor)
                return
            try:
                value = int(count_var.get())
            except (TypeError, ValueError):
                messagebox.showerror("数量错误", "数量必须是 0 到 3。", parent=editor)
                return
            if not 0 <= value <= 3:
                messagebox.showerror("数量错误", "数量必须是 0 到 3。", parent=editor)
                return
            if value == 0:
                counts.pop(selected_id, None)
                selected_id = None
            else:
                counts[selected_id] = value
            refresh()

        def add_card() -> None:
            value = option_ids.get(choice_var.get())
            if value is None:
                messagebox.showinfo("添加卡牌", "请先从下拉框选择卡牌。", parent=editor)
                return
            if value in counts:
                messagebox.showinfo("添加卡牌", "该卡牌已经在当前牌组中，请直接修改数量。", parent=editor)
                return
            counts[value] = 1
            refresh()
            table.selection_set(str(value))
            table.focus(str(value))
            on_select()

        def save_changes() -> None:
            if sum(counts.values()) != 40:
                messagebox.showerror("保存失败", "牌组必须正好包含 40 张牌。", parent=editor)
                return
            try:
                updated = self._repository.update_cards(
                    deck.key,
                    tuple(DeckCard(card_id=card_id, count=count) for card_id, count in counts.items()),
                )
            except (OSError, KeyError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=editor)
                return
            editor.destroy()
            self._match_id = None
            self._match_deck_key = None
            self._refresh_deck_choices()
            self.deck_status_var.set(f"已保存修改：{updated.name}（仍为同一统计卡组）")
            if self._service and self._service.running:
                self._service.set_selected_deck(updated.to_snapshot(), updated.key)
            self._update_stats_summary()

        table.bind("<<TreeviewSelect>>", on_select)
        search_entry.bind("<KeyRelease>", refresh_options)
        refresh()

    def _render_deck_info(self, deck: dict[str, object]) -> None:
        if not deck:
            self._set_text(self.deck_text, "请从本地牌组仓库选择牌组")
            return
        segments: list[tuple[str, str | None]] = [
            (
                f"{deck.get('deck_name') or '未命名牌组'}  "
                f"（{class_name(deck.get('class_id') if isinstance(deck.get('class_id'), int) else None)} / "
                f"{self._format_mode(deck.get('deck_format') if isinstance(deck.get('deck_format'), int) else 2)}）\n",
                "deck_header",
            ),
            (f"剩余牌库：{deck.get('total_cards', '?')} / {deck.get('total_cards', '?')} 张\n", "deck_header"),
            ("\n牌组卡牌\n", "deck_section"),
        ]
        cards = deck.get("cards", ())
        if isinstance(cards, (list, tuple)):
            for card in sorted((card for card in cards if isinstance(card, dict)), key=self._card_sort_key):
                segments.append((self._format_deck_row({
                    "card_id": card.get("card_id"),
                    "remaining": card.get("count"),
                    "initial": card.get("count"),
                }) + "\n", None))
        self._set_rich_text(self.deck_text, segments)

    def _render_active_deck_full(self) -> None:
        active = self._active_saved_deck()
        if active is None:
            self._set_text(self.deck_text, "请从本地牌组仓库选择牌组")
            return
        self._render_deck_info({
            "deck_name": active.name,
            "class_id": active.class_id,
            "deck_format": active.format_version,
            "total_cards": active.total_cards,
            "cards": [card.__dict__ for card in active.cards],
        })

    def _active_saved_deck(self) -> SavedDeck | None:
        return self._repository.active()

    def _active_deck_snapshot(self):
        deck = self._active_saved_deck()
        return deck.to_snapshot() if deck else None

    def _refresh_deck_choices(self) -> None:
        self._deck_choice_keys = [deck.key for deck in self._repository.decks]
        labels = [
            f"{deck.name}（{class_name(deck.class_id)} / {self._format_mode(deck.format_version)} / "
            f"{len(deck.cards)} 种 / {deck.total_cards} 张）"
            for deck in self._repository.decks
        ]
        self.deck_choice.configure(values=labels)
        active = self._active_saved_deck()
        if active is not None:
            index = self._deck_choice_keys.index(active.key)
            self.deck_choice.current(index)
            self.deck_status_var.set(
                f"已选择：{active.name}（{class_name(active.class_id)} / "
                f"{self._format_mode(active.format_version)}）；仓库位置：{self._repository.path}"
            )
            self._render_deck_info(active.to_snapshot().to_dict())
        else:
            self.deck_choice.set("")
            message = "尚未导入牌组，请粘贴官方牌组详情链接"
            if self._repository_error:
                message = f"牌组仓库读取失败：{self._repository_error}"
            self.deck_status_var.set(message)
            if hasattr(self, "deck_text"):
                self._set_text(self.deck_text, "请先导入或选择牌组")

    def _select_deck(self, _event: object = None) -> None:
        index = self.deck_choice.current()
        if not 0 <= index < len(self._deck_choice_keys):
            return
        try:
            deck = self._repository.select(self._deck_choice_keys[index])
        except (OSError, KeyError, ValueError) as exc:
            messagebox.showerror("切换失败", str(exc), parent=self)
            return
        self.deck_status_var.set(
            f"已选择：{deck.name}（{class_name(deck.class_id)} / "
            f"{self._format_mode(deck.format_version)}）；后续账本使用此牌组"
        )
        self._match_id = None
        self._match_deck_key = None
        self._render_deck_info(deck.to_snapshot().to_dict())
        if self._service and self._service.running:
            self._service.set_selected_deck(deck.to_snapshot(), deck.key)
        self._update_stats_summary()

    def _clear_deck_selection(self) -> None:
        """Detach the local deck ledger without deleting saved deck data."""
        try:
            self._repository.clear_selection()
        except (OSError, ValueError) as exc:
            messagebox.showerror("清空失败", str(exc), parent=self)
            return
        self._match_id = None
        self._match_deck_key = None
        self._refresh_deck_choices()
        self.deck_status_var.set("已清空当前牌组；特殊/解密对局将不使用本地牌库")
        if self._service and self._service.running:
            self._service.set_selected_deck(None, None)
        self._update_stats_summary()

    def _import_deck(self) -> None:
        raw = self.deck_url_var.get().strip()
        if not raw:
            try:
                raw = self.clipboard_get().strip()
            except tk.TclError:
                raw = ""
        try:
            parsed = self._parse_deck_input(raw)
        except OfficialDeckError as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        self._save_imported_deck(parsed)

    @staticmethod
    def _parse_deck_input(raw: str) -> OfficialDeck:
        """Accept either a full official hash/link or a four-character code.

        Official QR codes can encode either representation, so both import
        paths intentionally use this single resolver.
        """
        value = str(raw or "").strip()
        return import_deck_code(value) if len(value) == 4 and "." not in value else parse_official_deck(value)

    def _save_imported_deck(self, parsed: OfficialDeck) -> None:
        selected_class = next(
            (class_id for class_id, label in CLASS_NAMES.items() if label == self.import_class_var.get()),
            parsed.class_id,
        )
        selected_format = 1 if self.import_mode_var.get() == "轮换" else 2
        # The visible registration fields are authoritative.  This lets a
        # user correct an outdated class/format in a copied link while keeping
        # the original URL as the source for traceability.
        parsed = OfficialDeck(
            format_version=selected_format,
            class_id=selected_class,
            cards=parsed.cards,
            source=parsed.source,
        )
        preview_names = [get_card_name(card.card_id) for card in parsed.cards[:2]]
        default_name = " / ".join(preview_names) + " 牌组"
        name = simpledialog.askstring(
            "保存牌组",
            "请输入本地牌组名称：",
            initialvalue=default_name,
            parent=self,
        )
        if name is None:
            return
        try:
            saved = self._repository.add_official(name, parsed)
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.deck_url_var.set("")
        self._repository_error = ""
        self._refresh_deck_choices()
        self.deck_status_var.set(
            f"已导入并选择：{saved.name}（{class_name(saved.class_id)} / "
            f"{self._format_mode(saved.format_version)} / 40 张）"
        )
        self._match_id = None
        self._match_deck_key = None
        if self._service and self._service.running:
            self._service.set_selected_deck(saved.to_snapshot(), saved.key)
        self._update_stats_summary()

    @staticmethod
    def _deck_restriction_text(class_id: int, format_version: int) -> str:
        class_label = class_name(class_id)
        if int(format_version) == 1:
            newest = latest_card_pack()
            return f"可添加：{class_label} + 中立；轮换卡包 {max(0, newest - 5)}–{newest}"
        return f"可添加：{class_label} + 中立；无限模式不限制卡包"

    @staticmethod
    def _format_mode(format_version: int) -> str:
        return "轮换" if int(format_version) == 1 else "无限"

    def _delete_deck(self) -> None:
        deck = self._active_saved_deck()
        if deck is None:
            return
        if not messagebox.askyesno(
            "删除牌组",
            f"确定从本地仓库删除“{deck.name}”吗？",
            parent=self,
        ):
            return
        try:
            self._repository.delete(deck.key)
        except (OSError, KeyError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=self)
            return
        self._refresh_deck_choices()
        active = self._active_deck_snapshot()
        self._match_id = None
        self._match_deck_key = None
        if self._service and self._service.running:
            active_saved = self._active_saved_deck()
            self._service.set_selected_deck(active, active_saved.key if active_saved else None)
        self._update_stats_summary()

    @staticmethod
    @lru_cache(maxsize=1)
    def _runtime_keyword_rules() -> dict[str, object]:
        """Load the optional local static-keyword index for field display."""
        path = Path(__file__).resolve().parent / "data" / "card_rules.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _field_static_keywords(card_id: object) -> set[str]:
        if not isinstance(card_id, int) or card_id <= 0:
            return set()
        rules = TrackerApp._runtime_keyword_rules()
        entry = rules.get(str(canonical_card_id(card_id)), {})
        if not isinstance(entry, dict):
            return set()
        static = entry.get("static", {})
        if not isinstance(static, dict):
            return set()
        result: set[str] = set()
        if static.get("has_storm"):
            result.add("疾驰")
        if static.get("has_rush"):
            result.add("突进")
        return result

    @staticmethod
    def _format_field(cards: object) -> list[str]:
        if not isinstance(cards, (list, tuple)):
            return []
        lines: list[str] = []
        keyword_flags = (
            ("has_storm", "疾驰"),
            ("has_rush", "突进"),
            ("has_guard", "守护"),
            ("has_last_word", "谢幕曲"),
            ("has_sneak", "潜行"),
            ("has_cant_be_attacked", "无法被攻击"),
            ("has_cant_select", "无法被选中为目标"),
            ("has_killer", "必杀"),
            ("has_bane", "必杀"),
            ("has_drain", "虹吸"),
            ("has_cant_attack", "无法攻击"),
        )
        for card in cards:
            if not isinstance(card, dict):
                continue
            card_type = card.get("card_type", card.get("type"))
            try:
                is_amulet = int(card_type) in (2, 3)
            except (TypeError, ValueError):
                is_amulet = str(card_type).casefold() in {"amulet", "countdown_amulet"}
            if is_amulet:
                countdown = card.get("countdown", card.get("remaining_countdown"))
                counter = f"倒数={countdown}" if isinstance(countdown, int) and countdown >= 0 else "倒数=?"
                line = f"{TrackerApp._format_card_line(card)}  护符  {counter}"
            else:
                line = (
                    f"{TrackerApp._format_card_line(card)}  "
                    f"{card.get('attack')}/{card.get('life')}  进化={card.get('evolve_state')}"
                )
            keywords = TrackerApp._field_static_keywords(card.get("card_id"))
            for key, label in keyword_flags:
                if card.get(key):
                    keywords.add(label)
            buff = card.get("buff")
            if isinstance(buff, dict):
                if buff.get("quick"):
                    keywords.add("突进")
                if buff.get("rush"):
                    keywords.add("疾驰")
            statuses = card.get("statuses", card.get("keywords"))
            if isinstance(statuses, (list, tuple, set)):
                aliases = {"storm": "疾驰", "rush": "突进", "ward": "守护", "bane": "必杀", "ambush": "潜行", "last_words": "谢幕曲"}
                keywords.update(aliases.get(str(item).casefold(), str(item)) for item in statuses)
            if keywords:
                line += "  【" + "】【".join(sorted(keywords)) + "】"
            lines.append(line)
        return lines

    @staticmethod
    def _format_recent_history(mine: dict[str, object], opponent: dict[str, object]) -> str:
        def format_cards(value: object, turns: object = None) -> list[str]:
            if not isinstance(value, (list, tuple)):
                return []
            lines: list[str] = []
            turn_values = list(turns) if isinstance(turns, (list, tuple)) else []
            start = max(0, len(value) - 10)
            for index, item in enumerate(value[start:], start=start):
                prefix = f"T{turn_values[index]}：" if index < len(turn_values) and isinstance(turn_values[index], int) and turn_values[index] > 0 else ""
                if isinstance(item, (list, tuple)) and item:
                    lines.append(prefix + TrackerApp._card_label(item[0]))
                elif isinstance(item, int):
                    lines.append(prefix + TrackerApp._card_label(item))
                else:
                    lines.append(prefix + str(item))
            return lines

        turns = mine.get("_played_card_turns")
        opponent_turns = opponent.get("_played_card_turns")
        mine_lines = format_cards(mine.get("played_card_ids", ()), turns)
        opponent_lines = format_cards(opponent.get("played_card_ids", ()), opponent_turns)

        def action_lines(actions: object) -> list[str]:
            values: list[tuple[int, int, str]] = []
            if isinstance(actions, (list, tuple)):
                for item in actions:
                    if not isinstance(item, dict):
                        continue
                    turn, order, card_id, kind = item.get("turn"), item.get("order"), item.get("card_id"), item.get("kind")
                    if isinstance(turn, int) and isinstance(order, int) and isinstance(card_id, int) and isinstance(kind, str):
                        values.append((turn, order, f"T{turn}：{kind} {TrackerApp._card_label(card_id)}"))
            return [line for _turn, _order, line in sorted(values)[-20:]]

        own_actions = action_lines(mine.get("_recent_actions"))
        if own_actions:
            mine_lines = own_actions

        def append_event_plays(lines: list[str], player: dict[str, object]) -> None:
            events = player.get("_event_played_cards")
            if not isinstance(events, (list, tuple)):
                return
            # The persistent history can arrive after the public response.
            # Avoid showing that same play twice while retaining repeated cards.
            existing = list(lines)
            for event in events:
                if not isinstance(event, dict):
                    continue
                card_id, turn = event.get("card_id"), event.get("turn")
                if not isinstance(card_id, int):
                    continue
                prefix = f"T{turn}：" if isinstance(turn, int) and turn > 0 else ""
                line = prefix + TrackerApp._card_label(card_id)
                if line in existing:
                    existing.remove(line)
                else:
                    lines.append(line)

        append_event_plays(mine_lines, mine)
        append_event_plays(opponent_lines, opponent)
        knowledge = opponent.get("opponent_hand_knowledge")
        actions = knowledge.get("recent_actions", ()) if isinstance(knowledge, dict) else ()
        ordered_actions = action_lines(actions)
        if ordered_actions:
            opponent_lines = ordered_actions
        mine_mulligan = mine.get("mulligan_summary")
        if isinstance(mine_mulligan, dict) and mine_mulligan.get("initial_hand"):
            mine_lines.insert(0, "起手：" + "、".join(TrackerApp._card_label(v) for v in mine_mulligan.get("initial_hand", ())))
            replaced = mine_mulligan.get("replaced_cards", ())
            final_hand = mine_mulligan.get("final_hand", ())
            if replaced:
                mine_lines.insert(1, "换出：" + "、".join(TrackerApp._card_label(v) for v in replaced))
            if final_hand:
                mine_lines.insert(2, "换后：" + "、".join(TrackerApp._card_label(v) for v in final_hand))
        draw_history = mine.get("_draw_history")
        if isinstance(draw_history, (list, tuple)):
            for item in draw_history[-20:]:
                if not isinstance(item, dict) or not isinstance(item.get("turn"), int):
                    continue
                if item.get("kind") == "爆牌":
                    if isinstance(item.get("card_id"), int):
                        mine_lines.append(f"T{item['turn']}：爆牌 {TrackerApp._card_label(item['card_id'])}")
                    else:
                        mine_lines.append(f"T{item['turn']}：爆牌 {item.get('count', 1)} 张")
                elif isinstance(item.get("card_id"), int):
                    mine_lines.append(f"T{item['turn']}：抽取 {TrackerApp._card_label(item['card_id'])}")
        opponent_mulligan = opponent.get("mulligan_summary")
        if isinstance(opponent_mulligan, dict) and isinstance(opponent_mulligan.get("replaced_count"), int):
            opponent_lines.insert(0, f"起手换牌：{opponent_mulligan['replaced_count']} 张")
        if not mine_lines:
            mine_lines = ["（暂无）"]
        if not opponent_lines:
            opponent_lines = ["（暂无记录）"]
        evolution_events = knowledge.get("recent_evolution_events", ()) if isinstance(knowledge, dict) else ()
        if not actions and isinstance(evolution_events, (list, tuple)):
            for item in evolution_events[-10:]:
                if isinstance(item, dict):
                    turn = item.get("turn")
                    card_id = item.get("card_id")
                    kind = item.get("kind", "进化")
                    if isinstance(turn, int) and isinstance(card_id, int):
                        opponent_lines.append(f"T{turn}：对手{kind} {TrackerApp._card_label(card_id)}")
        return (
            "我方记录：\n"
            + "\n".join(mine_lines)
            + "\n\n对手记录：\n"
            + "\n".join(opponent_lines)
        )

    def _format_known_opponent_hand(self) -> list[str]:
        if not self._opponent_known_hand.cards:
            return ["（暂无已知明牌）"]
        values = list(self._opponent_known_hand.cards.items())
        values.sort(
            key=lambda item: (
                999
                if item[0] == "unknown_spell"
                else (
                    get_card_metadata(int(item[0])).cost
                    if isinstance(item[0], int) and get_card_metadata(int(item[0])) is not None
                    else 999
                ),
                UNKNOWN_CARD_TYPE_LABELS.get(str(item[0]), str(item[0]))
                if isinstance(item[0], str)
                else get_card_name(int(item[0])),
            )
        )
        lines: list[str] = []
        for value, count in values:
            if not isinstance(count, int) or count <= 0:
                continue
            name = (
                UNKNOWN_CARD_TYPE_LABELS.get(value, value)
                if isinstance(value, str)
                else get_card_name(int(value))
            )
            lines.append(f"{name}：{count}")
        return lines or ["（暂无已知明牌）"]

    def _format_opponent_hand(self, opponent: dict[str, object]) -> list[str]:
        hand = opponent.get("hand")
        if isinstance(hand, (list, tuple)):
            # The normal battle snapshot contains placeholder
            # BattleHandCardMpo objects for an opponent's hidden cards.  Those
            # objects have a real address but every card field is zero.  Do not
            # render them as the misleading "0费 0"; only a resolved card ID
            # is useful to a player.
            visible = [
                card
                for card in hand
                if isinstance(card, dict)
                and not card.get("hidden")
                and isinstance(card.get("base_card_id") or card.get("card_id"), int)
                and int(card.get("base_card_id") or card.get("card_id") or 0) > 0
            ]
            if visible:
                return [self._format_card_line(card) for card in visible]
        return self._format_known_opponent_hand()

    def _format_general_counters(self, snapshot: dict[str, object]) -> str:
        class_id = snapshot.get("opponent_class_id")
        if not isinstance(class_id, int):
            return "对手职业未知\n暂无专属计数器"
        knowledge = snapshot.get("opponent_hand_knowledge")
        if not isinstance(knowledge, dict):
            return f"对手职业：{class_name(class_id)}\n等待计数数据…"
        lines = []
        lines.append(f"进化次数：{knowledge.get('evolution_count', 0)}")
        lines.append(f"解放奥义计数：{knowledge.get('liberation_count', 0)}")
        triggers = knowledge.get("saint_daphen_triggers", ())
        if not isinstance(triggers, (list, tuple)) or not triggers:
            lines.append("圣德芬解放奥义：尚未瞬招")
        else:
            lines.append("圣德芬解放奥义：")
            evolution = int(knowledge.get("evolution_count", 0) or 0)
            turn_now = int(knowledge.get("current_turn", 0) or 0)
            for index, item in enumerate(triggers, 1):
                base = int(item.get("base_evolution", 0)) if isinstance(item, dict) else 0
                lines.append(f"圣德芬{index}：{max(0, evolution - base) + turn_now}")
        return "\n".join(lines)

    def _format_class_counters(self, snapshot: dict[str, object]) -> str:
        class_id = snapshot.get("opponent_class_id")
        knowledge = snapshot.get("opponent_hand_knowledge")
        if not isinstance(class_id, int):
            return "对手职业未知"
        if not isinstance(knowledge, dict):
            return f"对手职业：{class_name(class_id)}\n等待计数数据…"
        suffix = "（魔力增幅）" if class_id == 3 else ""
        lines = [f"对手职业：{class_name(class_id)}{suffix}"]
        if class_id == 3:
            turns = knowledge.get("turn_magic_boost", {})
            if isinstance(turns, dict):
                for key, value in sorted(turns.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999):
                    lines.append(f"T{key}：{value}")
            lines.append(f"Total：{knowledge.get('magic_boost', 0)}")
        else:
            lines.append("暂无该职业专属计数器")
        return "\n".join(lines)

    @staticmethod
    def _card_label(value: object) -> str:
        if not isinstance(value, int) or value <= 0:
            return str(value)
        return get_card_name(value)

    @staticmethod
    def _format_card_line(card: dict[str, object]) -> str:
        value = card.get("base_card_id") or card.get("card_id")
        name = TrackerApp._card_label(value)
        cost = card.get("cost")
        if not isinstance(cost, int):
            metadata = get_card_metadata(value) if isinstance(value, int) and value > 0 else None
            cost = metadata.cost if metadata is not None else "?"
        return f"{cost}费 {name}"

    @staticmethod
    def _card_sort_key(card: dict[str, object]) -> tuple[int, str]:
        value = card.get("card_id")
        metadata = get_card_metadata(value) if isinstance(value, int) and value > 0 else None
        return (metadata.cost if metadata is not None else 999, get_card_name(value) if isinstance(value, int) else "未知卡牌")

    @staticmethod
    def _format_deck_row(row: dict[str, object]) -> str:
        value = row.get("card_id")
        name = TrackerApp._card_label(value)
        metadata = get_card_metadata(value) if isinstance(value, int) and value > 0 else None
        cost = metadata.cost if metadata is not None else "?"
        return f"{cost}费 {name}  {row.get('remaining')}/{row.get('initial')}"

    def _close(self) -> None:
        if self._probability_window is not None:
            try:
                self._probability_window.destroy()
            except tk.TclError:
                pass
            self._probability_window = None
        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None
            self._overlay_canvas = None
        if self._service:
            self._service.stop()
        self.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=lambda value: int(value, 0), help="BattleModel address")
    parser.add_argument("--pid", type=int, help="target game PID; auto-detected when omitted")
    args = parser.parse_args()
    TrackerApp(args).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
