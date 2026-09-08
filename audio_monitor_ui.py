"""Recorder audio dashboard: GUI polls bounded snapshots, never audio callbacks."""
import math
import time

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from audio_monitor import AudioPreview


class AudioWaveform(QWidget):
    """High-tech OBS-style vertical VU meter channel strip with dB ruler, LED segments, and fader."""

    def __init__(self, title: str, color: str, parent=None, is_stereo: bool = False):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self.is_stereo = is_stereo
        self.snapshot = None
        self.message = '未测试'
        self.fader_level = 1.0  # 0.0 to 1.0 (default 100% / 0.0 dB)
        self.is_muted = False
        self.current_levels = [0.0, 0.0]
        self.current_peaks = [0.0, 0.0]
        self.current_db = [-60.0, -60.0]
        self.peak_hold = [0.0, 0.0]
        self.peak_hold_time = [0.0, 0.0]
        self.setMinimumHeight(195)
        self.setMinimumWidth(190)

    def display(self, snapshot, message: str) -> None:
        self.snapshot = snapshot
        self.message = message
        now = time.monotonic()

        has_data = False
        if snapshot is not None and len(snapshot) > 1 and snapshot[1] is not None:
            try:
                has_data = len(snapshot[1]) > 0
            except Exception:
                has_data = False

        if has_data:
            rows = snapshot[1]
            for ch in range(min(2, len(rows))):
                peak = float(rows[ch][0])
                if self.is_muted:
                    frac = 0.0
                    db = -60.0
                else:
                    db = 20.0 * math.log10(max(peak, 1e-4))
                    db = max(-60.0, min(0.0, db))
                    frac = max(0.0, min(1.0, (db + 60.0) / 60.0))

                self.current_levels[ch] = frac
                self.current_peaks[ch] = peak
                self.current_db[ch] = db

                # Peak hold with 600ms latch then smooth decay
                if frac >= self.peak_hold[ch]:
                    self.peak_hold[ch] = frac
                    self.peak_hold_time[ch] = now + 0.6
                elif now > self.peak_hold_time[ch]:
                    self.peak_hold[ch] = max(frac, self.peak_hold[ch] - 0.035)

            if len(rows) == 1:
                # Mirror mono mic to both bars for stereo balance display
                self.current_levels[1] = self.current_levels[0]
                self.current_peaks[1] = self.current_peaks[0]
                self.current_db[1] = self.current_db[0]
                self.peak_hold[1] = self.peak_hold[0]
        else:
            self.current_levels = [0.0, 0.0]
            self.current_peaks = [0.0, 0.0]
            self.current_db = [-60.0, -60.0]
            for ch in range(2):
                if now > self.peak_hold_time[ch]:
                    self.peak_hold[ch] = max(0.0, self.peak_hold[ch] - 0.05)

        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_click(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_click(event.pos())
        super().mouseMoveEvent(event)

    def _handle_click(self, pos) -> None:
        m_top = 40
        m_bottom = self.height() - 38
        track_top = m_top + 12
        track_bot = m_bottom - 4
        track_h = max(1, track_bot - track_top)
        content_w = 138
        base_x = max(14, (self.width() - content_w) // 2)
        f_x = base_x + 10

        # Click on fader slider area
        if abs(pos.x() - f_x) <= 16 and track_top - 10 <= pos.y() <= track_bot + 10:
            frac = max(0.0, min(1.0, (track_bot - pos.y()) / track_h))
            self.fader_level = frac
            self.update()
        # Click on bottom mute area
        elif pos.y() >= self.height() - 30 and pos.x() <= base_x + 50:
            self.is_muted = not self.is_muted
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        # 1. Cyber HUD Card Background
        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0.0, QColor('#0b1426'))
        grad.setColorAt(1.0, QColor('#050a14'))
        p.setBrush(QBrush(grad))
        border_alpha = 90 if not self.is_muted else 40
        p.setPen(QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), border_alpha), 1.2))
        p.drawRoundedRect(QRectF(rect), 12, 12)

        # 2. Header: Title & Dynamic Digital dB Readout
        p.setFont(QFont('Segoe UI', 9, QFont.Weight.Bold))
        p.setPen(self.color)
        p.drawText(14, 24, self.title)

        max_db = max(self.current_db[0], self.current_db[1])
        p.setFont(QFont('Consolas', 10, QFont.Weight.Bold))
        if self.is_muted:
            p.setPen(QColor('#ef4444'))
            p.drawText(self.width() - 85, 24, 'MUTE')
        elif self.snapshot is None or max_db <= -59.5:
            p.setPen(QColor('#64748b'))
            p.drawText(self.width() - 85, 24, '−∞ dB')
        else:
            if max_db >= -0.5:
                p.setPen(QColor('#ff0055'))
            elif max_db >= -9.0:
                p.setPen(QColor('#fbbf24'))
            else:
                p.setPen(QColor('#34d399'))
            p.drawText(self.width() - 85, 24, f'{max_db:.1f} dB')

        # Layout metrics
        m_top = 40
        m_bottom = self.height() - 38
        m_h = m_bottom - m_top

        # Center content
        content_w = 138
        base_x = max(14, (self.width() - content_w) // 2)

        # 3. FADER SLIDER (Left)
        f_x = base_x + 10
        p.setFont(QFont('Segoe UI', 8))
        p.setPen(QColor('#94a3b8'))
        fader_db_str = f"{(self.fader_level - 1.0) * 60.0:.0f} dB" if self.fader_level < 0.99 else "0.0 dB"
        p.drawText(f_x - 14, m_top + 4, fader_db_str)

        # Track
        track_top = m_top + 12
        track_bot = m_bottom - 4
        track_h = max(1, track_bot - track_top)
        p.setPen(QPen(QColor('#1e293b'), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(f_x, track_top, f_x, track_bot)

        # Active track up to knob
        knob_y = int(track_bot - self.fader_level * track_h)
        p.setPen(QPen(QColor('#38bdf8'), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(f_x, knob_y, f_x, track_bot)

        # Fader Ticks
        p.setPen(QPen(QColor('#475569'), 1))
        for step in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            ty = int(track_bot - step * track_h)
            p.drawLine(f_x - 7, ty, f_x - 3, ty)

        # Knob (Sleek pill handle)
        p.setBrush(QColor('#ffffff'))
        p.setPen(QPen(QColor('#0284c7'), 1.5))
        p.drawRoundedRect(QRectF(f_x - 6, knob_y - 8, 12, 16), 4, 4)

        # 4. DUAL METER BARS (Center)
        bar_w = 12
        gap = 4
        meter_x0 = base_x + 42
        channels = 2
        labels = ('L', 'R') if self.is_stereo else ('M', 'M')

        for ch in range(channels):
            bx = meter_x0 + ch * (bar_w + gap)
            # Bar trough
            p.setPen(QPen(QColor('#0f172a'), 1))
            p.setBrush(QColor('#020617'))
            p.drawRoundedRect(QRectF(bx, m_top, bar_w, m_h), 3, 3)

            # Draw 32 segmented LEDs per bar
            level_frac = self.current_levels[ch] * self.fader_level
            hold_frac = self.peak_hold[ch] * self.fader_level
            num_segs = 32
            seg_h = (m_h - (num_segs - 1) * 1) / num_segs

            for s in range(num_segs):
                s_frac = (s + 0.5) / num_segs
                sy = m_bottom - (s + 1) * (seg_h + 1)

                # Zone color: Safe / Warning / Danger
                if s_frac > 0.85:  # -9dB to 0dB (Neon Red)
                    active_col = QColor('#ef4444')
                    dim_col = QColor(239, 68, 68, 25)
                elif s_frac > 0.66:  # -20dB to -9dB (Neon Amber)
                    active_col = QColor('#fbbf24')
                    dim_col = QColor(251, 191, 36, 25)
                else:  # Safe (Neon Cyber Green/Mint)
                    active_col = QColor('#10b981')
                    dim_col = QColor(16, 185, 129, 25)

                if s_frac <= level_frac and not self.is_muted:
                    p.fillRect(QRectF(bx + 1, sy, bar_w - 2, seg_h), active_col)
                else:
                    p.fillRect(QRectF(bx + 1, sy, bar_w - 2, seg_h), dim_col)

            # Peak hold indicator line
            if hold_frac > 0.02 and not self.is_muted:
                hy = int(m_bottom - hold_frac * m_h)
                p.setPen(QPen(QColor('#ffffff'), 2))
                p.drawLine(bx, hy, bx + bar_w, hy)

            # Channel label at bottom
            p.setFont(QFont('Segoe UI', 8, QFont.Weight.Bold))
            p.setPen(QColor('#94a3b8'))
            p.drawText(bx + 2, m_bottom + 14, labels[ch])

        # 5. dB SCALE RULER (Right)
        scale_x = meter_x0 + channels * (bar_w + gap) + 6
        ticks = [
            (0.0, ' 0'),
            (0.1, '-6'),
            (0.2, '-12'),
            (0.3, '-18'),
            (0.4, '-24'),
            (0.5, '-30'),
            (0.6, '-36'),
            (0.7, '-42'),
            (0.8, '-48'),
            (0.9, '-54'),
            (1.0, '-60'),
        ]
        p.setFont(QFont('Consolas', 7))
        for frac, txt in ticks:
            ty = int(m_top + frac * m_h)
            tick_col = QColor('#ef4444') if frac <= 0.1 else (QColor('#fbbf24') if frac <= 0.35 else QColor('#475569'))
            p.setPen(QPen(tick_col, 1))
            p.drawLine(scale_x, ty, scale_x + 4, ty)
            p.setPen(QColor('#94a3b8') if frac > 0.1 else QColor('#f87171'))
            p.drawText(scale_x + 7, ty + 3, txt)

        # 6. FOOTER (Mute & Status)
        p.setFont(QFont('Segoe UI', 8))
        if self.is_muted:
            p.setPen(QColor('#ef4444'))
            p.drawText(16, self.height() - 10, '🔇 已静音')
        else:
            p.setPen(QColor('#38bdf8'))
            p.drawText(16, self.height() - 10, '🔊 正常')

        # Status text on right
        p.setPen(QColor('#64748b'))
        status_str = self.message if self.message else ('实时监听' if self.snapshot else '等待输入')
        p.drawText(self.width() - 85, self.height() - 10, status_str[:6])
        p.end()


class AudioMonitorPanel(QWidget):
    def __init__(self, board, sd):
        super().__init__(board)
        self.board, self.sd = board, sd
        self.preview = None
        self.wanted = False
        self.pending_record = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        header = QHBoxLayout()
        lbl_title = QLabel('AUDIO MIXER  /  实时音频电平监测 (OBS级)')
        lbl_title.setStyleSheet('font-weight: 800; color: #38bdf8;')
        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(QLabel('自动检测 · 不外放'))
        layout.addLayout(header)

        # Side-by-side vertical channel strips (Mic & Desktop Audio)
        strips_layout = QHBoxLayout()
        strips_layout.setSpacing(10)
        self.mic = AudioWaveform('MIC 麦克风', '#22d3ee', parent=self, is_stereo=False)
        self.system = AudioWaveform('SYS 系统声音', '#c084fc', parent=self, is_stereo=True)
        strips_layout.addWidget(self.mic, 1)
        strips_layout.addWidget(self.system, 1)
        layout.addLayout(strips_layout)

        hint = QLabel('选好音源即可在上方电平表观察实时音量与峰值（绿区安全、黄区正常、红区过载）。')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(70)
        board.cmb_mic.currentIndexChanged.connect(self.selection_changed)
        board.cmb_sys.currentIndexChanged.connect(self.selection_changed)

    def selection_changed(self):
        if self.preview:
            self.preview.stop()
        # Clear previous-device traces immediately, including pending close.
        self.mic.display(None, '切换中' if self.wanted else '未测试')
        self.system.display(None, '切换中' if self.wanted else '未测试')

    def prepare_recording(self, callback):
        self.wanted = False
        if self.preview:
            self.preview.stop()
            self.pending_record = callback
            self.board.btn_rec.setEnabled(False)
            return False
        return True

    def stop_preview(self):
        self.wanted = False
        if self.pending_record:
            self.board.btn_rec.setEnabled(True)
        self.pending_record = None
        if self.preview:
            self.preview.stop()

    def shutdown(self):
        self.stop_preview()
        self.timer.stop()
        if self.preview:
            self.preview.wait_closed()
            self.preview = None

    def poll(self):
        self.wanted = (self.board.isVisible() and not self.board._closing
                       and not self.board.recorder and not self.board._busy_stop
                       and not self.pending_record)
        if not self.wanted and self.preview:
            self.preview.stop()
        if self.preview and not self.preview.alive:
            self.preview = None
        if self.pending_record and not self.preview:
            callback, self.pending_record = self.pending_record, None
            self.board.btn_rec.setEnabled(True)
            callback()
        recorder = self.board.recorder
        if self.wanted and not self.preview and not recorder:
            mic, system = self.board.cmb_mic.currentData(), self.board.cmb_sys.currentData()
            if mic is not None or system is not None:
                self.preview = AudioPreview(self.sd, mic, system)
            else:
                self.wanted = False
        audio = getattr(recorder, 'audio_recorder', None)
        levels = getattr(audio, 'levels', None) if recorder else (
            self.preview.levels if self.preview and self.wanted and not self.preview.stopping else None)
        for source, widget, combo in (('mic', self.mic, self.board.cmb_mic), ('sys', self.system, self.board.cmb_sys)):
            snapshot = levels.snapshot(source) if levels else None
            if snapshot and time.monotonic() - snapshot[0] > .6:
                snapshot = None
            message = '等待输入' if (recorder or self.wanted) else '未测试'
            if combo.currentData() is None:
                message = '不录制'
            elif self.preview and self.wanted and source in self.preview.errors:
                message = '设备失败 · 悬停查看原因'
            elif snapshot:
                peak = max(row[0] for row in snapshot[1])
                message = '过载 · 请降低音量' if peak >= .98 else ('有声音输入' if peak > .001 else '静音 / 请播放声音')
                if snapshot[2]:
                    message = '输入溢出 · 请检查设备'
            if recorder and getattr(recorder, 'is_paused', False):
                message = '已暂停 · 仅监测输入'
            widget.display(snapshot, message)
            error = self.preview.errors.get(source, '') if self.preview else ''
            widget.setToolTip(combo.currentText() + ('\n' + error if error else ''))

    def hideEvent(self, event):
        self.stop_preview()
        super().hideEvent(event)
