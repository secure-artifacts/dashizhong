from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "media_player_ui.py"


class MediaStreamFallbackTests(unittest.TestCase):
    def test_source_contains_bounded_temporary_fallback(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("MAX_COMPAT_CACHE_BYTES = 512 * 1024 * 1024", source)
        self.assertIn("tempfile.mkdtemp(prefix=\"ClockAlarm-media-\")", source)
        self.assertIn("self.stream_worker.retire_cache(self._media_cache_dir)", source)
        self.assertIn("YtDlpStreamWorker", source)
        self.assertIn("prefetch", source)

    def test_quality_switcher_and_caching(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("_show_quality_menu", source)
        self.assertIn("_select_quality", source)
        self.assertIn("player_client': ['ios', 'visionos', 'mweb', 'android', 'web']", source)
        self.assertIn("fallback_opts['extractor_args'] = {'youtube': {'player_client': ['mweb', 'web_safari', 'ios', 'web']}}", source)

    def test_normalize_cookie_content(self) -> None:
        from media_player_ui import normalize_cookie_content
        self.assertEqual(normalize_cookie_content(""), "")
        self.assertEqual(normalize_cookie_content("   "), "")

        netscape_raw = ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\taf8723\n"
        norm = normalize_cookie_content(netscape_raw)
        self.assertTrue(norm.startswith("# Netscape HTTP Cookie File"))
        self.assertIn("LOGIN_INFO\taf8723", norm)

        json_raw = '[{"name": "LOGIN_INFO", "value": "token999", "domain": ".youtube.com", "secure": true}]'
        norm = normalize_cookie_content(json_raw)
        self.assertIn("# Netscape HTTP Cookie File", norm)
        self.assertIn("LOGIN_INFO\ttoken999", norm)

        header_raw = "Cookie: SID=abc12345; HSID=xyz678;"
        norm = normalize_cookie_content(header_raw)
        self.assertIn("# Netscape HTTP Cookie File", norm)
        self.assertIn(".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tabc12345", norm)

        import base64
        b64_raw = base64.b64encode(b'{"name": "LOGIN_INFO", "value": "b64token", "domain": ".youtube.com"}').decode()
        norm = normalize_cookie_content(b64_raw)
        self.assertIn("# Netscape HTTP Cookie File", norm)
        self.assertIn("LOGIN_INFO\tb64token", norm)

    def test_settings_dialog_has_cookies_ui(self) -> None:
        settings_source = (ROOT / "settings_ui.py").read_text(encoding="utf-8")
        self.assertIn("cookies_toggle", settings_source)
        self.assertIn("cookies_card", settings_source)
        self.assertIn("cookies_edit", settings_source)
        self.assertIn("normalize_cookie_content", settings_source)
        self.assertIn("_show_cookie_help", settings_source)

    def test_media_cache_lru_and_clear(self) -> None:
        import tempfile
        import time
        import os
        from media_player_ui import get_media_cache_size, prune_media_cache, clear_media_cache

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            f1 = tmppath / "media-1.mp4"
            f2 = tmppath / "media-2.mp4"
            f3 = tmppath / "media-3.mp4"
            f1.write_bytes(b"A" * 1000)
            f2.write_bytes(b"B" * 2000)
            f3.write_bytes(b"C" * 3000)

            self.assertEqual(get_media_cache_size(tmppath), 6000)

            now = time.time()
            os.utime(f1, (now - 300, now - 300))
            os.utime(f2, (now - 200, now - 200))
            os.utime(f3, (now - 100, now - 100))

            freed = prune_media_cache(tmppath, max_bytes=4000)
            self.assertEqual(freed, 3000)
            self.assertFalse(f1.exists())
            self.assertFalse(f2.exists())
            self.assertTrue(f3.exists())
            self.assertEqual(get_media_cache_size(tmppath), 3000)

            freed_all = clear_media_cache(tmppath)
            self.assertEqual(freed_all, 3000)
            self.assertFalse(f3.exists())
            self.assertEqual(get_media_cache_size(tmppath), 0)

    def test_settings_and_cleaner_contain_cache_integration(self) -> None:
        settings_source = (ROOT / "settings_ui.py").read_text(encoding="utf-8")
        self.assertIn("cache_limit_spin", settings_source)
        self.assertIn("btn_clear_cache", settings_source)
        self.assertIn("_clear_cache_action", settings_source)
        self.assertIn("prune_media_cache", settings_source)

        cleaner_source = (ROOT / "cleaner.py").read_text(encoding="utf-8")
        self.assertIn("Clock/Alarm 媒体缓存", cleaner_source)


if __name__ == "__main__":
    unittest.main()

