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
import re
import sys
from threading import Thread

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
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

from .card_catalog import (
    get_card_metadata,
    get_card_name,
    is_card_allowed,
    load_card_catalog,
)
from .deck_repository import DeckRepository, SavedDeck
from .faith_probability import calculate_faith_damage_probability
from .match_history import (
    CLASS_NAMES,
    MatchHistory,
    MatchRecord,
    class_name,
    format_timestamp_local,
    orient_class_ids,
    result_label,
    terminal_match_id,
)
from .meta_deck_source import refresh_wbarts_meta_cache_daily
from .official_deck import OfficialDeckError, import_deck_code, parse_official_deck
from .opponent_key_probability import calculate_key_probability
from .opponent_deck_matcher import (
    META_TIER_ORDER,
    MetaDeckProfile,
    OpponentDeckMatcher,
    canonicalize_meta_deck_labels,
    load_meta_deck_profiles,
    load_session_opponent_observations,
    meta_archetype_sort_key,
    meta_profile_from_saved_deck,
    meta_tier_label,
)
from .tracker_service import TrackerConfig, TrackerService


CLASS_ICON_FILES = {
    1: "class_icons/1.svg",  # Forestcraft
    2: "class_icons/2.svg",  # Swordcraft
    3: "class_icons/3.svg",  # Runecraft
    4: "class_icons/4.svg",  # Dragoncraft
    5: "class_icons/5.svg",  # Abysscraft
    6: "class_icons/6.svg",  # Havencraft
    7: "class_icons/7.svg",  # Portalcraft
}


APP_STYLESHEET = """
QWidget#qtRoot, QWidget#page, QWidget#dashboardPage, QWidget#statsPage,
QWidget#decksPage, QWidget#metaPage, QWidget#probabilityPage, QWidget#settingsPage {
    background: #f4f7fb;
    color: #172536;
}
QWidget#page, QWidget#dashboardPage, QWidget#statsPage, QWidget#decksPage,
QWidget#metaPage, QWidget#probabilityPage, QWidget#settingsPage {
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
QLabel#deckClassIcon {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 6px;
    padding: 2px;
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
QListWidget#deckList::item:hover {
    background: #edf8f9;
}
QListWidget#deckList::item:selected:hover {
    background: #d5eff1;
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
QFrame#chartCard {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 8px;
}
QFrame#deckCardTile, QFrame#overlayCardTile {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 10px;
}
QFrame#deckCardTile:hover, QFrame#overlayCardTile:hover {
    border: 1px solid #55aebb;
    background: #f8fdfe;
}
QLabel#cardName {
    color: #1d3348;
    font-size: 11px;
    font-weight: 600;
}
QLabel#cardCount {
    color: #43637c;
    font-size: 11px;
    font-weight: 700;
}
QLineEdit, QComboBox, QSpinBox {
    min-height: 30px;
    border: 1px solid #cbd9e5;
    border-radius: 7px;
    padding: 3px 8px;
    background: #ffffff;
    color: #1b344b;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    background: #eef2f6;
    color: #7d8996;
    border-color: #d5dee7;
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


def _plain_spinbox(minimum: int, maximum: int, value: int | None = None) -> QSpinBox:
    """Create a numeric input without the distracting inline arrow buttons."""
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    if value is not None:
        spin.setValue(value)
    return spin


def _opponent_hand_size(snapshot: object, opponent: object) -> int | None:
    """Return the unknown deck-origin cards currently left in the opponent hand.

    The memory reader masks opponent card identities with ``{"hidden": True}``
    placeholders, so the list length remains a reliable total hand count even
    when the actual cards are not revealed.  Publicly identified/generated
    cards are tracked separately and are excluded from the probability model.
    """
    if not isinstance(opponent, dict):
        return None
    raw_count = opponent.get("hand_count")
    if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count >= 0:
        hand_size = raw_count
    else:
        hand = opponent.get("hand")
        if not isinstance(hand, (list, tuple)):
            return None
        hand_size = len(hand)

    known_count = 0
    knowledge: object = None
    if isinstance(snapshot, dict):
        knowledge = snapshot.get("opponent_hand_knowledge")
    if not isinstance(knowledge, dict):
        knowledge = opponent.get("opponent_hand_knowledge")
    if isinstance(knowledge, dict):
        for key in ("known_cards", "known_types"):
            items = knowledge.get(key)
            if not isinstance(items, (list, tuple)):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                count = item.get("count")
                if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                    known_count += count
    return max(0, hand_size - known_count)


def _opponent_mulligan_count(snapshot: object, opponent: object) -> int | None:
    """Read the opponent's replacement count from the latest tracker data."""
    candidates: list[object] = []
    if isinstance(snapshot, dict):
        training = snapshot.get("training_observation")
        mulligan = training.get("mulligan") if isinstance(training, dict) else None
        if isinstance(mulligan, dict):
            candidates.append(mulligan.get("opponent_replaced_count"))
    if isinstance(opponent, dict):
        summary = opponent.get("mulligan_summary")
        if isinstance(summary, dict):
            candidates.append(summary.get("replaced_count"))
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 4:
            return value
    return None


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


class ClassWinRateChart(QFrame):
    """Seven-class chart with a win-rate or match-count presentation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chartCard")
        self.setMinimumWidth(620)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._rows: list[tuple[str, float, int, int, QIcon]] = []
        self._mode = "rate"
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(("按胜率", "按对局数"))
        self.mode_combo.setFixedWidth(112)
        self.mode_combo.currentIndexChanged.connect(
            lambda index: self.set_mode("games" if index == 1 else "rate")
        )

    def set_rows(self, rows: list[tuple[str, float, int, int, QIcon]]) -> None:
        self._rows = list(rows)
        self.update()

    def set_mode(self, mode: str) -> None:
        value = "games" if mode == "games" else "rate"
        if value == self._mode:
            return
        self._mode = value
        self.update()

    @staticmethod
    def _rate_color(rate: float, has_data: bool) -> QColor:
        """Map 30%→70% continuously from red through yellow to green."""
        if not has_data:
            return QColor("#dfe6eb")
        red = QColor("#e24b4b")
        yellow = QColor("#e6bd3f")
        green = QColor("#43a653")
        clamped = max(0.0, min(100.0, float(rate)))
        if clamped <= 50.0:
            amount = max(0.0, min(1.0, (clamped - 30.0) / 20.0))
            start, end = red, yellow
        else:
            amount = max(0.0, min(1.0, (clamped - 50.0) / 20.0))
            start, end = yellow, green
        return QColor(
            round(start.red() + (end.red() - start.red()) * amount),
            round(start.green() + (end.green() - start.green()) * amount),
            round(start.blue() + (end.blue() - start.blue()) * amount),
        )

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(880, 260)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self.mode_combo.move(max(14, self.width() - self.mode_combo.width() - 12), 8)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#244f70"))
        painter.drawText(14, 22, "职业胜率" if self._mode == "rate" else "职业对局数")
        if not self._rows:
            painter.setPen(QColor("#8798a8"))
            painter.drawText(14, 62, "暂无已完成对局")
            return

        left, right, top, bottom = 36, 24, 52, 58
        baseline = max(top + 30, self.height() - bottom)
        chart_height = max(50, baseline - top)
        plot_width = max(1, self.width() - left - right)
        slot_width = plot_width / max(1, len(self._rows))
        bar_width = max(22, min(64, int(slot_width * 0.52)))
        if self._mode == "rate":
            scale_max = 100.0
            guides: tuple[float, ...] = (0.0, 50.0, 100.0)
            guide_suffix = "%"
        else:
            maximum = max((int(row[3]) for row in self._rows), default=0)
            scale_max = float(max(1, maximum))
            midpoint = max(1, math.ceil(scale_max / 2))
            guides = tuple(float(value) for value in sorted(set((0, midpoint, int(scale_max)))))
            guide_suffix = "局"
        for guide in guides:
            y = baseline - int(chart_height * guide / scale_max)
            painter.setPen(QColor("#e4ebf1"))
            painter.drawLine(left, y, self.width() - right, y)
            painter.setPen(QColor("#8798a8"))
            guide_text = f"{int(guide)}{guide_suffix}" if guide.is_integer() else f"{guide:g}{guide_suffix}"
            painter.drawText(5, y + 4, guide_text)
        for index, (label, rate, wins, total, icon) in enumerate(self._rows):
            # Compute the center from the full plot width.  The old integer
            # slot calculation accumulated rounding error, which made the
            # last icon/bar visibly drift away from its grid slot.
            center = int(round(left + (index + 0.5) * slot_width))
            x = center - bar_width // 2
            has_data = total > 0
            clamped = max(0.0, min(100.0, float(rate)))
            value = clamped if self._mode == "rate" else float(total)
            height = int(chart_height * value / scale_max) if has_data else 0
            color = self._rate_color(clamped, has_data)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            if height:
                painter.drawRoundedRect(x, baseline - height, bar_width, height, 5, 5)
            else:
                painter.drawRoundedRect(x, baseline - 2, bar_width, 2, 1, 1)
            painter.setPen(QColor("#244f70"))
            rate_text = f"{clamped:.1f}%" if has_data else "—"
            text_width = painter.fontMetrics().horizontalAdvance(rate_text)
            rate_y = max(top + 13, baseline - height - 6)
            painter.drawText(center - text_width // 2, rate_y, rate_text)
            if self._mode == "games":
                count_text = f"{total}局" if has_data else "0局"
                count_width = painter.fontMetrics().horizontalAdvance(count_text)
                count_y = min(baseline - 4, rate_y + 14)
                painter.drawText(center - count_width // 2, count_y, count_text)
            elif height >= 30:
                match_text = f"{wins}/{total}"
                match_width = painter.fontMetrics().horizontalAdvance(match_text)
                painter.setPen(QColor("#385a72"))
                painter.drawText(center - match_width // 2, baseline - max(16, height // 2), match_text)
            if not icon.isNull():
                icon_size = 26
                painter.drawPixmap(center - icon_size // 2, baseline + 9, icon.pixmap(QSize(icon_size, icon_size)))


def _visible_window_rect_for_pid(pid: int | None) -> tuple[int, int, int, int] | None:
    """Return the largest visible top-level window belonging to ``pid``.

    The tracker is deliberately a normal desktop application, so using the
    read-only user32 window enumeration here is enough to attach the overlay
    to the game without injecting anything into the game process.  Keeping the
    Win32 calls lazy also lets the Qt module remain importable in tooling that
    is not running on Windows.
    """
    if os.name != "nt" or not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        best: tuple[int, int, int, int] | None = None
        best_area = 0
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd: int, _lparam: int) -> bool:
            nonlocal best, best_area
            if not user32.IsWindowVisible(hwnd):
                return True
            owner_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if int(owner_pid.value) != int(pid):
                return True
            rect = Rect()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            area = width * height
            # Ignore tiny helper/tool windows; the Unity/SVWB surface is the
            # largest visible window for the target process in practice.
            if width >= 240 and height >= 240 and area > best_area:
                best_area = area
                best = (int(rect.left), int(rect.top), width, height)
            return True

        callback = enum_proc_type(visit)
        user32.EnumWindows(callback, 0)
        return best
    except (AttributeError, OSError, TypeError, ValueError):
        return None


class OverlayWindow(QWidget):
    """Three-column, draggable, always-on-top deck overlay.

    The old Tk overlay showed the whole deck in three compact columns.  Keep
    that behaviour in the migrated window, while using the SVWB top-level
    window as the default anchor and height when it is available.
    """

    _COLUMNS = 3

    def __init__(self, parent: "QtTrackerWindow") -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.parent_window = parent
        self.setWindowTitle("Shadowverse Tracker · Overlay")
        self.setMinimumSize(360, 360)
        self.resize(430, 720)
        self.setStyleSheet(APP_STYLESHEET + "QWidget#overlayRoot { background:#f4f7fb; }")
        self.setObjectName("overlayRoot")
        self._drag_start_global: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self._user_moved = False
        self._placement_done = False
        self._attached_pid: int | None = None
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(500)
        self._follow_timer.timeout.connect(self._follow_game_window)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)
        self.header = QFrame()
        self.header.setObjectName("headerCard")
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header.setToolTip("拖动标题栏移动悬浮记牌器")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(10, 7, 10, 7)
        self.title = StrongBodyLabel("悬浮记牌器")
        self.stats = CaptionLabel("等待对局数据")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.stats.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(self.title)
        header_layout.addWidget(self.stats)
        root.addWidget(self.header)
        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        for column in range(self._COLUMNS):
            self.grid.setColumnStretch(column, 1)
        root.addWidget(self.content, 1)
        self.close_button = TransparentPushButton("Esc 关闭")
        self.close_button.clicked.connect(self.close)
        root.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)
        for widget in (self.header, self.title, self.stats):
            widget.installEventFilter(self)

    def _target_pid(self) -> int | None:
        configured = getattr(self.parent_window, "_startup_pid", None)
        if isinstance(configured, int) and configured > 0:
            return configured
        service = getattr(self.parent_window, "_service", None)
        detected = getattr(service, "_pid", None)
        return int(detected) if isinstance(detected, int) and detected > 0 else None

    def _fallback_parent_rect(self) -> tuple[int, int, int, int] | None:
        try:
            rect = self.parent_window.frameGeometry()
            if rect.width() >= 240 and rect.height() >= 240:
                return rect.x(), rect.y(), rect.width(), rect.height()
        except (AttributeError, RuntimeError):
            pass
        return None

    def _place_next_to_game(self, *, force: bool = False) -> None:
        if self._user_moved and not force:
            return
        pid = self._target_pid()
        if not force and self._placement_done and pid == self._attached_pid:
            return
        rect = _visible_window_rect_for_pid(pid)
        attached = rect is not None
        if rect is None:
            rect = self._fallback_parent_rect()
        if rect is None:
            return
        left, top, game_width, game_height = rect
        width = max(390, min(460, self.width()))
        screen = QApplication.screenAt(QPoint(left, top)) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        height = max(360, int(game_height))
        if available is not None:
            height = min(height, available.height())
            y = max(available.top(), min(top, available.bottom() - height + 1))
            right_x = left + game_width + 6
            if right_x + width - 1 <= available.right():
                x = right_x
            else:
                x = left - width - 6
                if x < available.left():
                    x = max(available.left(), available.right() - width + 1)
        else:
            x = left + game_width + 6
            y = top
        self.setFixedSize(width, height)
        self.move(int(x), int(y))
        self._placement_done = True
        self._attached_pid = pid if attached else None

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if not self._user_moved:
            self._place_next_to_game(force=True)
        self._follow_timer.start()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._follow_timer.stop()
        super().closeEvent(event)

    def _follow_game_window(self) -> None:
        if not self._user_moved:
            self._place_next_to_game(force=True)

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        if watched in (self.header, self.title, self.stats):
            event_type = event.type()
            if event_type == QEvent.Type.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                global_pos = getattr(event, "globalPosition", lambda: QPoint())()
                self._drag_start_global = global_pos.toPoint() if hasattr(global_pos, "toPoint") else global_pos
                self._drag_start_pos = self.pos()
                self._user_moved = True
                self.header.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if event_type == QEvent.Type.MouseMove and self._drag_start_global is not None and self._drag_start_pos is not None:
                buttons = getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)()
                if buttons & Qt.MouseButton.LeftButton:
                    global_pos = getattr(event, "globalPosition", lambda: QPoint())()
                    point = global_pos.toPoint() if hasattr(global_pos, "toPoint") else global_pos
                    self.move(self._drag_start_pos + point - self._drag_start_global)
                    return True
            if event_type == QEvent.Type.MouseButtonRelease and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                self._drag_start_global = None
                self._drag_start_pos = None
                self.header.setCursor(Qt.CursorShape.OpenHandCursor)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _card_image_height(self, card_count: int) -> int:
        grid_rows = max(1, math.ceil(card_count / self._COLUMNS))
        available = max(150, self.height() - self.header.sizeHint().height() - self.close_button.sizeHint().height() - 42)
        row_height = max(36, (available - self.grid.verticalSpacing() * max(0, grid_rows - 1)) // grid_rows)
        # A deck normally has 15–20 unique cards, but custom lists can have
        # more.  Keep the lower bound small enough that three columns still
        # fit every row inside a 720p game window instead of reintroducing a
        # scrollbar or clipping the final row.
        return max(8, min(150, row_height - 28))

    def update_snapshot(self, snapshot: dict[str, object] | None) -> None:
        # If the overlay was opened before the reader discovered the game PID,
        # retry the native attachment on the next snapshot.  Once the user has
        # dragged it, never snap it back automatically.
        if not self._user_moved and self._attached_pid is None:
            self._place_next_to_game()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        deck = self.parent_window._active_deck()
        if deck is None:
            self.stats.setText("未选择牌组")
            self.title.setText("悬浮记牌器")
            return
        stats = self.parent_window._history.stats(deck.key)
        self.stats.setText(
            f"总胜率 {float(stats['win_rate']):.1f}%（{int(stats['finished'])}局）  "
            f"先手 {float(stats['first']['win_rate']):.1f}%  "
            f"后手 {float(stats['second']['win_rate']):.1f}%"
        )
        ledger = snapshot.get("deck_ledger") if isinstance(snapshot, dict) else None
        if not isinstance(ledger, dict):
            ledger = {
                "deck_name": deck.name,
                "authoritative_deck_count": deck.total_cards,
                "rows": [
                    {"card_id": card.card_id, "remaining": card.count, "initial": card.count}
                    for card in deck.cards
                ],
            }
        rows = ledger.get("rows", ())
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, (list, tuple)) else []
        rows.sort(key=lambda row: (int(row.get("remaining", 0)) <= 0, self.parent_window._card_sort_key(row)))
        count = ledger.get("authoritative_deck_count", deck.total_cards)
        total = sum(int(row.get("initial", 0)) for row in rows)
        self.title.setText(f"{deck.name}  ·  {count}/{total}")
        image_height = self._card_image_height(len(rows))
        for index, row in enumerate(rows):
            card_id = row.get("card_id")
            name = self.parent_window._card_name(card_id)
            remaining = row.get("remaining", "?")
            initial = row.get("initial", "?")
            tile = QFrame()
            tile.setObjectName("overlayCardTile")
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.setFixedHeight(image_height + 28)
            tile.setToolTip(name)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(4, 4, 4, 4)
            tile_layout.setSpacing(2)
            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setFixedHeight(image_height)
            image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            pixmap = self.parent_window._card_image_pixmap(card_id, image_height - 2)
            if pixmap is not None and not pixmap.isNull():
                image.setPixmap(pixmap)
            else:
                image.setText(name)
                image.setWordWrap(True)
                image.setStyleSheet("background:#eaf0f5;border-radius:6px;color:#1d3348;padding:4px;")
            tile_layout.addWidget(image)
            count_label = QLabel(f"剩余 {remaining}/{initial}")
            count_label.setObjectName("cardCount")
            count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if isinstance(remaining, int) and remaining <= 0:
                count_label.setStyleSheet("color:#b33c4b;")
                tile.setStyleSheet("QFrame#overlayCardTile { border:1px solid #e49ba3; background:#fff7f7; }")
            tile_layout.addWidget(count_label)
            self.grid.addWidget(tile, index // self._COLUMNS, index % self._COLUMNS)


class DeckCardTile(QFrame):
    """Card tile that exposes a lightweight double-click edit affordance."""

    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class DeckEditorDialog(QDialog):
    """Compact card-count editor for the migrated deck page."""

    def __init__(self, window: "QtTrackerWindow", deck: SavedDeck) -> None:
        super().__init__(window)
        self.setWindowTitle(f"编辑牌组 · {deck.name}")
        self.resize(650, 500)
        self.window_ref = window
        self.deck = deck
        self.counts: dict[int, int] = dict(window._deck_card_counts(deck))
        try:
            self.catalog = load_card_catalog()
        except (OSError, ValueError):
            self.catalog = {}
        layout = QVBoxLayout(self)
        info = QLabel("修改每种卡牌数量；牌组总数必须保持 40 张。")
        info.setObjectName("muted")
        layout.addWidget(info)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("matchTable")
        self.table.setHorizontalHeaderLabels(("费用", "卡牌名称", "数量", "Card ID"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._begin_table_count_edit)
        layout.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("添加新卡"))
        self.card_search = QtLineEdit()
        self.card_search.setPlaceholderText("输入卡牌名称或 Card ID 筛选")
        self.card_search.textChanged.connect(self._refresh_card_options)
        add_row.addWidget(self.card_search, 1)
        self.card_choice = ComboBox()
        self.card_choice.setMinimumWidth(220)
        add_row.addWidget(self.card_choice)
        self.add_card_button = PushButton("添加新卡")
        self.add_card_button.clicked.connect(self._add_card)
        add_row.addWidget(self.add_card_button)
        layout.addLayout(add_row)

        self.total_label = QLabel()
        self.total_label.setObjectName("muted")
        layout.addWidget(self.total_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._rebuild_table()
        self._refresh_card_options()
        self._update_total()

    def _sorted_card_ids(self) -> list[int]:
        return sorted(
            self.counts,
            key=lambda card_id: (
                get_card_metadata(card_id).cost if get_card_metadata(card_id) else 99,
                self.window_ref._card_name(card_id),
                card_id,
            ),
        )

    def _rebuild_table(self) -> None:
        self.table.setRowCount(0)
        for card_id in self._sorted_card_ids():
            row = self.table.rowCount()
            self.table.insertRow(row)
            metadata = get_card_metadata(card_id)
            cost = str(metadata.cost) if metadata else "?"
            self.table.setItem(row, 0, QTableWidgetItem(cost))
            self.table.setItem(row, 1, QTableWidgetItem(self.window_ref._card_name(card_id)))
            spin = _plain_spinbox(0, 3, self.counts[card_id])
            spin.setReadOnly(True)
            spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            spin.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            spin.setToolTip("双击这一行编辑数量")
            spin.valueChanged.connect(self._update_total)
            spin.editingFinished.connect(lambda value=card_id, editor=spin: self._set_count(value, editor.value()))
            self.table.setCellWidget(row, 2, spin)
            self.table.setItem(row, 3, QTableWidgetItem(str(card_id)))

    def _begin_table_count_edit(self, row: int, _column: int) -> None:
        spin = self.table.cellWidget(row, 2)
        if not isinstance(spin, QSpinBox):
            return
        spin.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        spin.setReadOnly(False)
        spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        spin.setFocus(Qt.FocusReason.MouseFocusReason)
        spin.lineEdit().selectAll()

    def _set_count(self, card_id: int, value: int) -> None:
        if value <= 0:
            self.counts.pop(card_id, None)
        else:
            self.counts[card_id] = min(3, int(value))
        self._rebuild_table()
        self._refresh_card_options()
        self._update_total()

    def _refresh_card_options(self, _query: str | None = None) -> None:
        query = self.card_search.text().strip().casefold()
        self.card_choice.blockSignals(True)
        self.card_choice.clear()
        for card in sorted(self.catalog.values(), key=lambda item: (item.cost, item.name, item.card_id)):
            if card.card_id in self.counts:
                continue
            if not is_card_allowed(card.card_id, self.deck.class_id, self.deck.format_version):
                continue
            if query and query not in card.name.casefold() and query not in str(card.card_id):
                continue
            self.card_choice.addItem(f"{card.cost}费 {card.name}", userData=card.card_id)
        self.card_choice.blockSignals(False)

    def _add_card(self) -> None:
        card_id = self.card_choice.currentData()
        if not isinstance(card_id, int) or card_id <= 0:
            QMessageBox.information(self, "添加卡牌", "请先选择一张可加入当前牌组的卡牌。")
            return
        if card_id in self.counts:
            QMessageBox.information(self, "添加卡牌", "该卡牌已经在当前牌组中，请直接修改数量。")
            return
        self.counts[card_id] = 1
        self._rebuild_table()
        self._refresh_card_options()
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

        # Commit the editor currently holding focus as well; clicking Save can
        # otherwise happen before QSpinBox emits editingFinished().
        for row in range(self.table.rowCount()):
            card_item = self.table.item(row, 3)
            spin = self.table.cellWidget(row, 2)
            if card_item is None or not isinstance(spin, QSpinBox):
                continue
            try:
                card_id = int(card_item.text())
            except (TypeError, ValueError):
                continue
            if spin.value() <= 0:
                self.counts.pop(card_id, None)
            else:
                self.counts[card_id] = spin.value()
        return tuple(
            DeckCard(card_id=card_id, count=count)
            for card_id, count in self.counts.items()
            if count > 0
        )

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
    opponent_backfill_received = Signal(object)
    meta_cache_received = Signal(object)

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
        self._card_image_roots = self._find_card_image_roots()
        self._card_image_paths: dict[int, Path | None] = {}
        self._card_image_index: dict[int, Path] | None = None
        self._card_image_cache: dict[tuple[int, int], QPixmap] = {}
        self._deck_detail_render_pending = False
        self._deck_detail_dirty = True
        self._deck_image_generation = 0
        self._deck_image_queue: list[tuple[QLabel, int]] = []
        # Counts edited directly in the card grid are kept as a small draft
        # until the user brings the deck back to exactly 40 cards.  This lets
        # a user change 2→3 on one card and 3→2 on another without losing the
        # first edit to the repository's strict 40-card validation.
        self._deck_card_drafts: dict[str, dict[int, int]] = {}
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
        # A BattleInfo snapshot can occasionally reverse the two class IDs.
        # The saved deck's class is authoritative for the local side, so repair
        # any affected rows before the statistics page is first rendered.
        try:
            self._history.reconcile_deck_class_ids({
                deck.key: deck.class_id for deck in self._repository.decks
            })
        except (OSError, ValueError) as exc:
            self._history_error = str(exc)
        # Opponent deck recognition is intentionally offline and conservative:
        # the polling thread only supplies public played-card IDs, while this
        # cached matcher waits for enough evidence before assigning a label.
        loaded_meta_profiles = load_meta_deck_profiles()
        bundled_meta_path = Path(__file__).resolve().parent / "data" / "meta_decks.json"
        bundled_meta_profiles = load_meta_deck_profiles(bundled_meta_path) if bundled_meta_path.is_file() else ()
        self._remote_meta_profiles: tuple[MetaDeckProfile, ...] = canonicalize_meta_deck_labels(
            loaded_meta_profiles,
            bundled_meta_profiles,
        )
        self._meta_profiles: tuple[MetaDeckProfile, ...] = self._merge_local_meta_profiles(
            self._remote_meta_profiles,
        )
        self._meta_refresh_in_progress = False
        self._meta_refresh_status = "使用本地缓存"
        self._opponent_backfill_in_progress = False
        self._opponent_deck_matcher = OpponentDeckMatcher(self._meta_profiles)
        self._recognized_opponent_deck_name = ""
        self._recognized_opponent_deck_confidence: float | None = None
        self._record_matches = True
        self._updating_key_inputs = False
        self._set_application_icon()
        self._build_ui()
        self.snapshot_received.connect(self._render_snapshot)
        self.status_received.connect(self._set_status)
        self.error_received.connect(self._on_error)
        self.deck_received.connect(self._on_deck_event)
        self.opponent_backfill_received.connect(self._apply_opponent_deck_backfill)
        self.meta_cache_received.connect(self._apply_meta_cache_refresh)
        self._refresh_deck_choices()
        self._refresh_stats_page()
        # Existing history rows predate persisted opponent-card observations.
        # Defer the optional log scan until the window is shown so loading the
        # dashboard remains responsive, especially for large session logs.
        QTimer.singleShot(0, self._start_opponent_deck_backfill)
        QTimer.singleShot(0, self._start_meta_cache_refresh)
        QTimer.singleShot(250, self._start_service)

    # ----- shell and navigation -------------------------------------------------

    def _build_ui(self) -> None:
        dashboard = self._build_dashboard_page()
        decks = self._build_decks_page()
        meta = self._build_meta_page()
        probability = self._build_probability_page()
        stats = self._build_stats_page()
        settings = self._build_settings_page()
        self.dashboard_page = dashboard
        self.decks_page = decks
        self.meta_page = meta
        self.probability_page = probability
        self.stats_page = stats
        self.settings_page = settings
        self.decks_page.installEventFilter(self)
        self.addSubInterface(dashboard, FluentIcon.HOME, "对局仪表盘")
        self.addSubInterface(stats, FluentIcon.HISTORY, "详细统计")
        self.addSubInterface(decks, FluentIcon.LIBRARY, "我的卡组")
        self.addSubInterface(meta, FluentIcon.GLOBE, "Meta 卡组")
        self.addSubInterface(probability, FluentIcon.SYNC, "概率计算器")
        # Settings remain available to the window logic (connection mode and
        # recording preferences), but are intentionally not exposed as a
        # fifth navigation item.  The compact navigation is the four primary
        # user-facing pages above.
        self.navigationInterface.setExpandWidth(218)
        self.navigationInterface.expand(useAni=False)

    @staticmethod
    def _page(name: str = "page") -> QWidget:
        page = QWidget()
        page.setObjectName(name)
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
        page = self._page("dashboardPage")
        layout = self._page_layout(page)
        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 13)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = TitleLabel("Shadowverse Tracker")
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
        self.deck_choice_icon = QLabel()
        self.deck_choice_icon.setObjectName("deckClassIcon")
        self.deck_choice_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.deck_choice_icon.setFixedSize(28, 28)
        self.deck_choice_icon.setVisible(False)
        controls.addWidget(self.deck_choice_icon)
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
        page = self._page("decksPage")
        layout = self._page_layout(page)
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("我的卡组"))
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
        self.deck_list.setIconSize(QSize(26, 26))
        self.deck_list.setMouseTracking(True)
        self.deck_list.currentRowChanged.connect(self._select_deck_list_row)
        splitter.addWidget(self.deck_list)
        detail = QFrame()
        detail.setObjectName("panelCard")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 10, 12, 12)
        detail_layout.setSpacing(7)
        detail_top = QHBoxLayout()
        self.deck_detail_title = QLabel("牌组卡牌")
        self.deck_detail_title.setObjectName("sectionTitle")
        detail_top.addWidget(self.deck_detail_title)
        detail_top.addStretch(1)
        self.deck_detail_hint = QLabel("双击卡牌或直接编辑数量；末尾可添加新卡")
        self.deck_detail_hint.setObjectName("muted")
        detail_top.addWidget(self.deck_detail_hint)
        detail_layout.addLayout(detail_top)
        self.deck_detail_scroll = QScrollArea()
        self.deck_detail_scroll.setWidgetResizable(True)
        self.deck_detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_detail_content = QWidget()
        self.deck_card_grid = QGridLayout(self.deck_detail_content)
        self.deck_card_grid.setContentsMargins(2, 2, 2, 2)
        self.deck_card_grid.setSpacing(9)
        self.deck_card_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.deck_detail_scroll.setWidget(self.deck_detail_content)
        detail_layout.addWidget(self.deck_detail_scroll, 1)
        splitter.addWidget(detail)
        splitter.setSizes((340, 660))
        layout.addWidget(splitter, 1)
        self.deck_page_hint = QLabel("牌组链接会自动识别职业和模式；选择空项可解除绑定。")
        self.deck_page_hint.setObjectName("muted")
        layout.addWidget(self.deck_page_hint)
        return page

    def _local_meta_profiles(self) -> tuple[MetaDeckProfile, ...]:
        """Build in-memory Meta entries for every saved local deck."""
        profiles: list[MetaDeckProfile] = []
        for deck in self._repository.decks:
            profile = meta_profile_from_saved_deck(deck)
            if profile is not None:
                profiles.append(profile)
        return tuple(profiles)

    def _merge_local_meta_profiles(
        self,
        profiles: tuple[MetaDeckProfile, ...] | list[MetaDeckProfile],
    ) -> tuple[MetaDeckProfile, ...]:
        """Keep WBArts cache and private saved decks in one UI/matcher list."""
        merged = list(profiles)
        seen = {profile.profile_id for profile in merged}
        for profile in self._local_meta_profiles():
            if profile.profile_id not in seen:
                merged.append(profile)
                seen.add(profile.profile_id)
        return tuple(merged)

    def _refresh_local_meta_profiles(self) -> None:
        """Refresh local Meta entries after a deck is added, edited or deleted."""
        self._meta_profiles = self._merge_local_meta_profiles(self._remote_meta_profiles)
        self._opponent_deck_matcher = OpponentDeckMatcher(self._meta_profiles)
        if hasattr(self, "meta_deck_list"):
            self._refresh_meta_page()

    def _build_meta_page(self) -> QWidget:
        """Build the lightweight, text-only view of the cached Meta builds."""
        page = self._page("metaPage")
        layout = self._page_layout(page)

        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("Meta 卡组"))
        title_row.addStretch(1)
        self.meta_cache_status = QLabel(self._meta_refresh_status)
        self.meta_cache_status.setObjectName("muted")
        title_row.addWidget(self.meta_cache_status)
        layout.addLayout(title_row)

        filters = QFrame()
        filters.setObjectName("actionCard")
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(12, 9, 12, 9)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(QLabel("模式"))
        self.meta_format_filter = ComboBox()
        self.meta_format_filter.addItem("全部模式", userData="")
        self.meta_format_filter.addItem("轮换", userData="rotation")
        self.meta_format_filter.addItem("无限", userData="unlimited")
        self.meta_format_filter.currentIndexChanged.connect(lambda _index: self._refresh_meta_page())
        filter_layout.addWidget(self.meta_format_filter)
        filter_layout.addWidget(QLabel("职业"))
        self.meta_class_filter = ComboBox()
        self.meta_class_filter.addItem("全部职业", userData=0)
        for class_id in range(1, 8):
            self.meta_class_filter.addItem(class_name(class_id), userData=class_id)
            icon = self._class_icon(class_id)
            if not icon.isNull():
                self.meta_class_filter.setItemIcon(self.meta_class_filter.count() - 1, icon)
        self.meta_class_filter.currentIndexChanged.connect(lambda _index: self._refresh_meta_page())
        filter_layout.addWidget(self.meta_class_filter)
        self.meta_search = LineEdit()
        self.meta_search.setPlaceholderText("搜索卡组名称或类型")
        self.meta_search.textChanged.connect(lambda _text: self._refresh_meta_page())
        filter_layout.addWidget(self.meta_search, 1)
        layout.addWidget(filters)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.meta_deck_list = QListWidget()
        self.meta_deck_list.setObjectName("deckList")
        self.meta_deck_list.setMinimumWidth(300)
        self.meta_deck_list.setIconSize(QSize(24, 24))
        self.meta_deck_list.currentRowChanged.connect(self._select_meta_deck_row)
        splitter.addWidget(self.meta_deck_list)

        detail = QFrame()
        detail.setObjectName("panelCard")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 10, 12, 12)
        detail_layout.setSpacing(7)
        detail_top = QHBoxLayout()
        self.meta_detail_title = QLabel("卡组卡牌")
        self.meta_detail_title.setObjectName("sectionTitle")
        detail_top.addWidget(self.meta_detail_title)
        detail_top.addStretch(1)
        self.meta_detail_hint = QLabel("仅显示文字，减少图片加载")
        self.meta_detail_hint.setObjectName("muted")
        detail_top.addWidget(self.meta_detail_hint)
        detail_layout.addLayout(detail_top)
        self.meta_card_table = QTableWidget(0, 3)
        self.meta_card_table.setObjectName("matchTable")
        self.meta_card_table.setAlternatingRowColors(True)
        self.meta_card_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.meta_card_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.meta_card_table.verticalHeader().setVisible(False)
        self.meta_card_table.setHorizontalHeaderLabels(("费用", "卡牌名称", "数量"))
        meta_header = self.meta_card_table.horizontalHeader()
        meta_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        meta_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        meta_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.meta_card_table.setColumnWidth(0, 62)
        self.meta_card_table.setColumnWidth(2, 72)
        detail_layout.addWidget(self.meta_card_table, 1)
        splitter.addWidget(detail)
        splitter.setSizes((340, 660))
        layout.addWidget(splitter, 1)

        note = QLabel("数据来自本地缓存；我的卡组会自动加入列表。启动时每天最多向 WBArts 检查一次，网络失败时继续使用旧缓存。")
        note.setObjectName("muted")
        layout.addWidget(note)
        self._refresh_meta_page()
        return page

    @staticmethod
    def _meta_format_label(value: object) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized in {"rotation", "rot", "1", "format_1", "format1", "轮换"}:
            return "轮换"
        if normalized in {"unlimited", "unlim", "2", "format_2", "format2", "无限"}:
            return "无限"
        return str(value or "未知")

    def _filtered_meta_profiles(self) -> list[MetaDeckProfile]:
        format_filter = ""
        class_filter = 0
        query = ""
        if hasattr(self, "meta_format_filter"):
            format_filter = str(self.meta_format_filter.currentData() or "").strip().casefold()
        if hasattr(self, "meta_class_filter"):
            try:
                class_filter = int(self.meta_class_filter.currentData() or 0)
            except (TypeError, ValueError):
                class_filter = 0
        if hasattr(self, "meta_search"):
            query = self.meta_search.text().strip().casefold()
        result: list[MetaDeckProfile] = []
        for profile in self._meta_profiles:
            profile_format = str(profile.format or "").strip().casefold()
            if format_filter and self._meta_format_label(profile_format).casefold() != (
                "轮换" if format_filter == "rotation" else "无限"
            ):
                continue
            if class_filter and int(profile.class_id) != class_filter:
                continue
            if query and query not in f"{profile.name} {profile.archetype}".casefold():
                continue
            result.append(profile)
        return sorted(
            result,
            key=lambda profile: (
                *meta_archetype_sort_key(
                    profile.archetype,
                    profile.name,
                    profile.tier,
                ),
                int(profile.class_id),
                profile.profile_id,
            ),
        )

    def _refresh_meta_page(self) -> None:
        if not hasattr(self, "meta_deck_list"):
            return
        previous = self.meta_deck_list.currentItem()
        previous_id = previous.data(Qt.ItemDataRole.UserRole) if previous is not None else ""
        profiles = self._filtered_meta_profiles()
        self.meta_deck_list.blockSignals(True)
        self.meta_deck_list.clear()
        grouped: dict[str, list[MetaDeckProfile]] = {tier: [] for tier in META_TIER_ORDER}
        for profile in profiles:
            grouped.setdefault(meta_tier_label(profile.tier, profile.archetype), []).append(profile)
        for tier in META_TIER_ORDER:
            tier_profiles = grouped.get(tier, [])
            if not tier_profiles:
                continue
            header = QListWidgetItem(f"{tier}  ·  {len(tier_profiles)} 套卡组")
            header.setData(Qt.ItemDataRole.UserRole, None)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setForeground(QColor("#58738a"))
            header.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold))
            self.meta_deck_list.addItem(header)
            for profile in tier_profiles:
                format_label = self._meta_format_label(profile.format)
                item = QListWidgetItem(
                    f"{profile.display_name}\n{class_name(profile.class_id)} · {format_label} · {profile.total_cards}/40"
                )
                item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
                icon = self._class_icon(profile.class_id)
                if not icon.isNull():
                    item.setIcon(icon)
                self.meta_deck_list.addItem(item)
        target_row = next(
            (
                row
                for row in range(self.meta_deck_list.count())
                if self.meta_deck_list.item(row).data(Qt.ItemDataRole.UserRole)
            ),
            -1,
        )
        if previous_id:
            for row in range(self.meta_deck_list.count()):
                if self.meta_deck_list.item(row).data(Qt.ItemDataRole.UserRole) == previous_id:
                    target_row = row
                    break
        self.meta_deck_list.setCurrentRow(target_row if profiles else -1)
        self.meta_deck_list.blockSignals(False)
        if profiles and target_row >= 0:
            self._select_meta_deck_row(self.meta_deck_list.currentRow())
        else:
            self._select_meta_deck_row(-1)

    def _select_meta_deck_row(self, row: int) -> None:
        if not hasattr(self, "meta_card_table"):
            return
        profile: MetaDeckProfile | None = None
        if 0 <= row < self.meta_deck_list.count():
            profile_id = self.meta_deck_list.item(row).data(Qt.ItemDataRole.UserRole)
            profile = next((item for item in self._meta_profiles if item.profile_id == profile_id), None)
        self.meta_card_table.setRowCount(0)
        if profile is None:
            self.meta_detail_title.setText("卡组卡牌")
            self.meta_detail_hint.setText("暂无符合筛选条件的缓存卡组")
            return
        self.meta_detail_title.setText(
            f"{profile.display_name} · {class_name(profile.class_id)} · {self._meta_format_label(profile.format)} · {profile.total_cards}/40"
        )
        self.meta_detail_hint.setText(
            f"{profile.tier} · 更新于 {profile.updated_at or '未知'} · 仅文字模式"
        )
        cards = sorted(
            profile.cards.items(),
            key=lambda item: (get_card_metadata(item[0]).cost if get_card_metadata(item[0]) else 99, self._card_name(item[0]), item[0]),
        )
        for card_id, count in cards:
            row_index = self.meta_card_table.rowCount()
            self.meta_card_table.insertRow(row_index)
            metadata = get_card_metadata(card_id)
            self.meta_card_table.setItem(row_index, 0, QTableWidgetItem(str(metadata.cost if metadata else "?")))
            self.meta_card_table.setItem(row_index, 1, QTableWidgetItem(self._card_name(card_id)))
            self.meta_card_table.setItem(row_index, 2, QTableWidgetItem(str(count)))

    def _start_meta_cache_refresh(self) -> None:
        if self._meta_refresh_in_progress:
            return
        self._meta_refresh_in_progress = True
        thread = Thread(target=self._meta_cache_refresh_worker, name="meta-deck-refresh", daemon=True)
        thread.start()

    def _meta_cache_refresh_worker(self) -> None:
        try:
            profiles, status = refresh_wbarts_meta_cache_daily()
        except Exception as exc:  # pragma: no cover - defensive boundary for startup thread
            profiles, status = self._meta_profiles, f"failed: {exc}"
        self.meta_cache_received.emit((profiles, status))

    def _apply_meta_cache_refresh(self, payload: object) -> None:
        self._meta_refresh_in_progress = False
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        profiles, status = payload
        if isinstance(profiles, (list, tuple)):
            self._remote_meta_profiles = tuple(
                item for item in profiles if isinstance(item, MetaDeckProfile)
            )
            self._meta_profiles = self._merge_local_meta_profiles(
                self._remote_meta_profiles,
            )
            self._opponent_deck_matcher = OpponentDeckMatcher(self._meta_profiles)
        status_text = str(status or "使用本地缓存")
        if status_text == "updated":
            self._meta_refresh_status = "今日已更新"
        elif status_text == "skipped":
            self._meta_refresh_status = "今日已检查 · 使用缓存"
        else:
            self._meta_refresh_status = "更新失败 · 使用旧缓存"
        if hasattr(self, "meta_cache_status"):
            self.meta_cache_status.setText(self._meta_refresh_status)
        self._refresh_meta_page()
        if status_text == "updated":
            # Re-run the optional historical scan with the newly downloaded
            # profiles so a first launch can label old terminal matches too.
            QTimer.singleShot(0, self._start_opponent_deck_backfill)

    def _build_probability_page(self) -> QWidget:
        page = self._page("probabilityPage")
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
        self.probability_draws = _plain_spinbox(1, 40, 1)
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
        self.key_strategy = ComboBox()
        self.key_strategy.addItem("Unknown 未知", userData="unknown")
        self.key_strategy.addItem("Known 已知", userData="known")
        self.key_strategy.currentIndexChanged.connect(self._sync_key_strategy_inputs)
        self.key_deck_remaining = _plain_spinbox(0, 36, 36)
        self.key_hand_size = _plain_spinbox(0, 10, 4)
        self.key_mulligan = _plain_spinbox(0, 4, 0)
        # These values are owned by Tracker snapshots.  Keep them visible for
        # the calculation, but prevent accidental edits in the probability
        # form so a later snapshot can always refresh them.
        self._key_tracker_inputs = (
            self.key_deck_remaining,
            self.key_hand_size,
            self.key_mulligan,
        )
        for editor in self._key_tracker_inputs:
            editor.setEnabled(False)
            editor.setToolTip("由 Tracker 自动读取")
        self.key_keep1_types = _plain_spinbox(0, 40, 0)
        self.key_keep2_types = _plain_spinbox(0, 40, 0)
        self.key_seen_keep1 = _plain_spinbox(0, 40, 0)
        self.key_seen_keep2 = _plain_spinbox(0, 40, 0)
        self.key_copies = _plain_spinbox(1, 3, 3)
        self.key_limit = _plain_spinbox(0, 3, 1)
        self.key_seen = _plain_spinbox(0, 3, 0)

        key_grid = QGridLayout()
        key_grid.setHorizontalSpacing(8)
        key_grid.setVerticalSpacing(6)
        key_grid.addWidget(QLabel("策略"), 0, 0)
        key_grid.addWidget(self.key_strategy, 0, 1, 1, 3)

        def pair(row: int, label: str, editor: QSpinBox, column: int) -> None:
            key_grid.addWidget(QLabel(label), row, column)
            key_grid.addWidget(editor, row, column + 1)

        pair(1, "对手牌库", self.key_deck_remaining, 0)
        pair(1, "未知手牌", self.key_hand_size, 2)
        pair(2, "换牌数量", self.key_mulligan, 0)
        pair(2, "留1类型", self.key_keep1_types, 2)
        pair(3, "留2类型", self.key_keep2_types, 0)
        pair(3, "已见留1", self.key_seen_keep1, 2)
        pair(4, "已见留2", self.key_seen_keep2, 0)
        pair(4, "Key投入", self.key_copies, 2)
        pair(5, "Key留牌上限", self.key_limit, 0)
        pair(5, "Key已见", self.key_seen, 2)
        key_grid.setColumnStretch(1, 1)
        key_grid.setColumnStretch(3, 1)
        key.layout().addLayout(key_grid)
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
        self.faith_total = _plain_spinbox(0, 1000)
        self.faith_min_z = _plain_spinbox(0, 1000)
        faith_form.addRow("信仰总值 X+Y+Z", self.faith_total)
        faith_form.addRow("需要 Z ≥", self.faith_min_z)
        faith.layout().addLayout(faith_form)
        faith_button = PrimaryPushButton("计算")
        faith_button.clicked.connect(self._calculate_faith)
        faith.layout().addWidget(faith_button)
        self.faith_result = QLabel("每个信仰点独立以 1/3 概率分配给 X、Y、Z")
        self.faith_result.setWordWrap(True); self.faith_result.setObjectName("muted")
        faith.layout().addWidget(self.faith_result)
        grid.addWidget(faith, 1, 0)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self._sync_key_strategy_inputs()
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
        page = self._page("statsPage")
        layout = self._page_layout(page)
        title_row = QHBoxLayout()
        title_row.addWidget(SubtitleLabel("详细统计"))
        title_row.addWidget(QLabel("筛选牌组"))
        self.stats_deck_filter = ComboBox()
        self.stats_deck_filter.setMinimumWidth(260)
        self.stats_deck_filter.currentIndexChanged.connect(lambda _index: self._refresh_stats_page())
        title_row.addWidget(self.stats_deck_filter)
        title_row.addStretch(1)
        self.stats_reset_button = PushButton("重置筛选牌组")
        self.stats_reset_button.setIcon(FluentIcon.DELETE.icon())
        self.stats_reset_button.clicked.connect(self._reset_stats)
        title_row.addWidget(self.stats_reset_button)
        layout.addLayout(title_row)
        stats_metrics = QHBoxLayout()
        stats_metrics.setSpacing(10)
        self.stats_rate_metric = MetricCard("卡组胜率", "—", "未选择牌组")
        self.stats_games_metric = MetricCard("总对局", "—", "胜 / 负")
        self.stats_first_metric = MetricCard("先手胜率", "—", "0 局")
        self.stats_second_metric = MetricCard("后手胜率", "—", "0 局")
        for metric in (
            self.stats_rate_metric,
            self.stats_games_metric,
            self.stats_first_metric,
            self.stats_second_metric,
        ):
            stats_metrics.addWidget(metric, 1)
        layout.addLayout(stats_metrics)

        # Keep the chart as a full-width visual block, matching the compact
        # matchup dashboards users are familiar with.
        self.stats_class_chart = ClassWinRateChart()
        layout.addWidget(self.stats_class_chart)

        breakdown_title = QHBoxLayout()
        breakdown_title.addWidget(QLabel("对手职业先后手胜率"))
        breakdown_title.addStretch(1)
        breakdown_title.addWidget(QLabel("筛选职业"))
        self.stats_opponent_filter = ComboBox()
        self.stats_opponent_filter.setMinimumWidth(150)
        self.stats_opponent_filter.addItem("全部职业", userData="")
        for class_id in range(1, 8):
            self.stats_opponent_filter.addItem(class_name(class_id), userData=class_name(class_id))
            icon = self._class_icon(class_id)
            if not icon.isNull():
                self.stats_opponent_filter.setItemIcon(self.stats_opponent_filter.count() - 1, icon)
        self.stats_opponent_filter.currentIndexChanged.connect(lambda _index: self._refresh_stats_page())
        breakdown_title.addWidget(self.stats_opponent_filter)
        layout.addLayout(breakdown_title)
        self.stats_breakdown = QTableWidget(0, 5)
        self.stats_breakdown.setObjectName("matchTable")
        self.stats_breakdown.setAlternatingRowColors(True)
        self.stats_breakdown.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_breakdown.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stats_breakdown.verticalHeader().setVisible(False)
        self.stats_breakdown.setHorizontalHeaderLabels(("对手职业", "总局数", "先手胜率", "后手胜率", "先手率"))
        breakdown_header = self.stats_breakdown.horizontalHeader()
        for column in range(5):
            breakdown_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        # Keep the summary readable without allowing an empty first column to
        # consume the whole window on compact displays.
        for column, width in ((0, 126), (1, 72), (2, 112), (3, 112), (4, 92)):
            self.stats_breakdown.setColumnWidth(column, width)
        self.stats_breakdown.setMinimumWidth(514)
        self.stats_breakdown.setMinimumHeight(135)
        self.stats_breakdown.setMaximumHeight(210)
        layout.addWidget(self.stats_breakdown)

        match_title = QHBoxLayout()
        match_title.addWidget(QLabel("详细对局"))
        match_title.addStretch(1)
        match_hint = QLabel("对手卡组按公开出牌自动匹配；也可双击手动输入")
        match_hint.setObjectName("muted")
        match_title.addWidget(match_hint)
        layout.addLayout(match_title)
        self.match_table = QTableWidget(0, 7)
        self.match_table.setObjectName("matchTable")
        self.match_table.setAlternatingRowColors(True)
        self.match_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.match_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.match_table.setHorizontalHeaderLabels(("我的牌组", "对手职业", "对手卡组", "先后手", "回合数", "时间（本地）", "结果"))
        match_header = self.match_table.horizontalHeader()
        for column in range(7):
            match_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        # Five Chinese characters fit in these columns while leaving room for
        # the class mark.  The remaining metadata stays compact as well.
        for column, width in (
            (0, 118),  # 我的牌组 + icon
            (1, 94),   # 对手职业
            (2, 126),  # 对手卡组 + icon + inline edit
            (3, 68),
            (4, 62),
            (5, 126),
            (6, 62),
        ):
            self.match_table.setColumnWidth(column, width)
        self.match_table.itemChanged.connect(self._on_match_table_item_changed)
        layout.addWidget(self.match_table, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = self._page("settingsPage")
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

    def switchTo(self, interface: QWidget) -> None:  # noqa: N802 - FluentWindow API
        super().switchTo(interface)
        if interface is getattr(self, "decks_page", None) and self._deck_detail_dirty:
            self._schedule_deck_detail_render()

    def _is_page_current(self, page: QWidget | None) -> bool:
        if page is None:
            return False
        stacked = getattr(self, "stackedWidget", None)
        try:
            return stacked is not None and stacked.currentWidget() is page
        except (AttributeError, RuntimeError):
            return bool(page.isVisible())

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        if watched is getattr(self, "decks_page", None) and event.type() == QEvent.Type.Show:
            if self._deck_detail_dirty:
                self._schedule_deck_detail_render()
        return super().eventFilter(watched, event)

    # ----- card art and deck identity ----------------------------------------

    @staticmethod
    def _find_card_image_roots() -> list[Path]:
        """Find the optional card-art pack in source and frozen runs."""
        package_root = Path(__file__).resolve().parents[2]
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        roots = (
            runtime_root / "SV_WB_Cards",
            runtime_root / "SV_WB_Cards" / "SV_WB_Cards",
            package_root / "SV_WB_Cards",
            package_root / "SV_WB_Cards" / "SV_WB_Cards",
            Path.cwd() / "SV_WB_Cards",
            Path.cwd() / "SV_WB_Cards" / "SV_WB_Cards",
        )
        return list(dict.fromkeys(root for root in roots if root.is_dir()))

    def _card_image_path(self, card_id: object) -> Path | None:
        if not isinstance(card_id, int) or card_id <= 0:
            return None
        if card_id in self._card_image_paths:
            return self._card_image_paths[card_id]
        if self._card_image_index is None:
            self._card_image_index = self._build_card_image_index()
        path = self._card_image_index.get(card_id)
        self._card_image_paths[card_id] = path
        return path

    def _build_card_image_index(self) -> dict[int, Path]:
        """Index card art once instead of recursively scanning per card tile."""
        preferred: dict[int, Path] = {}
        fallback: dict[int, Path] = {}
        token_pattern = re.compile(r"(?<!\d)(\d{6,})(?!\d)")
        for root in self._card_image_roots:
            for suffix in ("*.webp", "*.png"):
                for item in root.rglob(suffix):
                    ids = token_pattern.findall(item.stem)
                    if not ids:
                        continue
                    is_preferred = "_evo" not in item.stem and "@" not in item.stem
                    target = preferred if is_preferred else fallback
                    for token in ids:
                        value = int(token)
                        target.setdefault(value, item)
        return {**fallback, **preferred}

    def _card_image_pixmap(self, card_id: object, height: int = 160) -> QPixmap | None:
        if not isinstance(card_id, int) or card_id <= 0:
            return None
        cache_key = (card_id, int(height))
        if cache_key in self._card_image_cache:
            return self._card_image_cache[cache_key]
        path = self._card_image_path(card_id)
        if path is None:
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        scaled = pixmap.scaledToHeight(
            max(1, int(height)), Qt.TransformationMode.SmoothTransformation
        )
        self._card_image_cache[cache_key] = scaled
        return scaled

    def _make_card_tile(
        self,
        card_id: int,
        count: int,
        *,
        load_image: bool = True,
    ) -> QFrame:
        """Create a full-art card tile with an inline count editor."""
        tile = DeckCardTile()
        tile.setObjectName("deckCardTile")
        tile.setMinimumWidth(145)
        tile.setToolTip("双击卡牌或直接编辑数量")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(5)
        image = QLabel()
        image.setObjectName("deckCardImage")
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setFixedHeight(164)
        image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        pixmap = self._card_image_pixmap(card_id, 158) if load_image else None
        if pixmap is not None and not pixmap.isNull():
            image.setPixmap(pixmap)
        elif load_image:
            image.setText(self._card_name(card_id))
            image.setWordWrap(True)
            image.setStyleSheet("background:#eaf0f5;border-radius:6px;color:#1d3348;padding:6px;")
        else:
            image.setText("加载中…")
            image.setStyleSheet("color:#8798a8;")
        layout.addWidget(image)
        name = QLabel(self._card_name(card_id))
        name.setObjectName("cardName")
        name.setWordWrap(True)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(name)
        metadata = get_card_metadata(card_id)
        cost = metadata.cost if metadata else "?"
        count_row = QHBoxLayout()
        count_label = QLabel(f"{cost}费")
        count_label.setObjectName("cardCount")
        count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        count_row.addWidget(count_label)
        count_editor = _plain_spinbox(0, 3, count)
        count_editor.setFixedWidth(48)
        count_editor.setReadOnly(True)
        count_editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        count_editor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        count_editor.setToolTip("双击卡牌编辑数量")
        count_editor.editingFinished.connect(
            lambda value=card_id, editor=count_editor: self._finish_card_count_edit(value, editor)
        )
        count_row.addWidget(count_editor)
        count_row.addStretch(1)
        layout.addLayout(count_row)
        tile.double_clicked.connect(
            lambda editor=count_editor: self._begin_card_count_edit(editor)
        )
        return tile

    @staticmethod
    def _begin_card_count_edit(editor: QSpinBox) -> None:
        editor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        editor.setReadOnly(False)
        editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        editor.lineEdit().selectAll()

    def _finish_card_count_edit(self, card_id: int, editor: QSpinBox) -> None:
        editor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        editor.setReadOnly(True)
        editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._set_deck_card_draft(card_id, editor.value())

    def _set_deck_card_draft(self, card_id: int, count: int) -> None:
        deck = self._active_deck()
        if deck is None:
            return
        counts = self._deck_card_counts(deck)
        if card_id not in counts:
            return
        if counts[card_id] == count and deck.key not in self._deck_card_drafts:
            return
        if count <= 0:
            counts.pop(card_id, None)
        else:
            counts[card_id] = min(3, int(count))
        total = sum(counts.values())
        self._deck_card_drafts[deck.key] = counts
        if total == deck.total_cards:
            # A complete deck can be persisted immediately.  Keeping the
            # repository as the source of truth also preserves match binding.
            from .memory.deck import DeckCard

            try:
                updated = self._repository.update_cards(
                    deck.key,
                    tuple(DeckCard(card_id=value, count=amount) for value, amount in counts.items() if amount > 0),
                )
            except (OSError, KeyError, ValueError) as exc:
                self._show_error("数量保存失败", str(exc))
                return
            self._deck_card_drafts.pop(deck.key, None)
            self._on_deck_saved(updated)
            return
        self._deck_detail_dirty = True
        self._schedule_deck_detail_render()

    def _class_icon(self, class_id: int | None) -> QIcon:
        """Return the official SVWB class mark for a saved deck."""
        if class_id is None:
            return QIcon()
        asset_name = CLASS_ICON_FILES.get(int(class_id))
        path = self._app_asset_path(asset_name) if asset_name else None
        return QIcon(str(path)) if path is not None else QIcon()

    # ----- deck repository ------------------------------------------------------

    def _active_deck(self) -> SavedDeck | None:
        return self._repository.active()

    def _deck_card_counts(self, deck: SavedDeck) -> dict[int, int]:
        """Return persisted counts plus any in-progress grid edits."""
        draft = self._deck_card_drafts.get(deck.key)
        if draft is not None:
            return dict(draft)
        return {card.card_id: card.count for card in deck.cards}

    @staticmethod
    def _format_mode(value: int) -> str:
        return "轮换" if int(value) == 1 else "无限"

    def _deck_label(self, deck: SavedDeck) -> str:
        # The repository only accepts complete decks, so repeating ``40张`` in
        # every selector item adds noise without conveying new information.
        return f"{deck.name}（{class_name(deck.class_id)} / {self._format_mode(deck.format_version)}）"

    def _refresh_deck_choices(self) -> None:
        self._deck_choice_keys = [None, *[deck.key for deck in self._repository.decks]]
        labels = [""] + [self._deck_label(deck) for deck in self._repository.decks]
        active = self._active_deck()
        for combo in (getattr(self, "deck_choice", None),):
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear(); combo.addItems(labels)
            for index, deck in enumerate(self._repository.decks, start=1):
                icon = self._class_icon(deck.class_id)
                if not icon.isNull():
                    combo.setItemIcon(index, icon)
            combo.setCurrentIndex(self._deck_choice_keys.index(active.key) if active else 0)
            combo.blockSignals(False)
        if hasattr(self, "deck_choice_icon"):
            icon = self._class_icon(active.class_id) if active is not None else QIcon()
            self.deck_choice_icon.setPixmap(icon.pixmap(QSize(22, 22)) if not icon.isNull() else QPixmap())
            self.deck_choice_icon.setVisible(not icon.isNull())
        if hasattr(self, "deck_list"):
            self.deck_list.blockSignals(True)
            self.deck_list.clear()
            blank = QListWidgetItem("（未选择牌组）")
            blank.setData(Qt.ItemDataRole.UserRole, None)
            self.deck_list.addItem(blank)
            for deck in self._repository.decks:
                item = QListWidgetItem(self._deck_label(deck))
                item.setData(Qt.ItemDataRole.UserRole, deck.key)
                icon = self._class_icon(deck.class_id)
                if not icon.isNull():
                    item.setIcon(icon)
                self.deck_list.addItem(item)
            self.deck_list.setCurrentRow(self._deck_choice_keys.index(active.key) if active else 0)
            self.deck_list.blockSignals(False)
        self._refresh_stats_filter()
        self._deck_detail_dirty = True
        if self._is_page_current(getattr(self, "decks_page", None)):
            self._schedule_deck_detail_render()
        self._refresh_local_meta_profiles()
        self._update_header_stats()
        self._refresh_stats_page()

    def _sync_deck_selection_ui(self, *, render_detail: bool = True) -> None:
        """Update selection/highlight widgets without rebuilding their items."""
        active = self._active_deck()
        index = self._deck_choice_keys.index(active.key) if active else 0
        combo = getattr(self, "deck_choice", None)
        if combo is not None:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        if hasattr(self, "deck_choice_icon"):
            icon = self._class_icon(active.class_id) if active is not None else QIcon()
            self.deck_choice_icon.setPixmap(icon.pixmap(QSize(22, 22)) if not icon.isNull() else QPixmap())
            self.deck_choice_icon.setVisible(not icon.isNull())
        deck_list = getattr(self, "deck_list", None)
        if deck_list is not None and 0 <= index < deck_list.count():
            deck_list.blockSignals(True)
            deck_list.setCurrentRow(index)
            deck_list.blockSignals(False)
        if render_detail:
            self._deck_detail_dirty = True
            if self._is_page_current(getattr(self, "decks_page", None)):
                self._schedule_deck_detail_render()
        self._update_header_stats()

    def _schedule_deck_detail_render(self) -> None:
        """Render the visible deck after its selection highlight can repaint."""
        if self._deck_detail_render_pending:
            return
        self._deck_detail_render_pending = True

        def render() -> None:
            self._deck_detail_render_pending = False
            if self._is_page_current(getattr(self, "decks_page", None)):
                self._render_deck_detail()

        QTimer.singleShot(0, render)

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
        # Keep the existing combo/list items in place so the clicked row stays
        # highlighted and the expensive card-grid rebuild is not mixed with
        # item insertion/selection signals.
        self._deck_detail_dirty = True
        self._deck_image_generation += 1
        self._deck_image_queue.clear()
        self._sync_deck_selection_ui(render_detail=False)
        if self._is_page_current(getattr(self, "decks_page", None)):
            self._schedule_deck_detail_render()
        self._restart_service_deck()

    def _select_deck_list_row(self, row: int) -> None:
        self._select_deck_index(row)

    def _render_deck_detail(self) -> None:
        deck = self._active_deck()
        if not hasattr(self, "deck_card_grid"):
            return
        self._deck_detail_dirty = False
        self._deck_image_generation += 1
        image_generation = self._deck_image_generation
        self._deck_image_queue.clear()
        while self.deck_card_grid.count():
            item = self.deck_card_grid.takeAt(0)
            if item.widget() is not None:
                widget = item.widget()
                widget.setParent(None)
                widget.deleteLater()
        if deck is None:
            self.deck_detail_title.setText("牌组卡牌")
            self.deck_detail_hint.setText("未选择牌组；选择左侧空项可进行特殊/解密对局")
            empty = QLabel("未选择牌组")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deck_card_grid.addWidget(empty, 0, 0, 1, 4)
            return
        counts = self._deck_card_counts(deck)
        draft_total = sum(counts.values())
        self.deck_detail_title.setText(
            f"{deck.name} · {class_name(deck.class_id)} · {self._format_mode(deck.format_version)} · {draft_total}/40"
        )
        hint = "双击卡牌或直接编辑数量；末尾可添加新卡"
        if deck.key in self._deck_card_drafts:
            hint += f" · 数量草稿 {draft_total}/40，补齐后自动保存"
        self.deck_detail_hint.setText(hint)
        cards = sorted(
            counts.items(),
            key=lambda item: self._deck_card_sort_key(item[0]),
        )
        for index, card in enumerate(cards):
            tile = self._make_card_tile(
                card[0],
                card[1],
                load_image=False,
            )
            self.deck_card_grid.addWidget(tile, index // 4, index % 4)
            image = tile.findChild(QLabel, "deckCardImage")
            if image is not None:
                self._deck_image_queue.append((image, card[0]))
        add_tile = QFrame()
        add_tile.setObjectName("deckCardTile")
        add_layout = QVBoxLayout(add_tile)
        add_layout.setContentsMargins(12, 12, 12, 12)
        add_layout.addStretch(1)
        add_button = PrimaryPushButton("添加新卡")
        add_button.setToolTip("打开编辑器，搜索并添加当前职业允许的卡牌")
        add_button.clicked.connect(self._add_new_card)
        add_layout.addWidget(add_button)
        add_layout.addStretch(1)
        self.deck_card_grid.addWidget(add_tile, len(cards) // 4, len(cards) % 4)
        for column in range(4):
            self.deck_card_grid.setColumnStretch(column, 1)
        if self._deck_image_queue:
            QTimer.singleShot(0, lambda generation=image_generation: self._load_deck_image_chunk(generation))

    def _deck_card_sort_key(self, card_id: int) -> tuple[int, str]:
        metadata = get_card_metadata(card_id)
        return (metadata.cost if metadata else 99, self._card_name(card_id))

    def _load_deck_image_chunk(self, generation: int) -> None:
        """Load a few card images per event-loop turn to keep deck switching responsive."""
        if generation != self._deck_image_generation:
            return
        for _ in range(2):
            if not self._deck_image_queue:
                break
            image, card_id = self._deck_image_queue.pop(0)
            try:
                if image is None or image.parent() is None:
                    continue
                pixmap = self._card_image_pixmap(card_id, 158)
                if pixmap is not None and not pixmap.isNull():
                    image.setStyleSheet("")
                    image.setText("")
                    image.setPixmap(pixmap)
                else:
                    image.setText(self._card_name(card_id))
                    image.setWordWrap(True)
                    image.setObjectName("cardImageFallback")
                    image.setStyleSheet("background:#eaf0f5;border-radius:6px;color:#1d3348;padding:6px;")
            except RuntimeError:
                continue
        if generation == self._deck_image_generation and self._deck_image_queue:
            QTimer.singleShot(0, lambda: self._load_deck_image_chunk(generation))

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
        self._deck_card_drafts.pop(deck.key, None)
        self._refresh_deck_choices()
        self._restart_service_deck()

    def _edit_deck(self) -> None:
        deck = self._active_deck()
        if deck is None:
            self._show_info("编辑牌组", "请先选择一个牌组。")
            return
        dialog = DeckEditorDialog(self, deck)
        dialog.exec()

    def _add_new_card(self) -> None:
        """Open the editor's searchable add-card control from the grid tail."""
        if self._active_deck() is None:
            self._show_info("添加新卡", "请先选择一个牌组。")
            return
        self._edit_deck()

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
        service = self._service
        if service is None or not service.running:
            return
        active = self._active_deck()
        snapshot = active.to_snapshot() if active is not None else None
        key = active.key if active is not None else None
        # TrackerService can swap its local ledger atomically.  Restarting the
        # reader thread here used to block the UI while it joined the polling
        # thread, which made deck switching feel like a freeze.
        QTimer.singleShot(
            0,
            lambda: service.set_selected_deck(snapshot, key)
            if service is self._service and service.running
            else None,
        )

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
        # The deck list itself has not changed; only synchronize the current
        # row/icon and statistics after the service confirms the switch.
        self._sync_deck_selection_ui(render_detail=False)

    def _start_opponent_deck_backfill(self) -> None:
        """Scan the optional session log away from the Qt event loop."""
        if (
            self._opponent_backfill_in_progress
            or not self._history.records
            or not self._opponent_deck_matcher.profiles
        ):
            return
        self._opponent_backfill_in_progress = True
        path = Path("logs") / "app_session.jsonl"

        def scan() -> None:
            try:
                observations = load_session_opponent_observations(path)
            except Exception:  # pragma: no cover - defensive boundary for log I/O
                observations = {}
            self._opponent_backfill_in_progress = False
            self.opponent_backfill_received.emit(observations)

        Thread(target=scan, name="opponent-deck-backfill", daemon=True).start()

    def _apply_opponent_deck_backfill(self, value: object) -> None:
        """Apply session-log observations and refresh only when labels change."""
        observations = value if isinstance(value, dict) else {}
        if not observations:
            return
        try:
            labels_added = self._history.auto_match_opponent_decks(
                self._opponent_deck_matcher,
                observations,
            )
        except (OSError, ValueError, TypeError) as exc:
            self._history_error = str(exc)
            return
        if labels_added:
            self._refresh_stats_page()

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

    @staticmethod
    def _played_card_ids(value: object) -> tuple[int, ...]:
        """Extract card IDs from the reader's public played-card tuples."""
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
                card_id = int(raw)
            except (TypeError, ValueError):
                continue
            if card_id > 0:
                result.append(card_id)
        return tuple(result)

    def _update_opponent_deck_match(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        """Update the live candidate without ever blocking the tracker UI."""
        if not self._opponent_deck_matcher.profiles:
            return
        active = self._active_deck()
        _, opponent_class_id = orient_class_ids(
            snapshot.get("self_class_id"),
            snapshot.get("opponent_class_id"),
            active.class_id if active is not None else None,
        )
        observed = self._played_card_ids(opponent.get("played_card_ids"))
        result = self._opponent_deck_matcher.match(observed, opponent_class_id)
        if result is None:
            return
        self._recognized_opponent_deck_name = result.label
        self._recognized_opponent_deck_confidence = result.confidence

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
            self._recognized_opponent_deck_name = ""
            self._recognized_opponent_deck_confidence = None
        self._update_opponent_deck_match(snapshot, opponent)
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
            self_class_id, opponent_class_id = orient_class_ids(
                snapshot.get("self_class_id"),
                snapshot.get("opponent_class_id"),
                deck.class_id,
            )
            record = MatchRecord(
                match_id=model_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                deck_key=self._match_deck_key,
                deck_name=deck.name,
                self_class_id=self_class_id,
                opponent_class_id=opponent_class_id,
                opponent_class=class_name(opponent_class_id),
                result=terminal,
                result_code=result_code,
                turn=turn,
                is_first=mine.get("is_first_side") if isinstance(mine.get("is_first_side"), bool) else None,
                opponent_deck_name=self._recognized_opponent_deck_name,
                opponent_played_card_ids=self._played_card_ids(opponent.get("played_card_ids")),
            )
            if not self._history.add(record):
                # A terminal snapshot can arrive before the last public card
                # event.  Fill an initially blank label once a later snapshot
                # separates the candidates, but never overwrite a user's
                # manually edited label.  Keep the public-card evidence even
                # when the profile cache cannot identify the exact build yet.
                existing = next(
                    (item for item in self._history.records if item.match_id == model_id),
                    None,
                )
                if existing is not None:
                    observed = self._played_card_ids(opponent.get("played_card_ids"))
                    if len(observed) > len(existing.opponent_played_card_ids):
                        self._history.update_opponent_played_cards(model_id, observed)
                    if self._recognized_opponent_deck_name and not existing.opponent_deck_name:
                        self._history.update_opponent_deck(model_id, self._recognized_opponent_deck_name)
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
        self._reset_probability_tracker_inputs()
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
        if self._recognized_opponent_deck_name:
            confidence = (
                f" · {self._recognized_opponent_deck_confidence * 100:.0f}%"
                if self._recognized_opponent_deck_confidence is not None
                else ""
            )
            lines.append(f"对手卡组：{self._recognized_opponent_deck_name}{confidence}")
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

    def _sync_key_strategy_inputs(self, _index: int = -1) -> None:
        """Known mode exposes the mulligan-policy fields used by the old UI."""
        known = (self.key_strategy.currentData() or "unknown") == "known"
        for editor in (
            self.key_keep1_types,
            self.key_keep2_types,
            self.key_seen_keep1,
            self.key_seen_keep2,
            self.key_limit,
        ):
            editor.setEnabled(known)

    def _reset_probability_tracker_inputs(self) -> None:
        """Clear tracker-owned values when the previous match has ended."""
        if not hasattr(self, "_key_tracker_inputs"):
            return
        self._updating_key_inputs = True
        try:
            self.key_deck_remaining.setValue(36)
            self.key_hand_size.setValue(4)
            self.key_mulligan.setValue(0)
        finally:
            self._updating_key_inputs = False

    def _update_probability_inputs(self, snapshot: dict[str, object], opponent: dict[str, object]) -> None:
        deck = opponent.get("deck_count")
        hand_size = _opponent_hand_size(snapshot, opponent)
        swapped = _opponent_mulligan_count(snapshot, opponent)
        self._updating_key_inputs = True
        try:
            if isinstance(deck, int):
                self.key_deck_remaining.setValue(max(0, min(36, deck)))
            if isinstance(hand_size, int):
                self.key_hand_size.setValue(max(0, min(10, hand_size)))
            if isinstance(swapped, int) and 0 <= swapped <= 4:
                self.key_mulligan.setValue(swapped)
        finally:
            self._updating_key_inputs = False

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
            keep1_types=self.key_keep1_types.value(),
            keep2_types=self.key_keep2_types.value(),
            seen_keep1=self.key_seen_keep1.value(),
            seen_keep2=self.key_seen_keep2.value(),
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

    def _refresh_stats_filter(self) -> None:
        combo = getattr(self, "stats_deck_filter", None)
        if combo is None:
            return
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("全部卡组", None)
        for deck in self._repository.decks:
            # QFluentWidgets.ComboBox follows the Qt signature
            # ``addItem(text, icon=None, userData=None)``.  Passing the key as
            # the second positional argument silently stores it as an icon,
            # leaving currentData() empty and making the page appear stuck on
            # “全部卡组”.
            combo.addItem(self._deck_label(deck), userData=deck.key)
            icon = self._class_icon(deck.class_id)
            if not icon.isNull():
                combo.setItemIcon(combo.count() - 1, icon)
        target = combo.findData(previous) if previous is not None else 0
        combo.setCurrentIndex(target if target >= 0 else 0)
        combo.blockSignals(False)

    def _stats_filter_key(self) -> str | None:
        combo = getattr(self, "stats_deck_filter", None)
        if combo is None:
            return None
        value = combo.currentData()
        return value if isinstance(value, str) and value else None

    def _stats_opponent_filter_name(self) -> str | None:
        combo = getattr(self, "stats_opponent_filter", None)
        if combo is None:
            return None
        value = combo.currentData()
        return value if isinstance(value, str) and value else None

    def _refresh_stats_page(self) -> None:
        if not hasattr(self, "match_table"): return
        filter_key = self._stats_filter_key()
        opponent_filter = self._stats_opponent_filter_name()
        stats = self._history.stats(filter_key)
        scope_label = "全部卡组" if filter_key is None else next(
            (deck.name for deck in self._repository.decks if deck.key == filter_key),
            "已选牌组",
        )
        has_records = bool(self._history.records)
        self.stats_reset_button.setText("重置所有卡组" if filter_key is None else "重置筛选牌组")
        self.stats_reset_button.setEnabled(has_records)
        first = stats["first"]
        second = stats["second"]
        self.stats_rate_metric.set_value(
            f"{float(stats['win_rate']):.1f}%", f"{int(stats['finished'])} 局 · {scope_label}"
        )
        self.stats_games_metric.set_value(
            f"{int(stats['finished'])}", f"{int(stats['wins'])} 胜 / {int(stats['losses'])} 负"
        )
        self.stats_first_metric.set_value(
            f"{float(first['win_rate']):.1f}%", f"{int(first['finished'])} 局"
        )
        self.stats_second_metric.set_value(
            f"{float(second['win_rate']):.1f}%", f"{int(second['finished'])} 局"
        )
        all_by_class = stats.get("by_class", {})
        all_by_class = all_by_class if isinstance(all_by_class, dict) else {}
        chart_rows: list[tuple[str, float, int, int, QIcon]] = []
        for class_id in range(1, 8):
            opponent_class = class_name(class_id)
            group = all_by_class.get(opponent_class, {})
            group = group if isinstance(group, dict) else {}
            total = int(group.get("finished", 0))
            wins = int(group.get("wins", 0))
            chart_rows.append(
                (
                    opponent_class,
                    float(group.get("win_rate", 0.0)),
                    wins,
                    total,
                    self._class_icon(class_id),
                )
            )
        self.stats_class_chart.set_rows(chart_rows)

        # The table has its own opponent-class filter while the chart remains
        # a seven-class overview for the selected deck.
        table_stats = self._history.stats(filter_key, opponent_filter)
        by_class = table_stats.get("by_class", {})
        by_class = by_class if isinstance(by_class, dict) else {}
        known_classes = [class_name(class_id) for class_id in range(1, 8)]
        table_classes = [opponent_filter] if opponent_filter else list(known_classes)
        if not opponent_filter:
            table_classes.extend(sorted(str(value) for value in by_class if value not in known_classes))
        self.stats_breakdown.setRowCount(0)
        for opponent_class in table_classes:
            group = by_class.get(opponent_class, {})
            group = group if isinstance(group, dict) else {}
            row = self.stats_breakdown.rowCount()
            self.stats_breakdown.insertRow(row)
            class_id = next(
                (class_id for class_id in range(1, 8) if class_name(class_id) == opponent_class),
                next(
                    (
                        record.opponent_class_id
                        for record in self._history.records
                        if record.opponent_class == opponent_class
                        and (filter_key is None or record.deck_key == filter_key)
                    ),
                    None,
                ),
            )
            class_item = QTableWidgetItem(opponent_class)
            icon = self._class_icon(class_id)
            if not icon.isNull():
                class_item.setIcon(icon)
            self.stats_breakdown.setItem(row, 0, class_item)
            total = int(group.get("finished", 0))
            first_group = group.get("first", {})
            first_group = first_group if isinstance(first_group, dict) else {}
            second_group = group.get("second", {})
            second_group = second_group if isinstance(second_group, dict) else {}
            first_total = int(first_group.get("finished", 0))
            first_rate = first_total * 100 / total if total else 0.0
            self.stats_breakdown.setItem(row, 1, QTableWidgetItem(str(total)))
            self.stats_breakdown.setItem(row, 2, QTableWidgetItem(f"{float(first_group.get('win_rate', 0.0)):.1f}%"))
            self.stats_breakdown.setItem(row, 3, QTableWidgetItem(f"{float(second_group.get('win_rate', 0.0)):.1f}%"))
            self.stats_breakdown.setItem(row, 4, QTableWidgetItem(f"{first_rate:.1f}%"))

        records = [
            record for record in self._history.records
            if (filter_key is None or record.deck_key == filter_key)
            and (opponent_filter is None or record.opponent_class == opponent_filter)
            and record.result in {"胜利", "失败"}
        ]
        self.match_table.blockSignals(True)
        self.match_table.setRowCount(0)
        for record in reversed(records):
            row = self.match_table.rowCount(); self.match_table.insertRow(row)
            values = (
                record.deck_name,
                record.opponent_class,
                self._canonical_meta_deck_label(record.opponent_deck_name) or "（双击输入）",
                "先手" if record.is_first is True else "后手" if record.is_first is False else "未知",
                str(record.turn or "—"),
                format_timestamp_local(record.timestamp),
                record.result,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsEditable
                    if column == 2
                    else item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                item.setData(Qt.ItemDataRole.UserRole, record.match_id)
                if column == 0:
                    deck = next((deck for deck in self._repository.decks if deck.key == record.deck_key), None)
                    icon = self._class_icon(deck.class_id if deck else record.self_class_id)
                    if not icon.isNull():
                        item.setIcon(icon)
                elif column == 2:
                    icon = self._class_icon(record.opponent_class_id)
                    if not icon.isNull():
                        item.setIcon(icon)
                self.match_table.setItem(row, column, item)
        self.match_table.blockSignals(False)

    def _on_match_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 2:
            return
        match_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(match_id, str) or not match_id:
            return
        value = item.text().strip()
        if value == "（双击输入）":
            value = ""
        self._history.update_opponent_deck(match_id, value)

    def _reset_stats(self) -> None:
        filter_key = self._stats_filter_key()
        if filter_key is None:
            if not self._history.records:
                self._show_info("重置胜率", "当前没有可重置的对局记录。")
                return
            answer = QMessageBox.question(
                self,
                "重置所有卡组统计",
                "确定要删除所有卡组的本地胜负统计吗？\n此操作不可撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._history.clear_all()
            self._refresh_stats_page()
            self._update_header_stats()
            return
        deck = next((deck for deck in self._repository.decks if deck.key == filter_key), None)
        if deck is None:
            return
        answer = QMessageBox.question(self, "重置胜率", f"删除“{deck.name}”的本地胜负记录？")
        if answer != QMessageBox.StandardButton.Yes: return
        self._history.clear_deck(filter_key); self._refresh_stats_page(); self._update_header_stats()

    # ----- formatting helpers and small dialogs --------------------------------

    def _canonical_meta_deck_label(self, value: object) -> str:
        """Collapse cached build/sample names to the website archetype label."""
        clean = str(value or "").strip()
        if not clean or clean == "（双击输入）":
            return clean
        lowered = clean.casefold()
        for profile in self._meta_profiles:
            known = {str(profile.name or "").strip(), str(profile.profile_id or "").strip()}
            if clean in known or lowered in {item.casefold() for item in known if item}:
                return profile.display_name
        return clean

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
