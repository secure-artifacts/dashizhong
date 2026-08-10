from __future__ import annotations

import ast
import builtins
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cleaner
import storage
import autostart


ROOT = Path(__file__).resolve().parents[1]


class CleanerBoundaryTests(unittest.TestCase):
    def test_safe_defaults_exclude_irreversible_and_system_scopes(self) -> None:
        self.assertEqual(cleaner.DEFAULT_SCOPES, ["temp", "thumbs"])
        self.assertNotIn("recycle", cleaner.DEFAULT_SCOPES)
        self.assertNotIn("wu", cleaner.DEFAULT_SCOPES)
        self.assertNotIn("delivery", cleaner.DEFAULT_SCOPES)

    def test_empty_scope_never_expands_to_defaults(self) -> None:
        with mock.patch.object(cleaner, "_clean_temp") as clean_temp:
            report = cleaner.run_selective_clean([])
        clean_temp.assert_not_called()
        self.assertIn("未选择任何清理范围", report.notes)

    def test_temp_roots_ignore_temp_and_tmp_environment_values(self) -> None:
        dangerous = Path.cwd()
        local = Path(r"C:\Users\Example\AppData\Local")
        windows = Path(r"C:\Windows")
        with (
            mock.patch.dict(
                os.environ,
                {"TEMP": str(dangerous), "TMP": str(dangerous)},
                clear=False,
            ),
            mock.patch.object(cleaner, "_trusted_local_appdata", return_value=local),
            mock.patch.object(cleaner, "_trusted_windows_directory", return_value=windows),
        ):
            roots = [path for _label, path in cleaner._temp_roots()]
        self.assertNotIn(dangerous, roots)
        self.assertIn(local / "Temp", roots)
        self.assertIn(windows / "Temp", roots)

    def test_windows_reparse_attribute_is_detected(self) -> None:
        fake_stat = SimpleNamespace(
            st_file_attributes=cleaner._FILE_ATTRIBUTE_REPARSE_POINT,
            st_mode=stat.S_IFDIR,
        )
        with mock.patch.object(cleaner.os, "lstat", return_value=fake_stat):
            self.assertTrue(cleaner._is_reparse_point(Path("junction")))

    def test_recursive_clean_skips_a_reparse_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "approved"
            root.mkdir()
            ordinary = root / "ordinary.tmp"
            ordinary.write_text("delete me", encoding="utf-8")
            escape = root / "escape"
            escape.mkdir()
            sentinel = escape / "sentinel.txt"
            sentinel.write_text("keep me", encoding="utf-8")

            real_check = cleaner._is_reparse_point

            def marked(path: Path) -> bool:
                candidate = Path(path)
                try:
                    if candidate.samefile(escape):
                        return True
                except OSError:
                    pass
                return real_check(candidate)

            report = cleaner.CleanReport()
            with mock.patch.object(cleaner, "_is_reparse_point", side_effect=marked):
                cleaner._clear_directory_contents(root, report, "测试根")

            self.assertFalse(ordinary.exists())
            self.assertTrue(sentinel.exists())
            self.assertTrue(any("已跳过目录链接" in error for error in report.errors))

    def test_dangerous_root_is_rejected(self) -> None:
        report = cleaner.CleanReport()
        result = cleaner._validated_cleanup_root(Path.cwd(), report, "工作目录")
        self.assertIsNone(result)
        self.assertTrue(any("危险" in error for error in report.errors))


class ConsentAndLifecyclePolicyTests(unittest.TestCase):
    def test_first_run_autostart_is_off(self) -> None:
        prefs = storage.DEFAULT_STATE["prefs"]
        self.assertFalse(prefs["autostart"])
        self.assertFalse(prefs["autostart_consent"])

    def test_packaged_launcher_is_the_only_autostart_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = Path(temp_dir) / "Clock-Alarm.exe"
            launcher.write_bytes(b"MZ")
            with mock.patch.dict(
                os.environ,
                {"CLOCK_ALARM_LAUNCHER": str(launcher)},
                clear=False,
            ):
                self.assertEqual(
                    autostart._launch_command(),
                    f'"{launcher.resolve()}"',
                )

    def test_main_has_no_unconditional_autostart_enable(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("set_autostart(True)", source)
        self.assertIn("autostart_consent", source)

    def test_settings_are_reachable_from_both_current_menus(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        clock_source = (ROOT / "world_clock_ui.py").read_text(encoding="utf-8")
        self.assertIn('QAction("设置"', main_source)
        self.assertIn('QAction("⚙️  设置"', clock_source)
        self.assertIn("host.show_settings()", clock_source)

    def test_installer_does_not_create_autostart_without_app_consent(self) -> None:
        source = (ROOT / "installer" / "Clock-Alarm.iss").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Tasks: autostart", source)
        self.assertNotIn('Name: "autostart"', source)
        self.assertIn("ValueType: none", source)

    def test_recorder_cancel_does_not_create_predictable_output(self) -> None:
        source = (ROOT / "recorder_ui.py").read_text(encoding="utf-8")
        self.assertNotIn("_discard_", source)
        self.assertNotIn("self.cmb_filter", source)
        self.assertIn("rec.discard()", source)
        self.assertIn("shutdown_for_exit", source)

    def test_ffmpeg_lookup_fails_closed_without_managed_binary(self) -> None:
        source = (ROOT / "screen_recorder.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_ffmpeg_bin"
        )
        namespace = {"Path": Path}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "screen_recorder.py"), "exec"), namespace)
        real_import = builtins.__import__

        def deny_imageio(name, *args, **kwargs):
            if name == "imageio_ffmpeg":
                raise ImportError("unavailable")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=deny_imageio):
            with self.assertRaises(RuntimeError):
                namespace["_ffmpeg_bin"]()

    def test_media_queue_has_hard_limits_and_cancellation(self) -> None:
        source = (ROOT / "media_player_ui.py").read_text(encoding="utf-8")
        self.assertIn("MAX_QUEUE_ITEMS = 500", source)
        self.assertIn("MAX_INPUT_URLS = 20", source)
        self.assertIn("self.extractor.cancel()", source)
        self.assertIn("len(self.playlist) >= MAX_QUEUE_ITEMS", source)


class ReleaseBoundaryTests(unittest.TestCase):
    def test_runtime_requirements_are_exactly_pinned(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        active = [
            line.strip()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(active)
        for requirement in active:
            package_part = requirement.split(";", 1)[0].strip()
            self.assertIn("==", package_part)
            self.assertNotIn(">=", package_part)

    def test_release_actions_are_pinned_to_full_commit_ids(self) -> None:
        import re

        for workflow_name in ("release.yml", "codeql.yml"):
            source = (
                ROOT / ".github" / "workflows" / workflow_name
            ).read_text(encoding="utf-8")
            uses = re.findall(r"^\s*uses:\s*([^#\s]+)", source, re.MULTILINE)
            self.assertTrue(uses)
            for action in uses:
                self.assertRegex(action, r"@(?:[0-9a-f]{40})$")

    def test_release_tag_is_not_interpolated_inside_shell_source(self) -> None:
        source = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('$tag = "${{ github.ref_name }}"', source)
        self.assertIn("$env:RELEASE_TAG -match", source)

    def test_offline_launcher_has_no_absolute_development_path(self) -> None:
        source = (ROOT / "launcher" / "ClockAlarmLauncher.cs").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(".gemini", source.lower())
        self.assertNotIn("antigravity", source.lower())
        self.assertIn('Path.Combine(root, "runtime")', source)


if __name__ == "__main__":
    unittest.main()
