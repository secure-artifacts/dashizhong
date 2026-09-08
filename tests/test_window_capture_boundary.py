import unittest
from unittest.mock import patch

import numpy as np
import screen_recorder as sr


class WindowCaptureTests(unittest.TestCase):
    def test_unavailable_window_never_falls_back_to_desktop(self):
        for target in ({'hwnd': 42, 'kind': 'browser'}, {'hwnd': 0, 'kind': 'window'}):
            with self.subTest(target=target), patch.object(sr, 'capture_window_locked', return_value=None) as locked, patch.object(sr, 'mss') as desktop:
                self.assertIsNone(sr.capture_bgr({'left': 0, 'top': 0, 'width': 80, 'height': 80}, target))
                locked.assert_called_once_with(target['hwnd'])
                desktop.mss.assert_not_called()

    def test_valid_window_uses_only_target_pixels(self):
        pixels = np.zeros((30, 40, 3), dtype=np.uint8)
        with patch.object(sr, 'capture_window_locked', return_value=pixels), patch.object(sr, 'mss') as desktop:
            self.assertIs(sr.capture_bgr(target={'hwnd': 42}), pixels)
            desktop.mss.assert_not_called()

    def test_minimized_or_closed_target_has_no_desktop_fallback(self):
        with patch.object(sr.win32gui, 'IsWindow', return_value=False):
            self.assertIsNone(sr.capture_window_locked(42))
        with patch.object(sr.win32gui, 'IsWindow', return_value=True), patch.object(sr.win32gui, 'IsIconic', return_value=True), patch.object(sr.win32gui, 'GetWindowDC') as dc:
            self.assertIsNone(sr.capture_window_locked(42))
            dc.assert_not_called()

    def test_explicit_screen_capture_still_uses_screen_backend(self):
        with patch.object(sr, 'mss') as desktop:
            desktop.mss.return_value.__enter__.return_value.grab.return_value = np.zeros((20, 30, 4), dtype=np.uint8)
            frame = sr.capture_bgr({'left': 0, 'top': 0, 'width': 30, 'height': 20}, {'kind': 'screen', 'hwnd': 0})
            self.assertEqual(frame.shape, (20, 30, 3))
            desktop.mss.return_value.__enter__.return_value.grab.assert_called_once()


if __name__ == '__main__':
    unittest.main()
