import ast
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def method(filename, cls, name, **globals_):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), filename, 'exec'), ns)
    return ns[name]


class RecoveryTests(unittest.TestCase):
    def test_preparation_failure_restores_recorder_controls(self):
        board = SimpleNamespace(_start_session=Mock(side_effect=OSError('unavailable')),
                                recorder=None, _on_save_finished=Mock())
        method('recorder_ui.py', 'FloatingRecorderBoard', '_start')(board)
        self.assertIn('unavailable', board._on_save_finished.call_args.args[0])

    def test_save_dialog_failure_delegates_cleanup_off_gui_thread(self):
        board = SimpleNamespace(_stop_session=Mock(side_effect=OSError('denied')),
                                recorder=Mock(), _finalize_session=Mock())
        method('recorder_ui.py', 'FloatingRecorderBoard', '_stop')(board)
        board.recorder.discard.assert_not_called()
        path, message = board._finalize_session.call_args.args
        self.assertIsNone(path)
        self.assertIn('denied', message)

    def test_pause_is_ignored_while_save_dialog_or_worker_is_active(self):
        board = SimpleNamespace(_busy_stop=True, recorder=Mock())
        method('recorder_ui.py', 'FloatingRecorderBoard', '_pause_resume')(board)
        board.recorder.pause.assert_not_called()
        board.recorder.resume.assert_not_called()

    def test_double_stop_opens_one_nonblocking_dialog_even_when_paused(self):
        factory = Mock()
        board = SimpleNamespace(recorder=Mock(is_paused=True), _busy_stop=False,
                                _closing=False, embedded=False, showNormal=Mock(), raise_=Mock(),
                                _set_status=Mock(), txt_save_dir=Mock(),
                                _timestamp=lambda: 'test', _save_dialog_finished=Mock())
        board.txt_save_dir.text.return_value = 'recordings'
        board._set_save_busy = lambda: setattr(board, '_busy_stop', True)
        stop = method('recorder_ui.py', 'FloatingRecorderBoard', '_stop_session',
                      Path=Path, QFileDialog=factory, Qt=Mock())
        stop(board)
        stop(board)
        factory.assert_called_once()
        factory.return_value.open.assert_called_once()
        factory.return_value.exec.assert_not_called()
        board.recorder.pause.assert_called_once()

    def test_dialog_completion_cannot_start_two_save_workers(self):
        dialog = Mock()
        dialog.selectedFiles.return_value = ['recording.mp4']
        board = SimpleNamespace(_save_dialog=dialog, _closing=False, _finalize_session=Mock())
        finish = method('recorder_ui.py', 'FloatingRecorderBoard', '_save_dialog_finished',
                        QFileDialog=object)
        finish(board, dialog, True)
        finish(board, dialog, True)
        board._finalize_session.assert_called_once_with('recording.mp4')
        dialog.deleteLater.assert_called_once()

    def test_saving_disables_both_control_surfaces_and_hides_overlay(self):
        board = SimpleNamespace(_busy_stop=False, duration_timer=Mock(), preview_timer=Mock(),
                                btn_rec=Mock(), btn_pause=Mock(), btn_stop=Mock(),
                                control_bar=Mock(), overlay=Mock())
        method('recorder_ui.py', 'FloatingRecorderBoard', '_set_save_busy')(board)
        self.assertTrue(board._busy_stop)
        board.btn_stop.setEnabled.assert_called_once_with(False)
        board.control_bar.btn_stop.setEnabled.assert_called_once_with(False)
        board.overlay.set_draw_mode.assert_called_once_with(False)
        board.overlay.hide.assert_called_once()
        board.preview_timer.stop.assert_called_once()

    def test_overlay_native_input_mode_does_not_steal_window_order(self):
        con = SimpleNamespace(SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_NOZORDER=4,
                              SWP_NOACTIVATE=16, SWP_FRAMECHANGED=32)
        for drawing in (True, False):
            with self.subTest(drawing=drawing):
                gui = Mock()
                gui.GetWindowLong.return_value = 0x08000020
                overlay = SimpleNamespace(winId=lambda: 123, is_draw_mode=drawing)
                method('recorder_ui.py', 'RecordingDrawOverlay', '_apply_input_mode',
                       win32gui=gui, win32con=con)(overlay)
                style = gui.SetWindowLong.call_args.args[2]
                self.assertEqual(bool(style & 0x20), not drawing)
                self.assertEqual(bool(style & 0x08000000), not drawing)
                flags = gui.SetWindowPos.call_args.args[-1]
                self.assertTrue(flags & con.SWP_NOZORDER)
                self.assertTrue(flags & con.SWP_NOACTIVATE)

    def test_capture_failure_marks_session_stopped(self):
        recorder = SimpleNamespace(is_recording=True, _error='',
                                   _capture_loop=Mock(side_effect=RuntimeError('capture failed')))
        method('screen_recorder.py', 'ScreenRecorder', '_video_loop')(recorder)
        self.assertFalse(recorder.is_recording)
        self.assertIn('capture failed', recorder._error)

    def test_open_tools_switches_existing_window_to_requested_tab(self):
        buttons = [Mock(), Mock(), Mock()]
        clock = SimpleNamespace(detail_stack=Mock(), tools_window=Mock(), tools_buttons=buttons)
        method('world_clock_ui.py', 'FloatingWorldClock', 'show_tools')(clock, 2)
        clock.detail_stack.setCurrentIndex.assert_called_once_with(2)
        clock.tools_window.showNormal.assert_called_once()
        buttons[2].setChecked.assert_called_once_with(True)
        buttons[0].setChecked.assert_called_once_with(False)

    def test_capture_error_offers_save_instead_of_discarding_recording(self):
        board = SimpleNamespace(recorder=SimpleNamespace(is_recording=False, _error='window closed'),
                                _busy_stop=False, duration_timer=Mock(), _stop=Mock(), _set_status=Mock())
        method('recorder_ui.py', 'FloatingRecorderBoard', '_tick')(board)
        board._stop.assert_called_once()
        self.assertIn('window closed', board._set_status.call_args.args[0])


class AudioStartupTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'screen_recorder.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AudioRecorder')
        self.sd = Mock()
        self.sd.query_devices.return_value = {'max_input_channels': 2}
        self.wave = Mock()
        self.threading = Mock()
        self.ffmpeg = Mock(return_value='ffmpeg.exe')
        ns = dict(queue=queue, sd=self.sd, wave=self.wave, threading=self.threading,
                  _ffmpeg_bin=self.ffmpeg, AudioLevels=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                     'screen_recorder.py', 'exec'), ns)
        self.AudioRecorder = ns['AudioRecorder']

    def test_selected_mic_and_system_start_pause_resume_and_stop(self):
        mic, system = Mock(), Mock()
        self.sd.InputStream.side_effect = [mic, system]
        rec = self.AudioRecorder(0, 1, 'test.wav')
        rec.start()
        self.assertTrue(rec.is_recording)
        mic.start.assert_called_once()
        system.start.assert_called_once()
        self.wave.open.assert_called_once_with('test.wav', 'wb')
        callback = self.sd.InputStream.call_args_list[0].kwargs['callback']
        rec.pause()
        callback(Mock(), 10, None, None)
        self.assertTrue(rec.q_mic.empty())
        rec.resume()
        callback(Mock(), 10, None, None)
        self.assertFalse(rec.q_mic.empty())
        rec.stop()
        self.assertFalse(rec.is_recording)
        mic.close.assert_called_once()
        system.close.assert_called_once()
        self.wave.open.return_value.close.assert_called_once()

    def test_no_audio_does_not_require_ffmpeg_or_open_devices(self):
        rec = self.AudioRecorder(None, None, 'test.wav')
        rec.start()
        self.ffmpeg.assert_not_called()
        self.sd.InputStream.assert_not_called()
        self.wave.open.assert_not_called()
        rec.stop()

    def test_missing_ffmpeg_reports_cause_without_starting_devices(self):
        self.ffmpeg.side_effect = RuntimeError('missing encoder')
        rec = self.AudioRecorder(0, None, 'test.wav')
        with self.assertRaisesRegex(RuntimeError, 'FFmpeg'):
            rec.start()
        self.assertFalse(rec.is_recording)
        self.sd.InputStream.assert_not_called()

    def test_system_start_failure_closes_both_streams(self):
        mic, system = Mock(), Mock()
        system.start.side_effect = RuntimeError('device busy')
        self.sd.InputStream.side_effect = [mic, system]
        rec = self.AudioRecorder(0, 1, 'test.wav')
        with self.assertRaisesRegex(RuntimeError, 'device busy'):
            rec.start()
        self.assertFalse(rec.is_recording)
        mic.close.assert_called_once()
        system.close.assert_called_once()
        self.wave.open.assert_not_called()
        rec.stop()  # UI cleanup is safe after a failed start.
        mic.close.assert_called_once()

    def test_wav_open_failure_releases_device(self):
        stream = self.sd.InputStream.return_value
        self.wave.open.side_effect = OSError('disk full')
        rec = self.AudioRecorder(0, None, 'test.wav')
        with self.assertRaisesRegex(OSError, 'disk full'):
            rec.start()
        self.assertFalse(rec.is_recording)
        stream.close.assert_called_once()
