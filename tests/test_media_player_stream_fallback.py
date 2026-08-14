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
        self.assertIn("shutil.rmtree(self._media_cache_dir, ignore_errors=True)", source)
        self.assertIn("YtDlpStreamWorker", source)
        self.assertIn("prefetch", source)

    def test_quality_switcher_and_caching(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("_show_quality_menu", source)
        self.assertIn("_select_quality", source)
        self.assertIn("player_client': ['android', 'web']", source)


if __name__ == "__main__":
    unittest.main()
