from __future__ import annotations

import os
import threading
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QFrame,
    QLabel,
    QFileDialog,
    QSlider,
    QMessageBox,
    QListWidget,
    QSplitter,
    QMenu
)
from PyQt6.QtGui import QKeyEvent, QAction
import vlc
import yt_dlp

MAX_INPUT_URLS = 100
MAX_URL_LENGTH = 2048
MAX_TITLE_LENGTH = 240
MAX_QUEUE_ITEMS = 500
DEFAULT_PLAYLIST_LIMIT = 100


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
                        if not url: continue
                        
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
                    self.limit_reached.emit(
                        f"已达到本次加载上限（{max_items} 项）"
                    )
                if not cancel_event.is_set():
                    self.finished.emit()
            except Exception as e:
                if not cancel_event.is_set():
                    self.error.emit(str(e))
        threading.Thread(target=_run, daemon=True).start()

class YtDlpStreamWorker(QObject):
    stream_extracted = pyqtSignal(str)
    error = pyqtSignal(str)
    def extract(self, url: str):
        def _run():
            try:
                # We prioritize 1080p initially, but allow switching later if needed
                if len(url) > MAX_URL_LENGTH:
                    raise ValueError("链接过长")
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
                        self.stream_extracted.emit(best_url)
                    else:
                        self.error.emit("Could not extract stream URL.")
            except Exception as e:
                self.error.emit(str(e))
        threading.Thread(target=_run, daemon=True).start()


class MediaPlayerWindow(QWidget):
    def __init__(self, parent=None, *, state=None, save_state=None):
        super().__init__(parent)
        self.state = state if isinstance(state, dict) else {}
        self.save_state = save_state
        self.setWindowTitle("Clock/Alarm - 视频播放器")
        self.resize(1000, 700)
        
        self.setStyleSheet("""
            QWidget { background-color: #0f0f0f; color: #f1f1f1; }
            QPlainTextEdit { background: #272727; border: 1px solid #3f3f3f; border-radius: 8px; padding: 10px; color: #fff; font-size: 14px; }
            QPlainTextEdit:focus { border: 1px solid #cc0000; }
            QPushButton { background: transparent; color: #f1f1f1; border: none; font-weight: bold; border-radius: 8px; padding: 6px 10px; }
            QPushButton:hover { background: rgba(255,255,255,0.1); }
            QPushButton#primary { background: #cc0000; color: #fff; }
            QPushButton#primary:hover { background: #ff0000; }
            QSlider::groove:horizontal { border: none; height: 6px; background: rgba(255,255,255,0.2); border-radius: 3px; }
            QSlider::handle:horizontal { background: #ff0000; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #ff0000; border-radius: 3px; }
            QListWidget { background: #0f0f0f; border: none; outline: none; padding: 0px; }
            QListWidget::item { padding: 12px 8px; border-bottom: 1px solid #272727; color: #f1f1f1; border-radius: 8px; margin-bottom: 2px; }
            QListWidget::item:hover { background: #272727; }
            QListWidget::item:selected { background: #272727; font-weight: bold; }
        """)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Left side: Player
        self.player_widget = QWidget()
        self.layout = QVBoxLayout(self.player_widget)
        self.layout.setContentsMargins(20, 20, 10, 20)
        self.layout.setSpacing(15)
        
        # Video Frame
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background: #000; border-radius: 12px;")
        self.video_frame.setMinimumSize(400, 300)
        self.layout.addWidget(self.video_frame, stretch=1)
        
        # Controls Bar
        controls_container = QVBoxLayout()
        controls_container.setSpacing(8)
        
        # Progress Bar
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setTracking(True)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setMinimumHeight(20)
        controls_container.addWidget(self.slider)
        self._slider_dragging = False
        
        # Buttons Row
        controls = QHBoxLayout()
        
        self.prev_btn = QPushButton("⏮")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(self.play_prev)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setStyleSheet("font-size: 20px;")
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.next_btn = QPushButton("⏭")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(self.play_next)

        self.vol_label = QLabel("🔊")
        self.vol_label.setStyleSheet("font-size: 16px; color: #f1f1f1;")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(120)
        self.vol_slider.setTracking(True)
        self.vol_slider.setMinimumHeight(20)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self.set_volume)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #aaaaaa; font-family: 'Roboto', sans-serif; font-size: 13px; font-weight: 500;")
        
        self.quality_btn = QPushButton("自动画质")
        self.quality_btn.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.quality_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setStyleSheet("font-size: 18px;")
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addSpacing(10)
        controls.addWidget(self.vol_label)
        controls.addWidget(self.vol_slider)
        controls.addSpacing(15)
        controls.addWidget(self.time_label)
        controls.addStretch()
        controls.addWidget(self.quality_btn)
        controls.addWidget(self.fullscreen_btn)
        
        controls_container.addLayout(controls)
        self.layout.addLayout(controls_container)
        
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        self.layout.addWidget(self.status_label)
        
        # Right side: Queue and Input
        self.queue_widget = QWidget()
        self.queue_widget.setFixedWidth(320)
        qlayout = QVBoxLayout(self.queue_widget)
        qlayout.setContentsMargins(10, 20, 20, 20)
        qlayout.setSpacing(15)
        
        queue_header = QHBoxLayout()
        queue_title = QLabel("播放列表")
        queue_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.open_file_btn = QPushButton("📁 本地文件")
        self.open_file_btn.setStyleSheet("background: #272727; font-size: 12px;")
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.clicked.connect(self.open_file)
        
        self.import_list_btn = QPushButton("📁 导入列表")
        self.import_list_btn.setStyleSheet("background: #272727; font-size: 12px;")
        self.import_list_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_list_btn.clicked.connect(self.import_playlist)
        
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        queue_header.addWidget(self.open_file_btn)
        queue_header.addWidget(self.import_list_btn)
        qlayout.addLayout(queue_header)
        
        # Playback Mode Selector Buttons
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(4)
        
        self.seq_play_btn = QPushButton("顺序播放")
        self.single_loop_btn = QPushButton("单曲循环")
        self.random_play_btn = QPushButton("随机播放")
        
        for btn in (self.seq_play_btn, self.single_loop_btn, self.random_play_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1f1f1f; color: #aaaaaa; font-size: 11px;
                    border: 1px solid #2d2d2d; border-radius: 4px; padding: 4px 6px;
                }
                QPushButton:checked {
                    background: #1e3a8a; color: #38bdf8; border-color: #0ea5e9;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #272727;
                }
            """)
            mode_layout.addWidget(btn)
            
        qlayout.addLayout(mode_layout)
        
        self.seq_play_btn.clicked.connect(lambda: self.set_play_mode("sequence"))
        self.single_loop_btn.clicked.connect(lambda: self.set_play_mode("single_loop"))
        self.random_play_btn.clicked.connect(lambda: self.set_play_mode("random"))
        
        # Set default active mode
        self.play_mode = self.state.setdefault("media", {}).setdefault("play_mode", "sequence")
        self.set_play_mode(self.play_mode)
        
        self.queue_list = QListWidget()
        self.queue_list.itemDoubleClicked.connect(self._on_queue_double_click)
        self.queue_list.setCursor(Qt.CursorShape.PointingHandCursor)
        qlayout.addWidget(self.queue_list, stretch=1)
        
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("粘贴链接 (支持多行)\\n例如：YouTube 视频或播放列表")
        self.url_input.setMaximumHeight(80)
        qlayout.addWidget(self.url_input)
        
        btn_layout = QHBoxLayout()
        self.add_queue_btn = QPushButton("加入列表")
        self.add_queue_btn.setObjectName("primary")
        self.add_queue_btn.clicked.connect(self.add_to_queue)
        self.add_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.clear_queue_btn = QPushButton("清空")
        self.clear_queue_btn.setStyleSheet("background: #272727; color: #f1f1f1;")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        self.clear_queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn_layout.addWidget(self.add_queue_btn, stretch=3)
        btn_layout.addWidget(self.clear_queue_btn, stretch=1)
        qlayout.addLayout(btn_layout)
        
        self.main_layout.addWidget(self.player_widget, stretch=1)
        self.main_layout.addWidget(self.queue_widget)
        
        # VLC Setup
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        
        # Timer to update slider
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()
        
        self.extractor = YtDlpWorker()
        self.extractor.item_extracted.connect(self._on_item_extracted)
        self.extractor.finished.connect(self._on_extract_finished)
        self.extractor.error.connect(self._on_extract_error)
        self.extractor.limit_reached.connect(self._on_extract_limit)
        
        self.stream_worker = YtDlpStreamWorker()
        self.stream_worker.stream_extracted.connect(self._on_stream_extracted)
        self.stream_worker.error.connect(self._on_stream_error)
        
        # State
        self.playlist = [] # list of (title, url)
        self.current_index = -1
        self.is_playing_state = False
        self.is_fullscreen = False
        self._extract_limited = False
        
        # VLC Event Manager for auto next track
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached)

    def set_window_id(self):
        if os.name == 'nt':
            self.player.set_hwnd(int(self.video_frame.winId()))
        elif os.name == 'posix':
            self.player.set_xwindow(int(self.video_frame.winId()))

    def _on_vlc_end_reached(self, event):
        QTimer.singleShot(0, self.play_next)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.queue_widget.hide()
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.showFullScreen()
        else:
            self.queue_widget.show()
            self.layout.setContentsMargins(20, 20, 10, 20)
            self.showNormal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        super().keyPressEvent(event)

    def set_volume(self, value):
        self.player.audio_set_volume(value)
        if value == 0:
            self.vol_label.setText("🔇")
        elif value < 50:
            self.vol_label.setText("🔉")
        else:
            self.vol_label.setText("🔊")

    def toggle_play(self):
        if self.playlist and self.current_index == -1:
            self.play_next()
            return
            
        if self.is_playing_state:
            self.pause()
        else:
            self.play()

    def play(self):
        self.set_window_id()
        self.player.play()
        self.is_playing_state = True
        self.play_btn.setText("⏸")
        self.status_label.setText("正在播放")

    def pause(self):
        self.player.pause()
        self.is_playing_state = False
        self.play_btn.setText("▶")
        self.status_label.setText("已暂停")

    def stop(self):
        self.player.stop()
        self.is_playing_state = False
        self.play_btn.setText("▶")
        self.slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.status_label.setText("已停止")

    def open_file(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "选择音视频文件")
        if filenames:
            remaining = max(0, MAX_QUEUE_ITEMS - len(self.playlist))
            if remaining == 0:
                QMessageBox.information(self, "播放列表", "播放列表已达到安全上限。")
                return
            accepted = filenames[:remaining]
            for f in accepted:
                title = os.path.basename(f)
                self.playlist.append((title, f))
                self.queue_list.addItem(title)
            if len(filenames) > remaining:
                QMessageBox.information(
                    self,
                    "播放列表",
                    f"播放列表最多保留 {MAX_QUEUE_ITEMS} 项，其余文件未加入。",
                )
            if self.current_index == -1:
                self.play_next()

    def set_buttons_enabled(self, enabled: bool):
        self.add_queue_btn.setEnabled(enabled)
        self.import_list_btn.setEnabled(enabled)

    def add_to_queue(self):
        text = self.url_input.toPlainText().strip()
        if not text: return
        
        urls = [u.strip() for u in text.splitlines() if u.strip()]
        if len(urls) > MAX_INPUT_URLS:
            QMessageBox.warning(
                self,
                "链接数量过多",
                f"一次最多解析 {MAX_INPUT_URLS} 行链接，请分批添加。",
            )
            return
        if any(len(url) > MAX_URL_LENGTH for url in urls):
            QMessageBox.warning(
                self, "链接过长", f"单个链接不能超过 {MAX_URL_LENGTH} 个字符。"
            )
            return
        media_cfg = self.state.get("media")
        if not isinstance(media_cfg, dict):
            media_cfg = {}
        if not bool(media_cfg.get("allow_online", True)) and any(
            url.startswith(("http://", "https://")) for url in urls
        ):
            QMessageBox.information(
                self,
                "在线播放已关闭",
                "请在“设置”中启用在线视频链接和 YouTube。",
            )
            return
        remaining = MAX_QUEUE_ITEMS - len(self.playlist)
        if remaining <= 0:
            QMessageBox.information(self, "播放列表", "播放列表已达到安全上限。")
            return
        configured_limit = max(
            1,
            min(
                200,
                int(media_cfg.get("playlist_limit") or DEFAULT_PLAYLIST_LIMIT),
            ),
        )
        extract_limit = min(configured_limit, remaining)
        self.url_input.clear()
        self.status_label.setText("正在解析链接...")
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
        self.status_label.setText("列表已清空")
            
    def _on_item_extracted(self, title, url):
        if len(self.playlist) >= MAX_QUEUE_ITEMS:
            self.extractor.cancel()
            self._on_extract_limit(
                f"播放列表最多保留 {MAX_QUEUE_ITEMS} 项，已停止解析。"
            )
            return
        title = str(title)[:MAX_TITLE_LENGTH] or "Unknown Title"
        url = str(url)
        if not url or len(url) > MAX_URL_LENGTH:
            return
        self.playlist.append((title, url))
        self.queue_list.addItem(title)
        
    def _on_extract_finished(self):
        self.set_buttons_enabled(True)
        if not self._extract_limited:
            self.status_label.setText("解析完成")
        if self.current_index == -1 and self.playlist:
            self.play_next()

    def _on_extract_limit(self, message):
        self._extract_limited = True
        self.set_buttons_enabled(True)
        self.status_label.setText(str(message))
            
    def _on_extract_error(self, err):
        self.set_buttons_enabled(True)
        self.status_label.setText(f"解析错误: {err}")
        QMessageBox.warning(self, "Extraction Error", err)
        
    def _on_queue_double_click(self, item):
        idx = self.queue_list.row(item)
        self.play_index(idx)

    def play_prev(self):
        if self.current_index > 0:
            self.play_index(self.current_index - 1)

    def play_next(self):
        if not self.playlist:
            return
            
        if self.play_mode == "single_loop":
            if self.current_index >= 0:
                self.play_index(self.current_index)
            else:
                self.play_index(0)
        elif self.play_mode == "random":
            import random
            idx = random.randint(0, len(self.playlist) - 1)
            self.play_index(idx)
        else: # sequence
            if self.current_index < len(self.playlist) - 1:
                self.play_index(self.current_index + 1)
            else:
                self.play_index(0)

    def set_play_mode(self, mode: str):
        self.play_mode = mode
        self.seq_play_btn.setChecked(mode == "sequence")
        self.single_loop_btn.setChecked(mode == "single_loop")
        self.random_play_btn.setChecked(mode == "random")
        self.state.setdefault("media", {})["play_mode"] = mode

    def import_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入播放列表", "", "播放列表 (*.txt *.m3u)"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="gbk") as f:
                    lines = f.readlines()
            except Exception as e:
                QMessageBox.warning(self, "导入失败", f"无法读取文件: {e}")
                return
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法读取文件: {e}")
            return
            
        urls = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            urls.append(line)
            
        if not urls:
            QMessageBox.information(self, "导入列表", "未在文件中找到有效的视频路径或链接。")
            return
            
        media_cfg = self.state.get("media")
        if not isinstance(media_cfg, dict):
            media_cfg = {}
            
        remaining = MAX_QUEUE_ITEMS - len(self.playlist)
        if remaining <= 0:
            QMessageBox.information(self, "播放列表", "播放列表已达到安全上限。")
            return
            
        configured_limit = max(
            1,
            min(
                200,
                int(media_cfg.get("playlist_limit") or DEFAULT_PLAYLIST_LIMIT),
            ),
        )
        extract_limit = min(configured_limit, remaining)
        
        self.status_label.setText("正在导入并解析列表项目...")
        self.set_buttons_enabled(False)
        self._extract_limited = False
        self.extractor.extract(urls[:extract_limit], extract_limit)

    def play_index(self, index: int):
        if index < 0 or index >= len(self.playlist): return
        
        self.current_index = index
        self.queue_list.setCurrentRow(index)
        title, url = self.playlist[index]
        
        if url.startswith("http"):
            self.status_label.setText(f"正在提取流地址: {title}...")
            self.stream_worker.extract(url)
        else:
            self._play_stream(title, url)
            
    def _on_stream_extracted(self, stream_url):
        if self.current_index >= 0:
            title = self.playlist[self.current_index][0]
            self._play_stream(title, stream_url)
            
    def _on_stream_error(self, err):
        self.status_label.setText(f"播放失败: {err}")
        self.play_next()

    def _play_stream(self, title: str, uri: str):
        media = self.instance.media_new(uri)
        self.player.set_media(media)
        self.set_window_id()
        self.player.audio_set_volume(self.vol_slider.value())
        self.player.play()
        self.is_playing_state = True
        self.play_btn.setText("⏸")
        self.status_label.setText(f"正在播放: {title}")
        self.setWindowTitle(f"Clock/Alarm - {title}")

    def _format_time(self, ms: int) -> str:
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def update_ui(self):
        if not self.player.is_playing():
            return
        if self._slider_dragging:
            return
        
        length = self.player.get_length()
        if length > 0:
            pos = self.player.get_position()
            self.slider.blockSignals(True)
            self.slider.setValue(int(pos * 1000))
            self.slider.blockSignals(False)
            
            cur_time = int(pos * length)
            self.time_label.setText(f"{self._format_time(cur_time)} / {self._format_time(length)}")

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        self.set_position(self.slider.value())

    def set_position(self, value):
        self.player.set_position(value / 1000.0)

    def closeEvent(self, event):
        self.player.stop()
        if self.save_state:
            try:
                self.save_state()
            except Exception:
                pass
        event.accept()
