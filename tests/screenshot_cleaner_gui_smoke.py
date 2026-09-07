"""Optional Qt integration tests with synthetic screenshots and cleanup tasks.

Run with the application's Python/Qt dependencies:
    python -B tests/screenshot_cleaner_gui_smoke.py
Never captures the desktop, writes clipboard/settings, or cleans real files.
Set CLOCK_ALARM_SMOKE_IMAGE to optionally save a synthetic progress UI preview.
"""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QObject, QEvent, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget, QLineEdit
import cleaner
import main as shell
import screenshot_app as shot
import settings_ui
from theme import apply_app_palette


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    apply_app_palette(app, 'dark')
    font_file = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
    if font_file.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    errors, messages, clipboard = [], [], []
    def exception_hook(kind, value, tb):
        errors.append(f'{kind.__name__}: {value}')
        traceback.print_exception(kind, value, tb)
    sys.excepthook = exception_hook
    QMessageBox.warning = lambda *args: messages.append(args[-1])
    shot.copy_image_to_clipboard = lambda image: clipboard.append(image)
    background = QPixmap(800, 600)
    background.fill(QColor('#234567'))
    capture = lambda: (background, QRect(0, 0, 800, 600))
    shot.capture_virtual_desktop = capture

    def pump(seconds=0.15, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            assert not errors, errors
            if until and until():
                return
            time.sleep(0.005)
        if until:
            assert until(), 'GUI did not reach expected state'

    # Construct only the host QObject: no autostart, real hotkeys or saved state.
    host = shell.ClockAlarmApp.__new__(shell.ClockAlarmApp)
    QObject.__init__(host)
    host._screenshot_active = False
    host._cleaning = False
    host.cleaner_progress_window = None
    logs, notifications = [], []
    host.store = SimpleNamespace(state={'screenshot': {'auto_save': False}},
                                 append_log=lambda *args: logs.append(args))
    host.tray = SimpleNamespace(showMessage=lambda *args: notifications.append(args))
    windows = [QWidget() for _ in range(6)]
    host.world_clock_board, tools, todo, notes, manager, invisible = windows
    host.world_clock_board.tools_window = tools
    host.todo_board = SimpleNamespace(windows={'one': todo}, manager_win=manager)
    host.notes_ctl = SimpleNamespace(windows={'one': notes, 'hidden': invisible}, manager_win=None)
    host.recorder_board = host.media_player_board = None
    for window in windows[:-1]:
        window.show()
    host.clean_progress.connect(host._on_clean_progress)
    host.clean_finished.connect(host._on_clean_finished)

    def check_restored():
        assert all(w.isVisible() for w in windows[:-1])
        assert not invisible.isVisible()
        assert not host._screenshot_active
        assert shot._EDITOR_REF is None

    for action in ('cancel', 'close', 'accept', 'pin'):
        host.start_screenshot_region()
        host.start_screenshot_region()  # Duplicate hotkey must be ignored.
        assert not any(w.isVisible() for w in windows)
        pump(2, lambda: shot._EDITOR_REF is not None)
        editor = shot._EDITOR_REF
        results = []
        editor.finished.connect(results.append)
        if action in ('accept', 'pin'):
            for kind, point, buttons in (
                (QEvent.Type.MouseButtonPress, QPointF(80, 80), Qt.MouseButton.LeftButton),
                (QEvent.Type.MouseMove, QPointF(420, 300), Qt.MouseButton.LeftButton),
                (QEvent.Type.MouseButtonRelease, QPointF(420, 300), Qt.MouseButton.NoButton),
            ):
                button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
                QApplication.sendEvent(editor, QMouseEvent(kind, point, point, button, buttons,
                                                           Qt.KeyboardModifier.NoModifier))
            assert editor.phase == 'edit'
            exported = editor.export_image()
            assert not exported.isNull() and exported.width() > 300
            assert exported.pixelColor(10, 10).name() == '#234567'
        if action == 'close':
            editor.close()
        else:
            editor._on_action(action)
        pump()
        check_restored()
        assert len(results) == 1, 'Finish callback must run exactly once'
    assert len(clipboard) == 3  # Two selection auto-copies, one explicit accept.
    assert len(shot._PINNED_REFS) == 1 and shot._PINNED_REFS[0].isVisible()
    for pin in shot._PINNED_REFS:
        pin.close()

    def fail(*args, **kwargs):
        raise RuntimeError('synthetic launch failure')
    shot.capture_virtual_desktop = fail
    host.start_screenshot_region()
    pump(2, lambda: not host._screenshot_active)
    check_restored()
    shot.capture_virtual_desktop = capture
    editor_class = shot.ScreenshotEditor
    shot.ScreenshotEditor = fail
    host.start_screenshot_region()
    pump(2, lambda: not host._screenshot_active)
    check_restored()
    shot.ScreenshotEditor = editor_class
    assert len(messages) == 2
    print('PASS screenshot: controllers, selection, accept, pin, cancel, close, failure recovery')

    with tempfile.TemporaryDirectory(prefix='screenshot-save-') as folder:
        host.store.state['screenshot']['save_dir'] = folder
        host.start_screenshot_region()
        pump(2, lambda: shot._EDITOR_REF is not None)
        editor = shot._EDITOR_REF
        editor.sel = QRect(10, 10, 200, 150)
        editor._enter_edit_mode()
        editor._shortcut_action('save')
        dialog = editor._save_dialog
        assert dialog and not editor.isVisible()
        editor._save_image_as(editor.export_image())
        assert editor._save_dialog is dialog
        dialog.reject()
        pump()
        assert editor.isVisible() and editor._save_dialog is None
        editor._shortcut_action('save')
        dialog = editor._save_dialog
        pump()
        dialog.findChild(QLineEdit, 'fileNameEdit').setText('saved-test.png')
        dialog.accept()
        pump()
        saved = QImage(str(Path(folder) / 'saved-test.png'))
        assert saved.width() == 200 and saved.height() == 150
        check_restored()

        host.start_screenshot_region()
        pump(2, lambda: shot._EDITOR_REF is not None)
        editor = shot._EDITOR_REF
        editor.sel = QRect(10, 10, 200, 150)
        editor.cfg['auto_save'] = True
        def no_directory():
            raise OSError('synthetic disk failure')
        editor._default_save_dir = no_directory
        editor._on_action('accept')
        assert editor.isVisible() and not editor._finished_emitted
        assert messages[-1] == 'synthetic disk failure'
        editor.close()
        pump()
        check_restored()
    print('PASS screenshot: Ctrl+S, cancel/retry save, decoded PNG, disk failure keeps editor')

    # Synthetic background work: never invoke any filesystem cleanup function.
    later_scopes = []
    def synthetic_temp(report):
        for index in range(100):
            if cleaner._cancel_requested(report):
                break
            report.files_removed += 1
            report.bytes_freed += 1024 * 1024
            cleaner._notify_progress(report, item=f'测试缓存-{index}.tmp', force=True)
            time.sleep(0.03)
    cleaner._clean_temp = synthetic_temp
    cleaner._clean_thumbs = lambda report: later_scopes.append('thumbs')
    ticks = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: ticks.append(1))
    heartbeat.start(10)
    host.start_deep_clean(scopes=['temp', 'thumbs'])
    progress = host.cleaner_progress_window
    pump(2, lambda: '5 个文件' in progress.stats.text())
    assert ticks, 'Event loop blocked during cleanup'
    image_path = os.environ.get('CLOCK_ALARM_SMOKE_IMAGE')
    if image_path:
        assert progress.grab().save(image_path)
    progress.close_button.click()
    assert not progress.isVisible()
    host.start_deep_clean(scopes=['temp'])
    assert host.cleaner_progress_window is progress and progress.isVisible()
    progress.cancel_button.click()
    assert progress.cancel_event.is_set() and not progress.cancel_button.isEnabled()
    pump(2, lambda: not host._cleaning)
    assert progress.status.text() == '清理已停止'
    assert progress.progress.value() == 0 and not progress.timer.isActive()
    assert not later_scopes
    assert logs and notifications
    cleaner._clean_temp = lambda report: None
    host.start_deep_clean(scopes=['temp'])
    pump(2, lambda: not host._cleaning)
    progress = host.cleaner_progress_window
    assert progress.status.text() == '清理完成'
    assert progress.progress.value() == progress.progress.maximum()
    assert progress.close_button.text() == '关闭'
    cleaner._clean_temp = fail
    host.start_deep_clean(scopes=['temp'])
    pump(2, lambda: not host._cleaning)
    assert '失败' in host.cleaner_progress_window.status.text()
    assert 'synthetic launch failure' in host.cleaner_progress_window.details.toPlainText()
    settings_ui.CleanerProgressDialog = fail
    host.start_deep_clean(scopes=['temp'])
    assert not host._cleaning and len(messages) == 4
    heartbeat.stop()
    print('PASS cleaner: live threaded updates, background/reopen, cancel, complete, errors')
    app.closeAllWindows()
    pump()
    assert not errors, errors


if __name__ == '__main__':
    main()
