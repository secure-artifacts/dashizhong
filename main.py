"""SuperTools application shell for the retained desktop tools."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from cleaner import CleanReport, run_deep_clean_async
from hotkeys import ToolkitHotkeys
from skin import bundle_root
from storage import JsonStore
from theme import apply_app_palette


def _install_exception_hooks() -> Path:
    log_path = Path(__file__).resolve().parent / "DesktopToolkit-error.log"
    if getattr(sys, "frozen", False):
        log_path = Path(sys.executable).resolve().parent / "DesktopToolkit-error.log"

    def _write(message: str) -> None:
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(message if message.endswith("\n") else message + "\n")
        except OSError:
            pass

    def _hook(exc_type, exc_value, exc_traceback) -> None:
        _write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}]\n"
            + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        )

    sys.excepthook = _hook

    class _Logger:
        def write(self, message):
            _write(message)

        def flush(self):
            pass

    if sys.stdout is None or getattr(sys, "frozen", False):
        sys.stdout = _Logger()
        sys.stderr = _Logger()
    return log_path


class ToolkitApp(QObject):
    clean_finished = pyqtSignal(object)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.store = JsonStore()
        self._cleaning = False
        self.recorder_board = None
        self.world_clock_board = None
        self.media_player_board = None
        self.todo_board = None
        self.notes_ctl = None
        self._shutdown_started = False

        mode = str((self.store.state.get("prefs") or {}).get("theme") or "dark")
        apply_app_palette(app, mode)

        self.tray = self._make_tray()
        screenshot_cfg = self.store.state.get("screenshot") or {}
        self.hotkeys = ToolkitHotkeys(
            open_hub=self.show_world_clock,
            shot_region=self.start_screenshot_region,
            hub_combo="Ctrl+Alt+T",
            region_combo=str(screenshot_cfg.get("hotkey_region") or "Ctrl+Alt+A"),
        )

        self._apply_saved_autostart()

        self.clean_finished.connect(self._on_clean_finished)
        self.app.aboutToQuit.connect(self._shutdown_recorder)
        self.alarm_timer = QTimer(self)
        self.alarm_timer.timeout.connect(self._alarm_tick)
        self.alarm_timer.start(1000)
        self.store.append_log("login", "SuperTools started")
        QTimer.singleShot(200, self.show_world_clock)

    def _cb(self) -> SimpleNamespace:
        return SimpleNamespace(
            save_state=self.store.save_state,
            rebind_screenshot_hotkeys=self.rebind_screenshot_hotkeys,
            pause_screenshot_hotkeys=self.pause_screenshot_hotkeys,
            resume_screenshot_hotkeys=self.resume_screenshot_hotkeys,
        )

    def _make_tray(self) -> QSystemTrayIcon:
        logo = bundle_root() / "logo.png"
        icon = QIcon(str(logo)) if logo.exists() else QIcon()
        tray = QSystemTrayIcon(icon, self.app)
        menu = QMenu()
        for text, callback in (
            ("闹钟 / 世界时钟 / 倒计时", self.show_world_clock),
            ("区域截图", self.start_screenshot_region),
            ("屏幕录像", self.show_recorder_board),
            ("待办事项", self.show_todos),
            ("便签", self.show_notes),
            ("视频播放器", self.show_media_player2),
            ("电脑清理", self.start_deep_clean),
        ):
            action = QAction(text, menu)
            action.triggered.connect(lambda _checked=False, cb=callback: cb())
            menu.addAction(action)
        menu.addSeparator()
        settings_action = QAction("设置", menu)
        settings_action.triggered.connect(
            lambda _checked=False: self.show_settings()
        )
        menu.addAction(settings_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.setToolTip("SuperTools")
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_world_clock()

    def show_hub(self) -> None:
        """Compatibility entry point for the global hotkey; opens the clock shell."""
        self.show_world_clock()

    def start_screenshot_region(self) -> None:
        from screenshot_app import start_screenshot

        start_screenshot(state=self.store.state)

    def rebind_screenshot_hotkeys(self) -> str:
        screenshot_cfg = self.store.state.setdefault("screenshot", {})
        result = self.hotkeys.rebind(
            region=str(screenshot_cfg.get("hotkey_region") or "Ctrl+Alt+A")
        )
        self.store.save_state()
        return result

    def pause_screenshot_hotkeys(self) -> None:
        try:
            self.hotkeys.pause_screenshot_hotkeys()
        except Exception:
            pass

    def resume_screenshot_hotkeys(self) -> None:
        try:
            self.hotkeys.resume_screenshot_hotkeys()
        except Exception:
            pass

    def show_recorder_board(self) -> None:
        from recorder_ui import FloatingRecorderBoard

        if self.recorder_board is None:
            self.recorder_board = FloatingRecorderBoard(self._cb(), self.store.state)
        self.recorder_board.show()
        self.recorder_board.raise_()

    def show_world_clock(self) -> None:
        from world_clock_ui import FloatingWorldClock

        if self.world_clock_board is None:
            self.world_clock_board = FloatingWorldClock(self.store.state, host=self)
        self.world_clock_board.show()
        self.world_clock_board.raise_()
        self.world_clock_board.activateWindow()

    def show_media_player2(self) -> None:
        from media_player_ui import MediaPlayerWindow

        if self.media_player_board is None:
            self.media_player_board = MediaPlayerWindow(
                state=self.store.state,
                save_state=self.store.save_state,
            )
        self.media_player_board.show()
        self.media_player_board.raise_()

    def show_settings(self) -> None:
        from settings_ui import SettingsDialog

        dialog = SettingsDialog(self.store.state, self.store.save_state)
        dialog.exec()

    def start_deep_clean(self, scopes: list[str] | None = None) -> None:
        if self._cleaning:
            self.tray.showMessage(
                "清理", "正在清理中，请稍候。", QSystemTrayIcon.MessageIcon.Warning, 3000
            )
            return
        if scopes is None:
            from PyQt6.QtWidgets import QDialog
            from settings_ui import CleanerDialog

            dialog = CleanerDialog(self.store.state, self.store.save_state)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            selected_scopes = dialog.selected_scopes()
        else:
            selected_scopes = list(scopes)
        if not selected_scopes:
            QMessageBox.information(None, "电脑清理", "没有选择任何清理项目。")
            return
        self._cleaning = True
        self.tray.showMessage(
            "清理", "开始清理电脑。", QSystemTrayIcon.MessageIcon.Information, 3000
        )

        def done(report: CleanReport) -> None:
            self.clean_finished.emit(report)

        run_deep_clean_async(done, scopes=selected_scopes)

    def _on_clean_finished(self, report: object) -> None:
        self._cleaning = False
        if isinstance(report, CleanReport):
            summary = report.summary()
            self.tray.showMessage(
                "清理完成", summary, QSystemTrayIcon.MessageIcon.Information, 6000
            )
            self.store.append_log("clean_done", summary)

    def _apply_saved_autostart(self) -> None:
        """Apply only a recorded user choice; legacy implicit persistence is disabled."""
        from autostart import set_autostart

        prefs = self.store.state.setdefault("prefs", {})
        if not bool(prefs.get("autostart_consent")):
            prefs["autostart"] = False
            set_autostart(False)
            self.store.save_state()
            return
        set_autostart(bool(prefs.get("autostart")))

    def show_todos(self) -> None:
        from simple_boards import TodosController

        if self.todo_board is None:
            self.todo_board = TodosController(self.store.state, self.store.save_state)
        self.todo_board.show_all()

    def show_todos_manager(self) -> None:
        from simple_boards import TodosController

        if self.todo_board is None:
            self.todo_board = TodosController(self.store.state, self.store.save_state)
        self.todo_board.show_manager()

    def show_notes(self) -> None:
        from simple_boards import NotesController

        if self.notes_ctl is None:
            self.notes_ctl = NotesController(self.store.state, self.store.save_state)
        self.notes_ctl.show_all()

    def show_notes_manager(self) -> None:
        from simple_boards import NotesController

        if self.notes_ctl is None:
            self.notes_ctl = NotesController(self.store.state, self.store.save_state)
        self.notes_ctl.show_manager()

    def add_note(self) -> None:
        from simple_boards import NotesController

        if self.notes_ctl is None:
            self.notes_ctl = NotesController(self.store.state, self.store.save_state)
        self.notes_ctl.add_note()

    def show_alarm_board(self) -> None:
        self.show_world_clock()

    def _alarm_tick(self) -> None:
        import datetime as dt

        now = dt.datetime.now()
        timer_cfg = self.store.state.setdefault("timer", {})
        if (
            timer_cfg.get("active")
            and int(timer_cfg.get("remaining") or 0) > 0
            and not timer_cfg.get("paused")
        ):
            timer_cfg["remaining"] = int(timer_cfg.get("remaining") or 0) - 1
            if timer_cfg["remaining"] <= 0:
                timer_cfg["active"] = False
                try:
                    from alarm_sounds import play_ringtone

                    play_ringtone(str(timer_cfg.get("ringtone") or "beep"))
                except Exception:
                    pass
                name = timer_cfg.get("name") or "时间到"
                self.tray.showMessage(
                    "倒计时", name, QSystemTrayIcon.MessageIcon.Information, 6000
                )
                self.store.save_state()

        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%Y-%m-%d")
        for alarm in self.store.state.get("alarms") or []:
            if not alarm.get("enabled"):
                continue
            if alarm.get("time") == current_time and alarm.get("last_triggered_date") != current_day:
                alarm["last_triggered_date"] = current_day
                if alarm.get("repeat") == "once":
                    alarm["enabled"] = False
                self.store.save_state()
                self.show_ringing_alarm(alarm)

    def show_ringing_alarm(self, alarm_data: dict) -> None:
        try:
            from world_clock_ui import AlarmRingingDialog

            active_dialog = getattr(self, "_active_alarm_dialog", None)
            if active_dialog is not None:
                try:
                    active_dialog.close()
                except Exception:
                    pass
            dialog = AlarmRingingDialog(alarm_data)
            self._active_alarm_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception as exc:
            print(f"Failed to show alarm dialog: {exc}")

    def _shutdown_recorder(self) -> None:
        board = self.recorder_board
        if board is None:
            return
        try:
            board.shutdown_for_exit()
        except Exception:
            pass

    def quit(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._shutdown_recorder()
        try:
            self.hotkeys.close()
        except Exception:
            pass
        self.store.save_state()
        self.app.quit()


def main() -> int:
    _install_exception_hooks()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setApplicationName("SuperTools")
    logo = bundle_root() / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))
    try:
        ToolkitApp(app)
    except Exception as exc:
        traceback.print_exc()
        QMessageBox.critical(None, "SuperTools", f"启动失败：{exc}")
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
