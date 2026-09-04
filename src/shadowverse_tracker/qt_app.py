"""Modern Qt dashboard for Shadowverse Tracker.

This module is the UI migration branch's shell.  The memory reader, deck
ledger, match history and training recorder stay in their existing modules;
this window only translates their snapshots into a compact Qt dashboard.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit as QtLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
    TransparentPushButton,
    setTheme,
    setThemeColor,
    Theme,
)

from .card_catalog import get_card_metadata, get_card_name
from .deck_repository import DeckRepository, SavedDeck
from .faith_probability import calculate_faith_damage_probability
from .match_history import (
    CLASS_NAMES,
    MatchHistory,
    MatchRecord,
    class_name,
    result_label,
    terminal_match_id,
)
from .official_deck import OfficialDeckError, import_deck_code, parse_official_deck
from .opponent_key_probability import calculate_key_probability
from .tracker_service import TrackerConfig, TrackerService


APP_STYLESHEET = """
QWidget#qtRoot, QWidget#page {
    background: #f4f7fb;
    color: #172536;
}
QWidget#page {
    background: #f4f7fb;
}
QFrame#headerCard, QFrame#statusCard, QFrame#metricCard,
QFrame#panelCard, QFrame#actionCard, QFrame#settingsCard {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
}
QFrame#headerCard {
    border-top: 3px solid #169eb0;
}
QLabel#eyebrow {
    color: #4f7890;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statusPill {
    background: #e6f5f5;
    color: #087887;
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statusPill[error="true"] {
    background: #fff0f0;
    color: #b33c4b;
}
QLabel#statusPill[connected="true"] {
    background: #e7f7ee;
    color: #24784d;
}
QLabel#metricTitle {
    color: #71859a;
    font-size: 11px;
}
QLabel#metricValue {
    color: #1e4d70;
    font-size: 20px;
    font-weight: 700;
}
QLabel#metricHint {
    color: #8798a8;
    font-size: 10px;
}
QLabel#sectionTitle {
    color: #244f70;
    font-size: 13px;
    font-weight: 700;
}
QLabel#muted {
    color: #74879a;
    font-size: 11px;
}
QTextEdit#dataView {
    background: #fbfcfe;
    color: #1d3348;
    border: 1px solid #e0e8f0;
    border-radius: 8px;
    padding: 7px;
    font-size: 11px;
}
QTextEdit#dataView:focus {
    border: 1px solid #79bdc8;
}
QListWidget#deckList {
    background: #fbfcfe;
    border: 1px solid #dfe7ef;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget#deckList::item {
    padding: 9px 8px;
    border-radius: 7px;
}
QListWidget#deckList::item:selected {
    background: #dff2f4;
    color: #0b6f80;
}
QTableWidget#matchTable {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #dfe7ef;
    border-radius: 8px;
    gridline-color: #edf1f5;
    selection-background-color: #dff2f4;
    selection-color: #164e63;
}
QHeaderView::section {
    background: #eef4f8;
    color: #46677f;
    border: none;
    border-bottom: 1px solid #dfe7ef;
    padding: 7px;
    font-weight: 600;
}
QFrame#calculatorCard {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
}
QLineEdit, QComboBox, QSpinBox {
    min-height: 30px;
    border: 1px solid #cbd9e5;
    border-radius: 7px;
    padding: 3px 8px;
    background: #ffffff;
    color: #1b344b;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #42a9b5;
}
QPushButton {
    min-height: 30px;
    border-radius: 7px;
}
QSplitter::handle {
    background: #e0e8ef;
}
"""


def _set_font(widget: QWidget, size: int, *, bold: bool = False) -> None:
    font = widget.font()
    font.setPointSize(size)
    font.setBold(bold)
    widget.setFont(font)


def _read_card_id(card: object) -> int | None:
    if not isinstance(card, dict):
        return None
    value = card.get("base_card_id") or card.get("card_id")
    return value if isinstance(value, int) and value > 0 else None


class QtCardPanel(QFrame):
    """A titled white content card used by the dashboard pages."""

    def __init__(self, title: str, *, object_name: str = "panelCard", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)
        self.body = QTextEdit()
        self.body.setObjectName("dataView")
        self.body.setReadOnly(True)
        self.body.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.body, 1)

    def set_text(self, value: str) -> None:
        self.body.setPlainText(value)


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "—", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("metricHint")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)

    def set_value(self, value: object, hint: str | None = None) -> None:
        self.value_label.setText(str(value))
        if hint is not None:
            self.hint_label.setText(hint)


class OverlayWindow(QWidget):
    """Small always-on-top deck window with the same visual language."""

    def __init__(self, parent: "QtTrackerWindow") -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.parent_window = parent
        self.setWindowTitle("Shadowverse 悬浮记牌器")
        self.setMinimumSize(300, 360)
        self.resize(360, 620)
        self.setStyleSheet(APP_STYLESHEET + "QWidget#overlayRoot { background:#f4f7fb; }")
        self.setObjectName("overlayRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        self.header = QFrame()
        self.header.setObjectName("headerCard")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(12, 9, 12, 9)
        self.title = StrongBodyLabel("悬浮记牌器")
        self.stats = CaptionLabel("等待对局数据")
        header_layout.addWidget(self.title)
        header_layout.addWidget(self.stats)
        root.addWidget(self.header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(7)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)
        close = TransparentPushButton("Esc 关闭")
        close.clicked.connect(self.close)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def update_snapshot(self, snapshot: dict[str, object] | None) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        deck = self.parent_window._active_deck()
        if deck is None:
            self.stats.setText("未选择牌组")
            return
        stats = self.parent_window._history.stats(deck.key)
        self.stats.setText(
            f"总胜率 {float(stats['win_rate']):.1f}%（{int(stats['finished'])}局）  "
            f"先手 {float(stats['first']['win_rate']):.1f}%  "
            f"后手 {float(stats['second']['win_rate']):.1f}%"
        )
        ledger = snapshot.get("deck_ledger") if isinstance(snapshot, dict) else None
        rows = ledger.get("rows", ()) if isinstance(ledger, dict) else [
            {"card_id": card.card_id, "remaining": card.count, "initial": card.count}
            for card in deck.cards
        ]
        rows = [row for row in rows if isinstance(row, dict)]
        rows.sort(key=lambda row: (int(row.get("remaining", 0)) <= 0, self.parent_window._card_sort_key(row)))
        count = ledger.get("authoritative_deck_count", "?") if isinstance(ledger, dict) else deck.total_cards
        total = sum(int(row.get("initial", 0)) for row in rows)
        self.title.setText(f"{deck.name}  ·  {count}/{total}")
        for index, row in enumerate(rows):
            card_id = row.get("card_id")
            name = self.parent_window._card_name(card_id)
            remaining = row.get("remaining", "?")
            initial = row.get("initial", "?")
            label = QLabel(f"{name}\n{remaining}/{initial}")
            label.setWordWrap(True)
            label.setMinimumHeight(42)
            label.setStyleSheet(
                "background:#ffffff;border:1px solid %s;border-radius:8px;padding:7px;color:#1d3348;"
                % ("#e49ba3" if isinstance(remaining, int) and remaining <= 0 else "#dbe4ee")
            )
            self.grid.addWidget(label, index // 2, index % 2)


class DeckEditorDialog(QDialog):
    """Compact card-count editor for the migrated deck page."""

    def __init__(self, window: "QtTrackerWindow", deck: SavedDeck) -> None:
        super().__init__(window)
        self.setWindowTitle(f"编辑牌组 · {deck.name}")
        self.resize(650, 500)
        self.window_ref = window
        self.deck = deck
        layout = QVBoxLayout(self)
        info = QLabel("修改每种卡牌数量；牌组总数必须保持 40 张。")
        info.setObjectName("muted")
        layout.addWidget(info)
        self.table = QTableWidget(len(deck.cards), 4)
        self.table.setObjectName("matchTable")
        self.table.setHorizontalHeaderLabels(("费用", "卡牌名称", "数量", "Card ID"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for row, card in enumerate(deck.cards):
            metadata = get_card_metadata(card.card_id)
            cost = str(metadata.cost) if metadata else "?"
            self.table.setItem(row, 0, QTableWidgetItem(cost))
            self.table.setItem(row, 1, QTableWidgetItem(window._card_name(card.card_id)))
            spin = QSpinBox()
            spin.setRange(0, 3)
            spin.setValue(card.count)
            self.table.setCellWidget(row, 2, spin)
            self.table.setItem(row, 3, QTableWidgetItem(str(card.card_id)))
        layout.addWidget(self.table, 1)
        self.total_label = QLabel()
        self.total_label.setObjectName("muted")
        layout.addWidget(self.total_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for row in range(self.table.rowCount()):
            spin = self.table.cellWidget(row, 2)
            if isinstance(spin, QSpinBox):
                spin.valueChanged.connect(self._update_total)
        self._update_total()

    def _update_total(self) -> None:
        total = sum(
            self.table.cellWidget(row, 2).value()
            for row in range(self.table.rowCount())
            if isinstance(self.table.cellWidget(row, 2), QSpinBox)
        )
        self.total_label.setText(f"当前总数：{total}/40")
        self.total_label.setStyleSheet("color:#24784d;" if total == 40 else "color:#b33c4b;")

    def cards(self):
        from .memory.deck import DeckCard

        cards = []
        for row, original in enumerate(self.deck.cards):
            spin = self.table.cellWidget(row, 2)
            count = spin.value() if isinstance(spin, QSpinBox) else original.count
            if count:
                cards.append(DeckCard(card_id=original.card_id, count=count))
        return tuple(cards)

    def accept(self) -> None:
        cards = self.cards()
        if sum(card.count for card in cards) != 40:
            QMessageBox.warning(self, "无法保存", "牌组必须正好包含 40 张牌。")
            return
        try:
            updated = self.window_ref._repository.update_cards(self.deck.key, cards)
        except (OSError, KeyError, ValueError) as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.window_ref._on_deck_saved(updated)
        super().accept()


class QtTrackerWindow(FluentWindow):
    """Qt/Fluent dashboard that consumes the existing tracker service."""

    snapshot_received = Signal(object)
    status_received = Signal(str)
    error_received = Signal(object)
    deck_received = Signal(object)

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.setObjectName("qtRoot")
        self.setWindowTitle("Shadowverse Tracker")
        self.resize(1280, 820)
        self.setMinimumSize(1060, 700)
        self._startup_pid: int | None = getattr(args, "pid", None)
        self._model_address = int(getattr(args, "model", 0) or 0)
        self._service: TrackerService | None = None
        self._last_snapshot: dict[str, object] | None = None
        self._match_id: str | None = None
        self._match_deck_key: str | None = None
        self._last_model_address: str | None = None
        self._last_turn: int | None = None
        self._last_result_code: int | None = None
        self._match_sequence = 0
        self._status_text = "未连接 · 自动识别客户端"
        self._overlay: OverlayWindow | None = None
        self._deck_choice_keys: list[str | None] = []
        self._repository = DeckRepository()
        self._repository_error = ""
        try:
            self._repository.load()
        except (OSError, ValueError) as exc:
            self._repository_error = str(exc)
        self._history = MatchHistory()
        self._history_error = ""
        try:
            self._history.load()
        except (OSError, ValueError) as exc:
            self._history_error = str(exc)
        self._record_matches = True
        self._set_application_icon()
        self._build_ui()
        self.snapshot_received.connect(self._render_snapshot)
        self.status_received.connect(self._set_status)
        self.error_received.connect(self._on_error)
        self.deck_received.connect(self._on_deck_event)
        self._refresh_deck_choices()
        self._refresh_stats_page()
        QTimer.singleShot(250, self._start_service)

    # ----- shell and navigation -------------------------------------------------

    def _build_ui(self) -> None:
        dashboard = self._build_dashboard_page()
        decks = self._build_decks_page()
        probability = self._build_probability_page()
        stats = self._build_stats_page()
        settings = self._build_settings_page()
        self.dashboard_page = dashboard
        self.decks_page = decks
        self.probability_page = probability
        self.stats_page = stats
        self.settings_page = settings
        self.addSubInterface(dashboard, FluentIcon.HOME, "对局仪表盘")
        self.addSubInterface(decks, FluentIcon.LIBRARY, "牌组管理")
        self.addSubInterface(probability, FluentIcon.SYNC, "概率计算")
        self.addSubInterface(stats, FluentIcon.HISTORY, "对局统计")
        self.addSubInterface(settings, FluentIcon.SETTING, "设置", NavigationItemPosition.BOTTOM)

    @staticmethod
    def _page() -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        return page

    def _page_layout(self, page: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(12)
        return layout

    @staticmethod
    def _app_asset_path(name: str) -> Path | None:
        """Locate an icon in source runs and PyInstaller onedir builds."""
        package_root = Path(__file__).resolve().parent
        roots = [package_root / "assets"]
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            roots.insert(0, Path(frozen_root) / "shadowverse_tracker" / "assets")
        executable_root = Path(sys.executable).resolve().parent
        roots.extend((executable_root / "shadowverse_tracker" / "assets", executable_root / "_internal" / "shadowverse_tracker" / "assets"))
        return next((root / name for root in roots if (root / name).is_file()), None)

    def _set_application_icon(self) -> None:
        icon_path = self._app_asset_path("kandima_icon.ico") or self._app_asset_path("Kandima_icon.png")
        if icon_path is None:
            return
        icon = QIcon(str(icon_path))
        self.setWindowIcon(icon)
        application = QApplication.instance()
        if application is not None:
            application.setWindowIcon(icon)

    def _build_dashboard_page(self) -> QWidget:
        page = self._page()
        layout = self._page_layout(page)
        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 13)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = TitleLabel("影之诗 Tracker")
        subtitle = QLabel("只读对局仪表盘 · Steam / 国服")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        self.status_pill = QLabel(self._status_text)
        self.status_pill.setObjectName("statusPill")
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        header_layout.addLayout(top)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.deck_choice = ComboBox()
        self.deck_choice.setMinimumWidth(330)
        self.deck_choice.currentIndexChanged.connect(self._select_deck_index)
        controls.addWidget(QLabel("当前牌组"))
        controls.addWidget(self.deck_choice, 1)
        self.connection_mode = ComboBox()
        self.connection_mode.addItems(("自动", "Steam", "国服"))
        self.connection_mode.setCurrentIndex(0)
        self.connection_mode.currentTextChanged.connect(self._change_connection_mode)
        controls.addWidget(QLabel("连接"))
        controls.addWidget(self.connection_mode)
        self.overlay_button = PrimaryPushButton("悬浮记牌器")
        self.overlay_button.setIcon(FluentIcon.VIEW.icon())
        self.overlay_button.clicked.connect(self._toggle_overlay)
        controls.addWidget(self.overlay_button)
        self.stats_button = PushButton("详细统计")
        self.stats_button.setIcon(FluentIcon.HISTORY.icon())
        self.stats_button.clicked.connect(lambda: self._switch_page(self.stats_page))
        controls.addWidget(self.stats_button)
        header_layout.addLayout(controls)
        layout.addWidget(header)

        self.metric_deck = MetricCard("剩余牌库", "40 / 40", "等待对局数据")
        self.metric_turn = MetricCard("当前回合", "—", "未连接")
        self.metric_client = MetricCard("连接客户端", "自动", "等待启动")
        self.metric_rate = MetricCard("当前牌组胜率", "—", "未选择牌组")
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        for card in (self.metric_deck, self.metric_turn, self.metric_client, self.metric_rate):
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        self.dashboard_status = QFrame()
        self.dashboard_status.setObjectName("statusCard")
        status_layout = QHBoxLayout(self.dashboard_status)
        status_layout.setContentsMargins(14, 9, 14, 9)
        self.dashboard_status_label = QLabel("等待游戏启动或重新连接 · 自动重试")
        self.dashboard_status_label.setObjectName("muted")
        status_layout.addWidget(self.dashboard_status_label, 1)
        self.dashboard_deck_label = QLabel("未选择本地牌组")
        self.dashboard_deck_label.setObjectName("eyebrow")
        status_layout.addWidget(self.dashboard_deck_label)
        layout.addWidget(self.dashboard_status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.hand_panel = QtCardPanel("我的手牌")
        self.deck_panel = QtCardPanel("剩余牌库")
        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        self.field_panel = QtCardPanel("目前对局")
        self.history_panel = QtCardPanel("最近记录")
        right.addWidget(self.field_panel)
        right.addWidget(self.history_panel)
        right.setSizes((370, 280))
        splitter.addWidget(self.hand_panel)
        splitter.addWidget(self.deck_panel)
        splitter.addWidget(right)
        splitter.setSizes((260, 320, 520))
        layout.addWidget(splitter, 1)
        return page

    def _build_decks_page(self) -> QWidget:
        page = self._page()
        layout = self._page_layout(page)
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("牌组管理"))
        title_row.addStretch(1)
        self.deck_delete_button = PushButton("删除")
        self.deck_delete_button.setIcon(FluentIcon.DELETE.icon())
        self.deck_delete_button.clicked.connect(self._delete_deck)
        self.deck_edit_button = PushButton("编辑牌组")
        self.deck_edit_button.setIcon(FluentIcon.EDIT.icon())
        self.deck_edit_button.clicked.connect(self._edit_deck)
        title_row.addWidget(self.deck_edit_button)
        title_row.addWidget(self.deck_delete_button)
        layout.addLayout(title_row)
        import_card = QFrame()
        import_card.setObjectName("actionCard")
        import_layout = QHBoxLayout(import_card)
        import_layout.setContentsMargins(12, 9, 12, 9)
        import_layout.addWidget(QLabel("官方链接 / 牌组码"))
        self.deck_url = LineEdit()
        self.deck_url.setPlaceholderText("粘贴官方牌组链接、hash 或四位牌组码")
        import_layout.addWidget(self.deck_url, 1)
        self.deck_save_button = PrimaryPushButton("保存")
        self.deck_save_button.clicked.connect(self._import_deck)
        import_layout.addWidget(self.deck_save_button)
        layout.addWidget(import_card)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.deck_list = QListWidget()
        self.deck_list.setObjectName("deckList")
        self.deck_list.setMinimumWidth(290)
        self.deck_list.currentRowChanged.connect(self._select_deck_list_row)
        splitter.addWidget(self.deck_list)
        detail = QtCardPanel("牌组卡牌")
        self.deck_detail = detail.body
        splitter.addWidget(detail)
        splitter.setSizes((340, 660))
        layout.addWidget(splitter, 1)
        self.deck_page_hint = QLabel("牌组链接会自动识别职业和模式；选择空项可解除绑定。")
        self.deck_page_hint.setObjectName("muted")
        layout.addWidget(self.deck_page_hint)
        return page

    def _build_probability_page(self) -> QWidget:
        page = self._page()
        layout = self._page_layout(page)
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("概率计算"))
        title_row.addWidget(QLabel("抽牌、对手 Key、天晶深渊"), 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        grid = QGridLayout()
        grid.setSpacing(12)
        draw = self._calculator_card("抽牌概率")
        draw_form = QFormLayout()
        self.probability_card = ComboBox()
        self.probability_card.setMinimumWidth(270)
        self._probability_cards: list[tuple[int, int, int]] = []
        self.probability_draws = QSpinBox()
        self.probability_draws.setRange(1, 40)
        self.probability_draws.setValue(1)
        self.probability_result = QLabel("选择牌库中的卡牌后计算")
        self.probability_result.setObjectName("muted")
        draw_form.addRow("目标卡牌", self.probability_card)
        draw_form.addRow("未来抽牌", self.probability_draws)
        draw_layout = draw.layout()
        draw_layout.addLayout(draw_form)
        draw_button = PrimaryPushButton("计算")
        draw_button.clicked.connect(self._calculate_draw_probability)
        draw_layout.addWidget(draw_button)
        draw_layout.addWidget(self.probability_result)
        grid.addWidget(draw, 0, 0)

        key = self._calculator_card("对手 Key 牌概率")
        key_form = QFormLayout()
        self.key_strategy = ComboBox()
        self.key_strategy.addItem("Unknown 未知", "unknown")
        self.key_strategy.addItem("Known 已知", "known")
        self.key_deck_remaining = QSpinBox(); self.key_deck_remaining.setRange(0, 40); self.key_deck_remaining.setValue(36)
        self.key_hand_size = QSpinBox(); self.key_hand_size.setRange(0, 10); self.key_hand_size.setValue(4)
        self.key_mulligan = QSpinBox(); self.key_mulligan.setRange(0, 4); self.key_mulligan.setValue(0)
        self.key_copies = QSpinBox(); self.key_copies.setRange(0, 40); self.key_copies.setValue(3)
        self.key_limit = QSpinBox(); self.key_limit.setRange(0, 4); self.key_limit.setValue(1)
        self.key_seen = QSpinBox(); self.key_seen.setRange(0, 40); self.key_seen.setValue(0)
        key_form.addRow("策略", self.key_strategy)
        key_form.addRow("对手牌库", self.key_deck_remaining)
        key_form.addRow("未知手牌", self.key_hand_size)
        key_form.addRow("换牌数量", self.key_mulligan)
        key_form.addRow("Key投入", self.key_copies)
        key_form.addRow("留牌上限", self.key_limit)
        key_form.addRow("Key已见", self.key_seen)
        key.layout().addLayout(key_form)
        key_buttons = QHBoxLayout()
        key_now = PrimaryPushButton("计算当前")
        key_now.clicked.connect(lambda: self._calculate_key(False))
        key_next = PushButton("计算下回合")
        key_next.clicked.connect(lambda: self._calculate_key(True))
        key_buttons.addWidget(key_now); key_buttons.addWidget(key_next)
        key.layout().addLayout(key_buttons)
        self.key_result = QLabel("等待对局数据")
        self.key_result.setWordWrap(True); self.key_result.setObjectName("muted")
        key.layout().addWidget(self.key_result)
        grid.addWidget(key, 0, 1)

        faith = self._calculator_card("天晶深渊伤害概率")
        faith_form = QFormLayout()
        self.faith_total = QSpinBox(); self.faith_total.setRange(0, 1000)
        self.faith_min_z = QSpinBox(); self.faith_min_z.setRange(0, 1000)
        faith_form.addRow("信仰总值 X+Y+Z", self.faith_total)
        faith_form.addRow("需要 Z ≥", self.faith_min_z)
        faith.layout().addLayout(faith_form)
        faith_button = PrimaryPushButton("计算")
        faith_button.clicked.connect(self._calculate_faith)
        faith.layout().addWidget(faith_button)
        self.faith_result = QLabel("每个信仰点独立以 1/3 概率分配给 X、Y、Z")
        self.faith_result.setWordWrap(True); self.faith_result.setObjectName("muted")
        faith.layout().addWidget(self.faith_result)
        grid.addWidget(faith, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    @staticmethod
    def _calculator_card(title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("calculatorCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        return card

    def _build_stats_page(self) -> QWidget:
        page = self._page()
        layout = self._page_layout(page)
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("详细统计"))
        title_row.addStretch(1)
        self.stats_deck_label = QLabel("当前牌组")
        self.stats_deck_label.setObjectName("muted")
        title_row.addWidget(self.stats_deck_label)
        self.stats_reset_button = PushButton("重置当前牌组胜率")
        self.stats_reset_button.setIcon(FluentIcon.DELETE.icon())
        self.stats_reset_button.clicked.connect(self._reset_stats)
        title_row.addWidget(self.stats_reset_button)
        layout.addLayout(title_row)
        self.stats_summary = QLabel("未选择牌组")
        self.stats_summary.setObjectName("sectionTitle")
        layout.addWidget(self.stats_summary)
        self.match_table = QTableWidget(0, 7)
        self.match_table.setObjectName("matchTable")
        self.match_table.setAlternatingRowColors(True)
        self.match_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.match_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.match_table.setHorizontalHeaderLabels(("时间", "结果", "对手职业", "先后手", "回合", "结果码", "牌组"))
        self.match_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.match_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.match_table, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = self._page()
        layout = self._page_layout(page)
        layout.addWidget(SubtitleLabel("设置"))
        card = QFrame(); card.setObjectName("settingsCard")
        form = QFormLayout(card)
        form.setContentsMargins(16, 14, 16, 16)
        self.settings_connection_mode = ComboBox(); self.settings_connection_mode.addItems(("自动", "Steam", "国服"))
        self.settings_connection_mode.currentTextChanged.connect(self._change_connection_mode)
        form.addRow("连接方式", self.settings_connection_mode)
        self.record_checkbox = CheckBox("启用本地胜负统计（训练记录始终自动保存）")
        self.record_checkbox.setChecked(True)
        self.record_checkbox.stateChanged.connect(self._toggle_recording)
        form.addRow("本地统计", self.record_checkbox)
        hint = QLabel("读取服务始终保持只读；连接客户端变化会自动重启读取线程。")
        hint.setObjectName("muted")
        form.addRow("说明", hint)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _switch_page(self, page: QWidget) -> None:
        self.switchTo(page)

    # ----- deck repository ------------------------------------------------------

    def _active_deck(self) -> SavedDeck | None:
        return self._repository.active()

    @staticmethod
    def _format_mode(value: int) -> str:
        return "轮换" if int(value) == 1 else "无限"

    def _deck_label(self, deck: SavedDeck) -> str:
        return f"{deck.name}（{class_name(deck.class_id)} / {self._format_mode(deck.format_version)} / {deck.total_cards}张）"

    def _refresh_deck_choices(self) -> None:
        self._deck_choice_keys = [None, *[deck.key for deck in self._repository.decks]]
        labels = [""] + [self._deck_label(deck) for deck in self._repository.decks]
        for combo in (getattr(self, "deck_choice", None),):
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear(); combo.addItems(labels)
            active = self._active_deck()
            combo.setCurrentIndex(self._deck_choice_keys.index(active.key) if active else 0)
            combo.blockSignals(False)
        if hasattr(self, "deck_list"):
            self.deck_list.blockSignals(True)
            self.deck_list.clear()
            blank = QListWidgetItem("（未选择牌组）")
            blank.setData(Qt.ItemDataRole.UserRole, None)
            self.deck_list.addItem(blank)
            for deck in self._repository.decks:
                item = QListWidgetItem(self._deck_label(deck))
                item.setData(Qt.ItemDataRole.UserRole, deck.key)
                self.deck_list.addItem(item)
            active = self._active_deck()
            self.deck_list.setCurrentRow(self._deck_choice_keys.index(active.key) if active else 0)
            self.deck_list.blockSignals(False)
        self._render_deck_detail()
        self._update_header_stats()

    def _select_deck_index(self, index: int) -> None:
        if not 0 <= index < len(self._deck_choice_keys):
            return
        key = self._deck_choice_keys[index]
        try:
            if key is None:
                self._repository.clear_selection()
            else:
                self._repository.select(key)
        except (OSError, KeyError, ValueError) as exc:
            self._show_error("切换牌组失败", str(exc)); return
        self._match_id = None; self._match_deck_key = None
        self._refresh_deck_choices()
        self._restart_service_deck()

    def _select_deck_list_row(self, row: int) -> None:
        self._select_deck_index(row)

    def _render_deck_detail(self) -> None:
        deck = self._active_deck()
        if not hasattr(self, "deck_detail"):
            return
        if deck is None:
            self.deck_detail.setPlainText("未选择牌组\n\n选择空项可进行特殊/解密对局。")
            return
        lines = [
            deck.name,
            f"职业：{class_name(deck.class_id)}    模式：{self._format_mode(deck.format_version)}",
            f"牌组总数：{deck.total_cards}/40",
            "",
        ]
        for card in sorted(deck.cards, key=lambda item: (get_card_metadata(item.card_id).cost if get_card_metadata(item.card_id) else 99, self._card_name(item.card_id))):
            metadata = get_card_metadata(card.card_id)
            cost = metadata.cost if metadata else "?"
            lines.append(f"{cost}费  {self._card_name(card.card_id)}  ×{card.count}")
        self.deck_detail.setPlainText("\n".join(lines))

    def _import_deck(self) -> None:
        raw = self.deck_url.text().strip()
        if not raw:
            try: raw = QApplication.clipboard().text().strip()
            except Exception: raw = ""
        try:
            parsed = import_deck_code(raw) if len(raw) == 4 and "." not in raw else parse_official_deck(raw)
        except OfficialDeckError as exc:
            self._show_error("导入失败", str(exc)); return
        preview = " / ".join(self._card_name(card.card_id) for card in parsed.cards[:2])
        name, ok = self._input_text("保存牌组", "请输入本地牌组名称：", f"{preview} 牌组")
        if not ok: return
        try:
            saved = self._repository.add_official(name, parsed)
        except (OSError, ValueError) as exc:
            self._show_error("保存失败", str(exc)); return
        self.deck_url.clear()
        self._refresh_deck_choices()
        self._on_deck_saved(saved)
        self._show_info("牌组已保存", f"已识别：{class_name(saved.class_id)} / {self._format_mode(saved.format_version)}")

    def _on_deck_saved(self, deck: SavedDeck) -> None:
        self._refresh_deck_choices()
        self._restart_service_deck()

    def _edit_deck(self) -> None:
        deck = self._active_deck()
        if deck is None:
            self._show_info("编辑牌组", "请先选择一个牌组。")
            return
        dialog = DeckEditorDialog(self, deck)
        dialog.exec()

    def _delete_deck(self) -> None:
        deck = self._active_deck()
        if deck is None: return
        answer = QMessageBox.question(self, "删除牌组", f"确定删除“{deck.name}”吗？")
        if answer != QMessageBox.StandardButton.Yes: return
        try: self._repository.delete(deck.key)
        except (OSError, KeyError, ValueError) as exc:
            self._show_error("删除失败", str(exc)); return
        self._refresh_deck_choices(); self._restart_service_deck()

    def _restart_service_deck(self) -> None:
        if self._service is not None and self._service.running:
            self._stop_service()
            self._start_service()

    # ----- service and status ---------------------------------------------------

    def _connection_mode_key(self) -> str:
        return {"Steam": "steam", "国服": "cn"}.get(self.connection_mode.currentText(), "auto")

    def _change_connection_mode(self, value: str) -> None:
        for combo in (self.connection_mode, self.settings_connection_mode):
            combo.blockSignals(True); combo.setCurrentText(value); combo.blockSignals(False)
        self.metric_client.set_value(value, "已选择连接方式")
        if self._service is not None and self._service.running:
            self._stop_service(); self._start_service()
        else:
            self._set_status(f"已选择{value} · 等待客户端启动")

    def _start_service(self) -> None:
        if self._service is not None and self._service.running: return
        config = TrackerConfig(
            model_address=self._model_address,
            pid=self._startup_pid,
            client_mode=self._connection_mode_key(),
            interval=0.05,
            output_path=Path("logs") / "app_session.jsonl",
            training_output_path=Path("logs") / "training_matches.jsonl",
            training_upload_queue_path=(Path("logs") / "training_upload_queue.jsonl" if os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_URL") else None),
            training_upload_url=os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_URL"),
            training_upload_enabled=os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_ENABLED", "").strip().casefold() in {"1", "true", "yes", "on"},
            training_upload_token=os.environ.get("SHADOWVERSE_TRACKER_UPLOAD_TOKEN"),
            reveal_opponent_hand=False,
            selected_deck=self._active_deck().to_snapshot() if self._active_deck() else None,
            selected_deck_key=self._active_deck().key if self._active_deck() else None,
        )
        self._service = TrackerService(
            config,
            on_snapshot=self.snapshot_received.emit,
            on_error=self.error_received.emit,
            on_status=self.status_received.emit,
            on_deck=self.deck_received.emit,
        )
        self._service.start()
        self._set_status("正在后台读取 · 不会暂停游戏")

    def _stop_service(self) -> None:
        if self._service is not None:
            self._service.stop()
            self._service = None

    @staticmethod
    def _compact_status(value: object) -> str:
        raw = str(value or "").strip(); lowered = raw.casefold()
        if "等待游戏启动或重新连接" in raw: return "等待游戏启动或重新连接 · 自动重试"
        if "已连接国服进程" in raw: return "已连接国服 · 正在读取"
        if "已连接steam进程" in lowered: return "已连接 Steam · 正在读取"
        if "process not found" in lowered: return "未检测到游戏客户端，启动后会自动重试"
        if "access is denied" in lowered or "拒绝访问" in raw: return "无法读取游戏进程，请以管理员身份运行"
        if "gameassembly" in lowered and ("unsupported" in lowered or "不支持" in raw): return "当前 GameAssembly 不受支持，请更新适配"
        if "gameassembly" in lowered: return "未找到兼容的 GameAssembly，正在重试"
        return raw if len(raw) <= 86 else "读取出现异常，正在自动重试"

    def _set_status(self, value: str) -> None:
        self._status_text = self._compact_status(value)
        if not hasattr(self, "status_pill"): return
        self.status_pill.setText(self._status_text)
        connected = "已连接" in self._status_text
        error = any(word in self._status_text for word in ("错误", "失败", "不支持", "无法", "未检测到"))
        self.status_pill.setProperty("connected", connected)
        self.status_pill.setProperty("error", error)
        self.status_pill.style().unpolish(self.status_pill); self.status_pill.style().polish(self.status_pill)
        self.dashboard_status_label.setText(self._status_text)

    def _on_error(self, value: object) -> None:
        self._set_status(str(value))

    def _on_deck_event(self, _value: object) -> None:
        self._refresh_deck_choices()

    def _toggle_recording(self, state: int) -> None:
        self._record_matches = bool(state)
        self._update_header_stats()

    def _close(self) -> None:
        if self._overlay is not None: self._overlay.close()
        self._stop_service()
        self.close()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._stop_service()
        event.accept()

    # ----- snapshot rendering ---------------------------------------------------

    def _render_snapshot(self, snapshot: object) -> None:
        if not isinstance(snapshot, dict): return
        self._last_snapshot = snapshot
        root = snapshot.get("root")
        players = root.get("players", ()) if isinstance(root, dict) else ()
        if not isinstance(players, (list, tuple)) or len(players) < 2 or not all(isinstance(item, dict) for item in players[:2]):
            return
        mine, opponent = players[0], players[1]
        address = str(snapshot.get("address") or "unknown")
        turn = mine.get("turn") if isinstance(mine.get("turn"), int) else None
        result_code = mine.get("result_code") if isinstance(mine.get("result_code"), int) else 0
        if self._is_new_match(address, turn, result_code):
            self._match_sequence += 1
            self._match_id = f"{address}:{os.getpid()}:{self._match_sequence}"
            active = self._active_deck()
            self._match_deck_key = active.key if active else None
        terminal = result_label(result_code, mine.get("life") if isinstance(mine.get("life"), int) else None, opponent.get("life") if isinstance(opponent.get("life"), int) else None)
        self._track_terminal(snapshot, mine, opponent, terminal, address, turn, result_code)
        if terminal in {"胜利", "失败"}:
            self._clear_match_view(terminal)
            return
        self._set_status("已连接，正在后台读取（不会暂停游戏）")
        self._update_snapshot_panels(snapshot, mine, opponent)
        self._last_model_address = address; self._last_turn = turn; self._last_result_code = result_code
        if self._overlay is not None and self._overlay.isVisible(): self._overlay.update_snapshot(snapshot)

    def _is_new_match(self, address: str, turn: int | None, result_code: int) -> bool:
        return (
            self._match_id is None or address != self._last_model_address or
            (result_code == 0 and self._last_result_code not in (None, 0)) or
            (result_code != 0 and self._last_result_code not in (None, 0, result_code)) or
            (turn is not None and self._last_turn is not None and turn + 2 < self._last_turn)
        )

    def _track_terminal(self, snapshot: dict[str, object], mine: dict[str, object], opponent: dict[str, object], terminal: str, address: str, turn: int | None, result_code: int) -> None:
        if not self._record_matches or terminal not in {"胜利", "失败"} or not self._match_id or not self._match_deck_key:
            return
        deck = self._active_deck()
        if deck is None: return
        model_id = terminal_match_id(
            address, result_code, turn,
            mine.get("life") if isinstance(mine.get("life"), int) else None,
            opponent.get("life") if isinstance(opponent.get("life"), int) else None,
            mine.get("deck_count") if isinstance(mine.get("deck_count"), int) else None,
            mine.get("cemetery_count") if isinstance(mine.get("cemetery_count"), int) else None,
            len(mine.get("played_card_ids", ())) if isinstance(mine.get("played_card_ids"), (list, tuple)) else 0,
            len(mine.get("destroyed_card_ids", ())) if isinstance(mine.get("destroyed_card_ids"), (list, tuple)) else 0,
        )
        try:
            self._history.add(MatchRecord(
                match_id=model_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                deck_key=self._match_deck_key,
                deck_name=deck.name,
                self_class_id=snapshot.get("self_class_id") if isinstance(snapshot.get("self_class_id"), int) else None,
                opponent_class_id=snapshot.get("opponent_class_id") if isinstance(snapshot.get("opponent_class_id"), int) else None,
                opponent_class=class_name(snapshot.get("opponent_class_id") if isinstance(snapshot.get("opponent_class_id"), int) else None),
                result=terminal,
                result_code=result_code,
                turn=turn,
                is_first=mine.get("is_first_side") if isinstance(mine.get("is_first_side"), bool) else None,
            ))
        except (OSError, ValueError) as exc:
            self._history_error = str(exc)
        self._refresh_stats_page()

    def _update_snapshot_panels(self, snapshot: dict[str, object], mine: dict[str, object], opponent: dict[str, object]) -> None:
        deck_count = mine.get("deck_count", "?")
        active = self._active_deck()
        total = active.total_cards if active else 40
        self.metric_deck.set_value(f"{deck_count} / {total}", "当前剩余牌库")
        self.metric_turn.set_value(f"T{mine.get('turn', '?')}", f"PP {mine.get('pp', '?')}/{mine.get('max_pp', '?')} · 生命 {mine.get('life', '?')}")
        self.metric_client.set_value("国服" if self._connection_mode_key() == "cn" else "Steam" if self._connection_mode_key() == "steam" else "自动", "已连接")
        self.hand_panel.set_text(self._format_hand(mine.get("hand")))
        self.deck_panel.set_text(self._format_ledger(snapshot.get("deck_ledger"), active))
        self.field_panel.set_text(self._format_field(mine.get("field"), opponent.get("field")))
        self.history_panel.set_text(self._format_history(mine, opponent, snapshot))
        self._refresh_probability_choices(snapshot.get("deck_ledger"))
        self._update_probability_inputs(snapshot, opponent)

    def _clear_match_view(self, result: str) -> None:
        self._set_status(f"本局{result} · 等待下一局")
        self.hand_panel.set_text("暂无手牌数据\n\n开始对局后显示我方手牌")
        self.deck_panel.set_text(self._format_ledger(None, self._active_deck()))
        self.field_panel.set_text("暂无场面数据\n\n开始对局后显示双方场面")
        self.history_panel.set_text("本局已结束\n\n详细操作保存在训练记录中")
        self._last_snapshot = None
        self._update_header_stats()

    def _format_hand(self, value: object) -> str:
        cards = value if isinstance(value, (list, tuple)) else ()
        if not cards: return "暂无公开手牌"
        lines = []
        for card in cards:
            card_id = _read_card_id(card)
            name = self._card_name(card_id)
            cost = card.get("cost", "?") if isinstance(card, dict) else "?"
            lines.append(f"{cost}费  {name}")
        return "\n".join(lines)

    def _format_ledger(self, ledger: object, active: SavedDeck | None) -> str:
        if not isinstance(ledger, dict):
            return "未选择本地牌组" if active is None else f"{active.name}\n剩余牌库：{active.total_cards}/{active.total_cards} 张"
        rows = ledger.get("rows", ())
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, (list, tuple)) else []
        lines = [str(ledger.get("deck_name") or active.name if active else "当前牌组"), f"剩余牌库：{ledger.get('authoritative_deck_count', '?')} 张", ""]
        remaining = [row for row in rows if isinstance(row.get("remaining"), int) and row.get("remaining", 0) > 0]
        depleted = [row for row in rows if isinstance(row.get("remaining"), int) and row.get("remaining", 0) <= 0]
        lines.append("未抽空")
        for row in sorted(remaining, key=self._card_sort_key): lines.append(self._format_ledger_row(row))
        lines.append("\n已抽空")
        for row in sorted(depleted, key=self._card_sort_key): lines.append(self._format_ledger_row(row))
        return "\n".join(lines)

    def _format_ledger_row(self, row: dict[str, object]) -> str:
        return f"{self._card_name(row.get('card_id'))}  {row.get('remaining', '?')}/{row.get('initial', '?')}"

    def _format_field(self, mine: object, opponent: object) -> str:
        def side(value: object) -> list[str]:
            cards = value if isinstance(value, (list, tuple)) else ()
            return [
                f"{self._card_name(_read_card_id(card))}  {card.get('attack', '?')}/{card.get('life', '?')}"
                for card in cards if isinstance(card, dict)
            ]
        own = side(mine); enemy = side(opponent)
        return "我方场面\n" + ("\n".join(own) or "（空）") + "\n\n对手场面\n" + ("\n".join(enemy) or "（空）")

    def _format_history(self, mine: dict[str, object], opponent: dict[str, object], snapshot: dict[str, object]) -> str:
        lines = [f"T{mine.get('turn', '?')} · 我方生命 {mine.get('life', '?')} · 对手生命 {opponent.get('life', '?')}"]
        events = snapshot.get("events", ())
        if isinstance(events, (list, tuple)):
            for event in events[-10:]:
                if not isinstance(event, dict): continue
                event_type = str(event.get("type") or "操作")
                actor = "我方" if event.get("is_ally") else "对手"
                lines.append(f"{actor} · {event_type}")
        return "\n".join(lines)

    def _update_header_stats(self) -> None:
        active = self._active_deck()
        if active is None:
            self.metric_rate.set_value("—", "未选择牌组")
            self.dashboard_deck_label.setText("未选择本地牌组")
            return
        stats = self._history.stats(active.key)
        self.metric_rate.set_value(f"{float(stats['win_rate']):.1f}%", f"{int(stats['finished'])} 局")
        self.dashboard_deck_label.setText(f"{active.name} · {class_name(active.class_id)} / {self._format_mode(active.format_version)}")

    # ----- probability and stats ------------------------------------------------

    def _update_probability_inputs(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        deck = opponent.get("deck_count")
        if isinstance(deck, int): self.key_deck_remaining.setValue(max(0, min(40, deck)))
        hand = opponent.get("hand")
        if isinstance(hand, (list, tuple)): self.key_hand_size.setValue(max(0, min(10, len(hand))))

    def _calculate_draw_probability(self) -> None:
        index = self.probability_card.currentIndex()
        choices = getattr(self, "_probability_cards", [])
        if not 0 <= index < len(choices): self.probability_result.setText("请选择目标卡牌"); return
        _card_id, remaining, total = choices[index]
        draws = min(self.probability_draws.value(), total)
        misses = math.comb(total - remaining, draws) / math.comb(total, draws) if draws <= total - remaining else 0.0
        self.probability_result.setText(f"未来 {draws} 抽至少 1 张：{(1 - misses) * 100:.1f}%（剩余 {remaining}/{total}）")

    def _calculate_key(self, after_next_draw: bool) -> None:
        deck_remaining = self.key_deck_remaining.value(); hand_size = self.key_hand_size.value()
        if after_next_draw:
            if deck_remaining <= 0: self.key_result.setText("无法计算：对手牌库为空"); return
            deck_remaining -= 1; hand_size += 1
        result = calculate_key_probability(
            deck_remaining=deck_remaining,
            hand_size=hand_size,
            mulligan_swapped=self.key_mulligan.value(),
            keep1_types=0, keep2_types=0, seen_keep1=0, seen_keep2=0,
            key_copies=self.key_copies.value(), key_keep_limit=self.key_limit.value(),
            key_seen=self.key_seen.value(), strategy=self.key_strategy.currentData() or "unknown",
        )
        if result.valid and result.percent is not None:
            label = "对手下回合 Key 概率" if after_next_draw else "对手当前 Key 概率"
            self.key_result.setText(f"{label}：{result.percent:.2f}%（牌库 {deck_remaining}，未知手牌 {hand_size}）")
        else: self.key_result.setText(f"无法计算：{result.reason}")

    def _calculate_faith(self) -> None:
        try: probability = calculate_faith_damage_probability(self.faith_total.value(), self.faith_min_z.value())
        except ValueError as exc: self.faith_result.setText(f"无法计算：{exc}"); return
        self.faith_result.setText(f"P(Z≥{self.faith_min_z.value()})：{probability * 100:.2f}%（N={self.faith_total.value()}，Z~Binomial(N, 1/3)）")

    def _refresh_probability_choices(self, ledger: object) -> None:
        choices = []
        if isinstance(ledger, dict):
            rows = ledger.get("rows", ())
            if isinstance(rows, (list, tuple)):
                total = ledger.get("authoritative_deck_count")
                if isinstance(total, int) and total > 0:
                    for row in rows:
                        if isinstance(row, dict) and isinstance(row.get("card_id"), int) and isinstance(row.get("remaining"), int) and row.get("remaining", 0) > 0:
                            choices.append((row["card_id"], row["remaining"], total))
        if not choices:
            active = self._active_deck()
            if active is not None:
                choices = [(card.card_id, card.count, active.total_cards) for card in active.cards if card.count > 0]
        self._probability_cards = choices
        self.probability_card.blockSignals(True); self.probability_card.clear()
        self.probability_card.addItems([self._card_name(item[0]) for item in choices])
        self.probability_card.blockSignals(False)

    def _refresh_stats_page(self) -> None:
        if not hasattr(self, "match_table"): return
        active = self._active_deck()
        self.stats_deck_label.setText(active.name if active else "未选择牌组")
        self.match_table.setRowCount(0)
        if active is None:
            self.stats_summary.setText("未选择牌组")
            return
        stats = self._history.stats(active.key)
        self.stats_summary.setText(
            f"总计 {stats['finished']} 局 · {stats['wins']} 胜 / {stats['losses']} 负 · 胜率 {float(stats['win_rate']):.1f}%   "
            f"先手 {float(stats['first']['win_rate']):.1f}%   后手 {float(stats['second']['win_rate']):.1f}%"
        )
        records = self._history.for_deck(active.key)
        for record in reversed(records):
            row = self.match_table.rowCount(); self.match_table.insertRow(row)
            values = (
                record.timestamp.replace("T", " ")[:16], record.result, record.opponent_class,
                "先手" if record.is_first is True else "后手" if record.is_first is False else "未知",
                str(record.turn or "—"), str(record.result_code), record.deck_name,
            )
            for col, value in enumerate(values): self.match_table.setItem(row, col, QTableWidgetItem(value))

    def _reset_stats(self) -> None:
        active = self._active_deck()
        if active is None: return
        answer = QMessageBox.question(self, "重置胜率", f"删除“{active.name}”的本地胜负记录？")
        if answer != QMessageBox.StandardButton.Yes: return
        self._history.clear_deck(active.key); self._refresh_stats_page(); self._update_header_stats()

    # ----- formatting helpers and small dialogs --------------------------------

    def _card_name(self, value: object) -> str:
        return get_card_name(value) if isinstance(value, int) else "未知卡牌"

    def _card_sort_key(self, row: object) -> tuple[int, str]:
        card_id = row.get("card_id") if isinstance(row, dict) else None
        metadata = get_card_metadata(card_id) if isinstance(card_id, int) else None
        return (metadata.cost if metadata else 99, self._card_name(card_id))

    def _input_text(self, title: str, label: str, initial: str) -> tuple[str, bool]:
        dialog = QDialog(self); dialog.setWindowTitle(title); dialog.resize(430, 130)
        layout = QVBoxLayout(dialog); layout.addWidget(QLabel(label)); edit = QtLineEdit(initial); layout.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        return edit.text().strip(), bool(ok and edit.text().strip())

    def _show_info(self, title: str, content: str) -> None:
        InfoBar.success(title, content, parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2200)

    def _show_error(self, title: str, content: str) -> None:
        InfoBar.error(title, content, parent=self, position=InfoBarPosition.TOP_RIGHT, duration=5000)

    def _toggle_overlay(self) -> None:
        if self._overlay is not None and self._overlay.isVisible():
            self._overlay.close(); return
        self._overlay = OverlayWindow(self)
        self._overlay.update_snapshot(self._last_snapshot)
        self._overlay.show()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=lambda value: int(value, 0), help="BattleModel address")
    parser.add_argument("--pid", type=int, help="target game PID; auto-detected when omitted")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    setThemeColor("#169eb0")
    app.setStyleSheet(APP_STYLESHEET)
    window = QtTrackerWindow(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
