from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "media_player_ui.py"


def _load_topmost_method():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    player_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MediaPlayerWindow"
    )
    method = next(
        node
        for node in player_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "set_always_on_top"
    )
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {
        "Qt": SimpleNamespace(
            WindowType=SimpleNamespace(WindowStaysOnTopHint="top-most")
        )
    }
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace["set_always_on_top"]


class _FakeButton:
    def __init__(self) -> None:
        self.tooltip = ""

    def setToolTip(self, text: str) -> None:
        self.tooltip = text


class _FakeWindow:
    def __init__(self, *, fullscreen: bool = False) -> None:
        self._always_on_top = False
        self.is_fullscreen = fullscreen
        self.always_on_top_btn = _FakeButton()
        self.flag_calls = []
        self.show_calls = 0
        self.fullscreen_calls = 0
        self.restored_geometry = None

    def isFullScreen(self) -> bool:
        return self.is_fullscreen

    def saveGeometry(self):
        return b"normal-geometry"

    def setWindowFlag(self, flag, enabled: bool) -> None:
        self.flag_calls.append((flag, enabled))

    def show(self) -> None:
        self.show_calls += 1

    def showFullScreen(self) -> None:
        self.fullscreen_calls += 1

    def restoreGeometry(self, geometry) -> None:
        self.restored_geometry = geometry


class MediaPlayerTopMostTests(unittest.TestCase):
    def test_player_layout_has_responsive_minimums(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("self.setMinimumSize(540, 360)", source)
        self.assertIn("self.queue_widget.setMinimumWidth(260)", source)
        self.assertIn("self.queue_widget.setMaximumWidth(320)", source)

    def test_button_uses_drawn_checkable_icon_and_is_added_to_controls(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("def _draw_pin", source)
        self.assertIn("self.always_on_top_btn.setCheckable(True)", source)
        self.assertIn("_make_dual_icon(_draw_pin, 18)", source)
        self.assertIn("controls.addWidget(self.always_on_top_btn)", source)

    def test_topmost_toggle_preserves_normal_geometry(self) -> None:
        toggle = _load_topmost_method()
        window = _FakeWindow()

        toggle(window, True)

        self.assertTrue(window._always_on_top)
        self.assertEqual(window.flag_calls, [("top-most", True)])
        self.assertEqual(window.show_calls, 1)
        self.assertEqual(window.fullscreen_calls, 0)
        self.assertEqual(window.restored_geometry, b"normal-geometry")
        self.assertEqual(window.always_on_top_btn.tooltip, "取消置顶")

    def test_quality_and_collapse_buttons_exist(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertIn("self.quality_btn", source)
        self.assertIn("self.toggle_playlist_btn", source)
        self.assertIn("def toggle_playlist_panel", source)


if __name__ == "__main__":
    unittest.main()
