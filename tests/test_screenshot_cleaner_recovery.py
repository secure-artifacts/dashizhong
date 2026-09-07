import itertools
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cleaner
from test_recorder_clock_recovery import method


class ScreenshotWindowTests(unittest.TestCase):
    class Window:
        def __init__(self):
            self.visible = True
        def isVisible(self):
            return self.visible
        def hide(self):
            self.visible = False
        def show(self):
            self.visible = True

    def test_controller_is_not_mistaken_for_a_window(self):
        clock, tools, todo, notes = [self.Window() for _ in range(4)]
        clock.tools_window = tools
        host = SimpleNamespace(world_clock_board=clock, recorder_board=None,
                               media_player_board=None, cleaner_progress_window=None,
                               todo_board=SimpleNamespace(windows={'one': todo}, manager_win=None),
                               notes_ctl=SimpleNamespace(windows={'one': notes}, manager_win=None))
        windows = method('main.py', 'ClockAlarmApp', '_screenshot_windows', QWidget=self.Window)(host)
        self.assertEqual(set(windows), {clock, tools, todo, notes})

    def test_failure_while_hiding_restores_previous_windows(self):
        first, broken = self.Window(), self.Window()
        broken.hide = Mock(side_effect=RuntimeError('window unavailable'))
        host = SimpleNamespace(_screenshot_active=False, _screenshot_windows=lambda: [first, broken])
        messages = Mock()
        method('main.py', 'ClockAlarmApp', 'start_screenshot_region',
               QTimer=Mock(), QMessageBox=messages)(host)
        self.assertTrue(first.visible)
        self.assertFalse(host._screenshot_active)
        messages.warning.assert_called_once()

    def test_repeated_hotkey_does_not_queue_multiple_editors(self):
        window = self.Window()
        host = SimpleNamespace(_screenshot_active=False, _screenshot_windows=lambda: [window])
        timer = Mock()
        start = method('main.py', 'ClockAlarmApp', 'start_screenshot_region',
                       QTimer=timer, QMessageBox=Mock())
        start(host)
        start(host)
        timer.singleShot.assert_called_once()
        self.assertFalse(window.visible)


class CleanerProgressTests(unittest.TestCase):
    def test_progress_reports_incremental_counts_from_isolated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(3):
                (root / f'cache-{i}.tmp').write_bytes(b'x' * 10)
            snapshots = []
            with patch.object(cleaner, '_temp_roots', return_value=[('测试目录', root)]), \
                 patch.object(cleaner.time, 'monotonic', side_effect=itertools.count()):
                report = cleaner.run_selective_clean(['temp'], on_progress=snapshots.append)
            self.assertEqual(report.files_removed, 3)
            self.assertEqual(report.bytes_freed, 30)
            self.assertTrue(any(p.files_removed == 1 for p in snapshots))
            self.assertEqual(snapshots[-1].completed_scopes, 1)
            self.assertEqual(snapshots[-1].total_scopes, 1)
            self.assertEqual(snapshots[-1].bytes_freed, 30)
            self.assertEqual(snapshots[0].files_removed, 0)
            self.assertIsNone(report._context)
            self.assertTrue(root.is_dir())

    def test_stop_preserves_remaining_files_and_skips_later_scopes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(3):
                (root / f'cache-{i}.tmp').write_bytes(b'test')
            cancel = threading.Event()
            snapshots = []
            def update(progress):
                snapshots.append(progress)
                if progress.files_removed >= 1:
                    cancel.set()
            with patch.object(cleaner, '_temp_roots', return_value=[('测试目录', root)]), \
                 patch.object(cleaner, '_clean_thumbs') as later, \
                 patch.object(cleaner.time, 'monotonic', side_effect=itertools.count()):
                report = cleaner.run_selective_clean(['temp', 'thumbs'],
                                                     on_progress=update, cancel_event=cancel)
            self.assertTrue(report.cancelled)
            self.assertEqual(report.files_removed, 1)
            self.assertEqual(len(list(root.iterdir())), 2)
            later.assert_not_called()
            self.assertEqual(snapshots[-1].completed_scopes, 0)
            self.assertIn('已停止', report.summary())

    def test_pre_cancelled_run_never_touches_selected_scope(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(cleaner, '_clean_temp') as clean:
            report = cleaner.run_selective_clean(['temp'], cancel_event=cancel)
        clean.assert_not_called()
        self.assertTrue(report.cancelled)

    def test_scope_exception_still_produces_terminal_report(self):
        done = Mock()
        with patch.object(cleaner, '_clean_temp', side_effect=RuntimeError('test failure')):
            thread = cleaner.run_deep_clean_async(done, scopes=['temp'])
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        done.assert_called_once()
        report = done.call_args.args[0]
        self.assertTrue(report.failed)
        self.assertIn('test failure', report.errors[0])

    def test_broken_progress_observer_does_not_abort_worker(self):
        with patch.object(cleaner, '_clean_temp') as clean:
            report = cleaner.run_selective_clean(['temp'],
                on_progress=Mock(side_effect=RuntimeError('observer closed')))
        clean.assert_called_once()
        self.assertFalse(report.failed)
