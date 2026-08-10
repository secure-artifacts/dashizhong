from __future__ import annotations

import datetime
import uuid
import os
import sys
from PyQt6.QtCore import Qt, QTimer, QPoint, QTime, QSize
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QIcon, QFontDatabase, QMouseEvent, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,

    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QTabWidget,
    QStackedWidget,
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTimeEdit,
    QCheckBox,
    QGridLayout,
    QSizePolicy,
    QAbstractItemView,
    QCompleter,
)
import pytz

from alarm_sounds import RINGTONES, ensure_ringtones, play_ringtone, stop_ringtone


def style_combo_popup(combo: QComboBox) -> None:
    view = combo.view()
    if view:
        view.setStyleSheet("""
            QAbstractItemView {
                background-color: #0d1b2a !important;
                color: #ffffff !important;
                selection-background-color: #0284c7 !important;
                selection-color: #ffffff !important;
                border: 1px solid #00e5ff !important;
                outline: none !important;
                padding: 4px !important;
            }
            QAbstractItemView::item {
                min-height: 28px !important;
                padding: 6px 12px !important;
                color: #ffffff !important;
                background-color: #0d1b2a !important;
            }
            QAbstractItemView::item:hover {
                background-color: #0284c7 !important;
                color: #ffffff !important;
            }
            QAbstractItemView::item:selected {
                background-color: #0284c7 !important;
                color: #ffffff !important;
            }
        """)


COUNTRY_NAMES_ZH = {
    "AE": "阿拉伯联合酋长国", "AR": "阿根廷", "AT": "奥地利", "AU": "澳大利亚",
    "BE": "比利时", "BR": "巴西", "CA": "加拿大", "CH": "瑞士", "CL": "智利",
    "CN": "中国", "CO": "哥伦比亚", "CZ": "捷克", "DE": "德国", "DK": "丹麦",
    "EG": "埃及", "ES": "西班牙", "FI": "芬兰", "FR": "法国", "GB": "英国", "GR": "希腊",
    "HK": "中国香港", "HU": "匈牙利", "ID": "印度尼西亚", "IE": "爱尔兰",
    "IL": "以色列", "IN": "印度", "IT": "意大利", "JP": "日本", "KE": "肯尼亚", "KR": "韩国",
    "MO": "中国澳门", "MX": "墨西哥", "MY": "马来西亚", "NG": "尼日利亚",
    "NL": "荷兰", "NO": "挪威", "NZ": "新西兰", "PE": "秘鲁", "PH": "菲律宾", "PK": "巴基斯坦",
    "PL": "波兰", "PT": "葡萄牙", "RO": "罗马尼亚", "RU": "俄罗斯", "SA": "沙特阿拉伯",
    "SE": "瑞典", "SG": "新加坡", "TH": "泰国", "TR": "土耳其", "TW": "中国台湾",
    "UA": "乌克兰", "US": "美国", "VN": "越南", "ZA": "南非",
}


def timezone_country_choices() -> list[tuple[str, str]]:
    """All pytz country zones, labelled by country/region and representative city."""
    choices: list[tuple[str, str]] = [("协调世界时 · UTC", "UTC")]
    for code, zones in pytz.country_timezones.items():
        fallback = str(pytz.country_names.get(code, code))
        country = COUNTRY_NAMES_ZH.get(code, fallback)
        for zone in zones:
            city = zone.split("/")[-1].replace("_", " ")
            choices.append((f"{country}（{code}） · {city}", zone))
    return sorted(choices, key=lambda item: item[0].casefold())

class ClockWidget(QWidget):
    def __init__(self, tz_name: str, display_name: str = "", on_remove=None, parent=None):
        super().__init__(parent)
        self.tz_name = tz_name
        self.tz = pytz.timezone(tz_name)
        self.setObjectName("clockCard")
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.name_label = QLabel(display_name or tz_name.split("/")[-1].replace("_", " "))
        self.name_label.setStyleSheet("color: #00e5ff; font-size: 13px; font-weight: bold;")
        self.name_label.setWordWrap(True)
        remove_btn = QPushButton("×")
        remove_btn.setObjectName("removeClock")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("移除这个世界时钟")
        if callable(on_remove):
            remove_btn.clicked.connect(lambda: on_remove(self))
        header.addWidget(self.name_label, 1)
        header.addWidget(remove_btn)
        
        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet("color: #ffffff; font-size: 28px; font-family: 'DS-Digital', monospace; letter-spacing: 2px;")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.date_label = QLabel("YYYY-MM-DD")
        self.date_label.setStyleSheet("color: #a3a3a3; font-size: 12px;")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.diff_label = QLabel("+0h")
        self.diff_label.setStyleSheet("color: #00e5ff; font-size: 11px;")
        self.diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.layout.addLayout(header)
        self.layout.addWidget(self.time_label)
        self.layout.addWidget(self.date_label)
        self.layout.addWidget(self.diff_label)
        
        self.setStyleSheet("""
            QWidget#clockCard { background: rgba(0, 229, 255, 0.05); border: 1px solid rgba(0, 229, 255, 0.1); border-radius: 8px; }
            QWidget#clockCard QLabel { background: transparent; border: none; }
            QPushButton#removeClock { background: transparent; color: #6f8b99; border: none; border-radius: 6px; font-size: 16px; padding: 0; }
            QPushButton#removeClock:hover { background: rgba(255,80,80,0.18); color: #ff8a8a; }
        """)
        
    def update_time(self, local_now: datetime.datetime):
        now_tz = local_now.astimezone(self.tz)
        self.time_label.setText(now_tz.strftime("%H:%M:%S"))
        self.date_label.setText(f"{now_tz.year}年{now_tz.month}月{now_tz.day}日")
        
        diff = (now_tz.utcoffset() - local_now.astimezone().utcoffset()).total_seconds() / 3600
        sign = "+" if diff >= 0 else ""
        self.diff_label.setText(f"{sign}{diff:g}h (与本地时差)")


class _ResizeHandle(QWidget):
    """Reliable manual resize zone for a frameless top-level window."""

    def __init__(self, host: QWidget, edges, cursor) -> None:
        super().__init__(host)
        self._host = host
        self._edges = edges
        self._press_global = None
        self._start_geometry = None
        self.setCursor(cursor)
        self.setMouseTracking(True)
        # A nearly invisible painted pixel keeps the edge hit-testable on a
        # translucent, frameless Windows window.
        self.setStyleSheet("background: rgba(255,255,255,2); border: none;")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._start_geometry = self._host.geometry()
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._press_global is None or self._start_geometry is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        start = self._start_geometry
        min_w = max(180, self._host.minimumWidth())
        min_h = max(90, self._host.minimumHeight())
        x, y, width, height = start.x(), start.y(), start.width(), start.height()

        if self._edges & Qt.Edge.LeftEdge:
            right_edge = start.x() + start.width()
            x = min(start.x() + delta.x(), right_edge - min_w)
            width = right_edge - x
        elif self._edges & Qt.Edge.RightEdge:
            width = max(min_w, start.width() + delta.x())
        if self._edges & Qt.Edge.TopEdge:
            bottom_edge = start.y() + start.height()
            y = min(start.y() + delta.y(), bottom_edge - min_h)
            height = bottom_edge - y
        elif self._edges & Qt.Edge.BottomEdge:
            height = max(min_h, start.height() + delta.y())

        self._host.setGeometry(x, y, width, height)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_global = None
        self._start_geometry = None
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        event.accept()


class FloatingWorldClock(QWidget):
    def __init__(self, state_dict: dict, host=None, parent=None):
        super().__init__(parent)
        self.state_dict = state_dict
        self.host = host
        
        # Load custom digital font
        font_root = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
        font_path = os.path.join(font_root, "assets", "fonts", "DS-DIGI.TTF")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)

        self.is_pinned = True
        self._drag_pos = None

        # Set window flags FIRST, without calling show() yet
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(680, 430)
        self.setMinimumSize(220, 100)
        self.setMouseTracking(True)
        self._drag_pos = None
        self._resize_dir = None
        self._resize_start_global = None
        self._resize_start_geom = None
        self._resize_handles: list[_ResizeHandle] = []
        self._clock_font_px = 0
        self._place_top_right()
        
        self.main_layout = QVBoxLayout(self)
        # Keep the painted panel on the actual window edge. Transparent outer
        # margins make frameless windows impossible to hit with the mouse on
        # some Windows/DPI combinations.
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_widget = QFrame()
        self.bg_widget.setObjectName("bg_widget")
        # autoFillBackground is REQUIRED for QFrame to paint its CSS background
        # inside a WA_TranslucentBackground parent window
        self.bg_widget.setAutoFillBackground(False)
        self.bg_widget.setStyleSheet("""
            QFrame#bg_widget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141c2b, stop:0.5 #0d1522, stop:1 #060b13);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
            QFrame#bg_widget QLabel {
                color: #ffffff;
            }
            QFrame#bg_widget QCheckBox {
                color: #ffffff;
            }
            QFrame#timeHero {
                background: qradialgradient(cx:0.5, cy:0.4, radius:0.8, fx:0.5, fy:0.4, stop:0 #091322, stop:1 #03070f);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 12px;
            }
            QFrame#detailsPanel {
                background: rgba(8, 18, 25, 0.96);
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 12px;
            }
            QSpinBox, QComboBox, QLineEdit, QTimeEdit, QListWidget {
                background: #020617; color: #f8fafc;
                border: 1px solid #00e5ff; border-radius: 6px;
                padding: 4px; min-height: 28px; font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1b2a;
                color: #ffffff;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                border: 1px solid #00e5ff;
                outline: none;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 6px 10px;
                color: #ffffff;
                background-color: #0d1b2a;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #0369a1;
                color: #ffffff;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { width: 10px; height: 10px; }
            QListWidget::item { padding: 8px; border-radius: 6px; margin: 2px; background: rgba(0,0,0,0.5); border: 1px solid rgba(0,229,255,0.1); color: #f8fafc; }
            QListWidget::item:selected { background: rgba(0,229,255,0.2); border: 1px solid #00e5ff; }
            QPushButton {
                background: rgba(0, 229, 255, 0.15); color: #00e5ff; border: 1px solid #00e5ff;
                font-weight: bold; font-size: 12px; padding: 6px 12px; border-radius: 6px;
            }
            QPushButton:hover { background: rgba(0, 229, 255, 0.3); color: #ffffff; }
            QPushButton#sectionButton {
                background: transparent; color: #8ea6b4;
                border: none; border-radius: 8px; padding: 7px 12px;
                font-size: 12px; font-weight: 700;
            }
            QPushButton#sectionButton:hover { background: rgba(56,189,248,0.10); color: #e0f2fe; }
            QPushButton#sectionButton:checked { background: rgba(56,189,248,0.16); color: #67e8f9; }
            QPushButton#overlayButton {
                background: rgba(255, 255, 255, 0.08); color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 2px 6px;
                font-size: 12px; font-weight: 800;
            }
            QPushButton#overlayButton:hover { background: rgba(56, 189, 248, 0.25); color: #ffffff; }
            QPushButton#windowButton {
                background: transparent; border: none; border-radius: 8px;
                color: #94a3b8; padding: 0; font-size: 16px; font-weight: 700;
            }
            QPushButton#windowButton:hover { background: rgba(148,163,184,0.16); color: #ffffff; }
            QPushButton#closeButton {
                background: transparent; border: none; border-radius: 8px;
                color: #94a3b8; padding: 0; font-size: 19px; font-weight: 500;
            }
            QPushButton#closeButton:hover { background: #c42b1c; color: #ffffff; }
            QPushButton#danger {
                background: rgba(255, 0, 60, 0.15); color: #ff003c; border: 1px solid #ff003c;
            }
            QPushButton#danger:hover { background: rgba(255, 0, 60, 0.3); color: #ffffff; }
        """)
        self.bg_layout = QVBoxLayout(self.bg_widget)
        self.bg_layout.setContentsMargins(3, 3, 3, 3)
        self.bg_layout.setSpacing(4)
        
        self.time_hero = self._build_time_hero()
        self.bg_layout.addWidget(self.time_hero, stretch=1)

        self.feature_toggle_btn = QPushButton("\u25BC")
        self.feature_toggle_btn.setParent(self.time_hero)
        self.feature_toggle_btn.setObjectName("overlayButton")
        self.feature_toggle_btn.setFixedSize(28, 22)
        self.feature_toggle_btn.setToolTip("快捷功能菜单")
        self.feature_toggle_btn.clicked.connect(self._toggle_feature_menu)

        self.feature_menu = QWidget()
        section_row = QHBoxLayout(self.feature_menu)
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(6)
        self.section_buttons = []
        for index, text in enumerate(("世界时钟", "闹钟", "倒计时")):
            btn = QPushButton(f"{text}  ›")
            btn.setObjectName("sectionButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, i=index: self._toggle_details(i))
            section_row.addWidget(btn)
            self.section_buttons.append(btn)
        section_row.addStretch(1)

        self.pin_btn = QPushButton()
        self.pin_btn.setObjectName("windowButton")
        self.pin_btn.setFixedSize(30, 28)
        self.pin_btn.setToolTip("置顶/取消置顶")
        self._set_pin_style()
        self.pin_btn.clicked.connect(self.toggle_pin)
        section_row.addWidget(self.pin_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(30, 28)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.hide)
        section_row.addWidget(close_btn)

        self.feature_menu.hide()
        self.bg_layout.addWidget(self.feature_menu)

        self._timezone_labels: dict[str, str] = {}
        self.details_panel = QFrame(objectName="detailsPanel")
        details_layout = QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(8, 8, 8, 8)
        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self._build_clock_tab())
        self.detail_stack.addWidget(self._build_alarm_tab())
        self.detail_stack.addWidget(self._build_timer_tab())
        details_layout.addWidget(self.detail_stack)
        self.details_panel.hide()
        self._expanded_index = -1
        self._collapsed_height = self.height()
        self.bg_layout.addWidget(self.details_panel, stretch=1)
        
        self.main_layout.addWidget(self.bg_widget, stretch=1)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(18, 18)
        self.resize_grip.setToolTip("拖动调整面板大小")
        self.resize_grip.setStyleSheet("QSizeGrip { background:transparent; border:none; }")
        self._create_resize_handles()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        
        self.clocks: list[ClockWidget] = []
        
        saved = self.state_dict.get("world_clock") or []
        for tz in saved:
            self.add_clock_by_name(tz, self._timezone_labels.get(str(tz), ""))
            
        self.tick()

    def _create_resize_handles(self) -> None:
        specs = (
            (Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeFDiagCursor),
            (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.LeftEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.RightEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeFDiagCursor),
        )
        self._resize_handles = [_ResizeHandle(self, edges, cursor) for edges, cursor in specs]
        self._place_resize_handles()

    def _place_resize_handles(self) -> None:
        if len(self._resize_handles) != 8:
            return
        rect = self.rect()
        left, top = rect.left(), rect.top()
        width, height = rect.width(), rect.height()
        edge, corner = 10, 16
        geometries = (
            (left, top + corner, edge, max(0, height - corner * 2)),
            (left + width - edge, top + corner, edge, max(0, height - corner * 2)),
            (left + corner, top, max(0, width - corner * 2), edge),
            (left + corner, top + height - edge, max(0, width - corner * 2), edge),
            (left, top, corner, corner),
            (left + width - corner, top, corner, corner),
            (left, top + height - corner, corner, corner),
            (left + width - corner, top + height - corner, corner, corner),
        )
        for handle, geometry in zip(self._resize_handles, geometries):
            handle.setGeometry(*geometry)
            handle.raise_()
        if hasattr(self, "resize_grip"):
            bg_rect = self.bg_widget.geometry()
            self.resize_grip.move(
                max(0, bg_rect.x() + bg_rect.width() - self.resize_grip.width() - 1),
                max(0, bg_rect.y() + bg_rect.height() - self.resize_grip.height() - 1),
            )
            self.resize_grip.raise_()
        if hasattr(self, "feature_toggle_btn"):
            self.feature_toggle_btn.move(14, 8)
            self.feature_toggle_btn.raise_()

    def _build_time_hero(self) -> QWidget:
        """Edge-to-edge giant HH:MM with a smaller live seconds display."""
        hero = QFrame(objectName="timeHero")
        hero.setMinimumHeight(60)
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(0, 0, 4, 2)
        layout.setSpacing(0)

        time_group = QWidget()
        time_group.setStyleSheet("background:transparent; border:none;")
        time_row = QHBoxLayout(time_group)
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(0)
        time_row.addStretch(1)

        self.local_time = QLabel("00:00")
        self.local_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.local_time.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.local_time.setStyleSheet(
            "color:#f8fdff; font-family:'DS-Digital','Consolas',monospace;"
            " font-weight:700; letter-spacing:0px;"
            " border:none; background:transparent;"
        )
        time_font = QFont("DS-Digital")
        time_font.setPixelSize(190)
        time_font.setBold(True)
        self.local_time.setFont(time_font)
        time_row.addWidget(self.local_time, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.local_seconds = QLabel(":00")
        self.local_seconds.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.local_seconds.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.local_seconds.setStyleSheet(
            "color:#7dd3fc; font-family:'DS-Digital','Consolas',monospace;"
            " font-weight:700; letter-spacing:0px; border:none; background:transparent;"
        )
        seconds_font = QFont("DS-Digital")
        seconds_font.setPixelSize(72)
        seconds_font.setBold(True)
        self.local_seconds.setFont(seconds_font)
        time_row.addWidget(
            self.local_seconds,
            alignment=Qt.AlignmentFlag.AlignBottom,
        )
        time_row.addStretch(1)
        layout.addWidget(time_group, stretch=1)

        self.local_date = QLabel("2026年08月04日星期二")
        self.local_date.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.local_date.setStyleSheet(
            "color:#7dd3fc; font-size:13px; font-weight:700; letter-spacing:1px;"
            " border:none; background:transparent;"
        )
        self.local_date.setFixedHeight(22)
        layout.addWidget(self.local_date)
        return hero

    def _toggle_feature_menu(self) -> None:
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(13, 22, 36, 0.96);
                color: #f8fafc;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 18px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
            }
            QMenu::item:selected {
                background: rgba(56, 189, 248, 0.22);
                color: #38bdf8;
            }
        """)

        def toggle_clock_details():
            visible = self.feature_menu.isHidden()
            self.feature_menu.setVisible(visible)

        actions = [
            ("⏰  闹钟 / 世界时钟 / 倒计时", toggle_clock_details),
            ("📋  待办事项", lambda: self.host.show_todos() if self.host else None),
            ("📝  便签", lambda: self.host.show_notes() if self.host else None),
            ("✂️  区域截图", lambda: self.host.start_screenshot_region() if self.host else None),
            ("🎥  屏幕录像", lambda: self.host.show_recorder_board() if self.host else None),
            ("🎬  视频播放器", lambda: self.host.show_media_player2() if self.host else None),
            ("🧹  电脑清理", lambda: self.host.start_deep_clean() if self.host else None),
        ]

        for text, slot in actions:
            act = QAction(text, menu)
            act.triggered.connect(slot)
            menu.addAction(act)

        menu.addSeparator()
        settings_action = QAction("⚙️  设置", menu)
        settings_action.triggered.connect(
            lambda: self.host.show_settings() if self.host else None
        )
        menu.addAction(settings_action)

        pos = self.feature_toggle_btn.mapToGlobal(QPoint(0, self.feature_toggle_btn.height() + 4))
        menu.exec(pos)

    def _place_top_right(self) -> None:
        scr = QGuiApplication.primaryScreen()
        if scr:
            geo = scr.availableGeometry()
            x = geo.right() - self.width() - 24
            y = geo.top() + 40
            self.move(max(geo.left(), x), max(geo.top(), y))

    def _fit_time_font(self) -> None:
        """Keep HH:MM huge while reserving compact room for live seconds."""
        if not hasattr(self, "time_hero") or not hasattr(self, "local_time"):
            return
        target = self.local_time.text() or "00:00"
        seconds_target = self.local_seconds.text() or ":00"
        area = self.time_hero.contentsRect()
        max_width = max(120, area.width() - 4)
        max_height = max(70, area.height() - self.local_date.height() - 2)
        low, high, best = 16, 320, 16
        while low <= high:
            pixel_size = (low + high) // 2
            font = QFont(self.local_time.font())
            font.setPixelSize(pixel_size)
            font.setBold(True)
            metrics = QFontMetrics(font)
            bounds = metrics.boundingRect(target)
            seconds_size = max(10, int(pixel_size * 0.38))
            seconds_font = QFont(self.local_seconds.font())
            seconds_font.setPixelSize(seconds_size)
            seconds_font.setBold(True)
            seconds_metrics = QFontMetrics(seconds_font)
            required_width = (
                metrics.horizontalAdvance(target)
                + seconds_metrics.horizontalAdvance(seconds_target)
            )
            if required_width <= max_width and bounds.height() <= max_height:
                best = pixel_size
                low = pixel_size + 1
            else:
                high = pixel_size - 1
        if best != self._clock_font_px:
            self._clock_font_px = best
            font = QFont(self.local_time.font())
            font.setPixelSize(best)
            font.setBold(True)
            self.local_time.setFont(font)
            seconds_font = QFont(self.local_seconds.font())
            seconds_font.setPixelSize(max(34, int(best * 0.38)))
            seconds_font.setBold(True)
            self.local_seconds.setFont(seconds_font)

    def _toggle_details(self, index: int) -> None:
        """Show one secondary feature at a time; clicking it again folds it."""
        if self._expanded_index == index and not self.details_panel.isHidden():
            self.details_panel.hide()
            self._expanded_index = -1
            for btn in self.section_buttons:
                btn.setChecked(False)
            self.feature_menu.hide()
            self.feature_toggle_btn.setText("\u25BC")
            self.resize(self.width(), max(self.minimumHeight(), self._collapsed_height))
            QTimer.singleShot(0, self._fit_time_font)
            return

        if self.details_panel.isHidden():
            self._collapsed_height = self.height()
        self._expanded_index = index
        self.detail_stack.setCurrentIndex(index)
        self.details_panel.show()
        self.feature_menu.hide()
        self.feature_toggle_btn.setText("\u25BC")
        for i, btn in enumerate(self.section_buttons):
            btn.setChecked(i == index)
        if self.height() < 610:
            self.resize(self.width(), 610)
        QTimer.singleShot(0, self._fit_time_font)
        if index == 1:
            # Existing alarms need the same adaptive space as alarms added in
            # the current session. Delay until the stacked page is laid out.
            QTimer.singleShot(0, self._grow_for_alarm_count)

    def _build_clock_tab(self):
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        hint = QLabel("按国家/地区和城市添加 · 时差会自动与电脑本地时间对比")
        hint.setStyleSheet(
            "color:#9db4c0; font-size:12px; font-weight:700; border:none; background:transparent;"
        )
        lay.addWidget(hint)

        self.accordion_widget = QWidget()
        self.accordion_layout = QVBoxLayout(self.accordion_widget)
        self.accordion_layout.setContentsMargins(0, 4, 0, 0)
        
        control_layout = QHBoxLayout()
        self.tz_combo = QComboBox()
        self.tz_combo.setEditable(True)
        self.tz_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for label, zone in timezone_country_choices():
            self.tz_combo.addItem(label, zone)
            self._timezone_labels.setdefault(zone, label)
        style_combo_popup(self.tz_combo)
        self.tz_combo.setCurrentIndex(-1)
        self.tz_combo.lineEdit().setPlaceholderText("输入国家、地区或城市搜索…")
        completer = self.tz_combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        
        add_btn = QPushButton("＋ 添加")
        add_btn.setMinimumWidth(72)
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self.add_clock)
        
        control_layout.addWidget(self.tz_combo)
        control_layout.addWidget(add_btn)
        self.accordion_layout.addLayout(control_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.clocks_container = QWidget()
        self.clocks_layout = QVBoxLayout(self.clocks_container)
        self.clocks_layout.setContentsMargins(0, 5, 0, 0)
        self.clocks_layout.setSpacing(10)
        self.clocks_layout.addStretch()
        
        self.scroll.setWidget(self.clocks_container)
        self.accordion_layout.addWidget(self.scroll, stretch=1)
        
        lay.addWidget(self.accordion_widget, stretch=1)
        return w

    def _build_alarm_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(10, 12, 10, 8)

        self.list_alarms = QListWidget()
        self.list_alarms.setMinimumHeight(160)
        self.list_alarms.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lay.addWidget(self.list_alarms, stretch=1)

        form = QGridLayout()
        form.addWidget(QLabel("时间"), 0, 0)
        self.time_alarm = QTimeEdit(QTime.currentTime())
        self.time_alarm.setDisplayFormat("HH:mm")
        form.addWidget(self.time_alarm, 0, 1)
        
        form.addWidget(QLabel("重复"), 0, 2)
        self.cmb_alarm_repeat = QComboBox()
        self.cmb_alarm_repeat.addItems(["仅一次", "每天"])
        style_combo_popup(self.cmb_alarm_repeat)
        form.addWidget(self.cmb_alarm_repeat, 0, 3)
        
        form.addWidget(QLabel("备注"), 1, 0)
        self.txt_alarm_name = QLineEdit()
        self.txt_alarm_name.setPlaceholderText("例如：起床、吃药")
        form.addWidget(self.txt_alarm_name, 1, 1, 1, 3)
        
        form.addWidget(QLabel("铃声"), 2, 0)
        self.cmb_alarm_ring = QComboBox()
        ensure_ringtones()
        for rid, name in RINGTONES:
            self.cmb_alarm_ring.addItem(name, rid)
        style_combo_popup(self.cmb_alarm_ring)
        form.addWidget(self.cmb_alarm_ring, 2, 1, 1, 2)
        
        btn_prev2 = QPushButton("试听")
        btn_prev2.clicked.connect(lambda: play_ringtone(self.cmb_alarm_ring.currentData() or "beep"))
        form.addWidget(btn_prev2, 2, 3)
        lay.addLayout(form)

        self.chk_alarm_tts = QCheckBox("响铃同时语音播报备注")
        self.chk_alarm_tts.setChecked(True)
        lay.addWidget(self.chk_alarm_tts)

        btns = QHBoxLayout()
        self.btn_alarm_add = QPushButton("＋ 添加闹钟")
        self.btn_alarm_add.clicked.connect(self._add_alarm)
        self.btn_alarm_del = QPushButton("删除选中")
        self.btn_alarm_del.setObjectName("danger")
        self.btn_alarm_del.clicked.connect(self._delete_alarm)
        btns.addWidget(self.btn_alarm_add)
        btns.addWidget(self.btn_alarm_del)
        lay.addLayout(btns)
        
        self._refresh_alarm_list()
        scroll.setWidget(w)
        return scroll

    def _build_timer_tab(self):
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        lay.setContentsMargins(10, 12, 10, 8)

        self.lbl_timer_display = QLabel("00:00:00")
        self.lbl_timer_display.setStyleSheet("color: #00e5ff; font-size: 50px; font-family: 'DS-Digital', monospace; font-weight: bold; text-shadow: 0 0 10px #00e5ff;")
        self.lbl_timer_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_timer_display)

        inputs = QHBoxLayout()
        self.spin_h = QSpinBox()
        self.spin_h.setRange(0, 23)
        self.spin_h.setSuffix(" 时")
        self.spin_m = QSpinBox()
        self.spin_m.setRange(0, 59)
        self.spin_m.setSuffix(" 分")
        self.spin_m.setValue(5)
        self.spin_s = QSpinBox()
        self.spin_s.setRange(0, 59)
        self.spin_s.setSuffix(" 秒")
        for s in (self.spin_h, self.spin_m, self.spin_s):
            inputs.addWidget(s)
        lay.addLayout(inputs)

        self.txt_timer_name = QLineEdit()
        self.txt_timer_name.setPlaceholderText("提示文字，例如：烧水、小憩")
        lay.addWidget(self.txt_timer_name)

        ring_row = QHBoxLayout()
        ring_row.addWidget(QLabel("铃声"))
        self.cmb_timer_ring = QComboBox()
        for rid, name in RINGTONES:
            self.cmb_timer_ring.addItem(name, rid)
        style_combo_popup(self.cmb_timer_ring)
        btn_preview = QPushButton("试听")
        btn_preview.clicked.connect(lambda: play_ringtone(self.cmb_timer_ring.currentData() or "beep"))
        ring_row.addWidget(self.cmb_timer_ring, 1)
        ring_row.addWidget(btn_preview)
        lay.addLayout(ring_row)

        self.chk_timer_tts = QCheckBox("结束时语音播报")
        self.chk_timer_tts.setChecked(True)
        lay.addWidget(self.chk_timer_tts)

        btns = QHBoxLayout()
        self.btn_timer_start = QPushButton("▶ 开始")
        self.btn_timer_start.clicked.connect(self._start_timer)
        self.btn_timer_pause = QPushButton("⏸ 暂停")
        self.btn_timer_pause.clicked.connect(self._pause_timer)
        self.btn_timer_pause.setEnabled(False)
        self.btn_timer_reset = QPushButton("重置")
        self.btn_timer_reset.setObjectName("danger")
        self.btn_timer_reset.clicked.connect(self._reset_timer)
        btns.addWidget(self.btn_timer_start)
        btns.addWidget(self.btn_timer_pause)
        btns.addWidget(self.btn_timer_reset)
        lay.addLayout(btns)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_timer_ui)
        self.refresh_timer.start(500)
        return w

    def _set_pin_style(self):
        if self.is_pinned:
            self.pin_btn.setText("◆")
            self.pin_btn.setToolTip("已置顶，点击取消")
            self.pin_btn.setStyleSheet(
                "QPushButton { background:rgba(56,189,248,0.14); border:none; border-radius:8px;"
                " color:#67e8f9; font-size:13px; }"
                "QPushButton:hover { background:rgba(56,189,248,0.25); color:#ffffff; }"
            )
        else:
            self.pin_btn.setText("◇")
            self.pin_btn.setToolTip("置顶")
            self.pin_btn.setStyleSheet(
                "QPushButton { background:transparent; border:none; border-radius:8px;"
                " color:#78909c; font-size:14px; }"
                "QPushButton:hover { background:rgba(148,163,184,0.16); color:#ffffff; }"
            )

    def _update_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.is_pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # Only re-show if window was already visible (changing flags hides it)
        if self.isVisible():
            self.show()
        
    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self._set_pin_style()
        self._update_window_flags()

    def toggle_accordion(self):
        if self.accordion_widget.isHidden():
            self.accordion_widget.show()
            if hasattr(self, "toggle_btn"):
                self.toggle_btn.setText("▲ 收起其他时区")
        else:
            self.accordion_widget.hide()
            if hasattr(self, "toggle_btn"):
                self.toggle_btn.setText("▼ 展开其他时区")
            
    def tick(self):
        now = datetime.datetime.now().astimezone()
        weekdays_cn = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        time_text = now.strftime("%H:%M")
        if self.local_time.text() != time_text:
            self.local_time.setText(time_text)
            QTimer.singleShot(0, self._fit_time_font)
        self.local_seconds.setText(now.strftime(":%S"))
        self.local_date.setText(
            f"{now.year:04d}年{now.month:02d}月{now.day:02d}日{weekdays_cn[now.weekday()]}"
        )
        
        now_utc = datetime.datetime.now(datetime.timezone.utc).astimezone()
        for cw in self.clocks:
            cw.update_time(now_utc)
            
    def add_clock(self):
        index = self.tz_combo.currentIndex()
        tz = self.tz_combo.itemData(index) if index >= 0 else None
        if not tz:
            typed = self.tz_combo.currentText().strip()
            exact = self.tz_combo.findText(typed, Qt.MatchFlag.MatchExactly)
            if exact >= 0:
                index = exact
                tz = self.tz_combo.itemData(exact)
        if not tz:
            self.tz_combo.setFocus()
            self.tz_combo.lineEdit().selectAll()
            return
        display = self.tz_combo.itemText(index)
        self.add_clock_by_name(str(tz), display)
        self.state_dict["world_clock"] = [cw.tz_name for cw in self.clocks]
        self.tz_combo.setCurrentIndex(-1)
        self.tz_combo.clearEditText()
        
    def add_clock_by_name(self, tz_name: str, display_name: str = ""):
        if any(cw.tz_name == tz_name for cw in self.clocks):
            return
        if tz_name not in pytz.all_timezones_set:
            return
        cw = ClockWidget(
            tz_name,
            display_name or self._timezone_labels.get(tz_name, ""),
            on_remove=self._remove_clock,
        )
        self.clocks.append(cw)
        self.clocks_layout.insertWidget(self.clocks_layout.count() - 1, cw)
        self.tick()

    def _remove_clock(self, clock: ClockWidget) -> None:
        if clock not in self.clocks:
            return
        self.clocks.remove(clock)
        self.clocks_layout.removeWidget(clock)
        clock.deleteLater()
        self.state_dict["world_clock"] = [cw.tz_name for cw in self.clocks]

    def _add_alarm(self):
        time_str = self.time_alarm.time().toString("HH:mm")
        name = self.txt_alarm_name.text().strip() or "闹钟"
        repeat = "once" if self.cmb_alarm_repeat.currentIndex() == 0 else "daily"
        alarm = {
            "id": str(uuid.uuid4())[:8],
            "time": time_str,
            "name": name,
            "repeat": repeat,
            "enabled": True,
            "ringtone": self.cmb_alarm_ring.currentData() or "beep",
            "tts": bool(self.chk_alarm_tts.isChecked()),
            "last_triggered_date": "",
        }
        self.state_dict.setdefault("alarms", []).append(alarm)
        self._refresh_alarm_list(select_id=alarm["id"])
        self._grow_for_alarm_count()
        self.txt_alarm_name.clear()

    def _delete_alarm(self):
        curr = self.list_alarms.currentItem()
        if not curr: return
        alarm_id = curr.data(Qt.ItemDataRole.UserRole)
        self.state_dict["alarms"] = [a for a in (self.state_dict.get("alarms") or []) if a.get("id") != alarm_id]
        self._refresh_alarm_list()

    def _refresh_alarm_list(self, select_id: str | None = None):
        self.list_alarms.clear()
        name_map = {rid: name for rid, name in RINGTONES}
        selected_item = None
        for a in self.state_dict.get("alarms") or []:
            rep = "每天" if a.get("repeat") == "daily" else "仅一次"
            st = "已开启" if a.get("enabled") else "已关闭"
            ring = name_map.get(str(a.get("ringtone") or "beep"), "经典哔哔")
            text = f"⏰ {a.get('time')}  ·  {rep}  ·  {a.get('name')}\n   铃声：{ring}  ·  状态：{st}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, a.get("id"))
            item.setSizeHint(QSize(0, 58))
            self.list_alarms.addItem(item)
            if select_id and a.get("id") == select_id:
                selected_item = item
        if self.list_alarms.count() == 0:
            empty = QListWidgetItem("（还没有闹钟，请在下方添加）")
            empty.setSizeHint(QSize(0, 44))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_alarms.addItem(empty)
        elif selected_item is not None:
            self.list_alarms.setCurrentItem(selected_item)
            self.list_alarms.scrollToItem(
                selected_item,
                QAbstractItemView.ScrollHint.EnsureVisible,
            )
            QTimer.singleShot(
                0,
                lambda item=selected_item: self.list_alarms.scrollToItem(
                    item, QAbstractItemView.ScrollHint.EnsureVisible
                ),
            )
        alarm_count = len(self.state_dict.get("alarms") or [])
        self.list_alarms.setMinimumHeight(min(334, max(160, alarm_count * 62 + 16)))
        self.list_alarms.setMaximumHeight(360)

    def _grow_for_alarm_count(self) -> None:
        """Give newly added alarms visible room, then rely on list scrolling."""
        count = len(self.state_dict.get("alarms") or [])
        list_height = min(334, max(160, count * 62 + 16))
        self.list_alarms.setMinimumHeight(list_height)
        self.list_alarms.setMaximumHeight(360)
        if not self.isVisible() or self._expanded_index != 1:
            return
        screen = self.screen()
        max_height = screen.availableGeometry().height() - 32 if screen else 860
        extra = min(3, max(0, count - 1)) * 62
        target = min(max_height, max(self.height(), 610 + extra))
        if target > self.height():
            self.resize(self.width(), target)

    def _update_timer_ui(self):
        t_cfg = self.state_dict.get("timer") or {}
        active = bool(t_cfg.get("active"))
        rem = int(t_cfg.get("remaining") or 0)
        h, m, s = rem // 3600, (rem % 3600) // 60, rem % 60
        self.lbl_timer_display.setText(f"{h:02d}:{m:02d}:{s:02d}")
        
        self.btn_timer_start.setEnabled(not active)
        self.btn_timer_pause.setEnabled(active or bool(t_cfg.get("paused")))
        if active:
            self.btn_timer_pause.setText("⏸ 继续" if t_cfg.get("paused") else "⏸ 暂停")
        else:
            self.btn_timer_pause.setText("⏸ 暂停")

    def _start_timer(self):
        t_cfg = self.state_dict.setdefault("timer", {})
        total = self.spin_h.value() * 3600 + self.spin_m.value() * 60 + self.spin_s.value()
        if total <= 0: return
        t_cfg["active"] = True
        t_cfg["remaining"] = total
        t_cfg["label"] = self.txt_timer_name.text().strip() or "倒计时"
        t_cfg["paused"] = False
        t_cfg["ringtone"] = self.cmb_timer_ring.currentData() or "beep"
        t_cfg["tts"] = bool(self.chk_timer_tts.isChecked())
        self._update_timer_ui()

    def _pause_timer(self):
        t_cfg = self.state_dict.setdefault("timer", {})
        if t_cfg.get("active"):
            t_cfg["active"] = False
            t_cfg["paused"] = True
        elif t_cfg.get("paused") and int(t_cfg.get("remaining") or 0) > 0:
            t_cfg["active"] = True
            t_cfg["paused"] = False
        self._update_timer_ui()

    def _reset_timer(self):
        t_cfg = self.state_dict.setdefault("timer", {})
        t_cfg["active"] = False
        t_cfg["remaining"] = 0
        t_cfg["paused"] = False
        stop_ringtone()
        self._update_timer_ui()

    # ── Resize / drag edge detection ──────────────────────────────────────
    def resizeEvent(self, event):
        """Scale the clock face with the window without clipping the digits."""
        self._place_resize_handles()
        super().resizeEvent(event)
        if hasattr(self, "local_time"):
            self._fit_time_font()
            QTimer.singleShot(0, self._fit_time_font)

    _EDGE = 8  # px from edge = resize zone

    def _get_resize_edges(self, pos):
        """Return (left, right, top, bottom) booleans for resize edges."""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        e = self._EDGE
        return (
            x < e,          # left
            x > w - e,      # right
            y < e,          # top
            y > h - e,      # bottom
        )

    def _cursor_for_edges(self, left, right, top, bottom):
        from PyQt6.QtCore import Qt as _Qt
        if (left and top) or (right and bottom):
            return _Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return _Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return _Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return _Qt.CursorShape.SizeVerCursor
        return _Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            left, right, top, bottom = self._get_resize_edges(pos)
            if any((left, right, top, bottom)):
                # Start resize
                self._resize_dir = (left, right, top, bottom)
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                self._drag_pos = None
            else:
                # Start drag-to-move
                self._drag_pos = event.globalPosition().toPoint()
                self._resize_dir = None
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self._resize_dir is not None:
                # Handle resize
                left, right, top, bottom = self._resize_dir
                gpos = event.globalPosition().toPoint()
                dx = gpos.x() - self._resize_start_global.x()
                dy = gpos.y() - self._resize_start_global.y()
                r = self._resize_start_geom
                new_x, new_y = r.x(), r.y()
                new_w, new_h = r.width(), r.height()
                if left:
                    new_x = r.x() + dx
                    new_w = max(220, r.width() - dx)
                if right:
                    new_w = max(220, r.width() + dx)
                if top:
                    new_y = r.y() + dy
                    new_h = max(100, r.height() - dy)
                if bottom:
                    new_h = max(100, r.height() + dy)
                self.setGeometry(new_x, new_y, new_w, new_h)
            elif self._drag_pos is not None:
                # Handle move
                delta = event.globalPosition().toPoint() - self._drag_pos
                self.move(self.pos() + delta)
                self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            # Update cursor based on hover position
            left, right, top, bottom = self._get_resize_edges(pos)
            self.setCursor(self._cursor_for_edges(left, right, top, bottom))

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        self._resize_dir = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()


class AlarmRingingDialog(QDialog):
    """Mobile-like popup window for alarm ringing.
    Appears centered on desktop, rings continuously until user clicks '关闭闹钟'.
    """

    def __init__(self, alarm_data: dict, parent=None):
        super().__init__(parent)
        self.alarm_data = alarm_data
        self.setWindowTitle("闹钟提醒 - SuperTools")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(440, 260)

        scr = QGuiApplication.primaryScreen()
        if scr:
            geo = scr.availableGeometry()
            x = geo.left() + (geo.width() - 440) // 2
            y = geo.top() + (geo.height() - 260) // 2
            self.move(x, y)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #220819, stop:1 #0a0209);
                border: 2px solid #ff2a6d;
                border-radius: 16px;
            }
            QLabel { color: #ffffff; }
        """)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(24, 20, 24, 20)
        bl.setSpacing(10)

        top_row = QHBoxLayout()
        icon_lbl = QLabel("⏰ 闹钟响铃提醒")
        icon_lbl.setStyleSheet("color: #ff2a6d; font-size: 16px; font-weight: 800; border: none; background: transparent;")
        top_row.addWidget(icon_lbl, 1)
        bl.addLayout(top_row)

        alarm_time = str(self.alarm_data.get("time") or datetime.datetime.now().strftime("%H:%M"))
        lbl_time = QLabel(alarm_time)
        lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_time.setStyleSheet("""
            color: #ffffff;
            font-size: 52px;
            font-family: 'DS-Digital', 'Consolas', monospace;
            font-weight: 800;
            border: none;
            background: transparent;
        """)
        bl.addWidget(lbl_time)

        alarm_name = str(self.alarm_data.get("name") or "提醒时间已到")
        lbl_name = QLabel(alarm_name)
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_name.setStyleSheet("color: #ff85a2; font-size: 15px; font-weight: 700; border: none; background: transparent;")
        bl.addWidget(lbl_name)

        btn_dismiss = QPushButton("🔔  关闭闹钟  🔔")
        btn_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dismiss.setStyleSheet("""
            QPushButton {
                background: #ff2a6d;
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
                border: none;
                border-radius: 12px;
                min-height: 48px;
            }
            QPushButton:hover {
                background: #ff5288;
            }
            QPushButton:pressed {
                background: #d9004c;
            }
        """)
        btn_dismiss.clicked.connect(self.dismiss)
        bl.addWidget(btn_dismiss)

        layout.addWidget(box)

        # Start continuous looping ringtone
        ringtone_id = str(self.alarm_data.get("ringtone") or "beep")
        try:
            from alarm_sounds import play_ringtone
            play_ringtone(ringtone_id, loop=True)
        except Exception:
            pass

    def dismiss(self) -> None:
        try:
            from alarm_sounds import stop_ringtone
            stop_ringtone()
        except Exception:
            pass
        self.close()

    def closeEvent(self, event) -> None:
        try:
            from alarm_sounds import stop_ringtone
            stop_ringtone()
        except Exception:
            pass
        super().closeEvent(event)

    def reject(self) -> None:
        try:
            from alarm_sounds import stop_ringtone
            stop_ringtone()
        except Exception:
            pass
        super().reject()
