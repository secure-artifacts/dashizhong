"""User-controlled settings and explicit cleaner consent dialogs."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from autostart import is_autostart_enabled, set_autostart
from cleaner import CLEAN_SCOPES, DEFAULT_SCOPES


RISKY_CLEAN_SCOPES = {"prefetch", "recycle", "wu", "delivery"}


VIDEO_CONTEXT_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
    ".mpeg", ".mpg", ".ts", ".mts", ".m2ts", ".3gp",
)


def _right_click_key_paths() -> list[str]:
    base = r"Software\Classes\SystemFileAssociations"
    return [
        base + r"\video\shell\PlayWithClockAlarm",
        *(base + rf"\{extension}\shell\PlayWithClockAlarm"
          for extension in VIDEO_CONTEXT_EXTENSIONS),
    ]


def _delete_registry_tree(root, path: str) -> None:
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            children = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            _delete_registry_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def is_right_click_association_enabled() -> bool:
    import winreg

    for key_path in _right_click_key_paths():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
                value, _value_type = winreg.QueryValueEx(key, "")
                if "Clock-Alarm.exe" in str(value):
                    return True
        except OSError:
            continue
    return False


def set_right_click_association(enabled: bool) -> None:
    import sys
    import winreg
    from pathlib import Path
    
    if enabled:
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
        else:
            app_root = Path(__file__).resolve().parent
            parent_exe = app_root.parent / "Clock-Alarm.exe"
            if parent_exe.exists():
                exe_path = str(parent_exe)
            else:
                exe_path = sys.executable
                
        exe_path = str(Path(exe_path).resolve())
        if not Path(exe_path).is_file():
            raise FileNotFoundError(f"播放器启动文件不存在：{exe_path}")
        cmd_value = f'"{exe_path}" --play "%1"'

        for key_path in _right_click_key_paths():
            command_path = key_path + r"\command"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "使用 Clock/Alarm 播放")
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{exe_path}",0')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_path) as cmd_key:
                winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_value)

        # Register as an application as well as a context-menu verb. This is
        # what makes Clock/Alarm appear in Windows 11's "Open with" chooser.
        application_key = r"Software\Classes\Applications\Clock-Alarm.exe"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, application_key) as key:
            winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, "Clock/Alarm 视频播放器")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, application_key + r"\DefaultIcon") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, application_key + r"\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd_value)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, application_key + r"\SupportedTypes") as key:
            for extension in VIDEO_CONTEXT_EXTENSIONS:
                winreg.SetValueEx(key, extension, 0, winreg.REG_SZ, "")

        capabilities_key = r"Software\ClockAlarm\Capabilities"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, capabilities_key) as key:
            winreg.SetValueEx(key, "ApplicationName", 0, winreg.REG_SZ, "Clock/Alarm 视频播放器")
            winreg.SetValueEx(key, "ApplicationDescription", 0, winreg.REG_SZ, "使用 Clock/Alarm 播放本地视频")
            winreg.SetValueEx(key, "ApplicationIcon", 0, winreg.REG_SZ, f'"{exe_path}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, capabilities_key + r"\FileAssociations") as key:
            for extension in VIDEO_CONTEXT_EXTENSIONS:
                winreg.SetValueEx(key, extension, 0, winreg.REG_SZ, "ClockAlarm.Video")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as key:
            winreg.SetValueEx(key, "ClockAlarm", 0, winreg.REG_SZ, capabilities_key)

        progid_key = r"Software\Classes\ClockAlarm.Video"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, progid_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Clock/Alarm 视频文件")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, progid_key + r"\DefaultIcon") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, progid_key + r"\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd_value)
        for extension in VIDEO_CONTEXT_EXTENSIONS:
            open_with_key = rf"Software\Classes\{extension}\OpenWithProgids"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, open_with_key) as key:
                winreg.SetValueEx(key, "ClockAlarm.Video", 0, winreg.REG_NONE, b"")
    else:
        for key_path in _right_click_key_paths():
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
            except FileNotFoundError:
                pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                pass
        _delete_registry_tree(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\Applications\Clock-Alarm.exe",
        )
        _delete_registry_tree(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\ClockAlarm.Video",
        )
        _delete_registry_tree(
            winreg.HKEY_CURRENT_USER,
            r"Software\ClockAlarm\Capabilities",
        )
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\RegisteredApplications",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, "ClockAlarm")
        except FileNotFoundError:
            pass
        for extension in VIDEO_CONTEXT_EXTENSIONS:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Classes\{extension}\OpenWithProgids",
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    winreg.DeleteValue(key, "ClockAlarm.Video")
            except FileNotFoundError:
                pass

    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


def _selected_cleaner_scopes(state: dict) -> list[str]:
    cleaner = state.get("cleaner")
    if not isinstance(cleaner, dict):
        return list(DEFAULT_SCOPES)
    scopes = cleaner.get("scopes")
    if not isinstance(scopes, list):
        return list(DEFAULT_SCOPES)
    allowed = {scope_id for scope_id, _label, _description in CLEAN_SCOPES}
    return [str(scope) for scope in scopes if str(scope) in allowed]


class _StyledDialog(QDialog):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setStyleSheet(
            """
            QDialog { background: #07111f; color: #e2e8f0; }
            QLabel, QCheckBox, QGroupBox { color: #e2e8f0; }
            QGroupBox {
                border: 1px solid #26445f; border-radius: 10px;
                margin-top: 10px; padding: 12px;
                font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QCheckBox { spacing: 8px; padding: 4px; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 1px solid #64748b;
                border-radius: 4px; background: #0f172a;
            }
            QCheckBox::indicator:checked { background: #0ea5e9; border-color: #38bdf8; }
            QPushButton {
                color: #f8fafc; background: #164e63; border: 1px solid #0e7490;
                border-radius: 7px; padding: 7px 14px; font-weight: 700;
            }
            QPushButton:hover { background: #155e75; }
            QSpinBox {
                color: #f8fafc; background: #0f172a; border: 1px solid #475569;
                border-radius: 6px; padding: 5px;
            }
            """
        )


class SettingsDialog(_StyledDialog):
    """Persistent preferences that require an explicit user choice."""

    def __init__(
        self,
        state: dict,
        save_state: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__("Clock/Alarm 设置", parent)
        self.state = state
        self.save_state = save_state
        self.resize(540, 600)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        general = QGroupBox("常规")
        general_layout = QVBoxLayout(general)
        self.autostart = QCheckBox("登录 Windows 后自动启动 Clock/Alarm")
        self.autostart.setChecked(is_autostart_enabled())
        general_layout.addWidget(self.autostart)
        note = QLabel("默认关闭；只有点击“保存设置”后才会修改开机启动。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#94a3b8; font-weight:400;")
        general_layout.addWidget(note)

        self.right_click_menu = QCheckBox("关联 Windows 右键菜单 (使用此播放器播放视频)")
        media_cfg = state.get("media") if isinstance(state.get("media"), dict) else {}
        initial_right_click = bool(
            media_cfg.get("right_click_association", False)
            or is_right_click_association_enabled()
        )
        self.right_click_menu.setChecked(initial_right_click)
        general_layout.addWidget(self.right_click_menu)

        layout.addWidget(general)

        cleaner_group = QGroupBox("电脑清理默认范围")
        cleaner_layout = QVBoxLayout(cleaner_group)
        selected = set(_selected_cleaner_scopes(state))
        self.cleaner_checks: dict[str, QCheckBox] = {}
        for scope_id, label, description in CLEAN_SCOPES:
            suffix = "（不可恢复）" if scope_id == "recycle" else ""
            check = QCheckBox(f"{label}{suffix} — {description}")
            check.setChecked(scope_id in selected)
            self.cleaner_checks[scope_id] = check
            cleaner_layout.addWidget(check)
        cleaner_note = QLabel("实际清理时仍会再次显示范围并要求确认。")
        cleaner_note.setStyleSheet("color:#94a3b8; font-weight:400;")
        cleaner_layout.addWidget(cleaner_note)
        layout.addWidget(cleaner_group)

        media_group = QGroupBox("视频播放器")
        media_form = QFormLayout(media_group)
        self.allow_online = QCheckBox("允许解析在线视频链接 and YouTube")
        self.allow_online.setChecked(bool(media_cfg.get("allow_online", True)))
        media_form.addRow(self.allow_online)
        self.playlist_limit = QSpinBox()
        self.playlist_limit.setRange(1, 200)
        self.playlist_limit.setValue(
            max(1, min(200, int(media_cfg.get("playlist_limit") or 100)))
        )
        self.playlist_limit.setSuffix(" 项")
        media_form.addRow("单次播放列表上限", self.playlist_limit)
        layout.addWidget(media_group)

        # Screenshot & Clipboard Section
        screenshot_group = QGroupBox("截图与剪贴板")
        screenshot_form = QFormLayout(screenshot_group)
        screenshot_cfg = state.setdefault("screenshot", {})
        
        self.screenshot_auto_copy = QCheckBox("截图框选完成后自动复制到剪贴板")
        self.screenshot_auto_copy.setChecked(bool(screenshot_cfg.get("auto_copy", True)))
        screenshot_form.addRow(self.screenshot_auto_copy)
        
        self.screenshot_auto_save = QCheckBox("截图完成后自动保存图片到本地")
        self.screenshot_auto_save.setChecked(bool(screenshot_cfg.get("auto_save", True)))
        screenshot_form.addRow(self.screenshot_auto_save)
        
        dir_widget = QWidget()
        dir_layout = QHBoxLayout(dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)
        
        from pathlib import Path
        default_dir = str(Path.home() / "Pictures" / "ParrotScreenshots")
        self.screenshot_save_dir = QLineEdit()
        self.screenshot_save_dir.setText(str(screenshot_cfg.get("save_dir") or default_dir))
        self.screenshot_save_dir.setPlaceholderText("选择保存截图的文件夹")
        
        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedWidth(75)
        
        def _choose_dir():
            from PyQt6.QtWidgets import QFileDialog
            chosen = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹", self.screenshot_save_dir.text())
            if chosen:
                self.screenshot_save_dir.setText(chosen)
                
        browse_btn.clicked.connect(_choose_dir)
        dir_layout.addWidget(self.screenshot_save_dir)
        dir_layout.addWidget(browse_btn)
        
        screenshot_form.addRow("截图保存目录", dir_widget)
        layout.addWidget(screenshot_group)

        # Global Hotkey Customization Section
        hotkey_group = QGroupBox("全局快捷键自定义")
        hotkey_layout = QVBoxLayout(hotkey_group)
        
        hotkeys_cfg = state.setdefault("hotkeys_config", {})
        self.hotkeys_master = QCheckBox("启用全局快捷键功能")
        self.hotkeys_master.setChecked(bool(hotkeys_cfg.setdefault("enabled", True)))
        hotkey_layout.addWidget(self.hotkeys_master)
        
        hotkey_form = QFormLayout()
        self.hotkey_enables = {}
        self.hotkey_inputs = {}
        
        hotkey_meta = [
            ("world_clock", "闹钟 / 时钟 / 倒计时", "Ctrl+Alt+T"),
            ("screenshot", "区域截图", "Ctrl+Alt+A"),
            ("recorder", "屏幕录像", "Ctrl+Alt+R"),
            ("todos", "待办事项", "Ctrl+Alt+D"),
            ("notes", "便签", "Ctrl+Alt+N"),
            ("media_player", "视频播放器", "Ctrl+Alt+V"),
            ("cleaner", "电脑清理", "Ctrl+Alt+C"),
        ]
        
        combos = hotkeys_cfg.setdefault("combos", {})
        enables = hotkeys_cfg.setdefault("enables", {})
        
        for key, name, default_combo in hotkey_meta:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            
            enable_chk = QCheckBox("启用")
            enable_chk.setChecked(bool(enables.setdefault(key, True)))
            
            input_edit = QLineEdit()
            input_edit.setText(str(combos.setdefault(key, default_combo)))
            input_edit.setPlaceholderText("例如 Ctrl+Alt+A")
            input_edit.setMinimumWidth(120)
            
            row_layout.addWidget(enable_chk)
            row_layout.addWidget(input_edit)
            
            hotkey_form.addRow(name, row_widget)
            
            self.hotkey_enables[key] = enable_chk
            self.hotkey_inputs[key] = input_edit
            
        hotkey_layout.addLayout(hotkey_form)
        layout.addWidget(hotkey_group)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _save(self) -> None:
        desired_autostart = self.autostart.isChecked()
        status = set_autostart(desired_autostart)
        actual_autostart = is_autostart_enabled()
        if actual_autostart != desired_autostart:
            QMessageBox.warning(self, "开机自启动", status)
            self.autostart.setChecked(actual_autostart)
            return

        prefs = self.state.setdefault("prefs", {})
        prefs["autostart"] = desired_autostart
        prefs["autostart_consent"] = True

        scopes = [
            scope_id
            for scope_id, check in self.cleaner_checks.items()
            if check.isChecked()
        ]
        cleaner = self.state.setdefault("cleaner", {})
        cleaner["scopes"] = scopes
        cleaner["scope_selection_version"] = 1

        media = self.state.setdefault("media", {})
        media["allow_online"] = self.allow_online.isChecked()
        media["playlist_limit"] = int(self.playlist_limit.value())

        # Save Screenshot configuration
        screenshot_cfg = self.state.setdefault("screenshot", {})
        screenshot_cfg["auto_copy"] = self.screenshot_auto_copy.isChecked()
        screenshot_cfg["auto_save"] = self.screenshot_auto_save.isChecked()
        save_dir_text = self.screenshot_save_dir.text().strip()
        if save_dir_text:
            screenshot_cfg["save_dir"] = save_dir_text

        # Save Hotkeys configuration
        hotkeys_cfg = self.state.setdefault("hotkeys_config", {})
        hotkeys_cfg["enabled"] = self.hotkeys_master.isChecked()
        
        combos = {}
        enables = {}
        for key in self.hotkey_inputs:
            combos[key] = self.hotkey_inputs[key].text().strip()
            enables[key] = self.hotkey_enables[key].isChecked()
            
        hotkeys_cfg["combos"] = combos
        hotkeys_cfg["enables"] = enables

        # Save Right-Click Context Menu association
        try:
            set_right_click_association(self.right_click_menu.isChecked())
        except Exception as exc:
            QMessageBox.critical(self, "右键菜单关联失败", str(exc))
            return
        self.state.setdefault("media", {})["right_click_association"] = (
            self.right_click_menu.isChecked()
        )

        self.save_state()
        self.accept()


class CleanerDialog(_StyledDialog):
    """Select a cleanup scope and confirm it before any deletion starts."""

    def __init__(
        self,
        state: dict,
        save_state: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__("电脑清理", parent)
        self.state = state
        self.save_state = save_state
        self._accepted_scopes: list[str] = []
        self.resize(600, 520)

        layout = QVBoxLayout(self)
        intro = QLabel("请选择本次要清理的项目。未勾选的范围不会被访问。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        selected = set(_selected_cleaner_scopes(state))
        self.checks: dict[str, QCheckBox] = {}
        for scope_id, label, description in CLEAN_SCOPES:
            check = QCheckBox(f"{label} — {description}")
            check.setChecked(scope_id in selected)
            if scope_id in RISKY_CLEAN_SCOPES:
                check.setToolTip("此项目影响系统缓存或不可恢复，请确认后再清理。")
            self.checks[scope_id] = check
            content_layout.addWidget(check)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        warning = QLabel(
            "安全保护始终启用：不会跟随目录链接，不会访问未批准目录；"
            "回收站内容删除后无法恢复。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#fbbf24;")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认并开始清理")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _confirm(self) -> None:
        scopes = [
            scope_id for scope_id, check in self.checks.items() if check.isChecked()
        ]
        if not scopes:
            QMessageBox.information(self, "电脑清理", "请至少选择一个清理项目。")
            return

        labels = {
            scope_id: label for scope_id, label, _description in CLEAN_SCOPES
        }
        selected_text = "、".join(labels[scope_id] for scope_id in scopes)
        extra = (
            "\n\n其中包含系统缓存或不可恢复项目，请再次确认。"
            if set(scopes) & RISKY_CLEAN_SCOPES
            else ""
        )
        result = QMessageBox.question(
            self,
            "确认清理范围",
            f"本次只会清理：{selected_text}。{extra}\n\n确定开始吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        cleaner = self.state.setdefault("cleaner", {})
        cleaner["scopes"] = list(scopes)
        cleaner["scope_selection_version"] = 1
        self.save_state()
        self._accepted_scopes = list(scopes)
        self.accept()

    def selected_scopes(self) -> list[str]:
        return list(self._accepted_scopes)
