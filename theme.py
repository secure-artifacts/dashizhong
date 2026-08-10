"""App theme: dark / light."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

DARK = {
    "bg": "#09090b",
    "panel": "#18181b",
    "card": "#27272a",
    "border": "#3f3f46",
    "text": "#fafafa",
    "muted": "#a1a1aa",
    "accent": "#ef4444",
    "accent2": "#dc2626",
    "input_bg": "#000000",
    "danger": "#ef4444",
}

LIGHT = {
    "bg": "#f4f4f5",
    "panel": "#ffffff",
    "card": "#e4e4e7",
    "border": "#d4d4d8",
    "text": "#18181b",
    "muted": "#71717a",
    "accent": "#dc2626",
    "accent2": "#991b1b",
    "input_bg": "#ffffff",
    "danger": "#dc2626",
}

def theme_tokens(mode: str) -> dict[str, str]:
    return LIGHT if mode == "light" else DARK


def apply_app_palette(app: QApplication, mode: str) -> None:
    t = theme_tokens(mode)
    p = QPalette()
    if mode == "light":
        p.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        p.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Button, QColor(t["card"]))
        p.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    else:
        p.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Base, QColor(t["input_bg"]))
        p.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Button, QColor(t["card"]))
        p.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(p)


def main_window_qss(mode: str) -> str:
    t = theme_tokens(mode)
    return f"""
    QMainWindow, QWidget#root {{
        background: {t['bg']};
        color: {t['text']};
    }}
    QFrame#sideNav {{
        background: {t['panel']};
        border-right: 1px solid {t['border']};
    }}
    QLabel#brand {{
        color: {t['text']};
        font-size: 16px; font-weight: 900;
        letter-spacing: 1px;
    }}
    QLabel#section {{
        color: {t['accent']}; font-size: 12px; font-weight: 900;
        padding: 10px 4px 4px 4px;
        text-transform: uppercase;
    }}
    QLabel#pageTitle {{
        color: {t['text']}; font-size: 20px; font-weight: 900;
    }}
    QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
    QPushButton#nav {{
        text-align: left; padding: 10px 12px; border: none; border-radius: 6px;
        background: transparent; color: {t['text']}; font-weight: 700;
    }}
    QPushButton#nav:hover {{ 
        background: rgba(220, 38, 38, 0.1); 
        color: {t['accent']}; 
    }}
    QPushButton#nav:pressed {{ 
        background: rgba(220, 38, 38, 0.2); 
        padding-top: 12px; padding-bottom: 8px;
    }}
    QPushButton#nav:checked {{
        background: rgba(220, 38, 38, 0.15); 
        color: {t['accent']};
        border-left: 3px solid {t['accent']};
        border-radius: 4px;
    }}
    QPushButton#homeCard {{
        background: {t['card']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 8px;
        padding: 16px 10px; font-weight: 700; min-height: 72px;
    }}
    QPushButton#homeCard:hover {{
        border: 1px solid {t['accent']};
        background: rgba(220, 38, 38, 0.05); color: {t['accent']};
    }}
    QPushButton#homeCard:pressed {{
        border: 2px solid {t['accent2']};
        background: rgba(220, 38, 38, 0.15);
        padding-top: 18px; padding-bottom: 14px;
    }}
    QPushButton#primary {{
        background: {t['accent']}; color: #ffffff;
        border: none;
        border-radius: 6px; padding: 9px 14px; font-weight: 800;
    }}
    QPushButton#primary:hover {{
        background: {t['accent2']};
    }}
    QPushButton#primary:pressed {{
        padding-top: 11px; padding-bottom: 7px;
    }}
    QPushButton#soft {{
        background: {t['panel']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 6px;
        padding: 8px 12px; font-weight: 700;
    }}
    QPushButton#soft:hover {{
        border: 1px solid {t['accent']};
        color: {t['accent']};
    }}
    QPushButton#soft:pressed {{
        background: rgba(220, 38, 38, 0.1);
        padding-top: 10px; padding-bottom: 6px;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox {{
        background: {t['input_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 6px; padding: 8px;
        font-weight: 600;
    }}
    QComboBox QAbstractItemView {{
        background-color: #0f172a !important;
        color: #ffffff !important;
        selection-background-color: #0284c7 !important;
        selection-color: #ffffff !important;
        border: 1px solid #38bdf8 !important;
        outline: none !important;
        padding: 4px !important;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 28px !important;
        padding: 6px 10px !important;
        color: #ffffff !important;
        background-color: #0f172a !important;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: #0284c7 !important;
        color: #ffffff !important;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: #0284c7 !important;
        color: #ffffff !important;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QListWidget:focus {{
        border: 1px solid {t['accent']};
    }}
    QFrame#panel {{
        background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 8px;
    }}
    QCheckBox {{ color: {t['text']}; spacing: 8px; font-weight: 600; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {t['border']};
        border-radius: 4px;
        background: {t['input_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {t['accent']};
        border: 1px solid {t['accent']};
    }}
    QScrollArea {{ border: none; background: transparent; }}
    """
