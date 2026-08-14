"""Media player with crystal-clear docked controls, smooth collapsible playlist, high-speed streaming, HD quality switcher, and modern UI."""

from __future__ import annotations

import os
import random
import shutil
import tempfile
import threading
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QRectF, QPointF, QSize, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QLabel, QFileDialog, QSlider, QListWidget, QListWidgetItem, QMenu, QSizePolicy
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
MAX_COMPAT_CACHE_BYTES = 512 * 1024 * 1024


# ─── Icon Factory ──────────────────────────────────────────────────────────

def _make_icon(draw_fn, size=22, color='#e2e8f0'):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, float(size), QColor(color))
    p.end()
    return QIcon(pm)


def _make_dual_icon(draw_fn, size=22, off_color='#94a3b8', on_color='#38bdf8'):
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


def _draw_pin(p, s, c):
    p.save()
    p.translate(s * 0.5, s * 0.5)
    p.rotate(-25)
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(c)
    head = QPainterPath()
    head.moveTo(-s * 0.18, -s * 0.30)
    head.lineTo(s * 0.18, -s * 0.30)
    head.lineTo(s * 0.13, -s * 0.18)
    head.lineTo(s * 0.10, s * 0.05)
    head.lineTo(s * 0.23, s * 0.15)
    head.lineTo(-s * 0.23, s * 0.15)
    head.lineTo(-s * 0.10, s * 0.05)
    head.lineTo(-s * 0.13, -s * 0.18)
    head.closeSubpath()
    p.drawPath(head)
    p.drawLine(QPointF(0, s * 0.15), QPointF(0, s * 0.40))
    p.restore()


def _draw_hd(p, s, c):
    p.setPen(QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.20, s * 0.76, s * 0.60), 3, 3)
    f = QFont('Arial', max(1, int(s * 0.30)))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(s * 0.12, s * 0.20, s * 0.76, s * 0.60), Qt.AlignmentFlag.AlignCenter, "HD")


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
    p.drawLine(QPointF(s - m, s - m - y_off), QPointF(s - m, s - m - y_off))
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


def _draw_playlist_icon(p, s, c):
    p.setPen(QPen(c, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(s * 0.20, s * 0.28), QPointF(s * 0.80, s * 0.28))
    p.drawLine(QPointF(s * 0.20, s * 0.50), QPointF(s * 0.80, s * 0.50))
    p.drawLine(QPointF(s * 0.20, s * 0.72), QPointF(s * 0.60, s * 0.72))


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
    media_ready = pyqtSignal(int, str, int)  # req_id, file_path, height
    media_status = pyqtSignal(int, str)
    error = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def load_media(self, req_id: int, url: str, target_height: int, cache_dir: str):
        self.cancel()
        cancel_event = threading.Event()
        self._cancel_event = cancel_event

        def _run():
            try:
                self.media_status.emit(req_id, "正在极速缓冲...")
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                output_stem = f"media-{req_id}-q{target_height}"
                output_template = str(Path(cache_dir) / f"{output_stem}.%(ext)s")

                # Check if cached
                cached_files = [
                    p for p in Path(cache_dir).glob(f"{output_stem}.*")
                    if p.is_file() and p.suffix.lower() not in {'.part', '.ytdl', '.json'}
                ]
                if cached_files:
                    playable = max(cached_files, key=lambda p: p.stat().st_mtime_ns)
                    self.media_ready.emit(req_id, str(playable), target_height)
                    return

                def _progress_hook(_status):
                    if cancel_event.is_set():
                        raise yt_dlp.utils.DownloadCancelled()

                if target_height > 0:
                    fmt_spec = f'bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]/best'
                else:
                    fmt_spec = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'

                ydl_opts = {
                    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                    'format': fmt_spec,
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 15,
                    'noplaylist': True,
                    'max_filesize': MAX_COMPAT_CACHE_BYTES,
                    'outtmpl': output_template,
                    'nopart': False,
                    'progress_hooks': [_progress_hook],
                }
                try:
                    import imageio_ffmpeg
                    ydl_opts['ffmpeg_location'] = imageio_ffmpeg.get_ffmpeg_exe()
                except Exception:
                    pass

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)

                if cancel_event.is_set():
                    return

                files = [
                    path for path in Path(cache_dir).glob(f"{output_stem}.*")
                    if path.is_file() and path.suffix.lower() not in {'.part', '.ytdl', '.json'}
                ]
                if not files:
                    raise RuntimeError("无法生成播放文件。")
                playable = max(files, key=lambda path: path.stat().st_mtime_ns)
                self.media_ready.emit(req_id, str(playable), target_height)
            except Exception as e:
                if not cancel_event.is_set():
                    self.error.emit(req_id, str(e))
        threading.Thread(target=_run, daemon=True).start()

    def prefetch(self, url: str, target_height: int, cache_dir: str):
        def _run():
            try:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                output_stem = f"prefetch-{abs(hash(url))}-q{target_height}"
                output_template = str(Path(cache_dir) / f"{output_stem}.%(ext)s")

                if any(Path(cache_dir).glob(f"{output_stem}.*")):
                    return

                if target_height > 0:
                    fmt_spec = f'bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]/best'
                else:
                    fmt_spec = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'

                ydl_opts = {
                    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                    'format': fmt_spec,
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 15,
                    'noplaylist': True,
                    'max_filesize': MAX_COMPAT_CACHE_BYTES,
                    'outtmpl': output_template,
                }
                try:
                    import imageio_ffmpeg
                    ydl_opts['ffmpeg_location'] = imageio_ffmpeg.get_ffmpeg_exe()
                except Exception:
                    pass

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()


# ─── Media Player Window ──────────────────────────────────────────────────

class MediaPlayerWindow(QWidget):
    def __init__(self, parent=None, *, state=None, save_state=None):
        super().__init__(parent)
        self.state = state if isinstance(state, dict) else {}
        self.save_state = save_state
        self.setWindowTitle("Clock/Alarm - Player")
        self.resize(1040, 700)
        self.setMinimumSize(540, 360)

        self._vlc_ready = True
        self._current_request_id = 0
        self._is_changing_media = False
        self._online_source_url = ""
        self._media_retry_pending = False
        self._media_cache_dir = tempfile.mkdtemp(prefix="ClockAlarm-media-")
        self._selected_quality_height = 0  # 0 means Auto / 1080p
        self._pending_seek_pos = 0

        self.setStyleSheet("""
            QWidget { background-color: #0b0f17; color: #f1f5f9; font-family: 'Segoe UI', system-ui, sans-serif; }
            QPlainTextEdit {
                background: #111827; border: 1px solid #1f2937;
                border-radius: 8px; padding: 8px; color: #fff; font-size: 13px;
            }
            QPlainTextEdit:focus { border: 1px solid #0284c7; }
            QPushButton {
                background: transparent; color: #cbd5e1; border: none;
                font-weight: bold; border-radius: 6px; padding: 4px 6px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); color: #ffffff; }
            QPushButton:disabled { opacity: 0.35; }
            QPushButton#primary { background: #0284c7; color: #fff; border-radius: 6px; }
            QPushButton#primary:hover { background: #0369a1; }
            QSlider::groove:horizontal {
                border: none; height: 6px;
                background: rgba(255,255,255,0.18); border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #38bdf8; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal { background: #0284c7; border-radius: 3px; }

            /* Modern Ultra-Clean Scrollbar */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.22);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(56, 189, 248, 0.7);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none; background: none; height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                height: 0px; border: none;
            }

            /* Playlist View */
            QListWidget {
                background: #0f172a; border: none; outline: none; padding: 4px;
            }
            QListWidget::item {
                padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.04);
                color: #94a3b8; border-radius: 8px; margin: 2px 2px;
                font-size: 13px;
            }
            QListWidget::item:hover {
                background: #1e293b; color: #f8fafc;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #0c4a6e);
                color: #ffffff; font-weight: bold; border-left: 3px solid #38bdf8;
            }
        """)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ── Left: Video + Controls Container ──
        self.player_widget = QWidget(self)
        self.player_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.player_layout = QVBoxLayout(self.player_widget)
        self.player_layout.setContentsMargins(14, 14, 10, 14)
        self.player_layout.setSpacing(10)

        # Video Frame
        self.video_frame = QVideoWidget(self.player_widget)
        self.video_frame.setStyleSheet("background: #000000; border-radius: 10px;")
        self.video_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.player_layout.addWidget(self.video_frame, stretch=1)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_frame)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.errorOccurred.connect(self._on_media_error)

        # ── Bottom Controls Bar (Crystal Clear, Fully Visible) ──
        self.controls_widget = QWidget(self.player_widget)
        self.controls_widget.setStyleSheet("""
            QWidget {
                background: #111827; border-radius: 10px; padding: 4px;
            }
        """)
        controls_vbox = QVBoxLayout(self.controls_widget)
        controls_vbox.setContentsMargins(14, 8, 14, 10)
        controls_vbox.setSpacing(6)

        # Progress slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setTracking(True)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setMinimumHeight(18)
        controls_vbox.addWidget(self.slider)
        self._slider_dragging = False

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._play_icon = _make_icon(_draw_play, 26, '#ffffff')
        self._pause_icon = _make_icon(_draw_pause, 26, '#ffffff')
        self._speaker_icon = _make_icon(_draw_speaker, 20, '#cbd5e1')
        self._muted_icon = _make_icon(_draw_speaker_muted, 20, '#cbd5e1')
        self._hd_icon = _make_icon(_draw_hd, 20, '#38bdf8')
        self._playlist_icon = _make_icon(_draw_playlist_icon, 20, '#cbd5e1')

        self.prev_btn = QPushButton()
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.setIcon(_make_icon(_draw_prev, 22, '#cbd5e1'))
        self.prev_btn.setIconSize(QSize(22, 22))
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setToolTip("上一曲")
        self.prev_btn.clicked.connect(lambda *a: self.play_prev())

        self.play_btn = QPushButton()
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setIcon(self._play_icon)
        self.play_btn.setIconSize(QSize(26, 26))
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setToolTip("播放 / 暂停 (快捷键: 空格)")
        self.play_btn.clicked.connect(lambda *a: self.toggle_play())

        self.next_btn = QPushButton()
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.setIcon(_make_icon(_draw_next, 22, '#cbd5e1'))
        self.next_btn.setIconSize(QSize(22, 22))
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setToolTip("下一曲")
        self.next_btn.clicked.connect(lambda *a: self.play_next())

        self.vol_btn = QPushButton()
        self.vol_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_btn.setIcon(self._speaker_icon)
        self.vol_btn.setIconSize(QSize(20, 20))
        self.vol_btn.setFixedSize(30, 30)
        self.vol_btn.setToolTip("音量")

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setMinimumWidth(40)
        self.vol_slider.setMaximumWidth(88)
        self.vol_slider.setTracking(True)
        self.vol_slider.setMinimumHeight(16)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self.set_volume)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet(
            "color: #94a3b8; font-family: 'Consolas', monospace; font-size: 12px; margin-left: 6px;"
        )

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #38bdf8; font-size: 11px; margin-left: 10px;")

        # Custom HD quality button
        self.quality_btn = QPushButton()
        self.quality_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.quality_btn.setIcon(self._hd_icon)
        self.quality_btn.setIconSize(QSize(22, 22))
        self.quality_btn.setFixedSize(34, 34)
        self.quality_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quality_btn.setToolTip("画质选择 (1080p/720p/480p/360p)")
        self.quality_btn.clicked.connect(self._show_quality_menu)

        # Toggle playlist button (Manual Collapse / Expand)
        self.toggle_playlist_btn = QPushButton()
        self.toggle_playlist_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_playlist_btn.setIcon(self._playlist_icon)
        self.toggle_playlist_btn.setIconSize(QSize(22, 22))
        self.toggle_playlist_btn.setFixedSize(34, 34)
        self.toggle_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_playlist_btn.setToolTip("折叠 / 展开播放列表")
        self.toggle_playlist_btn.clicked.connect(self.toggle_playlist_panel)

        self.always_on_top_btn = QPushButton()
        self.always_on_top_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.always_on_top_btn.setCheckable(True)
        self.always_on_top_btn.setChecked(False)
        self.always_on_top_btn.setIcon(_make_dual_icon(_draw_pin, 18))
        self.always_on_top_btn.setIconSize(QSize(18, 18))
        self.always_on_top_btn.setFixedSize(32, 32)
        self.always_on_top_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.always_on_top_btn.setToolTip("置顶窗口")
        self.always_on_top_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: 1px solid transparent; border-radius: 6px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); }
            QPushButton:checked { background: #0c4a6e; border-color: #38bdf8; }
        """)
        self.always_on_top_btn.clicked.connect(
            lambda checked=False: self.set_always_on_top(bool(checked))
        )
        self._always_on_top = False

        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fullscreen_btn.setIcon(_make_icon(_draw_expand, 18, '#cbd5e1'))
        self.fullscreen_btn.setIconSize(QSize(18, 18))
        self.fullscreen_btn.setFixedSize(32, 32)
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.setToolTip("全屏 (快捷键: Esc 退出)")
        self.fullscreen_btn.clicked.connect(lambda *a: self.toggle_fullscreen())

        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addSpacing(10)
        controls.addWidget(self.vol_btn)
        controls.addWidget(self.vol_slider)
        controls.addWidget(self.time_label)
        controls.addWidget(self.status_label)
        controls.addStretch()
        controls.addWidget(self.quality_btn)
        controls.addWidget(self.toggle_playlist_btn)
        controls.addWidget(self.always_on_top_btn)
        controls.addWidget(self.fullscreen_btn)

        controls_vbox.addLayout(controls)
        self.player_layout.addWidget(self.controls_widget)

        # ── Right: Modern Clean Collapsible Queue Panel ──
        self.queue_widget = QWidget(self)
        self.queue_widget.setMinimumWidth(260)
        self.queue_widget.setMaximumWidth(320)
        self.queue_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        qlayout = QVBoxLayout(self.queue_widget)
        qlayout.setContentsMargins(10, 14, 14, 14)
        qlayout.setSpacing(10)

        # Top row: playlist header, collapse button & open file
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        list_title = QLabel("播放列表")
        list_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #f8fafc;")
        top_row.addWidget(list_title)
        top_row.addStretch()

        self.open_file_btn = QPushButton()
        self.open_file_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_file_btn.setIcon(_make_icon(_draw_folder, 18))
        self.open_file_btn.setIconSize(QSize(18, 18))
        self.open_file_btn.setFixedSize(32, 32)
        self.open_file_btn.setStyleSheet(
            "background: #1e293b; border: 1px solid #334155; border-radius: 6px;"
        )
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.setToolTip("打开本地音视频文件")
        self.open_file_btn.clicked.connect(lambda *a: self.open_file())
        top_row.addWidget(self.open_file_btn)
        qlayout.addLayout(top_row)

        # Playback Mode Buttons
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(6)

        self.seq_play_btn = QPushButton()
        self.seq_play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seq_play_btn.setIcon(_make_dual_icon(_draw_repeat, 18))
        self.seq_play_btn.setIconSize(QSize(18, 18))
        self.seq_play_btn.setToolTip("顺序播放")

        self.single_loop_btn = QPushButton()
        self.single_loop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.single_loop_btn.setIcon(_make_dual_icon(_draw_repeat_one, 18))
        self.single_loop_btn.setIconSize(QSize(18, 18))
        self.single_loop_btn.setToolTip("单曲循环")

        self.random_play_btn = QPushButton()
        self.random_play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.random_play_btn.setIcon(_make_dual_icon(_draw_shuffle, 18))
        self.random_play_btn.setIconSize(QSize(18, 18))
        self.random_play_btn.setToolTip("随机播放")

        mode_btn_style = """
            QPushButton {
                background: #1e293b; border: 1px solid #334155; border-radius: 6px;
            }
            QPushButton:checked {
                background: #0284c7; border-color: #38bdf8;
            }
            QPushButton:hover { background: #334155; }
        """
        for btn in (self.seq_play_btn, self.single_loop_btn, self.random_play_btn):
            btn.setCheckable(True)
            btn.setFixedSize(32, 32)
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

        # Queue list (Horizontal scroll disabled, text wrapped)
        self.queue_list = QListWidget()
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.queue_list.setWordWrap(True)
        self.queue_list.itemDoubleClicked.connect(self._on_queue_double_click)
        self.queue_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_context_menu)
        qlayout.addWidget(self.queue_list, stretch=1)

        # URL input
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("粘贴链接 (每行一条)")
        self.url_input.setMaximumHeight(64)
        qlayout.addWidget(self.url_input)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.add_queue_btn = QPushButton()
        self.add_queue_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_queue_btn.setIcon(_make_icon(_draw_plus, 16, '#ffffff'))
        self.add_queue_btn.setIconSize(QSize(16, 16))
        self.add_queue_btn.setObjectName("primary")
        self.add_queue_btn.setFixedHeight(32)
        self.add_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_queue_btn.setToolTip("添加到播放列表")
        self.add_queue_btn.clicked.connect(lambda *a: self.add_to_queue())

        self.clear_queue_btn = QPushButton()
        self.clear_queue_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_queue_btn.setIcon(_make_icon(_draw_clear, 16, '#94a3b8'))
        self.clear_queue_btn.setIconSize(QSize(16, 16))
        self.clear_queue_btn.setFixedHeight(32)
        self.clear_queue_btn.setStyleSheet("background:#1e293b; border:1px solid #334155; border-radius:6px;")
        self.clear_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_queue_btn.setToolTip("清空播放列表")
        self.clear_queue_btn.clicked.connect(lambda *a: self.clear_queue())

        btn_layout.addWidget(self.add_queue_btn, stretch=3)
        btn_layout.addWidget(self.clear_queue_btn, stretch=1)
        qlayout.addLayout(btn_layout)

        self.main_layout.addWidget(self.player_widget, stretch=1)
        self.main_layout.addWidget(self.queue_widget)

        # Timer
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
        self.stream_worker.media_ready.connect(self._on_media_ready)
        self.stream_worker.media_status.connect(self._on_media_status)
        self.stream_worker.error.connect(self._on_stream_error)

        # Playback state
        self.playlist = []
        self.current_index = -1
        self.is_playing_state = False
        self.is_fullscreen = False
        self._extract_limited = False

        self._playlist_save_timer = QTimer(self)
        self._playlist_save_timer.setSingleShot(True)
        self._playlist_save_timer.setInterval(200)
        self._playlist_save_timer.timeout.connect(self._flush_playlist_state)
        self._restore_playlist()

    # ── Highlighting & Auto Scrolling ──

    def _scroll_to_current_playlist_item(self):
        if 0 <= self.current_index < self.queue_list.count():
            item = self.queue_list.item(self.current_index)
            self.queue_list.setCurrentItem(item)
            self.queue_list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)

    # ── Player Events ──

    def _ensure_vlc(self) -> bool:
        return self.player is not None

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(0, self.play_next)
        elif status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            self._media_retry_pending = False
            self._trigger_next_prefetch()

    def _on_playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.is_playing_state = playing
        self.play_btn.setIcon(self._pause_icon if playing else self._play_icon)

    def _on_media_error(self, error=None, error_string="") -> None:
        if self._media_retry_pending:
            return
        message = str(error_string or (self.player.errorString() if self.player else ""))
        labels = {
            QMediaPlayer.Error.ResourceError: "资源地址失效",
            QMediaPlayer.Error.FormatError: "媒体格式不兼容",
            QMediaPlayer.Error.NetworkError: "网络连接失败",
            QMediaPlayer.Error.AccessDeniedError: "视频需要权限或登录",
        }
        label = labels.get(error, "无法打开媒体")
        req_id = self._current_request_id
        self._finish_media_failure(req_id, label, message)

    # ── Quality Selector Menu ──

    def _show_quality_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a; border: 1px solid #1e293b;
                border-radius: 8px; padding: 6px; color: #f8fafc;
            }
            QMenu::item {
                padding: 6px 22px 6px 16px; border-radius: 6px; font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #0284c7; color: #ffffff;
            }
        """)

        auto_action = QAction("自动 (最高画质)", menu)
        auto_action.setCheckable(True)
        auto_action.setChecked(self._selected_quality_height == 0)
        auto_action.triggered.connect(lambda: self._select_quality(0))
        menu.addAction(auto_action)
        menu.addSeparator()

        for h in [1080, 720, 480, 360]:
            label = f"{h}p HD" if h >= 720 else f"{h}p"
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self._selected_quality_height == h)
            action.triggered.connect(lambda checked=False, height=h: self._select_quality(height))
            menu.addAction(action)

        menu.exec(self.quality_btn.mapToGlobal(QPointF(0, -menu.sizeHint().height()).toPoint()))

    def _select_quality(self, height: int):
        self._selected_quality_height = height
        if self.current_index < 0:
            return

        current_pos = self.player.position() if self.player else 0
        title, url = self.playlist[self.current_index]
        if url.startswith("http"):
            self._current_request_id += 1
            req_id = self._current_request_id
            self.stream_worker.cancel()
            self.stream_worker.load_media(req_id, url, self._selected_quality_height, self._media_cache_dir)
            self._pending_seek_pos = current_pos

    # ── Pre-fetching Next Video ──

    def _trigger_next_prefetch(self):
        if len(self.playlist) <= 1:
            return
        nxt = self.current_index + 1
        if nxt >= len(self.playlist):
            if self.play_mode == "sequence":
                nxt = 0
            else:
                return
        _title, next_url = self.playlist[nxt]
        if next_url.startswith("http"):
            self.stream_worker.prefetch(next_url, self._selected_quality_height, self._media_cache_dir)

    # ── Player Controls ──

    def set_window_id(self):
        return

    def toggle_playlist_panel(self):
        """Toggle right side playlist panel visibility."""
        is_visible = self.queue_widget.isVisible()
        self.queue_widget.setVisible(not is_visible)
        self.toggle_playlist_btn.setToolTip("展开播放列表" if is_visible else "折叠播放列表")
        if not is_visible:
            self._scroll_to_current_playlist_item()

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.queue_widget.hide()
            self.showFullScreen()
        else:
            self.queue_widget.show()
            self.showNormal()

    def set_always_on_top(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self._always_on_top:
            return

        was_fullscreen = self.isFullScreen() or self.is_fullscreen
        normal_geometry = None if was_fullscreen else self.saveGeometry()

        self._always_on_top = enabled
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)

        if was_fullscreen:
            self.showFullScreen()
        else:
            self.show()
            if normal_geometry is not None:
                self.restoreGeometry(normal_geometry)

        self.always_on_top_btn.setToolTip("取消置顶" if enabled else "置顶窗口")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play()
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
        self.stream_worker.cancel()
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
        remove_action = QAction("移除此项", menu)
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
        self._scroll_to_current_playlist_item()

        self._current_request_id += 1
        req_id = self._current_request_id
        self.stream_worker.cancel()
        self._online_source_url = ""
        self._media_retry_pending = False
        self._pending_seek_pos = 0

        title, url = self.playlist[index]
        if url.startswith("http"):
            self._online_source_url = url
            self.stream_worker.load_media(req_id, url, self._selected_quality_height, self._media_cache_dir)
        else:
            self._play_stream(req_id, title, url)

    def _on_media_status(self, req_id: int, message: str):
        if req_id == self._current_request_id:
            self.status_label.setText(message)

    def _on_media_ready(self, req_id: int, path: str, height: int):
        if req_id != self._current_request_id or self.current_index < 0:
            return
        self._media_retry_pending = False
        title = self.playlist[self.current_index][0]
        q_label = f" [{height}p]" if height > 0 else ""
        self.status_label.setText(f"{title}{q_label}")
        seek_pos = getattr(self, "_pending_seek_pos", 0)
        self._pending_seek_pos = 0
        self._play_stream(req_id, title, path, seek_pos_ms=seek_pos)

    def _on_stream_error(self, req_id: int, err: str):
        if req_id != self._current_request_id:
            return
        self._finish_media_failure(req_id, "加载失败", str(err))

    def _finish_media_failure(self, req_id: int, label: str, detail: str):
        if req_id != self._current_request_id or self._media_retry_pending:
            return
        self._media_retry_pending = True
        short_detail = detail.strip() or "未知原因"
        if len(short_detail) > 120:
            short_detail = short_detail[:117] + "…"
        self.status_label.setText(f"播放失败：{label}（{short_detail}），即将播放下一项")
        self.is_playing_state = False
        self.play_btn.setIcon(self._play_icon)
        QTimer.singleShot(1500, lambda r=req_id: self._advance_after_failure(r))

    def _advance_after_failure(self, req_id: int):
        if req_id != self._current_request_id:
            return
        self._media_retry_pending = False
        if len(self.playlist) <= 1:
            self.status_label.setText("播放失败：列表中没有其他可播放项目")
            return
        nxt = (max(self.current_index, 0) + 1) % len(self.playlist)
        self.play_index(nxt)

    def _play_stream(self, req_id: int, title: str, uri: str, seek_pos_ms: int = 0):
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
            if seek_pos_ms > 0:
                QTimer.singleShot(300, lambda p=seek_pos_ms: self.player.setPosition(p))
            self.is_playing_state = True
            self.play_btn.setIcon(self._pause_icon)
            self.setWindowTitle(f"Clock/Alarm - {title}")
            self._scroll_to_current_playlist_item()
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
        self.stream_worker.cancel()
        if self._vlc_ready and self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._persist_playlist(immediate=True)
        shutil.rmtree(self._media_cache_dir, ignore_errors=True)
        event.accept()
