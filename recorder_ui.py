"""Floating screen recorder board with live preview."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import cv2
import numpy as np
import win32api
import win32con
import win32gui
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QObject, QSize, QModelIndex
from PyQt6.QtGui import QPainter, QPen, QColor, QImage, QPixmap, QMouseEvent, QPalette, QRegion
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from audio_monitor_ui import AudioMonitorPanel
from skin import get_app_version, make_version_badge
import screen_recorder


class _PreviewBridge(QObject):
    frame = pyqtSignal(object)  # numpy BGR
    status = pyqtSignal(str)
    finished = pyqtSignal(str)


class RecordingDrawOverlay(QWidget):
    """Draw layer over the capture region.

    Windows + WA_TranslucentBackground only delivers mouse events on *opaque*
    pixels, so a fully transparent overlay never receives strokes. In draw mode
    we paint a faint veil (non-zero alpha) so every drag is captured.
    """

    exit_requested = pyqtSignal()  # user closed draw mode from overlay UI

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.drawing = False
        self.last_point = QPoint()
        self.cursor_pos = QPoint(-100, -100)
        self.brush_color = QColor(239, 68, 68)
        self.brush_size = 8
        self.canvas_image: QImage | None = None
        self.overlay_rgba: np.ndarray | None = None
        self.is_draw_mode = False
        self.target_region: dict | None = None
        self.controls_window: QWidget | None = None
        self._exit_btn = QRect()  # close-draw button on overlay

        self.track_timer = QTimer(self)
        self.track_timer.timeout.connect(self._track_region)
        self.track_timer.start(100)

    def _make_pen_cursor(self) -> None:
        from PyQt6.QtGui import QCursor, QPixmap, QPainterPath

        size = 48
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(30, 30, 30), 2))
        p.setBrush(self.brush_color)
        path = QPainterPath()
        path.moveTo(8, 40)
        path.lineTo(14, 28)
        path.lineTo(34, 8)
        path.lineTo(40, 14)
        path.lineTo(20, 34)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(self.brush_color)
        p.drawEllipse(4, 38, 10, 10)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(4, 38, 10, 10)
        p.setPen(QPen(self.brush_color, 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = max(6, min(16, self.brush_size))
        p.drawEllipse(6 - r // 2, 40 - r // 2, r * 2, r * 2)
        p.end()
        self.setCursor(QCursor(pm, 8, 42))

    def _apply_input_mode(self) -> None:
        """Apply click-through to the native window as well as Qt widgets."""
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            ex = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
            ex |= WS_EX_LAYERED
            if self.is_draw_mode:
                ex &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            else:
                ex |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            win32gui.SetWindowLong(hwnd, GWL_EXSTYLE, ex)
            win32gui.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER
                | win32con.SWP_NOACTIVATE
                | win32con.SWP_FRAMECHANGED,
            )
        except Exception:
            pass

    def set_region(self, region: dict | None) -> None:
        self.target_region = dict(region) if region else None
        self._track_region()

    def set_draw_mode(self, enabled: bool) -> None:
        self.is_draw_mode = bool(enabled)
        if enabled:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self._track_region()
            self._ensure_canvas()
            self._make_pen_cursor()
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self._apply_input_mode()
            self.update()
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.drawing = False
            self.cursor_pos = QPoint(-100, -100)
            self._apply_input_mode()
            # Keep overlay visible (strokes) but click-through while not drawing
            self.update()

    def _ensure_canvas(self) -> None:
        w = max(2, self.width())
        h = max(2, self.height())
        need = (
            self.canvas_image is None
            or self.canvas_image.isNull()
            or self.canvas_image.width() != w
            or self.canvas_image.height() != h
        )
        if not need:
            return
        # Non-premultiplied ARGB is more predictable for stroke alpha
        new_img = QImage(w, h, QImage.Format.Format_ARGB32)
        new_img.fill(Qt.GlobalColor.transparent)
        if self.canvas_image is not None and not self.canvas_image.isNull():
            p = QPainter(new_img)
            p.drawImage(0, 0, self.canvas_image)
            p.end()
        self.canvas_image = new_img
        self._sync_rgba()

    def _track_region(self) -> None:
        r = self.target_region
        if not r:
            return
        try:
            hwnd = int(r.get("hwnd") or 0)
            if hwnd > 0 and win32gui.IsWindow(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                w, h = max(2, rect[2] - rect[0]), max(2, rect[3] - rect[1])
                self.target_region = {**r, "left": x, "top": y, "width": w, "height": h}
            else:
                x = int(r.get("left") or 0)
                y = int(r.get("top") or 0)
                w = max(2, int(r.get("width") or 100))
                h = max(2, int(r.get("height") or 100))
            geo = self.geometry()
            if geo.x() != x or geo.y() != y or geo.width() != w or geo.height() != h:
                self.setGeometry(x, y, w, h)
            self._ensure_canvas()
            # Leave a native hit-test hole for the recording buttons. Never
            # repeatedly raise the full-screen overlay above other windows.
            if self.is_draw_mode and self.controls_window and self.controls_window.isVisible():
                controls_rect = self.controls_window.frameGeometry()
                controls_rect.translate(-self.geometry().topLeft())
                self.setMask(QRegion(self.rect()).subtracted(QRegion(controls_rect.adjusted(-4, -4, 4, 4))))
            else:
                self.clearMask()
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ensure_canvas()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # CRITICAL: non-zero alpha veil so Windows hit-tests this window
        if self.is_draw_mode:
            p.fillRect(self.rect(), QColor(14, 165, 233, 36))
            p.setPen(QPen(QColor(56, 189, 248, 220), 3, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(2, 2, max(0, self.width() - 5), max(0, self.height() - 5))
            p.setPen(QColor(255, 255, 255, 240))
            p.setFont(self.font())
            p.drawText(14, 26, "✏️ 画笔模式 · 按住左键拖动画线 · 右键或点右上角关闭")
            # Exit button (always reachable even when covering full screen)
            bw, bh = 110, 34
            self._exit_btn = QRect(max(8, self.width() - bw - 12), 10, bw, bh)
            p.setBrush(QColor(220, 38, 38, 230))
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawRoundedRect(self._exit_btn, 8, 8)
            p.setPen(QColor(255, 255, 255))
            p.drawText(self._exit_btn, Qt.AlignmentFlag.AlignCenter, "关闭画笔")
        else:
            self._exit_btn = QRect()
        if self.canvas_image is not None and not self.canvas_image.isNull():
            p.drawImage(0, 0, self.canvas_image)
        if self.is_draw_mode and self.cursor_pos.x() >= 0:
            r = max(4, self.brush_size // 2 + 2)
            cx, cy = self.cursor_pos.x(), self.cursor_pos.y()
            p.setPen(QPen(QColor(255, 255, 255, 230), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPoint(cx, cy), r + 2, r + 2)
            col = QColor(self.brush_color)
            col.setAlpha(200)
            p.setPen(QPen(col, 2))
            p.setBrush(col)
            p.drawEllipse(QPoint(cx, cy), max(3, self.brush_size // 2), max(3, self.brush_size // 2))

    def _map_pos(self, event: QMouseEvent) -> QPoint:
        try:
            gp = event.globalPosition().toPoint()
            return self.mapFromGlobal(gp)
        except Exception:
            return event.position().toPoint()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.is_draw_mode:
            return
        pt = self._map_pos(event)
        self.cursor_pos = pt
        # Close button / right-click exits draw mode
        if event.button() == Qt.MouseButton.RightButton:
            self.exit_requested.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._exit_btn.contains(pt):
            self.exit_requested.emit()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._ensure_canvas()
        if self.canvas_image is None:
            return
        self.drawing = True
        self.last_point = pt
        p = QPainter(self.canvas_image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.brush_color)
        r = max(2, self.brush_size // 2)
        p.drawEllipse(pt, r, r)
        p.end()
        self._sync_rgba()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pt = self._map_pos(event)
        self.cursor_pos = pt
        if self.drawing and self.is_draw_mode:
            self._ensure_canvas()
            if self.canvas_image is not None:
                p = QPainter(self.canvas_image)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(
                    QPen(
                        self.brush_color,
                        max(1, self.brush_size),
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin,
                    )
                )
                p.drawLine(self.last_point, pt)
                p.end()
                self.last_point = pt
                self._sync_rgba()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
            self._sync_rgba()
            self.update()
            event.accept()

    def clear_canvas(self) -> None:
        if self.canvas_image is not None:
            self.canvas_image.fill(Qt.GlobalColor.transparent)
            self.update()
            self._sync_rgba()

    def _sync_rgba(self) -> None:
        if self.canvas_image is None or self.canvas_image.isNull():
            self.overlay_rgba = None
            return
        try:
            img = self.canvas_image.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            bpl = img.bytesPerLine()
            ptr = img.bits()
            ptr.setsize(img.sizeInBytes())
            raw = np.frombuffer(ptr, np.uint8).reshape((h, bpl))[:, : w * 4].copy()
            rgba = raw.reshape((h, w, 4))
            self.overlay_rgba = rgba if np.any(rgba[:, :, 3]) else None
        except Exception:
            try:
                img = self.canvas_image.convertToFormat(QImage.Format.Format_RGBA8888)
                w, h = img.width(), img.height()
                ptr = img.bits()
                ptr.setsize(img.sizeInBytes())
                self.overlay_rgba = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
            except Exception:
                self.overlay_rgba = None

    @property
    def overlay_pil(self):
        if self.overlay_rgba is None:
            return None
        try:
            from PIL import Image

            return Image.fromarray(self.overlay_rgba, "RGBA")
        except Exception:
            return None


class RecordingControlBar(QWidget):
    """Floating bar while recording: brush / cursor / pause / stop."""

    def __init__(self, board: "FloatingRecorderBoard", parent=None):
        super().__init__(parent)
        self.board = board
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            QFrame#bar {
                background: rgba(15,23,42,0.96); border: 1px solid #6366f1;
                border-radius: 14px;
            }
            QLabel { color: #e2e8f0; font-weight: 700; }
            QPushButton {
                background: #6366f1; color: white; border: none; border-radius: 8px;
                padding: 8px 12px; font-weight: 800;
            }
            QPushButton#soft { background: #1e293b; border: 1px solid #334155; }
            QPushButton#soft:checked { background: #0ea5e9; color: #0f172a; }
            QPushButton#danger { background: #dc2626; }
            """
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        bar = QFrame(objectName="bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        self.lbl = QLabel("🔴 录制中")
        lay.addWidget(self.lbl)
        self.btn_cursor = QPushButton("指针色", objectName="soft")
        self.btn_cursor.clicked.connect(board._pick_cursor_color)
        lay.addWidget(self.btn_cursor)
        self.btn_brush = QPushButton("画笔开", objectName="soft")
        self.btn_brush.setCheckable(True)
        self.btn_brush.setToolTip("再点一次关闭画笔")
        self.btn_brush.clicked.connect(self._sync_brush)
        lay.addWidget(self.btn_brush)
        self.btn_clear = QPushButton("清除笔画", objectName="soft")
        self.btn_clear.setToolTip("清除屏幕上已画内容（不取消录制）")
        self.btn_clear.clicked.connect(self._clear_strokes)
        lay.addWidget(self.btn_clear)
        self.btn_pause = QPushButton("暂停", objectName="soft")
        self.btn_pause.clicked.connect(board._pause_resume)
        lay.addWidget(self.btn_pause)
        self.btn_stop = QPushButton("停止保存", objectName="danger")
        self.btn_stop.clicked.connect(board._stop)
        lay.addWidget(self.btn_stop)
        root.addWidget(bar)
        self.adjustSize()

    def _sync_brush(self) -> None:
        on = self.btn_brush.isChecked()
        self.board.btn_brush.setChecked(on)
        self.board._toggle_brush()
        self.btn_brush.setText("画笔关" if on else "画笔开")

    def _clear_strokes(self) -> None:
        self.board._clear_brush()
        # keep recording; only wipe overlay paint

    def set_recording_ui(self, recording: bool, paused: bool = False) -> None:
        if not recording:
            self.hide()
            return
        self.lbl.setText("⏸ 已暂停" if paused else "🔴 录制中")
        self.btn_pause.setText("继续" if paused else "暂停")
        for button in (self.btn_cursor, self.btn_brush, self.btn_clear, self.btn_pause, self.btn_stop):
            button.setEnabled(True)
        was_visible = self.isVisible()
        self.show()
        self.raise_()
        # bottom center of primary screen
        from PyQt6.QtGui import QGuiApplication

        scr = QGuiApplication.primaryScreen()
        if scr and not was_visible:
            g = scr.availableGeometry()
            self.adjustSize()
            self.move(g.center().x() - self.width() // 2, g.bottom() - self.height() - 24)


class RecorderComboDelegate(QStyledItemDelegate):
    """Delegate ensuring dropdown popup items have consistent legible text and height."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        option.palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        option.palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        option.palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 30))


class FloatingRecorderBoard(QWidget):
    """Recorder settings (+ optional floating control bar while recording)."""

    def __init__(self, callbacks=None, state=None, parent=None, *, embedded: bool = False):
        super().__init__(parent)
        self.callbacks = callbacks
        self.state = state if isinstance(state, dict) else {}
        self.embedded = embedded
        self.recorder: screen_recorder.ScreenRecorder | None = None
        self.overlay: RecordingDrawOverlay | None = None
        self.dragging = False
        self.drag_position = QPoint()
        self._bridge = _PreviewBridge(self)
        self._bridge.frame.connect(self._on_preview_frame)
        self._bridge.status.connect(self._set_status)
        self._bridge.finished.connect(self._on_save_finished)
        self._cursor_color = QColor(255, 220, 40)
        self._busy_stop = False
        self._save_dialog: QFileDialog | None = None
        self._save_thread: threading.Thread | None = None
        self._closing = False
        self.control_bar = RecordingControlBar(self)

        if not embedded:
            self.setWindowFlags(
                Qt.WindowType.Window
            )
            from skin import get_app_version
            self.setWindowTitle(f"Clock/Alarm v{get_app_version()} — 屏幕录制")
            self.setMinimumSize(460, 380)
            available = self.screen().availableGeometry()
            self.resize(min(820, available.width()), min(780, available.height() - 60))
        else:
            self.setWindowFlags(Qt.WindowType.Widget)

        self.duration_timer = QTimer(self)
        self.duration_timer.timeout.connect(self._tick)
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._idle_preview)
        self.preview_timer.start(200)

        self._init_ui()
        self._load_settings()
        self._refresh_targets()
        self._refresh_audio()

    def _cfg(self) -> dict:
        return self.state.setdefault("recorder", {})

    def _init_ui(self) -> None:
        if not self.embedded:
            self.setStyleSheet(
                """
                QFrame#mainContainer {
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 rgba(17,24,39,0.96), stop:1 rgba(11,18,32,0.98));
                    border: 1px solid rgba(148,163,184,0.22);
                    border-radius: 16px;
                }
                QLabel { color: #e2e8f0; font-size: 12px; font-weight: 600; }
                QLabel#title { color: #34d399; font-size: 14px; font-weight: 800; }
                QLabel#muted { color: #94a3b8; font-size: 11px; font-weight: 500; }
                QComboBox, QLineEdit, QSpinBox {
                    background: #0f172a; color: #ffffff;
                    border: 1px solid rgba(148,163,184,0.35); border-radius: 8px;
                    padding: 5px 8px; min-height: 26px; font-weight: 600;
                }
                QComboBox QAbstractItemView {
                    background-color: #0f172a; color: #ffffff;
                    selection-background-color: #059669; selection-color: #ffffff;
                    border: 1px solid #10b981; outline: none; padding: 4px;
                }
                QComboBox QAbstractItemView::item {
                    min-height: 28px; padding: 6px 10px;
                    color: #ffffff; background-color: #0f172a;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: #059669; color: #ffffff;
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: #059669; color: #ffffff;
                }
                QPushButton {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #10b981, stop:1 #059669);
                    border: none; color: white; font-weight: 700; font-size: 11px;
                    padding: 7px 12px; border-radius: 9px;
                }
                QPushButton:hover { background: #34d399; color: #042f1a; }
                QPushButton:disabled { background: #334155; color: #94a3b8; }
                QPushButton#danger {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ef4444, stop:1 #dc2626);
                }
                QPushButton#soft {
                    background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.08);
                }
                QPushButton#soft:checked { background: rgba(52,211,153,0.25); border-color: #34d399; }
                QCheckBox { color: #cbd5e1; spacing: 6px; }
                QCheckBox::indicator {
                    width: 15px; height: 15px; border-radius: 4px;
                    border: 1px solid #64748b; background: #0f172a;
                }
                QCheckBox::indicator:checked { background: #10b981; border-color: #059669; }
                QSlider::groove:horizontal { height: 5px; background: #334155; border-radius: 3px; }
                QSlider::handle:horizontal {
                    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
                    background: #fff; border: 2px solid #10b981;
                }
                """
            )
        root = QVBoxLayout(self)
        root.setContentsMargins(0 if self.embedded else 0, 0, 0, 0)
        box = QFrame(objectName="mainContainer")
        if self.embedded:
            box.setStyleSheet(
                "QFrame#mainContainer { background: transparent; border: none; }"
            )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4 if self.embedded else 14, 4 if self.embedded else 12, 4 if self.embedded else 14, 4 if self.embedded else 12)
        lay.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("🎥 屏幕录制设置", objectName="title"))
        from skin import make_version_badge
        header.addWidget(make_version_badge(self))
        header.addStretch(1)
        if not self.embedded:
            close_btn = QPushButton("×")
            close_btn.setFixedSize(26, 26)
            close_btn.setObjectName("soft")
            close_btn.clicked.connect(self.hide)
            header.addWidget(close_btn)
        lay.addLayout(header)

        # ── Live preview + controls in a resizable splitter ──────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #1e293b; border-radius: 3px; }"
            "QSplitter::handle:hover { background: #00e5ff; }"
        )

        # Preview pane
        preview_pane = QWidget()
        preview_pane.setMinimumHeight(100)
        preview_layout = QVBoxLayout(preview_pane)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_label = QLabel("预览：选择范围后显示实时画面")
        self.preview_label.setObjectName("muted")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.preview_label.setStyleSheet(
            "QLabel { background: #020617; border: 1px solid #1e293b; border-radius: 12px; color: #64748b; }"
        )
        preview_layout.addWidget(self.preview_label)
        splitter.addWidget(preview_pane)

        # Controls pane (scrollable)
        controls_pane = QScrollArea()
        self.controls_pane = controls_pane
        controls_pane.setMinimumHeight(100)
        controls_pane.setWidgetResizable(True)
        controls_pane.setFrameShape(QFrame.Shape.NoFrame)
        controls_pane.setStyleSheet("background: transparent;")
        controls_inner = QWidget()
        controls_layout = QVBoxLayout(controls_inner)
        controls_layout.setContentsMargins(4, 4, 8, 4)
        controls_layout.setSpacing(10)
        controls_pane.setWidget(controls_inner)
        splitter.addWidget(controls_pane)

        # Keep the preview compact; give extra height to the settings.
        splitter.setSizes([120, 600])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter, 1)

        # Alias for easy reference
        ctrl_lay = controls_layout

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)
        form.setColumnStretch(1, 1)
        form.addWidget(QLabel("分辨率"), 0, 0)
        self.cmb_res = QComboBox()
        self.cmb_res.addItem("1080p 高清 (推荐)", "1080p")
        self.cmb_res.addItem("720p 流畅", "720p")
        self.cmb_res.addItem("1440p 2K", "1440p")
        self.cmb_res.addItem("4K 超清 (更吃性能)", "4k")
        self._style_cb(self.cmb_res)
        form.addWidget(self.cmb_res, 0, 1)

        form.addWidget(QLabel("帧率"), 0, 2)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(12, 30)
        self.spin_fps.setValue(24)
        self.spin_fps.setSuffix(" fps")
        form.addWidget(self.spin_fps, 0, 3)

        form.addWidget(QLabel("录制目标"), 1, 0)
        self.cmb_target = QComboBox()
        self.cmb_target.setMinimumWidth(0)
        self._style_cb(self.cmb_target)
        form.addWidget(self.cmb_target, 1, 1, 1, 2)
        self.btn_refresh_targets = btn_ref_t = QPushButton("刷新", objectName="soft")
        btn_ref_t.clicked.connect(self._refresh_targets)
        form.addWidget(btn_ref_t, 1, 3)

        form.addWidget(QLabel("麦克风"), 2, 0)
        self.cmb_mic = QComboBox()
        self._style_cb(self.cmb_mic)
        form.addWidget(self.cmb_mic, 2, 1, 1, 3)

        form.addWidget(QLabel("系统声音"), 3, 0)
        self.cmb_sys = QComboBox()
        self._style_cb(self.cmb_sys)
        form.addWidget(self.cmb_sys, 3, 1, 1, 3)
        ctrl_lay.addLayout(form)

        self.audio_panel = AudioMonitorPanel(self, screen_recorder.sd)
        ctrl_lay.addWidget(self.audio_panel)

        # Cursor options (clean, single-row layout)
        cur_row = QHBoxLayout()
        self.chk_cursor = QCheckBox("录制时高亮鼠标指针")
        self.chk_cursor.setChecked(True)
        cur_row.addWidget(self.chk_cursor)
        self.btn_cursor_color = QPushButton("指针颜色", objectName="soft")
        self.btn_cursor_color.clicked.connect(self._pick_cursor_color)
        cur_row.addWidget(self.btn_cursor_color)
        cur_row.addWidget(QLabel("大小"))
        self.slider_cursor = QSlider(Qt.Orientation.Horizontal)
        self.slider_cursor.setRange(12, 48)
        self.slider_cursor.setValue(24)
        self.slider_cursor.setMinimumWidth(80)
        self.slider_cursor.setMaximumWidth(140)
        self.slider_cursor.valueChanged.connect(self._update_cursor_options)
        self.chk_cursor.toggled.connect(self._update_cursor_options)
        cur_row.addWidget(self.slider_cursor)
        cur_row.addStretch(1)
        ctrl_lay.addLayout(cur_row)

        # Retain hidden brush dummy widgets for test assertion and backward compatibility
        self.btn_brush = QPushButton("画笔", objectName="soft")
        self.btn_brush.hide()
        self.cmb_brush = QComboBox()
        self.cmb_brush.hide()
        self.slider_brush = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush.hide()
        self.btn_clear = QPushButton("清除", objectName="soft")
        self.btn_clear.hide()
        self.lbl_brush_hint = QLabel("")
        self.lbl_brush_hint.hide()

        # Save path
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("保存目录"))
        self.txt_save_dir = QLineEdit()
        default_dir = str(Path.home() / "Videos" / "ClockAlarmRecordings")
        self.txt_save_dir.setText(default_dir)
        self.txt_save_dir.setPlaceholderText("录制结束后的默认保存文件夹")
        self.btn_save_dir = btn_dir = QPushButton("浏览…", objectName="soft")
        btn_dir.clicked.connect(self._pick_save_dir)
        path_row.addWidget(self.txt_save_dir, 1)
        path_row.addWidget(btn_dir)
        ctrl_lay.addLayout(path_row)

        tip = QLabel("预览为实时效果（含指针高亮）。停止后用 ffmpeg 快速封装，不再整片重编码。")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        ctrl_lay.addWidget(tip)

        self.lbl_status = QLabel("就绪 · 选好目标后点开始")
        self.lbl_status.setStyleSheet("color: #34d399; font-weight: 700;")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        ctrl = QHBoxLayout()
        self.btn_rec = QPushButton("● 开始录制")
        self.btn_rec.clicked.connect(self._start)
        self.btn_pause = QPushButton("⏸ 暂停", objectName="soft")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._pause_resume)
        self.btn_stop = QPushButton("■ 停止并保存", objectName="danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        for button in (self.btn_rec, self.btn_pause, self.btn_stop):
            button.setMinimumHeight(38)
        ctrl.addWidget(self.btn_rec)
        if self.embedded:
            # pause/stop live on floating control bar only
            self.btn_pause.hide()
            self.btn_stop.hide()
            tip2 = QLabel("点开始后：底部悬浮条控制 画笔 / 指针色 / 暂停 / 停止")
            tip2.setObjectName("muted")
            lay.addWidget(tip2)
        else:
            ctrl.addWidget(self.btn_pause)
            ctrl.addWidget(self.btn_stop)
        lay.addLayout(ctrl)

        root.addWidget(box)

    def _load_settings(self) -> None:
        cfg = self._cfg()
        if cfg.get("save_dir"):
            self.txt_save_dir.setText(str(cfg["save_dir"]))
        if cfg.get("resolution") == "720p":
            self.cmb_res.setCurrentIndex(1)
        try:
            self.spin_fps.setValue(int(cfg.get("fps") or 24))
        except Exception:
            pass
        if cfg.get("cursor_color"):
            self._cursor_color = QColor(str(cfg["cursor_color"]))
        try:
            self.slider_cursor.setValue(int(cfg.get("cursor_radius") or 24))
        except Exception:
            pass
        self._update_cursor_btn()

    def _save_settings(self) -> None:
        cfg = self._cfg()
        cfg["save_dir"] = self.txt_save_dir.text().strip()
        cfg["resolution"] = self.cmb_res.currentData() or "1080p"
        cfg["fps"] = int(self.spin_fps.value())
        cfg["cursor_color"] = self._cursor_color.name()
        cfg["cursor_radius"] = int(self.slider_cursor.value())
        try:
            if self.callbacks and hasattr(self.callbacks, "save_state"):
                self.callbacks.save_state()
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _set_controls_locked(self, locked: bool) -> None:
        enabled = not locked
        for control in (
            getattr(self, "cmb_target", None),
            getattr(self, "btn_refresh_targets", None),
            getattr(self, "cmb_res", None),
            getattr(self, "spin_fps", None),
            getattr(self, "cmb_mic", None),
            getattr(self, "cmb_sys", None),
            getattr(self, "chk_cursor", None),
            getattr(self, "slider_cursor", None),
            getattr(self, "btn_cursor_color", None),
            getattr(self, "btn_brush", None),
            getattr(self, "cmb_brush", None),
            getattr(self, "slider_brush", None),
            getattr(self, "btn_clear", None),
            getattr(self, "txt_save_dir", None),
            getattr(self, "btn_save_dir", None),
        ):
            if control is not None:
                control.setEnabled(enabled)

    def _pick_save_dir(self) -> None:
        if getattr(self, "_picking_dir", False):
            return
        self._picking_dir = True
        try:
            raw = self.txt_save_dir.text().strip()
            start = raw if raw and Path(raw).is_dir() else str(Path.home() / "Videos")
            if not Path(start).exists():
                try:
                    Path(start).mkdir(parents=True, exist_ok=True)
                except Exception:
                    start = str(Path.home())
            path = QFileDialog.getExistingDirectory(
                self,
                "选择录制保存目录",
                start,
                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog,
            )
            if path:
                self.txt_save_dir.setText(path)
                self._save_settings()
        finally:
            self._picking_dir = False

    def _pick_cursor_color(self) -> None:
        if self._busy_stop:
            return
        drawing = bool(self.overlay and self.overlay.is_draw_mode)
        if self.overlay:
            self.overlay.set_draw_mode(False)
            self.overlay.hide()
        parent = self.control_bar if self.control_bar.isVisible() else self
        try:
            c = QColorDialog.getColor(
                self._cursor_color, parent, "选择鼠标高亮颜色",
                QColorDialog.ColorDialogOption.DontUseNativeDialog,
            )
        finally:
            if self.overlay and self.recorder and not self._busy_stop:
                self.overlay.show()
                self.overlay.set_draw_mode(drawing)
                self.control_bar.raise_()
        if c.isValid():
            self._cursor_color = c
            self._update_cursor_btn()
            self._save_settings()
            if self.recorder and hasattr(self.recorder, "cfg") and self.recorder.cfg:
                self.recorder.cfg.cursor_color_bgr = (c.blue(), c.green(), c.red())
            if self.control_bar:
                c_hex = c.name()
                r, g, b = c.red(), c.green(), c.blue()
                text_col = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 128 else "#ffffff"
                self.control_bar.btn_cursor.setStyleSheet(
                    f"QPushButton#soft {{ background-color: {c_hex} !important; color: {text_col} !important; font-weight: 800; border-radius: 6px; }}"
                )

    def _update_cursor_options(self) -> None:
        if self.recorder and not self._busy_stop:
            self.recorder.cfg.highlight_cursor = self.chk_cursor.isChecked()
            self.recorder.cfg.cursor_radius = int(self.slider_cursor.value())

    def _update_cursor_btn(self) -> None:
        c_hex = self._cursor_color.name()
        r, g, b = self._cursor_color.red(), self._cursor_color.green(), self._cursor_color.blue()
        text_col = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 128 else "#ffffff"
        self.btn_cursor_color.setStyleSheet(
            f"QPushButton#soft {{ background-color: {c_hex} !important; color: {text_col} !important; font-weight: 800; border-radius: 6px; padding: 4px 10px; border: 1px solid #ffffff; }}"
        )

    def _refresh_targets(self) -> None:
        self.cmb_target.clear()
        items: list[dict] = []
        try:
            items.extend(screen_recorder.get_monitors())
            items.extend(screen_recorder.get_window_list())
        except Exception as e:
            self._set_status(f"枚举窗口失败: {e}")
            items = screen_recorder.get_monitors()
        for it in items:
            self.cmb_target.addItem(it.get("title") or "?", it)
        self._style_cb(self.cmb_target)

    def _style_cb(self, cb: QComboBox) -> None:
        if not cb:
            return
        cb.setMaxVisibleItems(15)
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(10)
        cb.setItemDelegate(RecorderComboDelegate(cb))

        pal = cb.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Window, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#059669"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        cb.setPalette(pal)

        for i in range(cb.count()):
            cb.setItemData(i, QColor("#ffffff"), Qt.ItemDataRole.ForegroundRole)

        v = cb.view()
        if v:
            v.setPalette(pal)
            v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            v.setStyleSheet("""
                QAbstractItemView, QListView {
                    background-color: #0f172a;
                    color: #ffffff;
                    selection-background-color: #059669;
                    selection-color: #ffffff;
                    border: 1px solid #10b981;
                    outline: none;
                    padding: 4px;
                }
                QAbstractItemView::item, QListView::item {
                    color: #ffffff;
                    background-color: #0f172a;
                    min-height: 28px;
                    padding: 6px 10px;
                }
                QAbstractItemView::item:hover, QListView::item:hover {
                    background-color: #059669;
                    color: #ffffff;
                }
                QAbstractItemView::item:selected, QListView::item:selected {
                    background-color: #059669;
                    color: #ffffff;
                }
            """)

    def _refresh_audio(self) -> None:
        self.cmb_mic.clear()
        self.cmb_sys.clear()
        self.cmb_mic.addItem("不录制", None)
        self.cmb_sys.addItem("不录制", None)
        try:
            mics, systems = screen_recorder.get_audio_devices()
            for m in mics:
                self.cmb_mic.addItem(m["name"], m["index"])
            for s in systems:
                self.cmb_sys.addItem(s["name"], s["index"])
            if self.cmb_mic.count() > 1:
                self.cmb_mic.setCurrentIndex(1)
            if self.cmb_sys.count() > 1:
                self.cmb_sys.setCurrentIndex(1)
        except Exception:
            pass
        self._style_cb(self.cmb_mic)
        self._style_cb(self.cmb_sys)

    def _current_target(self) -> dict | None:
        data = self.cmb_target.currentData()
        return data if isinstance(data, dict) else None

    def _idle_preview(self) -> None:
        """Show live preview even when not recording."""
        if not self.isVisible() or self._busy_stop or (self.recorder and self.recorder.is_recording):
            return
        target = self._current_target()
        region = screen_recorder.resolve_region(target)
        frame = screen_recorder.capture_bgr(region, target=target)
        if frame is None:
            return
        if self.chk_cursor.isChecked():
            c = self._cursor_color
            screen_recorder.draw_cursor_highlight(
                frame,
                region,
                color_bgr=(c.blue(), c.green(), c.red()),
                radius=int(self.slider_cursor.value()),
            )
        small = cv2.resize(frame, (360, 200), interpolation=cv2.INTER_AREA)
        self._show_bgr(small)

    def _on_preview_frame(self, frame) -> None:
        if self.isVisible() and not self._busy_stop and isinstance(frame, np.ndarray):
            self._show_bgr(frame)

    def _show_bgr(self, frame_bgr: np.ndarray) -> None:
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg).scaled(
                self.preview_label.width() - 8,
                self.preview_label.height() - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(pix)
        except Exception:
            pass

    def _on_overlay_exit_draw(self) -> None:
        """Called from overlay close button / right-click."""
        self.btn_brush.blockSignals(True)
        self.btn_brush.setChecked(False)
        self.btn_brush.blockSignals(False)
        if self.overlay:
            self.overlay.set_draw_mode(False)
        # keep floating control bar in sync
        if getattr(self, "control_bar", None):
            self.control_bar.btn_brush.blockSignals(True)
            self.control_bar.btn_brush.setChecked(False)
            self.control_bar.btn_brush.setText("画笔开")
            self.control_bar.btn_brush.blockSignals(False)
        self.lbl_brush_hint.setText("标注用法：点「画笔标注」→ 画面出现淡蓝遮罩 → 按住左键拖动")
        self.lbl_brush_hint.setStyleSheet("")
        self._set_status("画笔已关闭")
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def _toggle_brush(self) -> None:
        if self._busy_stop:
            return
        if self.btn_brush.isChecked():
            self._ensure_overlay()
            if self.overlay:
                try:
                    self.overlay.exit_requested.disconnect(self._on_overlay_exit_draw)
                except Exception:
                    pass
                self.overlay.exit_requested.connect(self._on_overlay_exit_draw)
                self.overlay.brush_size = int(self.slider_brush.value())
                self._change_brush_color()
                # Panel can stay open; overlay is topmost over the capture region only
                self.overlay.set_draw_mode(True)
                self.overlay.raise_()
            self.lbl_brush_hint.setText(
                "✅ 画笔已开：录制区域会有淡蓝遮罩，在遮罩内拖动画线。"
                "右上角「关闭画笔」或右键可关。"
            )
            self.lbl_brush_hint.setStyleSheet("color: #fbbf24; font-weight: 700;")
            self._set_status("✏️ 画笔已开 · 在淡蓝遮罩区域拖动 · 右上角可关闭")
        else:
            if self.overlay:
                self.overlay.set_draw_mode(False)
            self.lbl_brush_hint.setText("标注用法：点「画笔标注」→ 画面出现淡蓝遮罩 → 按住左键拖动")
            self.lbl_brush_hint.setStyleSheet("")
            self._set_status("画笔关闭：鼠标可正常点击下方窗口")
        if self.control_bar.isVisible():
            self.control_bar.raise_()
            if self.overlay:
                self.overlay._track_region()

    def _change_brush_color(self) -> None:
        if not self.overlay:
            return
        m = {
            "红色": QColor(239, 68, 68),
            "绿色": QColor(16, 185, 129),
            "黄色": QColor(245, 158, 11),
            "蓝色": QColor(56, 189, 248),
            "白色": QColor(248, 250, 252),
        }
        self.overlay.brush_color = m.get(self.cmb_brush.currentText(), QColor(239, 68, 68))
        if self.overlay.is_draw_mode:
            self.overlay._make_pen_cursor()

    def _change_brush_size(self, v: int) -> None:
        if self.overlay:
            self.overlay.brush_size = int(v)
            if self.overlay.is_draw_mode:
                self.overlay._make_pen_cursor()
                self.overlay.update()

    def _clear_brush(self) -> None:
        if self.overlay:
            self.overlay.clear_canvas()
            self._set_status("已清除标注笔画")

    def _ensure_overlay(self) -> None:
        if self.overlay is None:
            self.overlay = RecordingDrawOverlay()
            self.overlay.controls_window = self.control_bar
            try:
                self.overlay.exit_requested.connect(self._on_overlay_exit_draw)
            except Exception:
                pass
        region = screen_recorder.resolve_region(self._current_target())
        if not region:
            try:
                mons = screen_recorder.get_monitors()
                # monitors[0] is virtual all; prefer mon1 primary
                region = mons[1] if len(mons) > 1 else (mons[0] if mons else None)
            except Exception:
                region = None
        if not region:
            # Absolute fallback: primary screen metrics
            try:
                x = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
                y = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
                w = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
                h = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
                region = {"left": x, "top": y, "width": max(2, w), "height": max(2, h)}
            except Exception:
                region = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        self.overlay.set_region(region)
        self.overlay._ensure_canvas()
        self.overlay.set_draw_mode(self.btn_brush.isChecked())
        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.raise_()

    def _start(self) -> None:
        try:
            if hasattr(self, "audio_panel") and not self.audio_panel.prepare_recording(self._start):
                return
            self._start_session()
        except Exception as exc:
            if self.recorder:
                self.recorder.discard()
            self._on_save_finished(f"启动失败：{exc}")

    def _start_session(self) -> None:
        if self._busy_stop or self._closing or self.recorder is not None:
            return
        self._save_settings()
        target = self._current_target()
        if not target:
            self._set_status("请选择录制目标")
            return
        res = self.cmb_res.currentData() or "1080p"
        fps = int(self.spin_fps.value())
        mic = self.cmb_mic.currentData()
        sysa = self.cmb_sys.currentData()
        c = self._cursor_color

        self._ensure_overlay()
        if self.overlay:
            # Keep existing strokes if brush already used; only clear when starting fresh without brush
            if not self.btn_brush.isChecked():
                self.overlay.clear_canvas()
            reg = screen_recorder.resolve_region(target)
            if reg:
                self.overlay.set_region(reg)
            if self.btn_brush.isChecked():
                self.overlay.set_draw_mode(True)

        def overlay_provider():
            if self.overlay is None:
                return None
            return self.overlay.overlay_rgba

        def preview_cb(frame):
            self._bridge.frame.emit(frame)

        self.recorder = screen_recorder.ScreenRecorder(
            target=target,
            mic_idx=mic,
            sys_idx=sysa,
            fps=fps,
            resolution=res,
            highlight_cursor=self.chk_cursor.isChecked(),
            cursor_color_bgr=(c.blue(), c.green(), c.red()),
            cursor_radius=int(self.slider_cursor.value()),
            preview_cb=preview_cb,
            overlay_provider=overlay_provider,
        )
        try:
            self.recorder.start()
        except Exception as e:
            self.recorder.discard()
            self._on_save_finished(f"启动失败: {e}")
            return

        self.btn_rec.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self._set_controls_locked(True)
        self.duration_timer.start(500)
        self._set_status("🔴 录制中 00:00")
        # Quiet UI: dock settings to taskbar; keep recorded screen completely clean
        self._enter_silent_recording_ui()

    def _pause_resume(self) -> None:
        if self._busy_stop or not self.recorder or not self.recorder.is_recording:
            return
        if self.recorder.is_paused:
            self.recorder.resume()
            self.btn_pause.setText("⏸ 暂停")
            self._set_status(f"🔴 录制中 {self._fmt(self.recorder.duration_seconds)}")
            if getattr(self, "control_bar", None) and self.control_bar.isVisible():
                try:
                    self.control_bar.set_recording_ui(True, paused=False)
                except Exception:
                    pass
        else:
            self.recorder.pause()
            self.btn_pause.setText("▶ 继续")
            self._set_status(f"⏸ 已暂停 {self._fmt(self.recorder.duration_seconds)}")
            if getattr(self, "control_bar", None) and self.control_bar.isVisible():
                try:
                    self.control_bar.set_recording_ui(True, paused=True)
                except Exception:
                    pass
        self._set_controls_locked(True)

    def _stop(self) -> None:
        try:
            self._stop_session()
        except Exception as exc:
            self._finalize_session(None, f"保存失败：{exc}")

    def _set_save_busy(self) -> None:
        self._busy_stop = True
        self.duration_timer.stop()
        self.preview_timer.stop()
        for button in (self.btn_rec, self.btn_pause, self.btn_stop,
                       self.control_bar.btn_cursor, self.control_bar.btn_brush,
                       self.control_bar.btn_clear, self.control_bar.btn_pause,
                       self.control_bar.btn_stop):
            button.setEnabled(False)
        if self.overlay:
            self.overlay.set_draw_mode(False)
            self.overlay.hide()
        self.control_bar.hide()

    def _stop_session(self) -> None:
        if self.recorder is None or self._busy_stop or self._closing:
            return
        self._set_save_busy()
        self.recorder.pause()
        self._set_status("录制已暂停，请选择保存位置…")
        if not self.embedded:
            self.showNormal()
            self.raise_()

        save_dir = self.txt_save_dir.text().strip() or str(Path.home() / "Videos")
        default_name = Path(save_dir) / f"录屏_{self._timestamp()}.mp4"
        # A non-native, asynchronous dialog keeps Qt responsive on Windows,
        # even when recording was paused from a topmost floating control bar.
        dialog = QFileDialog(self, "保存录屏")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setNameFilter("MP4 视频 (*.mp4)")
        dialog.setDefaultSuffix("mp4")
        dialog.setDirectory(save_dir)
        dialog.selectFile(default_name.name)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._save_dialog = dialog
        dialog.accepted.connect(lambda: self._save_dialog_finished(dialog, True))
        dialog.rejected.connect(lambda: self._save_dialog_finished(dialog, False))
        dialog.open()
        dialog.raise_()
        dialog.activateWindow()

    def _save_dialog_finished(self, dialog: QFileDialog, accepted: bool) -> None:
        if dialog is not self._save_dialog or self._closing:
            return
        selected = dialog.selectedFiles() if accepted else []
        self._save_dialog = None
        dialog.deleteLater()
        self._finalize_session(selected[0] if selected else None)

    def _finalize_session(self, path: str | None, failure_message: str = "") -> None:
        if self._save_thread is not None:
            return
        if self.recorder is None:
            self._on_save_finished(failure_message)
            return
        self._set_save_busy()
        self._set_status("正在保存，请稍候…" if path else "正在结束录制…")
        rec, bridge = self.recorder, self._bridge

        def worker():
            try:
                if path:
                    msg = rec.stop(path)
                else:
                    msg = rec.discard()
            except Exception as exc:
                msg = f"保存失败：{exc}"
                try:
                    rec.discard()
                except Exception:
                    pass
            if not self._closing:
                bridge.finished.emit(failure_message or msg)

        self._save_thread = threading.Thread(target=worker, daemon=True, name="RecorderSave")
        self._save_thread.start()

    def _enter_silent_recording_ui(self) -> None:
        """Minimize settings/main window noise while recording (keep clean screen, no floating controls)."""
        self._ui_hidden_for_rec = True
        try:
            self.preview_timer.stop()
        except Exception:
            pass
        # Never display floating control bar on recorded screen
        if getattr(self, "control_bar", None):
            self.control_bar.hide()
        # Keep overlay hidden unless user explicitly opened brush
        if self.overlay and not self.btn_brush.isChecked():
            self.overlay.hide()
        # Floating settings board docks to taskbar
        if not self.embedded:
            try:
                self.showMinimized()
            except Exception:
                pass
        # Main hub if embedded or parent window visible
        try:
            host = getattr(self.callbacks, "host", None) if self.callbacks else None
            from PyQt6.QtWidgets import QApplication

            for w in QApplication.topLevelWidgets():
                name = type(w).__name__
                # Hide hub main window; keep tray
                if name in ("MainWindow",) and w.isVisible():
                    w.setProperty("_dt_hidden_for_rec", True)
                    w.hide()
        except Exception:
            pass
        # Also hide non-embedded board if parent is hub page — parent is MainWindow content
        try:
            p = self.window()
            if p is not None and p is not self and type(p).__name__ == "MainWindow" and p.isVisible():
                p.setProperty("_dt_hidden_for_rec", True)
                p.hide()
        except Exception:
            pass

    def _leave_silent_recording_ui(self) -> None:
        if not getattr(self, "_ui_hidden_for_rec", False):
            return
        self._ui_hidden_for_rec = False
        try:
            self.preview_timer.start(200)
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication

            for w in QApplication.topLevelWidgets():
                if w.property("_dt_hidden_for_rec"):
                    w.setProperty("_dt_hidden_for_rec", False)
                    w.show()
                    w.raise_()
        except Exception:
            pass
        if not self.embedded:
            try:
                self.showNormal()
                self.raise_()
            except Exception:
                pass

    def _on_save_finished(self, msg: str) -> None:
        if self._closing:
            return
        self.duration_timer.stop()
        self._save_thread = None
        self._busy_stop = False
        self.recorder = None
        if self.overlay:
            self.overlay.hide()
            self.overlay.set_draw_mode(False)
        self.btn_brush.setChecked(False)
        self.btn_rec.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ 暂停")
        self.btn_stop.setEnabled(False)
        self._set_controls_locked(False)
        self._set_status(msg)
        self._refresh_targets()
        try:
            self.control_bar.set_recording_ui(False)
            self.control_bar.btn_brush.setChecked(False)
        except Exception:
            pass
        self._leave_silent_recording_ui()

    def _tick(self) -> None:
        if self.recorder and not self.recorder.is_recording and not self._busy_stop:
            error = self.recorder._error or "录制已意外停止，请检查录制目标和音视频设备"
            self.duration_timer.stop()
            self._set_status(f"录制异常终止：{error}。正在为您保留已录制内容…")
            self._stop()
            return
        if self.recorder and self.recorder.is_recording:
            self.recorder._update_duration()
            t = self._fmt(self.recorder.duration_seconds)
            if self.recorder.is_paused:
                self._set_status(f"⏸ 已暂停 {t}")
            else:
                self._set_status(f"🔴 录制中 {t}")

    @staticmethod
    def _fmt(sec: float) -> str:
        s = int(sec)
        return f"{s // 60:02d}:{s % 60:02d}"

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.dragging = False

    def hideEvent(self, event) -> None:
        self._save_settings()
        if hasattr(self, "audio_panel"):
            self.audio_panel.stop_preview()
        # Don't kill active recording on accidental hide — only hide overlay if idle
        if not (self.recorder and self.recorder.is_recording):
            if self.overlay:
                self.overlay.hide()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        if self._busy_stop:
            self._set_status("正在保存，请稍候…")
            event.ignore()
            return
        if self.recorder and self.recorder.is_recording:
            # OBS workflow: minimize to taskbar rather than killing in-progress recording
            event.ignore()
            self.showMinimized()
            return
        if hasattr(self, "audio_panel"):
            self.audio_panel.shutdown()
        if self.overlay:
            self.overlay.hide()
            self.overlay.deleteLater()
            self.overlay = None
        super().closeEvent(event)

    def shutdown_for_exit(self) -> None:
        """Synchronously end any active session before the application exits."""
        self._closing = True
        self.duration_timer.stop()
        self.preview_timer.stop()
        if hasattr(self, "audio_panel"):
            self.audio_panel.shutdown()
        if self._save_dialog:
            self._save_dialog.reject()
            self._save_dialog = None
        if self._save_thread and self._save_thread.is_alive():
            # Explicit application exit must finish an accepted save before
            # Python shuts down its threads and Qt objects.
            self._save_thread.join()
        recorder = self.recorder
        if recorder is not None:
            recorder.discard()
            self.recorder = None
        if self.overlay:
            self.overlay.hide()
