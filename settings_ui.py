"""User-controlled settings and explicit cleaner consent dialogs."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from autostart import is_autostart_enabled, set_autostart
from cleaner import CLEAN_SCOPES, DEFAULT_SCOPES


RISKY_CLEAN_SCOPES = {"prefetch", "recycle", "wu", "delivery"}


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

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        general = QGroupBox("常规")
        general_layout = QVBoxLayout(general)
        self.autostart = QCheckBox("登录 Windows 后自动启动 Clock/Alarm")
        self.autostart.setChecked(is_autostart_enabled())
        general_layout.addWidget(self.autostart)
        note = QLabel("默认关闭；只有点击“保存设置”后才会修改开机启动。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#94a3b8; font-weight:400;")
        general_layout.addWidget(note)
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
        media_cfg = state.get("media") if isinstance(state.get("media"), dict) else {}
        self.allow_online = QCheckBox("允许解析在线视频链接和 YouTube")
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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
