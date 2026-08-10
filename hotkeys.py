"""Global hotkeys for the clock shell and region screenshot."""

from __future__ import annotations

import sys
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QTimer
from PyQt6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
HOTKEY_HUB = 0xD001
HOTKEY_SHOT_REGION = 0xD002
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004


def _user32():
    if sys.platform != "win32":
        return None
    import ctypes

    return ctypes.windll.user32


def parse_hotkey_combo(combo: str) -> tuple[int, int] | None:
    if not combo or not str(combo).strip():
        return None
    parts = [part.strip().upper() for part in str(combo).replace(" ", "").split("+") if part.strip()]
    modifiers = 0
    virtual_key: int | None = None
    for part in parts:
        if part in ("CTRL", "CONTROL"):
            modifiers |= MOD_CONTROL
        elif part == "ALT":
            modifiers |= MOD_ALT
        elif part == "SHIFT":
            modifiers |= MOD_SHIFT
        elif part in ("WIN", "META"):
            modifiers |= 0x0008
        elif len(part) == 1 and ("A" <= part <= "Z" or "0" <= part <= "9"):
            virtual_key = ord(part)
        elif part.startswith("F") and part[1:].isdigit():
            number = int(part[1:])
            if 1 <= number <= 24:
                virtual_key = 0x70 + number - 1
        elif part in ("PRINTSCREEN", "PRTSC"):
            virtual_key = 0x2C
        elif part == "SPACE":
            virtual_key = 0x20
    if virtual_key is None:
        return None
    return modifiers, virtual_key


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, handlers: dict[int, Callable[[], None]]) -> None:
        super().__init__()
        self.handlers = handlers

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == WM_HOTKEY:
            callback = self.handlers.get(int(msg.wParam))
            if callback:
                QTimer.singleShot(0, callback)
                return True, 0
        return False, 0


class ClockAlarmHotkeys:
    def __init__(
        self,
        *,
        open_hub: Callable[[], None],
        shot_region: Callable[[], None],
        hub_combo: str = "Ctrl+Alt+T",
        region_combo: str = "Ctrl+Alt+A",
    ) -> None:
        self.open_hub = open_hub
        self.shot_region = shot_region
        self.hub_combo = hub_combo
        self.region_combo = region_combo
        self._ids: list[int] = []
        self._handlers = {
            HOTKEY_HUB: open_hub,
            HOTKEY_SHOT_REGION: shot_region,
        }
        self._filter = _Filter(self._handlers)
        app = QApplication.instance()
        if app:
            app.installNativeEventFilter(self._filter)
        self._register_all()

    def _unregister(self) -> None:
        user32 = _user32()
        if not user32:
            return
        for hotkey_id in list(self._ids):
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._ids.clear()

    def _unregister_shots(self) -> None:
        user32 = _user32()
        if not user32:
            return
        try:
            user32.UnregisterHotKey(None, HOTKEY_SHOT_REGION)
        except Exception:
            pass
        if HOTKEY_SHOT_REGION in self._ids:
            self._ids.remove(HOTKEY_SHOT_REGION)

    @staticmethod
    def _configure_api(user32) -> None:
        import ctypes

        try:
            user32.RegisterHotKey.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.c_uint,
            ]
            user32.RegisterHotKey.restype = wintypes.BOOL
        except Exception:
            pass

    def _register_all(self) -> None:
        user32 = _user32()
        if not user32:
            return
        self._unregister()
        self._configure_api(user32)
        for hotkey_id, combo, fallback in (
            (HOTKEY_HUB, self.hub_combo, (MOD_CONTROL | MOD_ALT, ord("T"))),
            (HOTKEY_SHOT_REGION, self.region_combo, (MOD_CONTROL | MOD_ALT, ord("A"))),
        ):
            modifiers, virtual_key = parse_hotkey_combo(combo) or fallback
            if user32.RegisterHotKey(None, hotkey_id, int(modifiers), int(virtual_key)):
                self._ids.append(hotkey_id)

    def pause_screenshot_hotkeys(self) -> None:
        self._unregister_shots()

    def resume_screenshot_hotkeys(self) -> None:
        user32 = _user32()
        if not user32:
            return
        self._unregister_shots()
        self._configure_api(user32)
        modifiers, virtual_key = parse_hotkey_combo(self.region_combo) or (
            MOD_CONTROL | MOD_ALT,
            ord("A"),
        )
        if user32.RegisterHotKey(None, HOTKEY_SHOT_REGION, int(modifiers), int(virtual_key)):
            self._ids.append(HOTKEY_SHOT_REGION)

    def rebind(self, hub: str | None = None, region: str | None = None) -> str:
        if hub is not None:
            self.hub_combo = hub
        if region is not None:
            self.region_combo = region
        self._register_all()
        region_ok = HOTKEY_SHOT_REGION in self._ids
        status = "成功" if region_ok else "失败"
        return f"时钟 {self.hub_combo} · 区域截图 {self.region_combo}：{status}"

    def close(self) -> None:
        self._unregister()
