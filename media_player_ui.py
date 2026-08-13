"""Media player with icon-based UI, thread-safe VLC bridge, and native window isolation."""

from __future__ import annotations

import os
import threading
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QRectF, QPointF, QSize, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QFrame, QLabel, QFileDialog, QSlider, QListWidget, QMenu
)
from PyQt6.QtGui import (
    QKeyEvent, QAction, QIcon, QPixmap, QPainter, QPen, QColor,
    QPainterPath, QFont
)
import yt_dlp

MAX_INPUT_URLS = 20
MAX_URL_LENGTH = 2048
MAX_TITLE_LENGTH = 240
MAX_QUEUE_ITEMS = 500
DEFAULT_PLAYLIST_LIMIT = 100


# ─── Icon Factory ──────────────────────────────────────────────────────────

def _make_icon(draw_fn, size=22, color='#d0d0d0'):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, float(size), QColor(color))
    p.end()
    return QIcon(pm)


def _make_dual_icon(draw_fn, size=22, off_color='#aaaaaa', on_color='#38bdf8'):
    """Icon with normal (off) and checked (on) states."""
    icon = QIcon()
    for state, color in ((QIcon.State.Off, off_color), (QIcon.State.On, on_color)):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_fn(p, float(size), QColor(color))
        p.end()
        icon.addPixmap(pm, QIcon.Mode.Normal, state)
    return icon


# ── Individual icon drawings ──

def _draw_folder(p, s, c):
    p.setPen(QPen(QColor('#e6a800'), 1.2))
    p.setBrush(QColor('#ffc107'))
    tab = QPainterPath()
    tab.moveTo(s * 0.12, s * 0.35)
    tab.lineTo(s * 0.12, s * 0.24)
    tab.lineTo(s * 0.42, s * 0.24)
    tab.lineTo(s * 0.48, s * 0.35)
    tab.closeSubpath()
    p.drawPath(tab)
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.35, s * 0.76, s * 0.42), 2, 2)


def _draw_prev(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRect(QRectF(s * 0.22, s * 0.26, s * 0.07, s * 0.48))
    tri = QPainterPath()
    tri.moveTo(s * 0.76, s * 0.22)
    tri.lineTo(s * 0.36, s * 0.5)
    tri.lineTo(s * 0.76, s * 0.78)
    tri.closeSubpath()
    p.drawPath(tri)


def _draw_play(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    tri = QPainterPath()
    tri.moveTo(s * 0.28, s * 0.18)
    tri.lineTo(s * 0.78, s * 0.5)
    tri.lineTo(s * 0.28, s * 0.82)
    tri.closeSubpath()
    p.drawPath(tri)


def _draw_pause(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    w = s * 0.14
    p.drawRoundedRect(QRectF(s * 0.24, s * 0.2, w, s * 0.6), 2, 2)
    p.drawRoundedRect(QRectF(s * 0.62, s * 0.2, w, s * 0.6), 2, 2)


def _draw_next(p, s, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    tri = QPainterPath()
    tri.moveTo(s * 0.24, s * 0.22)
    tri.lineTo(s * 0.64, s * 0.5)
    tri.lineTo(s * 0.24, s * 0.78)
    tri.closeSubpath()
    p.drawPath(tri)
    p.drawRect(QRectF(s * 0.71, s * 0.26, s * 0.07, s * 0.48))


def _draw_speaker(p, s, c):
    p.setPen(QPen(c, 1.2))
    p.setBrush(c)
    body = QPainterPath()
    body.moveTo(s * 0.12, s * 0.42)
    body.lineTo(s * 0.28, s * 0.42)
    body.lineTo(s * 0.48, s * 0.22)
    body.lineTo(s * 0.48, s * 0.78)
    body.lineTo(s * 0.28, s * 0.58)
    body.lineTo(s * 0.12, s * 0.58)
    body.closeSubpath()
    p.drawPath(body)
    p.setBrush(Qt.BrushStyle.NoBrush)
    wave1 = QPainterPath()
    wave1.moveTo(s * 0.58, s * 0.35)
    wave1.quadTo(s * 0.70, s * 0.5, s * 0.58, s * 0.65)
    p.drawPath(wave1)
    wave2 = QPainterPath()
    wave2.moveTo(s * 0.66, s * 0.26)
    wave2.quadTo(s * 0.84, s * 0.5, s * 0.66, s * 0.74)
    p.drawPath(wave2)


def _draw_speaker_muted(p, s, c):
    p.setPen(QPen(c, 1.2))
    p.setBrush(c)
    body = QPainterPath()
    body.moveTo(s * 0.12, s * 0.42)
    body.lineTo(s * 0.28, s * 0.42)
    body.lineTo(s * 0.48, s * 0.22)
    body.lineTo(s * 0.48, s * 0.78)
    body.lineTo(s * 0.28, s * 0.58)
    body.lineTo(s * 0.12, s * 0.58)
    body.closeSubpath()
    p.drawPath(body)
    p.setPen(QPen(QColor('#ff4444'), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(s * 0.58, s * 0.32), QPointF(s * 0.82, s * 0.68))
    p.drawLine(QPointF(s * 0.58, s * 0.68), QPointF(s * 0.82, s * 0.32))


def _draw_expand(p, s, c):
    pen = QPen(c, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m, L = s * 0.22, s * 0.2
    for x1, y1, dx, dy in [
        (m, m, L, 0), (m, m, 0, L),
        (s - m, m, -L, 0), (s - m, m, 0, L),
        (m, s - m, L, 0), (m, s - m, 0, -L),
        (s - m, s - m, -L, 0), (s - m, s - m, 0, -L),
    ]:
        p.drawLine(QPointF(x1, y1), QPointF(x1 + dx, y1 + dy))


def _draw_repeat(p, s, c):
    pen = QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m, t, b = s * 0.18, s * 0.3, s * 0.7
    p.drawLine(QPointF(m, t), QPointF(s - m, t))
    p.drawLine(QPointF(s - m, t), QPointF(s - m, b))
    p.drawLine(QPointF(s - m, b), QPointF(m, b))
    p.drawLine(QPointF(m, b), QPointF(m, t))
    a = s * 0.1
    p.drawLine(QPointF(s - m - a, t - a), QPointF(s - m, t))
    p.drawLine(QPointF(s - m - a, t + a), QPointF(s - m, t))
    p.drawLine(QPointF(m + a, b - a), QPointF(m, b))
    p.drawLine(QPointF(m + a, b + a), QPointF(m, b))


def _draw_repeat_one(p, s, c):
    _draw_repeat(p, s, c)
    p.setPen(QPen(c))
    f = QFont('Arial', max(1, int(s * 0.28)))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, '1')


def _draw_shuffle(p, s, c):
    pen = QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = s * 0.2
    y_off = s * 0.06
    p.drawLine(QPointF(m, m + y_off), QPointF(s - m, s - m - y_off))
    p.drawLine(QPointF(m, s - m - y_off), QPointF(s - m, m + y_off))
    a = s * 0.1
    p.drawLine(QPointF(s - m - a, m + y_off), QPointF(s - m, m + y_off))
    p.drawLine(QPointF(s - m, m + y_off + a), QPointF(s - m, m + y_off))
    p.drawLine(QPointF(s - m - a, s - m - y_off), QPointF(s - m, s - m - y_off))
    p.drawLine(QPointF(s - m, s - m - y_off - a), QPointF(s - m, s - m - y_off))


def _draw_plus(p, s, c):
    pen = QPen(c, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = s * 0.28
    p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m))
    p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))


def _draw_clear(p, s, c):
    pen = QPen(c, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = s * 0.28
    p.drawLine(QPointF(m, m), QPointF(s - m, s - m))
    p.drawLine(QPointF(s - m, m), QPointF(m, s - m))


# ─── Thread-Safe Signals ──────────────────────────────────────────────────

class VlcBridge(QObject):
    end_reached = pyqtSignal()


# ─── YtDlp Workers ────────────────────────────────────────────────────────

class YtDlpWorker(QObject):
    item_extracted = pyqtSignal(str, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    limit_reached = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def extract(self, urls: list[str], max_items: int):
        self.cancel()
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        max_items = max(1, min(MAX_QUEUE_ITEMS, int(max_items)))

        def _run():
            emitted = 0
            try:
                ydl_opts = {
                    'format': 'best',
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'playlistend': max_items,
                    'socket_timeout': 15,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    for url in urls:
                        if cancel_event.is_set() or emitted >= max_items:
                            break
                        url = url.strip()
                        if not url:
                            continue

                        if not url.startswith("http"):
                            self.item_extracted.emit(os.path.basename(url), url)
                            emitted += 1
                            continue

                        info = ydl.extract_info(url, download=False)
                        if 'entries' in info:
                            for entry in info['entries']:
                                if cancel_event.is_set() or emitted >= max_items:
                                    break
                                if entry:
                                    entry_url = entry.get('url') or entry.get('webpage_url')
                                    title = entry.get('title', 'Unknown Title')
                                    entry_url = str(entry_url or "")
                                    if entry_url and len(entry_url) <= MAX_URL_LENGTH:
                                        self.item_extracted.emit(
                                            str(title)[:MAX_TITLE_LENGTH],
                                            entry_url,
                                        )
                                        emitted += 1
                        else:
                            title = info.get('title', 'Unknown Title')
                            self.item_extracted.emit(
                                str(title)[:MAX_TITLE_LENGTH], url
                            )
                            emitted += 1
                if emitted >= max_items and not cancel_event.is_set():
                    self.limit_reached.emit(f"Limit: {max_items} items")
                if not cancel_event.is_set():
                    self.finished.emit()
            except Exception as e:
                if not cancel_event.is_set():
                    self.error.emit(str(e))
        threading.Thread(target=_run, daemon=True).start()


class YtDlpStreamWorker(QObject):
    stream_extracted = pyqtSignal(int, str)
    error = pyqtSignal(int, str)

    def extract(self, req_id: int, url: str):
        def _run():
            try:
                if len(url) > MAX_URL_LENGTH:
                    raise ValueError("URL too long")
                ydl_opts = {
                    'format': 'best',
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 15,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    best_url = info.get('url', None)
                    if best_url:
                        self.stream_extracted.emit(req_id, best_url)
                    else:
                        self.error.emit(req_id, "Could not extract stream URL.")
            except Exception as e:
                self.error.emit(req_id, str(e))
        threading.Thread(target=_run, daemon=True).start()


# ─── Media Player Window ──────────────────────────────────────────────────

class MediaPlayerWindow(QWidget):
    def __init__(self, parent=None, *, state=None, save_state=None):
        super().__init__(parent)
        self.state = state if isinstance(state, dict) else {}
        self.save_state = save_state
        self.setWindowTitle("Clock/Alarm - Player")
        self.resize(1000, 700)

        # Qt Multimedia uses the bundled asynchronous FFmpeg backend. Keeping
        # media operations out of libVLC's synchronous stop/set_media path
        # prevents the UI thread from freezing while files are switched.
        self._vlc_ready = True
        self.instance = None
        self.event_manager = None
        self._vlc_end_cb = None

        self._current_request_id = 0
        self._is_changing_media = False

        self.setStyleSheet("""
            QWidget { background-color: #0f0f0f; color: #f1f1f1; }
            QPlainTextEdit {
                background: #1a1a1a; border: 1px solid #3f3f3f;
                border-radius: 8px; padding: 10px; color: #fff; font-size: 14px;
            }
            QPlainTextEdit:focus { border: 1px solid #cc0000; }
            QPushButton {
                background: transparent; color: #f1f1f1; border: none;
                font-weight: bold; border-radius: 8px; padding: 6px 10px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.08); }
            QPushButton:disabled { opacity: 0.4; }
            QPushButton#primary { background: #cc0000; color: #fff; }
            QPushButton#primary:hover { background: #ff0000; }
            QSlider::groove:horizontal {
                border: none; height: 6px;
                background: rgba(255,255,255,0.15); border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ff0000; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal { background: #ff0000; border-radius: 3px; }
            QListWidget {
                background: #0f0f0f; border: none; outline: none; padding: 0px;
            }
            QListWidget::item {
                padding: 10px 8px; border-bottom: 1px solid #1a1a1a;
                color: #f1f1f1; border-radius: 6px; margin-bottom: 1px;
            }
            QListWidget::item:hover { background: #1a1a1a; }
            QListWidget::item:selected { background: #1a1a1a; font-weight: bold; }
        """)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ── Left: Player Area ──
        self.player_widget = QWidget()
        self.vlayout = QVBoxLayout(self.player_widget)
        self.vlayout.setContentsMargins(20, 20, 10, 20)
        self.vlayout.setSpacing(15)

        self.video_frame = QVideoWidget()
        self.video_frame.setStyleSheet("background: #000; border-radius: 12px;")
        self.video_frame.setMinimumSize(400, 300)
        self.vlayout.addWidget(self.video_frame, stretch=1)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_frame)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.errorOccurred.connect(self._on_media_error)

        # Controls
        controls_box = QVBoxLayout()
        controls_box.setSpacing(8)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setTracking(True)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setMinimumHeight(20)
        controls_box.addWidget(self.slider)
        self._slider_dragging = False

        controls = QHBoxLayout()

        # Cache icons
        self._play_icon = _make_icon(_draw_play, 28)
        self._pause_icon = _make_icon(_draw_pause, 28)
        self._speaker_icon = _make_icon(_draw_speaker, 20)
        self._muted_icon = _make_icon(_draw_speaker_muted, 20)

        self.prev_btn = QPushButton()
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.setIcon(_make_icon(_draw_prev, 24))
        self.prev_btn.setIconSize(QSize(24, 24))
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setToolTip("\u4e0a\u4e00\u66f2")
        self.prev_btn.clicked.connect(lambda *a: self.play_prev())

        self.play_btn = QPushButton()
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setIcon(self._play_icon)
        self.play_btn.setIconSize(QSize(28, 28))
        self.play_btn.setFixedSize(42, 42)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setToolTip("\u64ad\u653e / \u6682\u505c")
        self.play_btn.clicked.connect(lambda *a: self.toggle_play())

        self.next_btn = QPushButton()
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.setIcon(_make_icon(_draw_next, 24))
        self.next_btn.setIconSize(QSize(24, 24))
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setToolTip("\u4e0b\u4e00\u66f2")
        self.next_btn.clicked.connect(lambda *a: self.play_next())

        self.vol_btn = QPushButton()
        self.vol_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_btn.setIcon(self._speaker_icon)
        self.vol_btn.setIconSize(QSize(20, 20))
        self.vol_btn.setFixedSize(28, 28)
        self.vol_btn.setToolTip("\u97f3\u91cf")

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setTracking(True)
        self.vol_slider.setMinimumHeight(20)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self.set_volume)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet(
            "color: #777; font-family: 'Consolas', monospace; font-size: 12px;"
        )

        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fullscreen_btn.setIcon(_make_icon(_draw_expand, 18))
        self.fullscreen_btn.setIconSize(QSize(18, 18))
        self.fullscreen_btn.setFixedSize(30, 30)
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.setToolTip("\u5168\u5c4f")
        self.fullscreen_btn.clicked.connect(lambda *a: self.toggle_fullscreen())

        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addSpacing(10)
        controls.addWidget(self.vol_btn)
        controls.addWidget(self.vol_slider)
        controls.addSpacing(10)
        controls.addWidget(self.time_label)
        controls.addStretch()
        controls.addWidget(self.fullscreen_btn)

        controls_box.addLayout(controls)
        self.vlayout.addLayout(controls_box)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        self.vlayout.addWidget(self.status_label)

        # ── Right: Queue Panel ──
        self.queue_widget = QWidget()
        self.queue_widget.setFixedWidth(310)
        qlayout = QVBoxLayout(self.queue_widget)
        qlayout.setContentsMargins(10, 20, 16, 20)
        qlayout.setSpacing(10)

        # Top row: open file button
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.open_file_btn = QPushButton()
        self.open_file_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_file_btn.setIcon(_make_icon(_draw_folder, 20))
        self.open_file_btn.setIconSize(QSize(20, 20))
        self.open_file_btn.setFixedSize(36, 36)
        self.open_file_btn.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px;"
        )
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.setToolTip("\u6253\u5f00\u672c\u5730\u6587\u4ef6")
        self.open_file_btn.clicked.connect(lambda *a: self.open_file())

        top_row.addStretch()
        top_row.addWidget(self.open_file_btn)
        qlayout.addLayout(top_row)

        # Playback Mode Buttons
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(4)

        self.seq_play_btn = QPushButton()
        self.seq_play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seq_play_btn.setIcon(_make_dual_icon(_draw_repeat, 20))
        self.seq_play_btn.setIconSize(QSize(20, 20))
        self.seq_play_btn.setToolTip("\u987a\u5e8f\u64ad\u653e")

        self.single_loop_btn = QPushButton()
        self.single_loop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.single_loop_btn.setIcon(_make_dual_icon(_draw_repeat_one, 20))
        self.single_loop_btn.setIconSize(QSize(20, 20))
        self.single_loop_btn.setToolTip("\u5355\u66f2\u5faa\u73af")

        self.random_play_btn = QPushButton()
        self.random_play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.random_play_btn.setIcon(_make_dual_icon(_draw_shuffle, 20))
        self.random_play_btn.setIconSize(QSize(20, 20))
        self.random_play_btn.setToolTip("\u968f\u673a\u64ad\u653e")

        mode_btn_style = """
            QPushButton {
                background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px;
            }
            QPushButton:checked {
                background: #1e3a8a; border-color: #0ea5e9;
            }
            QPushButton:hover { background: #222222; }
        """
        for btn in (self.seq_play_btn, self.single_loop_btn, self.random_play_btn):
            btn.setCheckable(True)
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(mode_btn_style)
            mode_layout.addWidget(btn)

        mode_layout.addStretch()
        qlayout.addLayout(mode_layout)

        self.seq_play_btn.clicked.connect(lambda *a: self.set_play_mode("sequence"))
        self.single_loop_btn.clicked.connect(lambda *a: self.set_play_mode("single_loop"))
        self.random_play_btn.clicked.connect(lambda *a: self.set_play_mode("random"))

        # Default mode
        self.play_mode = self.state.setdefault("media", {}).setdefault(
            "play_mode", "sequence"
        )
        self.set_play_mode(self.play_mode)

        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.itemDoubleClicked.connect(self._on_queue_double_click)
        self.queue_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_context_menu)
        qlayout.addWidget(self.queue_list, stretch=1)

        # URL input (Standard input widget)
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("Paste URLs (one per line)")
        self.url_input.setMaximumHeight(70)
        qlayout.addWidget(self.url_input)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.add_queue_btn = QPushButton()
        self.add_queue_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_queue_btn.setIcon(_make_icon(_draw_plus, 18, '#ffffff'))
        self.add_queue_btn.setIconSize(QSize(18, 18))
        self.add_queue_btn.setObjectName("primary")
        self.add_queue_btn.setFixedHeight(34)
        self.add_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_queue_btn.setToolTip("\u6dfb\u52a0\u5230\u64ad\u653e\u5217\u8868")
        self.add_queue_btn.clicked.connect(lambda *a: self.add_to_queue())

        self.clear_queue_btn = QPushButton()
        self.clear_queue_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_queue_btn.setIcon(_make_icon(_draw_clear, 16, '#888888'))
        self.clear_queue_btn.setIconSize(QSize(16, 16))
        self.clear_queue_btn.setFixedHeight(34)
        self.clear_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_queue_btn.setToolTip("\u6e05\u7a7a\u64ad\u653e\u5217\u8868")
        self.clear_queue_btn.clicked.connect(lambda *a: self.clear_queue())

        btn_layout.addWidget(self.add_queue_btn, stretch=3)
        btn_layout.addWidget(self.clear_queue_btn, stretch=1)
        qlayout.addLayout(btn_layout)

        self.main_layout.addWidget(self.player_widget, stretch=1)
        self.main_layout.addWidget(self.queue_widget)

        # Timer (guarded by _vlc_ready and _is_changing_media in update_ui)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

        # Extractors
        self.extractor = YtDlpWorker()
        self.extractor.item_extracted.connect(self._on_item_extracted)
        self.extractor.finished.connect(self._on_extract_finished)
        self.extractor.error.connect(self._on_extract_error)
        self.extractor.limit_reached.connect(self._on_extract_limit)

        self.stream_worker = YtDlpStreamWorker()
        self.stream_worker.stream_extracted.connect(self._on_stream_extracted)
        self.stream_worker.error.connect(self._on_stream_error)

        # Playback state
        self.playlist = []
        self.current_index = -1
        self.is_playing_state = False
        self.is_fullscreen = False
        self._extract_limited = False

        # Keep the queue across full application restarts. State writes are
        # debounced so importing a large playlist does not block the UI once
        # per item; closeEvent still performs an immediate final flush.
        self._playlist_save_timer = QTimer(self)
        self._playlist_save_timer.setSingleShot(True)
        self._playlist_save_timer.setInterval(200)
        self._playlist_save_timer.timeout.connect(self._flush_playlist_state)
        self._restore_playlist()

    # ── Asynchronous Qt Multimedia backend ──

    def _ensure_vlc(self) -> bool:
        """Compatibility shim retained for existing call sites."""
        return self.player is not None

    def _on_vlc_end_reached_c_callback(self, event):
        QTimer.singleShot(0, self.play_next)

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(0, self.play_next)

    def _on_playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.is_playing_state = playing
        self.play_btn.setIcon(self._pause_icon if playing else self._play_icon)

    def _on_media_error(self, *args) -> None:
        message = self.player.errorString() if self.player else ""
        self.status_label.setText(f"播放失败：{message or '无法打开该媒体文件'}")

    # ── Player Controls ──

    def set_window_id(self):
        # QVideoWidget is already connected with setVideoOutput().
        return

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.queue_widget.hide()
            self.vlayout.setContentsMargins(0, 0, 0, 0)
            self.showFullScreen()
        else:
            self.queue_widget.show()
            self.vlayout.setContentsMargins(20, 20, 10, 20)
            self.showNormal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        super().keyPressEvent(event)

    def set_volume(self, value):
        if hasattr(self, "audio_output"):
            self.audio_output.setVolume(max(0.0, min(1.0, value / 100.0)))
        self.vol_btn.setIcon(self._muted_icon if value == 0 else self._speaker_icon)

    def toggle_play(self):
        if self.playlist and self.current_index == -1:
            self.play_next()
            return
        if self.is_playing_state:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self._ensure_vlc():
            return
        self.set_window_id()
        self.player.play()
        self.is_playing_state = True
        self.play_btn.setIcon(self._pause_icon)

    def pause(self):
        if not self._vlc_ready or self.player is None:
            return
        self.player.pause()
        self.is_playing_state = False
        self.play_btn.setIcon(self._play_icon)

    def stop(self):
        if self._vlc_ready and self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self.is_playing_state = False
        self.play_btn.setIcon(self._play_icon)
        self.slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.status_label.setText("")

    # ── File & Queue ──

    def _restore_playlist(self):
        media_cfg = self.state.setdefault("media", {})
        saved_playlist = media_cfg.get("playlist", [])
        if not isinstance(saved_playlist, list):
            saved_playlist = []

        restored = []
        allow_online = bool(media_cfg.get("allow_online", True))
        for entry in saved_playlist[:MAX_QUEUE_ITEMS]:
            if isinstance(entry, dict):
                title, url = entry.get("title", ""), entry.get("url", "")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                title, url = entry[0], entry[1]
            else:
                continue

            title = str(title)[:MAX_TITLE_LENGTH] or "Unknown"
            url = str(url)
            if not url or len(url) > MAX_URL_LENGTH:
                continue
            is_online = url.startswith(("http://", "https://"))
            if is_online and not allow_online:
                continue
            if not is_online and not os.path.isfile(url):
                continue
            restored.append((title, url))

        self.playlist.extend(restored)
        for title, _url in restored:
            self.queue_list.addItem(title)

        # Do not auto-play on application startup. Invalid or missing entries
        # are removed from the in-memory state and disappear on the next save.
        media_cfg["playlist"] = [
            {"title": title, "url": url} for title, url in self.playlist
        ]

    def _persist_playlist(self, *, immediate=False):
        self.state.setdefault("media", {})["playlist"] = [
            {"title": str(title)[:MAX_TITLE_LENGTH], "url": str(url)[:MAX_URL_LENGTH]}
            for title, url in self.playlist[:MAX_QUEUE_ITEMS]
        ]
        if not self.save_state:
            return
        if immediate:
            self._playlist_save_timer.stop()
            self._flush_playlist_state()
        else:
            self._playlist_save_timer.start()

    def _flush_playlist_state(self):
        if self.save_state:
            try:
                self.save_state()
            except Exception:
                pass

    def open_file(self):
        media_cfg = self.state.setdefault("media", {})
        start_dir = str(media_cfg.get("last_open_dir") or os.path.expanduser("~"))
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "导入本地音视频",
            start_dir,
            "音视频文件 (*.mp4 *.mkv *.avi *.mp3 *.flv *.mov *.wav *.m4a *.wmv *.webm);;所有文件 (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if filenames:
            media_cfg["last_open_dir"] = os.path.dirname(filenames[0])
            remaining = max(0, MAX_QUEUE_ITEMS - len(self.playlist))
            if remaining == 0:
                return
            for f in filenames[:remaining]:
                title = os.path.basename(f)
                self.playlist.append((title, f))
                self.queue_list.addItem(title)
            self._persist_playlist()
            if self.current_index == -1 and self.playlist:
                self.status_label.setText(f"已导入 {min(len(filenames), remaining)} 个本地文件")
                # Return from the modal file dialog before starting playback.
                QTimer.singleShot(0, self.play_next)

    def set_buttons_enabled(self, enabled: bool):
        self.add_queue_btn.setEnabled(enabled)
        self.open_file_btn.setEnabled(enabled)

    def add_to_queue(self):
        text = self.url_input.toPlainText().strip()
        if not text:
            return
        urls = [u.strip() for u in text.splitlines() if u.strip()]
        if len(urls) > MAX_INPUT_URLS:
            return
        if any(len(url) > MAX_URL_LENGTH for url in urls):
            return
        media_cfg = self.state.get("media")
        if not isinstance(media_cfg, dict):
            media_cfg = {}
        if not bool(media_cfg.get("allow_online", True)) and any(
            url.startswith(("http://", "https://")) for url in urls
        ):
            return
        remaining = MAX_QUEUE_ITEMS - len(self.playlist)
        if remaining <= 0:
            return
        configured_limit = max(
            1, min(200, int(media_cfg.get("playlist_limit") or DEFAULT_PLAYLIST_LIMIT))
        )
        extract_limit = min(configured_limit, remaining)
        self.url_input.clear()
        self.status_label.setText("Extracting...")
        self.set_buttons_enabled(False)
        self._extract_limited = False
        self.extractor.extract(urls, extract_limit)

    def clear_queue(self):
        self.extractor.cancel()
        self.set_buttons_enabled(True)
        self.playlist.clear()
        self.queue_list.clear()
        self.current_index = -1
        self.stop()
        self._persist_playlist()

    def _on_item_extracted(self, title, url):
        if len(self.playlist) >= MAX_QUEUE_ITEMS:
            self.extractor.cancel()
            self._on_extract_limit(f"Limit: {MAX_QUEUE_ITEMS}")
            return
        title = str(title)[:MAX_TITLE_LENGTH] or "Unknown"
        url = str(url)
        if not url or len(url) > MAX_URL_LENGTH:
            return
        self.playlist.append((title, url))
        self.queue_list.addItem(title)
        self._persist_playlist()

    def _on_extract_finished(self):
        self.set_buttons_enabled(True)
        if not self._extract_limited:
            self.status_label.setText("")
        if self.current_index == -1 and self.playlist:
            self.play_next()

    def _on_extract_limit(self, message):
        self._extract_limited = True
        self.set_buttons_enabled(True)
        self.status_label.setText(str(message))

    def _on_extract_error(self, err):
        self.set_buttons_enabled(True)
        self.status_label.setText(f"Error: {err}")

    def _on_queue_double_click(self, item):
        idx = self.queue_list.row(item)
        self.play_index(idx)

    def _queue_context_menu(self, pos):
        item = self.queue_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        idx = self.queue_list.row(item)
        remove_action = QAction("Remove", menu)
        remove_action.triggered.connect(lambda *a, i=idx: self._remove_item(i))
        menu.addAction(remove_action)
        menu.exec(self.queue_list.mapToGlobal(pos))

    def _remove_item(self, idx):
        if 0 <= idx < len(self.playlist):
            self.playlist.pop(idx)
            self.queue_list.takeItem(idx)
            if idx == self.current_index:
                self.stop()
                self.current_index = -1
            elif idx < self.current_index:
                self.current_index -= 1
            self._persist_playlist()

    # ── Playback ──

    def play_prev(self):
        if self.current_index > 0:
            self.play_index(self.current_index - 1)

    def play_next(self):
        if not self.playlist:
            return
        if self.play_mode == "single_loop":
            self.play_index(max(0, self.current_index))
        elif self.play_mode == "random":
            import random
            self.play_index(random.randint(0, len(self.playlist) - 1))
        else:
            nxt = self.current_index + 1
            self.play_index(nxt if nxt < len(self.playlist) else 0)

    def set_play_mode(self, mode: str):
        self.play_mode = mode
        self.seq_play_btn.setChecked(mode == "sequence")
        self.single_loop_btn.setChecked(mode == "single_loop")
        self.random_play_btn.setChecked(mode == "random")
        self.state.setdefault("media", {})["play_mode"] = mode

    def play_index(self, index: int):
        if index < 0 or index >= len(self.playlist):
            return
        self.current_index = index
        self.queue_list.setCurrentRow(index)
        self._current_request_id += 1
        req_id = self._current_request_id

        title, url = self.playlist[index]
        if url.startswith("http"):
            self.status_label.setText(f"Loading: {title}...")
            self.stream_worker.extract(req_id, url)
        else:
            self._play_stream(req_id, title, url)

    def _on_stream_extracted(self, req_id: int, stream_url: str):
        if req_id != self._current_request_id:
            return  # Discard stale request response
        if self.current_index >= 0:
            title = self.playlist[self.current_index][0]
            self._play_stream(req_id, title, stream_url)

    def _on_stream_error(self, req_id: int, err: str):
        if req_id != self._current_request_id:
            return
        self.status_label.setText(f"Error: {err}")

    def _play_stream(self, req_id: int, title: str, uri: str):
        if req_id != self._current_request_id:
            return
        if not self._ensure_vlc():
            return
        self._is_changing_media = True
        try:
            self.player.stop()
            source = QUrl(uri) if uri.startswith(("http://", "https://")) else QUrl.fromLocalFile(uri)
            self.player.setSource(source)
            self.audio_output.setVolume(self.vol_slider.value() / 100.0)
            self.player.play()
            self.is_playing_state = True
            self.play_btn.setIcon(self._pause_icon)
            self.status_label.setText(title)
            self.setWindowTitle(f"Clock/Alarm - {title}")
        finally:
            self._is_changing_media = False

    # ── UI Update ──

    def _format_time(self, ms: int) -> str:
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def update_ui(self):
        if self._is_changing_media or not self._vlc_ready or self.player is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            return
        if self._slider_dragging:
            return
        try:
            length = self.player.duration()
            if length > 0:
                cur_time = self.player.position()
                pos = cur_time / length
                self.slider.blockSignals(True)
                self.slider.setValue(int(pos * 1000))
                self.slider.blockSignals(False)
                self.time_label.setText(
                    f"{self._format_time(cur_time)} / {self._format_time(length)}"
                )
        except Exception:
            pass

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        self.set_position(self.slider.value())

    def set_position(self, value):
        if self._vlc_ready and self.player and not self._is_changing_media:
            try:
                duration = self.player.duration()
                if duration > 0:
                    self.player.setPosition(int(duration * value / 1000.0))
            except Exception:
                pass

    def closeEvent(self, event):
        if self._vlc_ready and self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._persist_playlist(immediate=True)
        event.accept()
