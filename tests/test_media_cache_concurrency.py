"""Exercise real worker synchronization with fake downloads in private test dirs."""
import ast
import hashlib
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from test_recorder_clock_recovery import method


class FakeQObject:
    def __init__(self, parent=None):
        pass


def worker_class(download):
    source = Path(__file__).resolve().parents[1] / 'media_player_ui.py'
    node = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                if isinstance(n, ast.ClassDef) and n.name == 'YtDlpStreamWorker')
    namespace = dict(QObject=FakeQObject, pyqtSignal=lambda *args: Mock(),
                     threading=threading, Path=Path, hashlib=hashlib, shutil=shutil,
                     MAX_COMPAT_CACHE_BYTES=512 * 1024 * 1024,
                     yt_dlp=SimpleNamespace(YoutubeDL=download,
                                            utils=SimpleNamespace(DownloadCancelled=RuntimeError)))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 str(source), 'exec'), namespace)
    return namespace['YtDlpStreamWorker']


class CacheConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        test = self
        class Download:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download=True):
                test.calls.append(url)
                test.entered.set()
                if not test.release.wait(2):
                    raise RuntimeError('test download timeout')
                for hook in self.opts['progress_hooks']:
                    hook({})
                Path(self.opts['outtmpl'].replace('%(ext)s', 'mp4')).write_bytes(b'fake-complete-video')
                return {}
        self.worker = worker_class(Download)()

    def joined(self, thread):
        self.assertIsNotNone(thread)
        thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_duplicate_prefetch_is_single_writer_and_playback_reuses_result(self):
        self.release.clear()
        first = self.worker.prefetch('https://test.invalid/a', 720, self.temp.name)
        self.assertTrue(self.entered.wait(1))
        for _ in range(20):
            self.assertIsNone(self.worker.prefetch('https://test.invalid/a', 720, self.temp.name))
        self.release.set()
        self.joined(first)
        self.joined(self.worker.load_media(1, 'https://test.invalid/a', 720, self.temp.name))
        self.assertEqual(len(self.calls), 1)
        self.worker.media_ready.emit.assert_called_once()
        self.assertTrue(Path(self.worker.media_ready.emit.call_args.args[1]).is_file())

    def test_foreground_cancels_prefetch_without_two_writers(self):
        self.release.clear()
        first = self.worker.prefetch('https://test.invalid/a', 0, self.temp.name)
        self.assertTrue(self.entered.wait(1))
        foreground = self.worker.load_media(2, 'https://test.invalid/b', 0, self.temp.name)
        time.sleep(0.05)
        self.assertEqual(len(self.calls), 1)
        self.release.set()
        self.joined(first)
        self.joined(foreground)
        self.assertEqual(self.calls, ['https://test.invalid/a', 'https://test.invalid/b'])
        self.worker.error.emit.assert_not_called()
        self.assertEqual(self.worker.media_ready.emit.call_args.args[0], 2)

    def test_stop_drops_delayed_download_completion(self):
        self.release.clear()
        foreground = self.worker.load_media(3, 'https://test.invalid/a', 0, self.temp.name)
        self.assertTrue(self.entered.wait(1))
        self.worker.cancel()
        self.release.set()
        self.joined(foreground)
        self.worker.media_ready.emit.assert_not_called()
        self.worker.error.emit.assert_not_called()

    def test_cache_retirement_waits_for_writer_and_does_not_recreate_root(self):
        root = Path(self.temp.name) / 'owned-cache'
        self.release.clear()
        first = self.worker.prefetch('https://test.invalid/a', 0, str(root))
        self.assertTrue(self.entered.wait(1))
        cleanup = self.worker.retire_cache(str(root))
        time.sleep(0.05)
        self.assertTrue(root.exists())
        self.release.set()
        self.joined(first)
        self.joined(cleanup)
        self.assertFalse(root.exists())

    def test_quality_is_part_of_cache_identity(self):
        for request, height in enumerate((360, 720, 360)):
            self.joined(self.worker.load_media(request, 'https://test.invalid/a', height, self.temp.name))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.worker.media_ready.emit.call_count, 3)

    def test_partial_and_unmerged_files_are_not_playable(self):
        class PartialDownload:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def extract_info(self, *args, **kwargs):
                for ext in ('mp4.part', 'f137.mp4', 'info.json'):
                    Path(self.opts['outtmpl'].replace('%(ext)s', ext)).write_bytes(b'partial')
        worker = worker_class(PartialDownload)()
        self.joined(worker.load_media(1, 'https://test.invalid/a', 0, self.temp.name))
        worker.media_ready.emit.assert_not_called()
        worker.error.emit.assert_called_once()


class PlaybackModeTests(unittest.TestCase):
    def test_sequence_wrap_and_single_loop(self):
        play_next = method('media_player_ui.py', 'MediaPlayerWindow', 'play_next')
        window = SimpleNamespace(playlist=['a', 'b'], current_index=1,
                                 play_mode='sequence', play_index=Mock())
        play_next(window)
        window.play_index.assert_called_with(0)
        window.play_mode = 'single_loop'
        play_next(window)
        window.play_index.assert_called_with(1)

    def test_random_uses_valid_playlist_index(self):
        rng = Mock()
        rng.randint.return_value = 2
        window = SimpleNamespace(playlist=['a', 'b', 'c'], current_index=0,
                                 play_mode='random', play_index=Mock())
        method('media_player_ui.py', 'MediaPlayerWindow', 'play_next', random=rng)(window)
        rng.randint.assert_called_once_with(0, 2)
        window.play_index.assert_called_once_with(2)

    def test_stale_end_event_does_not_advance_after_stop_or_switch(self):
        timer, player = Mock(), Mock()
        window = SimpleNamespace(_is_changing_media=False, _media_cache_dir='private',
                                 _current_request_id=1, play_next=Mock())
        status = player.MediaStatus.EndOfMedia
        method('media_player_ui.py', 'MediaPlayerWindow', '_on_media_status_changed',
               QMediaPlayer=player, QTimer=timer)(window, status)
        window._current_request_id = 2
        timer.singleShot.call_args.args[1]()
        window.play_next.assert_not_called()
