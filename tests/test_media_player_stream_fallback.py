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


if __name__ == "__main__":
    unittest.main()
