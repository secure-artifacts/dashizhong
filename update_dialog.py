"""Modern Dark Glassmorphism update notification dialog for Clock/Alarm."""
from __future__ import annotations

from typing import Callable
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from skin import get_app_version, make_version_badge
from update_checker import UpdateInfo


class UpdateDialog(QDialog):
    def __init__(
        self,
        info: UpdateInfo,
        on_ignore: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.on_ignore = on_ignore

        self.setWindowTitle(f"Clock/Alarm — 发现新版本 v{info.latest_version}")
        self.resize(580, 520)
        self.setMinimumSize(480, 420)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:0.5 #0c1322, stop:1 #080d17);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 14px;
                color: #f8fafc;
                font-family: 'Segoe UI', 'Microsoft YaHei', -apple-system, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
            }
            QTextBrowser {
                background: #090e18;
                border: 1px solid #1e293b;
                border-radius: 8px;
                color: #e2e8f0;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }
            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 18px;
                color: #f8fafc;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #475569;
            }
            QPushButton#primary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
                border: none;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#primary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #0284c7);
            }
            QPushButton#subtle {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton#subtle:hover {
                color: #94a3b8;
                background: rgba(255, 255, 255, 0.05);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # ── Header Row ──
        header_row = QHBoxLayout()
        header_title = QLabel("🚀 软件新版本已就绪")
        header_title.setStyleSheet("color: #ffffff; font-size: 17px; font-weight: bold;")
        header_row.addWidget(header_title)
        header_row.addStretch(1)
        header_row.addWidget(make_version_badge(self, f"当前 v{info.current_version}"))
        layout.addLayout(header_row)

        # ── Hero Card: Version Jump ──
        hero_card = QFrame()
        hero_card.setObjectName("heroCard")
        hero_card.setStyleSheet("""
            QFrame#heroCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #172238, stop:1 #111d30);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 12px;
            }
        """)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(6)

        ver_row = QHBoxLayout()
        ver_lbl = QLabel(f"v{info.current_version}  ➔  v{info.latest_version}")
        ver_lbl.setStyleSheet("color: #38bdf8; font-size: 20px; font-weight: 800; font-family: 'Segoe UI', Consolas;")
        ver_row.addWidget(ver_lbl)
        ver_row.addStretch(1)

        status_badge = QLabel("✨ 建议升级")
        status_badge.setStyleSheet("""
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 8px;
        """)
        ver_row.addWidget(status_badge)
        hero_layout.addLayout(ver_row)

        pub_text = f"发布时间：{info.published_at[:10]}" if info.published_at else "官方已验证构建发布"
        sub_lbl = QLabel(pub_text)
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hero_layout.addWidget(sub_lbl)

        layout.addWidget(hero_card)

        # ── Release Notes ──
        notes_label = QLabel("📋 本次更新内容与改进说明:")
        notes_label.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        layout.addWidget(notes_label)

        self.notes_browser = QTextBrowser()
        body_text = info.body.strip() if info.body else "本次版本包含最新功能优化、界面视觉提升与性能改进。"
        self.notes_browser.setPlainText(body_text)
        layout.addWidget(self.notes_browser, stretch=1)

        # ── Direct Download Asset Chips ──
        if info.download_urls:
            dl_row = QHBoxLayout()
            dl_row.setSpacing(8)
            dl_label = QLabel("快速直链下载:")
            dl_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
            dl_row.addWidget(dl_label)

            if "installer" in info.download_urls:
                btn_dl_setup = QPushButton("⚙️ 安装包 (.exe)")
                btn_dl_setup.setFixedHeight(30)
                btn_dl_setup.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_dl_setup.setStyleSheet("""
                    QPushButton {
                        background: #0f172a;
                        color: #38bdf8;
                        border: 1px solid rgba(56, 189, 248, 0.3);
                        border-radius: 6px;
                        font-size: 11px;
                        padding: 2px 10px;
                    }
                    QPushButton:hover {
                        background: rgba(56, 189, 248, 0.18);
                    }
                """)
                btn_dl_setup.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info.download_urls["installer"])))
                dl_row.addWidget(btn_dl_setup)

            if "portable" in info.download_urls:
                btn_dl_port = QPushButton("📦 绿色便携包 (.zip)")
                btn_dl_port.setFixedHeight(30)
                btn_dl_port.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_dl_port.setStyleSheet("""
                    QPushButton {
                        background: #0f172a;
                        color: #38bdf8;
                        border: 1px solid rgba(56, 189, 248, 0.3);
                        border-radius: 6px;
                        font-size: 11px;
                        padding: 2px 10px;
                    }
                    QPushButton:hover {
                        background: rgba(56, 189, 248, 0.18);
                    }
                """)
                btn_dl_port.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info.download_urls["portable"])))
                dl_row.addWidget(btn_dl_port)

            dl_row.addStretch(1)
            layout.addLayout(dl_row)

        # ── Bottom Action Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_skip = QPushButton("跳过此版本")
        self.btn_skip.setObjectName("subtle")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.setToolTip("不再提醒当前版本的更新")
        self.btn_skip.clicked.connect(self._skip_this_version)
        btn_layout.addWidget(self.btn_skip)

        btn_layout.addStretch(1)

        self.btn_later = QPushButton("稍后提醒")
        self.btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_later.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_later)

        self.btn_open_web = QPushButton("🚀 前往下载新版本")
        self.btn_open_web.setObjectName("primary")
        self.btn_open_web.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_web.clicked.connect(self._open_download_url)
        btn_layout.addWidget(self.btn_open_web)

        layout.addLayout(btn_layout)

    def _open_download_url(self) -> None:
        url = self.info.html_url or f"https://github.com/{DEFAULT_REPO}/releases"
        QDesktopServices.openUrl(QUrl(url))
        self.accept()

    def _skip_this_version(self) -> None:
        if callable(self.on_ignore):
            self.on_ignore(self.info.latest_version)
        self.reject()
