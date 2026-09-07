import unittest
from pathlib import Path

from scripts.release_notes import extract_release_notes


class ReleaseNotesTests(unittest.TestCase):
    def test_only_requested_version_is_included(self):
        text = "# Changelog\r\n## [v1.0.15] - 2026-09-07\r\n\r\n新版本内容\r\n\r\n---\r\n## [v1.0.14]\r\n旧版本内容\r\n"
        self.assertEqual(extract_release_notes(text, "1.0.15"), "## Clock/Alarm v1.0.15\n\n新版本内容")

    def test_missing_or_empty_notes_fail_release_preparation(self):
        for text in ("## [v1.0.14]\nOlder release", "## [v1.0.15]\n\n---\n"):
            with self.assertRaises(ValueError):
                extract_release_notes(text, "1.0.15")

    def test_invalid_versions_are_rejected(self):
        for version in ("v1.0.15", "01.0.15", "1.0.15-rc1", "1.0.*", "1.0.15\n"):
            with self.assertRaises(ValueError):
                extract_release_notes("", version)

    def test_current_version_has_release_notes_and_matching_installer(self):
        root = Path(__file__).resolve().parents[1]
        version = (root / "VERSION").read_text().strip()
        notes = extract_release_notes((root / "CHANGELOG.md").read_text(encoding="utf-8-sig"), version)
        self.assertIn("截图", notes)
        self.assertIn("清理", notes)
        self.assertIn(f'#define MyAppVersion "{version}"',
                      (root / "installer" / "Clock-Alarm.iss").read_text(encoding="utf-8-sig"))
