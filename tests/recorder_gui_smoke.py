"""Optional Windows GUI regression test, using synthetic input only.

Run with the application's Python/Qt dependencies:
    python -B tests/recorder_gui_smoke.py
No real screen, microphone, settings, or recordings are accessed.
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import cv2
import screen_recorder as sr
from PyQt6.QtWidgets import QApplication, QFileDialog, QLineEdit
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFontDatabase, QFont
from recorder_ui import FloatingRecorderBoard
from theme import apply_app_palette


class SyntheticStream:
    def __init__(self, *, callback, channels, samplerate, device):
        self.callback, self.channels = callback, channels
        self.active = False

    def start(self):
        self.active = True
        def feed():
            samples = np.zeros((441, self.channels), dtype=np.float32)
            while self.active:
                self.callback(samples, len(samples), None, None)
                time.sleep(0.01)
        self.thread = threading.Thread(target=feed, daemon=True)
        self.thread.start()

    def stop(self):
        self.active = False
        self.thread.join(timeout=1)

    def close(self):
        self.stop()


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    apply_app_palette(app, 'dark')
    # The offscreen platform has no automatic Windows font discovery.
    font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    app.setQuitOnLastWindowClosed(False)
    sr.sd.InputStream = SyntheticStream
    sr.sd.query_devices = lambda *a, **k: {'max_input_channels': 2}
    sr.get_audio_devices = lambda: ([], [])
    sr.get_monitors = lambda: [dict(title='测试画面', kind='screen', hwnd=0,
                                  left=0, top=0, width=800, height=800)]
    sr.get_window_list = lambda **k: []
    sr.capture_bgr = lambda *a, **k: np.full((180, 320, 3), 100, dtype=np.uint8)
    sr.draw_cursor_highlight = lambda *a, **k: None

    def pump(seconds=0.15, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until and until():
                return
            time.sleep(0.005)
        if until:
            assert until(), 'GUI worker did not complete'

    with tempfile.TemporaryDirectory(prefix='recorder-gui-') as temp:
        out = Path(temp)
        board = FloatingRecorderBoard(state={})
        board.txt_save_dir.setText(str(out))
        board.cmb_mic.addItem('测试麦克风', 0)
        board.cmb_sys.addItem('测试系统音频', 1)
        board.cmb_mic.setCurrentIndex(board.cmb_mic.count() - 1)
        board.cmb_sys.setCurrentIndex(board.cmb_sys.count() - 1)
        board.show()
        board.resize(1000, 820)
        pump()
        assert board.width() == 1000
        if os.environ.get('RECORDER_TEST_SCREENSHOTS'):
            board.grab().save(str(Path(os.environ['RECORDER_TEST_SCREENSHOTS']) / 'recorder-wide.png'))
        board.resize(460, 420)
        pump()
        assert board.width() <= 480 and board.height() == 420, board.size()
        assert board.controls_pane.verticalScrollBar().maximum() > 0
        assert board.controls_pane.horizontalScrollBar().maximum() == 0
        if os.environ.get('RECORDER_TEST_SCREENSHOTS'):
            board.grab().save(str(Path(os.environ['RECORDER_TEST_SCREENSHOTS']) / 'recorder-small.png'))
        board.resize(820, 780)
        print('PASS: panel grows/shrinks; compact settings scroll', flush=True)

        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start(10)
        try:
            for iteration in range(3):
                board.btn_rec.click()
                assert board.recorder and board.recorder.is_recording, board.lbl_status.text()
                pump(0.55)
                bar = board.control_bar
                bar.move(100, 500)
                bar.btn_brush.click()
                pump()
                assert board.overlay.is_draw_mode
                point = bar.frameGeometry().center() - board.overlay.geometry().topLeft()
                assert not board.overlay.mask().contains(point), 'Overlay covers recording buttons'
                bar.btn_brush.click()
                assert not board.overlay.is_draw_mode
                assert board.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                for _ in range(4):
                    bar.btn_pause.click()
                assert not board.recorder.is_paused
                bar.btn_pause.click()
                assert board.recorder.is_paused
                assert bar.pos() == QPoint(100, 500), 'Pause moved the toolbar'
                bar.btn_stop.click()
                dialog = board._save_dialog
                assert dialog and dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
                assert not board.overlay.isVisible() and not bar.isVisible()
                assert not bar.btn_stop.isEnabled()
                board._stop()  # Simulate an already queued second click.
                assert board._save_dialog is dialog
                before = len(ticks)
                pump(0.25)
                assert len(ticks) > before + 3, 'Save dialog blocked the event loop'
                assert dialog.isVisible() and board.isVisible()
                if iteration == 1:
                    private_dir = board.recorder._work_dir
                    dialog.reject()
                    pump(10, until=lambda: board.recorder is None)
                    assert not private_dir.exists()
                    print('PASS: paused cancel save resets controls', flush=True)
                    continue
                output = out / f'paused-{iteration}.mp4'
                # Enter the name as a user would; selectFile() does not replace
                # an already selected name after the non-native dialog opens.
                dialog.findChild(QLineEdit, 'fileNameEdit').setText(output.name)
                pump()
                assert Path(dialog.selectedFiles()[0]) == output
                rec = board.recorder
                original_stop = rec.stop
                calls = []
                def counted_stop(path):
                    calls.append(path)
                    time.sleep(0.15)
                    return original_stop(path)
                rec.stop = counted_stop
                dialog.accept()
                board._stop()
                before = len(ticks)
                pump(10, until=lambda: board.recorder is None)
                assert len(calls) == 1
                assert Path(calls[0]) == output, board.lbl_status.text()
                assert len(ticks) > before + 3
                assert output.stat().st_size > 1000
                video = cv2.VideoCapture(str(output))
                ok, frame = video.read()
                video.release()
                assert ok and frame is not None
                assert board.btn_rec.isEnabled() and not board.btn_stop.isEnabled()
                print('PASS: pause -> double save -> one worker -> decodable MP4; GUI responsive', flush=True)
        finally:
            timer.stop()
            board.shutdown_for_exit()
            for widget in app.topLevelWidgets():
                widget.close()
            app.quit()


if __name__ == '__main__':
    main()
