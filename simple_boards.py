"""Floating todo and note boards with multi-item and theme-color support."""

from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from productivity import NoteManager, TodoBoardsStore, TodoManager

NOTE_COLORS = [
    "#fef08a",
    "#bbf7d0",
    "#bfdbfe",
    "#fecaca",
    "#e9d5ff",
    "#fed7aa",
    "#f1f5f9",
]


def _luma(hex_color: str) -> float:
    c = QColor(hex_color)
    # relative luminance
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


def _fg_on(bg: str) -> str:
    """Readable text color on background."""
    return "#0f172a" if _luma(bg) > 0.55 else "#f8fafc"


def _muted_on(bg: str) -> str:
    return "#334155" if _luma(bg) > 0.55 else "#94a3b8"


def _board_qss(bg: str = "#bfdbfe", accent: str = "#4f46e5") -> str:
    """Windows Sticky Notes inspired surface with cute controls and modern pastel scrollbars."""
    fg = _fg_on(bg)
    muted = _muted_on(bg)
    light = _luma(bg) > 0.55
    input_bg = "rgba(255,255,255,0.30)" if light else "rgba(15,23,42,0.18)"
    item_bg = "rgba(255,255,255,0.18)" if light else "rgba(255,255,255,0.05)"
    control_fg = "#334155" if light else "#e2e8f0"

    sb_track = "rgba(0, 0, 0, 0.04)" if light else "rgba(255, 255, 255, 0.08)"
    sb_thumb = "rgba(0, 0, 0, 0.18)" if light else "rgba(255, 255, 255, 0.28)"
    sb_hover = "rgba(0, 0, 0, 0.35)" if light else "rgba(255, 255, 255, 0.48)"

    return f"""
    QFrame#box {{
        background: {bg}; border: none; border-radius: 12px;
    }}
    QWidget {{ color: {fg}; }}
    QLabel {{ color: {fg}; font-weight: 600; background: transparent; }}
    QLabel#title {{
        color: {fg}; font-size: 16px; font-weight: 900; background: transparent;
    }}
    QLineEdit, QTextEdit, QListWidget {{
        background: {input_bg}; color: {fg};
        border: none; border-radius: 8px; padding: 6px;
        selection-background-color: rgba(0,0,0,0.2); selection-color: {fg};
        font-size: 14px;
    }}
    QLineEdit#boardTitle, QLineEdit#noteTitle {{
        background: transparent; border: none; color: {fg};
        font-weight: 900; font-size: 16px; padding: 2px 4px;
    }}
    QListWidget {{ outline: none; }}
    QListWidget::item {{
        color: {fg}; background: {item_bg}; border: none; border-radius: 6px;
        padding: 9px 8px; margin: 2px 0; font-size: 14px;
    }}
    QListWidget::item:selected {{
        background: rgba(255,255,255,0.45); color: {fg}; border: none;
    }}
    QPushButton {{
        background: transparent; color: {control_fg}; border: none; border-radius: 6px;
        padding: 4px 6px; font-weight: 700; font-size: 13px;
    }}
    QPushButton:hover {{
        background: rgba(255,255,255,0.50); color: #0284c7;
    }}
    QPushButton:pressed {{
        background: rgba(255,255,255,0.75); color: #0369a1;
    }}
    QPushButton#soft {{
        background: transparent; color: {control_fg}; border: none; border-radius: 6px;
        font-weight: 700; font-size: 13px; padding: 4px 6px;
    }}
    QPushButton#soft:hover {{
        background: rgba(255,255,255,0.50); color: #0284c7;
    }}

    /* Modern Pastel Scrollbars */
    QScrollBar:vertical {{
        background: {sb_track};
        width: 8px;
        margin: 2px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {sb_thumb};
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {sb_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px; background: none; border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollBar:horizontal {{
        background: {sb_track};
        height: 8px;
        margin: 2px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {sb_thumb};
        min-width: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {sb_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px; background: none; border: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    """


class HeaderBar(QFrame):
    """Custom title bar for floating boards that allows smooth window dragging across the entire header."""

    def __init__(self, host: QWidget, parent=None):
        super().__init__(parent)
        self._host = host
        self._press_pos = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint() - self._host.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._host.move(event.globalPosition().toPoint() - self._press_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)


class DragLineEdit(QLineEdit):
    """Editable title line edit that allows dragging the window when dragging mouse."""

    def __init__(self, host: QWidget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._host = host
        self._press_pos = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint() - self._host.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._host.frameGeometry().topLeft() - self._press_pos
            if delta.manhattanLength() > 4:
                self._host.move(event.globalPosition().toPoint() - self._press_pos)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)


class _BoardResizeHandle(QWidget):
    """Manual resize zone shared by todo and sticky-note windows."""

    def __init__(self, host: QWidget, edges, cursor) -> None:
        super().__init__(host)
        self._host = host
        self._edges = edges
        self._press_global = None
        self._start_geometry = None
        self.setCursor(cursor)
        self.setStyleSheet("background: rgba(255,255,255,1); border: none;")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._start_geometry = self._host.geometry()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._press_global is None or self._start_geometry is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        start = self._start_geometry
        min_w = max(240, self._host.minimumWidth())
        min_h = max(120, self._host.minimumHeight())
        x, y, width, height = start.x(), start.y(), start.width(), start.height()
        if self._edges & Qt.Edge.LeftEdge:
            right_edge = start.x() + start.width()
            x = min(start.x() + delta.x(), right_edge - min_w)
            width = right_edge - x
        elif self._edges & Qt.Edge.RightEdge:
            width = max(min_w, start.width() + delta.x())
        if self._edges & Qt.Edge.TopEdge:
            bottom_edge = start.y() + start.height()
            y = min(start.y() + delta.y(), bottom_edge - min_h)
            height = bottom_edge - y
        elif self._edges & Qt.Edge.BottomEdge:
            height = max(min_h, start.height() + delta.y())
        self._host.setGeometry(x, y, width, height)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_global = None
        self._start_geometry = None
        event.accept()


class _DragBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragging = False
        self.drag_pos = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(240, 150)
        specs = (
            (Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeFDiagCursor),
            (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.LeftEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.RightEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeFDiagCursor),
        )
        self._resize_handles = [_BoardResizeHandle(self, edges, cursor) for edges, cursor in specs]
        self._place_resize_handles()

    def _place_resize_handles(self) -> None:
        width, height = self.width(), self.height()
        edge, corner = 10, 18
        geometries = (
            (0, corner, edge, max(0, height - corner * 2)),
            (width - edge, corner, edge, max(0, height - corner * 2)),
            (corner, 0, max(0, width - corner * 2), edge),
            (corner, height - edge, max(0, width - corner * 2), edge),
            (0, 0, corner, corner),
            (width - corner, 0, corner, corner),
            (0, height - corner, corner, corner),
            (width - corner, height - corner, corner, corner),
        )
        for handle, geometry in zip(self._resize_handles, geometries):
            handle.setGeometry(*geometry)
            handle.raise_()

    def resizeEvent(self, event) -> None:
        self._place_resize_handles()
        super().resizeEvent(event)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self.dragging and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

class TodoItemRowWidget(QWidget):
    """Custom row widget for todo items with clear checkbox and zero-overlap inline editing."""

    def __init__(self, item_data: dict, on_toggle=None, on_rename=None, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.on_toggle = on_toggle
        self.on_rename = on_rename
        self.setMinimumHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        # Clear, prominent Checkbox
        self.chk = QCheckBox()
        self.chk.setChecked(bool(item_data.get("done")))
        self.chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk.setToolTip("点击打勾标记完成 / 取消完成")
        self.chk.setStyleSheet("""
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 2px solid #64748b;
                background: #ffffff;
            }
            QCheckBox::indicator:hover {
                border-color: #10b981;
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
                border-color: #059669;
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
            }
        """)
        self.chk.toggled.connect(self._handle_toggle)
        lay.addWidget(self.chk)

        # Task Text Label (Double click to edit)
        self.lbl_text = QLabel(str(item_data.get("text") or ""))
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setToolTip("💡 双击可编辑修改此事项")
        self._update_label_style(bool(item_data.get("done")))
        lay.addWidget(self.lbl_text, 1)

        # In-place Edit LineEdit (hidden by default, 0% overlap)
        self.edit_line = QLineEdit(str(item_data.get("text") or ""))
        self.edit_line.setStyleSheet("""
            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 2px solid #10b981;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 14px;
                font-weight: 700;
            }
        """)
        self.edit_line.hide()
        self.edit_line.editingFinished.connect(self._finish_editing)
        lay.addWidget(self.edit_line, 1)

        # Connect double click on label to start editing
        self.lbl_text.mouseDoubleClickEvent = self._start_editing

    def _update_label_style(self, done: bool) -> None:
        font = self.lbl_text.font()
        font.setStrikeOut(done)
        self.lbl_text.setFont(font)
        if done:
            self.lbl_text.setStyleSheet("font-size: 14px; font-weight: 600; color: #94a3b8;")
        else:
            self.lbl_text.setStyleSheet("font-size: 14px; font-weight: 600;")

    def _handle_toggle(self, checked: bool) -> None:
        self._update_label_style(checked)
        if callable(self.on_toggle):
            self.on_toggle(str(self.item_data.get("id")), checked)

    def _start_editing(self, event=None) -> None:
        self.lbl_text.hide()
        self.edit_line.setText(self.lbl_text.text())
        self.edit_line.show()
        self.edit_line.setFocus()
        self.edit_line.selectAll()

    def _finish_editing(self) -> None:
        if not self.edit_line.isVisible():
            return
        new_text = self.edit_line.text().strip()
        if new_text and new_text != self.lbl_text.text():
            self.lbl_text.setText(new_text)
            if callable(self.on_rename):
                self.on_rename(str(self.item_data.get("id")), new_text)
        self.edit_line.hide()
        self.lbl_text.show()


class TodoBoard(_DragBase):
    """One floating todo list. Use ＋ to open another list board."""

    def __init__(
        self,
        board: dict,
        on_save,
        parent=None,
        *,
        on_add_board=None,
        on_close_board=None,
        on_open_manager=None,
    ):
        super().__init__(parent)
        self.board = board
        self.on_save = on_save
        self.on_add_board = on_add_board
        self.on_close_board = on_close_board
        self.on_open_manager = on_open_manager
        self.mgr = TodoManager(board)
        self.color = str(board.get("color") or "#fef08a")
        self._pinned = True
        self._collapsed = False
        self._full_h = 430
        self.resize(380, self._full_h)
        self._build()
        self._apply_color()
        self.refresh()

    def board_id(self) -> str:
        return str(self.board.get("id") or "")

    def _summary_title(self) -> str:
        items = self.mgr.list_items()
        open_items = [str(t.get("text") or "").strip() for t in items if not t.get("done")]
        open_items = [t for t in open_items if t]
        title = self.title_edit.text().strip() or str(self.board.get("title") or "待办")
        n = len(items)
        done = n - len(open_items)
        if open_items:
            first = open_items[0]
            if len(first) > 14:
                first = first[:14] + "…"
            extra = f" 等{len(open_items)}项" if len(open_items) > 1 else ""
            return f"{title} · ☐ {first}{extra}"
        if n:
            return f"{title} · 全部完成 ({done}/{n})"
        return f"{title} · 暂无事项"

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.box = QFrame(objectName="box")
        self.lay = QVBoxLayout(self.box)
        # Header bar container for dragging
        self.header_bar = HeaderBar(self)
        self.header_bar.setObjectName("headerBar")
        head = QHBoxLayout(self.header_bar)
        head.setSpacing(3)
        head.setContentsMargins(6, 2, 6, 2)

        # Editable board title
        self.title_edit = DragLineEdit(self, str(self.board.get("title") or "待办"))
        self.title_edit.setObjectName("boardTitle")
        self.title_edit.setPlaceholderText("待办列表名称…")
        self.title_edit.setMinimumHeight(28)
        self.title_edit.editingFinished.connect(self._rename)
        head.addWidget(self.title_edit, 1)

        # Cute buttons with tooltips
        self.btn_new = QPushButton("➕")
        self.btn_new.setObjectName("soft")
        self.btn_new.setFixedSize(28, 28)
        self.btn_new.setToolTip("➕ 新建待办窗口 (再开一个列表)")
        self.btn_new.clicked.connect(self._add_another)
        head.addWidget(self.btn_new)

        self.btn_list = QPushButton("📋")
        self.btn_list.setObjectName("soft")
        self.btn_list.setFixedSize(28, 28)
        self.btn_list.setToolTip("📋 待办清单库 (管理所有待办板)")
        self.btn_list.clicked.connect(self._open_manager)
        head.addWidget(self.btn_list)

        self.btn_pin = QPushButton("📌" if self._pinned else "📍")
        self.btn_pin.setObjectName("soft")
        self.btn_pin.setFixedSize(28, 28)
        self.btn_pin.setToolTip("📌 窗口置顶 (在最前)" if self._pinned else "📍 取消置顶")
        self.btn_pin.clicked.connect(self._toggle_pin)
        head.addWidget(self.btn_pin)

        self.btn_fold = QPushButton("➖")
        self.btn_fold.setObjectName("soft")
        self.btn_fold.setFixedSize(28, 28)
        self.btn_fold.setToolTip("➖ 折叠成细条 (展开按 🔺)")
        self.btn_fold.clicked.connect(self._toggle_collapse)
        head.addWidget(self.btn_fold)

        self.btn_color = QPushButton("🎨")
        self.btn_color.setObjectName("soft")
        self.btn_color.setFixedSize(28, 28)
        self.btn_color.setToolTip("🎨 更换便笺色彩主题")
        self.btn_color.clicked.connect(self._pick_color)
        head.addWidget(self.btn_color)

        self.btn_del_board = QPushButton("🗑️")
        self.btn_del_board.setObjectName("soft")
        self.btn_del_board.setFixedSize(28, 28)
        self.btn_del_board.setToolTip("🗑️ 彻底删除此待办窗口")
        self.btn_del_board.clicked.connect(self._delete_board)
        head.addWidget(self.btn_del_board)

        self.btn_close = QPushButton("❌")
        self.btn_close.setObjectName("soft")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setToolTip("❌ 关闭此窗口 (可再次打开)")
        self.btn_close.clicked.connect(self._close)
        head.addWidget(self.btn_close)

        self.lay.addWidget(self.header_bar)
        self.lbl_title = self.title_edit

        self.body_wrap = QWidget()
        bl = QVBoxLayout(self.body_wrap)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        self.list = QListWidget()
        self.list.setMinimumHeight(140)
        bl.addWidget(self.list, 1)
        tip = QLabel("双击事项可编辑")
        tip.setStyleSheet("font-size:11px; font-weight:600; color:#64748b;")
        bl.addWidget(tip)
        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("输入新待办内容…")
        self.inp.setMinimumHeight(34)
        self.inp.returnPressed.connect(self._add)
        self.btn_add = QPushButton("＋")
        self.btn_add.setMinimumHeight(34)
        self.btn_add.setFixedWidth(38)
        self.btn_add.setToolTip("添加待办")
        self.btn_add.clicked.connect(self._add)
        row.addWidget(self.inp, 1)
        row.addWidget(self.btn_add)
        bl.addLayout(row)
        row2 = QHBoxLayout()
        del_btn = QPushButton("删除选中", objectName="soft")
        del_btn.setMinimumHeight(30)
        del_btn.clicked.connect(self._delete)
        clr = QPushButton("清除已完成", objectName="soft")
        clr.setMinimumHeight(30)
        clr.clicked.connect(self._clear_done)
        row2.addWidget(del_btn)
        row2.addWidget(clr)
        bl.addLayout(row2)
        self.lay.addWidget(self.body_wrap, 1)
        root.addWidget(self.box)

    def _header_btn_style(self, fg: str, bg: str) -> str:
        control = "#475569" if _luma(bg) > 0.55 else "#e2e8f0"
        return (
            f"QPushButton {{ background:transparent; color:{control}; border:none; "
            f"border-radius:7px; padding:0; font-weight:700; font-size:14px; }}"
            f"QPushButton:hover {{ background:rgba(255,255,255,0.50); color:#2563eb; }}"
        )

    def _apply_color(self) -> None:
        qss = _board_qss(self.color, "#4f46e5")
        self.box.setStyleSheet(qss)
        fg = _fg_on(self.color)
        self.list.setStyleSheet(qss)
        for i in range(self.list.count()):
            self.list.item(i).setForeground(QColor(fg))
        soft = self._header_btn_style(fg, self.color)
        for b in (self.btn_new, self.btn_list, self.btn_pin, self.btn_fold, self.btn_color, self.btn_del_board, self.btn_close):
            b.setStyleSheet(soft)
        self.btn_new.setStyleSheet(soft + "QPushButton { font-size:20px; }")
        title_fg = "#273746" if _luma(self.color) > 0.55 else fg
        self.title_edit.setStyleSheet(
            f"QLineEdit#boardTitle {{ background:transparent; border:none; color:{title_fg}; "
            f"font-weight:900; font-size:16px; padding:2px 4px; }}"
        )
        self.board["color"] = self.color
        self.on_save()

    def _rename(self) -> None:
        name = self.title_edit.text().strip() or "待办"
        self.title_edit.setText(name)
        self.board["title"] = name
        self.on_save()

    def _add_another(self) -> None:
        self._rename()
        if callable(self.on_add_board):
            self.on_add_board()

    def _open_manager(self) -> None:
        if callable(self.on_open_manager):
            self.on_open_manager()

    def _close(self) -> None:
        """Hide and mark auto_open=False so next launch / 打开待办 won't reopen it."""
        self._rename()
        self.board["auto_open"] = False
        self.on_save()
        self.hide()
        if callable(self.on_close_board):
            self.on_close_board(self.board_id(), delete=False)

    def _delete_board(self) -> None:
        """Permanently remove this todo board from storage."""
        from PyQt6.QtWidgets import QMessageBox

        n = len(self.mgr.list_items())
        title = self.title_edit.text().strip() or "待办"
        msg = f"确定永久删除待办窗口「{title}」吗？"
        if n:
            msg += f"\n其中还有 {n} 条事项，删除后不可恢复。"
        reply = QMessageBox.question(
            self,
            "删除待办窗口",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.hide()
        if callable(self.on_close_board):
            self.on_close_board(self.board_id(), delete=True)

    def _apply_pin(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.btn_pin.setText("◆" if self._pinned else "◇")

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        self._apply_pin()

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self.body_wrap.setVisible(not self._collapsed)
        if self._collapsed:
            self.title_edit.setText(self._summary_title())
            self.title_edit.setReadOnly(True)
            self.btn_fold.setText("🔺")
            self.btn_new.hide()
            self.btn_list.hide()
            self.btn_pin.hide()
            self.btn_color.hide()
            self.btn_del_board.hide()
            self.btn_close.hide()
            self._full_h = max(self.height(), 280)
            self.lay.setContentsMargins(8, 4, 6, 4)
            self.lay.setSpacing(0)
            self.setMinimumHeight(0)
            self.setMaximumHeight(36)
            self.setFixedHeight(36)
            self.btn_fold.setFixedHeight(28)
            self.btn_fold.setFixedWidth(30)
        else:
            self.title_edit.setReadOnly(False)
            self.title_edit.setText(str(self.board.get("title") or "待办"))
            self.btn_fold.setText("➖")
            self.btn_new.show()
            self.btn_list.show()
            self.btn_pin.show()
            self.btn_color.show()
            self.btn_del_board.show()
            self.btn_close.show()
            self.btn_fold.setFixedHeight(30)
            self.btn_fold.setMinimumWidth(30)
            self.btn_fold.setMaximumWidth(16777215)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.resize(self.width(), self._full_h)
            self.lay.setContentsMargins(12, 10, 12, 12)
            self.lay.setSpacing(8)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self, "待办主题色")
        if c.isValid():
            self.color = c.name()
            self._apply_color()

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.mgr.list_items():
            it = QListWidgetItem(self.list)
            row_w = TodoItemRowWidget(
                t,
                on_toggle=self._on_row_toggle,
                on_rename=self._on_row_rename,
                parent=self.list,
            )
            sh = row_w.sizeHint()
            it.setSizeHint(QSize(sh.width(), max(44, sh.height())))
            it.setData(Qt.ItemDataRole.UserRole, t.get("id"))
            self.list.addItem(it)
            self.list.setItemWidget(it, row_w)
        self.list.blockSignals(False)
        if self._collapsed:
            self.title_edit.setText(self._summary_title())

    def _on_row_toggle(self, tid: str, checked: bool) -> None:
        for t in self.mgr.list_items():
            if str(t.get("id")) == str(tid):
                if bool(t.get("done")) != checked:
                    self.mgr.toggle(str(tid))
                    self.on_save()
                break
        if self._collapsed:
            self.title_edit.setText(self._summary_title())

    def _add(self) -> None:
        text = self.inp.text().strip()
        if not text:
            self.inp.setFocus()
            self.inp.setPlaceholderText("请先输入内容再添加…")
            return
        if self._collapsed:
            self._toggle_collapse()
        self.mgr.add(text)
        self.inp.clear()
        self.inp.setPlaceholderText("输入新待办内容…")
        self.on_save()
        self.refresh()
        self.inp.setFocus()
        if self.list.count():
            self.list.setCurrentRow(0)

    def _on_row_rename(self, tid: str, new_text: str) -> None:
        for t in self.mgr.list_items():
            if str(t.get("id")) == str(tid):
                t["text"] = new_text[:200]
                self.on_save()
                break
        if self._collapsed:
            self.title_edit.setText(self._summary_title())

    def _delete(self) -> None:
        it = self.list.currentItem()
        if not it:
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid:
            self.mgr.remove(str(tid))
            self.on_save()
            self.refresh()

    def _clear_done(self) -> None:
        self.mgr.clear_done()
        self.on_save()
        self.refresh()


class TodosController:
    """Manages multiple TodoBoard windows (like multi sticky notes)."""

    def __init__(self, state: dict, on_save):
        self.state = state
        self.on_save = on_save
        self.store = TodoBoardsStore(state)
        self.windows: dict[str, TodoBoard] = {}
        self.manager_win: TodoBoardsListWindow | None = None

    def show_manager(self) -> None:
        if self.manager_win is None:
            self.manager_win = TodoBoardsListWindow(self)
        self.manager_win.refresh()
        self.manager_win.show()
        self.manager_win.raise_()
        self.manager_win.activateWindow()

    def show_all(self) -> None:
        """Open at most ONE active todo board if none are currently visible."""
        visible_wins = [w for w in self.windows.values() if w.isVisible()]
        if visible_wins:
            for w in visible_wins:
                w.raise_()
                w.activateWindow()
            return

        boards = self.store.list_boards()
        if boards:
            target = None
            for b in boards:
                if b.get("auto_open", True):
                    target = b
                    break
            if not target:
                target = boards[0]
            self._ensure_window(target)
        else:
            self.add_board()

    def add_board(self) -> None:
        b = self.store.add_board()
        b["auto_open"] = True
        self.on_save()
        self._ensure_window(b)

    def _ensure_window(self, board: dict) -> None:
        bid = str(board.get("id") or "")
        if not bid:
            return
        board["auto_open"] = True
        if bid in self.windows:
            w = self.windows[bid]
            if not w.isVisible():
                w.show()
            w.raise_()
            w.activateWindow()
            return
        w = TodoBoard(
            board,
            self.on_save,
            on_add_board=self.add_board,
            on_close_board=self._on_close,
            on_open_manager=self.show_manager,
        )
        off = 28 * (len(self.windows) % 10)
        w.move(100 + off, 100 + off)
        w.show()
        w.raise_()
        self.windows[bid] = w

    def _on_close(self, board_id: str, delete: bool = False) -> None:
        w = self.windows.pop(board_id, None)
        if w is not None:
            try:
                w.hide()
                w.deleteLater()
            except Exception:
                pass
        if delete:
            self.store.remove_board(board_id)
            self.on_save()


class StickyNoteWindow(_DragBase):
    """One floating sticky note with color. Use ＋ to open another note."""

    def __init__(
        self,
        note: dict,
        mgr: NoteManager,
        on_save,
        on_close_note,
        parent=None,
        *,
        on_add_note=None,
        on_open_manager=None,
    ):
        super().__init__(parent)
        self.note = note
        self.mgr = mgr
        self.on_save = on_save
        self.on_close_note = on_close_note
        self.on_add_note = on_add_note
        self.on_open_manager = on_open_manager
        self.resize(320, 300)
        self.color = str(note.get("color") or NOTE_COLORS[0])
        self._pinned = True
        self._collapsed = False
        self._full_h = 300
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.box = QFrame(objectName="box")
        lay = QVBoxLayout(self.box)
        lay.setContentsMargins(12, 9, 12, 12)

        self.header_bar = HeaderBar(self)
        self.header_bar.setObjectName("headerBar")
        head = QHBoxLayout(self.header_bar)
        head.setSpacing(3)
        head.setContentsMargins(6, 2, 6, 2)

        self.title = DragLineEdit(self, str(note.get("title") or "便签"))
        self.title.setObjectName("noteTitle")
        self.title.setPlaceholderText("便签标题…")
        head.addWidget(self.title, 1)

        # Cute buttons with tooltips
        self.btn_new = QPushButton("➕", objectName="soft")
        self.btn_new.setFixedSize(28, 28)
        self.btn_new.setToolTip("➕ 新建一张便签")
        self.btn_new.clicked.connect(self._add_another)
        head.addWidget(self.btn_new)

        self.btn_list = QPushButton("📋", objectName="soft")
        self.btn_list.setFixedSize(28, 28)
        self.btn_list.setToolTip("📋 历史便签管理 (查看所有保存的便签)")
        self.btn_list.clicked.connect(self._open_manager)
        head.addWidget(self.btn_list)

        self.btn_pin = QPushButton("📌" if self._pinned else "📍", objectName="soft")
        self.btn_pin.setFixedSize(28, 28)
        self.btn_pin.setToolTip("📌 窗口置顶 (在最前)" if self._pinned else "📍 取消置顶")
        self.btn_pin.clicked.connect(self._toggle_pin)
        head.addWidget(self.btn_pin)

        self.btn_fold = QPushButton("➖", objectName="soft")
        self.btn_fold.setFixedSize(28, 28)
        self.btn_fold.setToolTip("➖ 折叠便签 (展开按 🔺)")
        self.btn_fold.clicked.connect(self._toggle_collapse)
        head.addWidget(self.btn_fold)

        self.btn_color = QPushButton("🎨", objectName="soft")
        self.btn_color.setFixedSize(28, 28)
        self.btn_color.setToolTip("🎨 更换便签颜色")
        self.btn_color.clicked.connect(self._pick_color)
        head.addWidget(self.btn_color)

        self.btn_delete = QPushButton("🗑️", objectName="soft")
        self.btn_delete.setFixedSize(28, 28)
        self.btn_delete.setToolTip("🗑️ 彻底删除这张便签")
        self.btn_delete.clicked.connect(self._delete_note)
        head.addWidget(self.btn_delete)

        self.btn_close = QPushButton("❌", objectName="soft")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setToolTip("❌ 关闭便签")
        self.btn_close.clicked.connect(self._close_and_save)
        head.addWidget(self.btn_close)

        lay.addWidget(self.header_bar)
        self.body = QTextEdit()
        self.body.setPlainText(str(note.get("body") or ""))
        self.body.setPlaceholderText("开始记录…")
        lay.addWidget(self.body, 1)
        root.addWidget(self.box)
        self._apply_note_style()
        self.title.editingFinished.connect(self._persist)
        self.body.textChanged.connect(self._persist)

    def _apply_note_style(self) -> None:
        fg = _fg_on(self.color)
        control = "#475569" if _luma(self.color) > 0.55 else "#e2e8f0"
        title_fg = "#273746" if _luma(self.color) > 0.55 else fg
        self.box.setStyleSheet(_board_qss(self.color, "#ca8a04"))
        self.title.setStyleSheet(
            f"QLineEdit#noteTitle {{ background:transparent; border:none; color:{title_fg}; "
            f"font-weight:800; font-size:15px; padding:2px 4px; }}"
        )
        self.body.setStyleSheet(
            f"QTextEdit {{ background:transparent; border:none; color:{fg}; "
            f"border-radius:8px; padding:7px 4px; font-size:15px; }}"
            if _luma(self.color) > 0.55
            else f"QTextEdit {{ background:transparent; border:none; color:{fg}; "
            f"border-radius:8px; padding:7px 4px; font-size:15px; }}"
        )
        soft = (
            f"QPushButton {{ background:transparent; color:{control}; border:none; "
            f"border-radius:7px; padding:0; font-weight:700; font-size:14px; }}"
            f"QPushButton:hover {{ background:rgba(255,255,255,0.50); color:#2563eb; }}"
        )
        for b in (self.btn_new, self.btn_list, self.btn_pin, self.btn_fold, self.btn_color, self.btn_delete, self.btn_close):
            b.setStyleSheet(soft)
        self.btn_new.setStyleSheet(soft + "QPushButton { font-size:19px; }")

    def _add_another(self) -> None:
        self._persist()
        if callable(self.on_add_note):
            self.on_add_note()

    def _open_manager(self) -> None:
        if callable(self.on_open_manager):
            self.on_open_manager()

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.btn_pin.setText("📌" if self._pinned else "📍")

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self.body.setVisible(not self._collapsed)
        if self._collapsed:
            name = self.title.text().strip() or "便签"
            self.title.setText(name)
            self.title.setReadOnly(True)
            self.title.show()
            self.title.setMinimumHeight(22)
            self.body.hide()
            self.btn_fold.setText("🔺")
            self.btn_new.hide()
            self.btn_list.hide()
            self.btn_pin.hide()
            self.btn_color.hide()
            self.btn_delete.hide()
            self.btn_close.hide()
            self._full_h = max(self.height(), 180)
            self.box.layout().setContentsMargins(8, 4, 6, 4)
            self.setMinimumHeight(0)
            self.setMaximumHeight(36)
            self.setFixedHeight(36)
            self.btn_fold.setFixedHeight(24)
            self.btn_fold.setFixedWidth(28)
            fg = _fg_on(self.color)
            self.title.setStyleSheet(
                f"QLineEdit#noteTitle {{ background: transparent; border: none; color: {fg}; "
                f"font-weight: 900; font-size: 13px; padding: 0 4px; }}"
            )
            self.setToolTip(name)
        else:
            self.title.setReadOnly(False)
            self.title.setMinimumHeight(0)
            self.body.show()
            self.btn_fold.setText("➖")
            self.btn_new.show()
            self.btn_list.show()
            self.btn_pin.show()
            self.btn_color.show()
            self.btn_delete.show()
            self.btn_close.show()
            self.btn_fold.setFixedHeight(22)
            self.btn_fold.setMinimumWidth(28)
            self.btn_fold.setMaximumWidth(16777215)
            self.box.layout().setContentsMargins(12, 9, 12, 12)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.resize(self.width(), self._full_h)
            self.setToolTip("")
            self._apply_note_style()

    def _persist(self) -> None:
        nid = str(self.note.get("id") or "")
        if not nid:
            return
        self.mgr.update(nid, self.title.text(), self.body.toPlainText())
        for n in self.mgr.list_items():
            if n.get("id") == nid:
                n["color"] = self.note.get("color") or NOTE_COLORS[0]
                break
        self.on_save()

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(str(self.note.get("color") or NOTE_COLORS[0])), self, "便签颜色")
        if c.isValid():
            self.note["color"] = c.name()
            self.color = c.name()
            self._apply_note_style()
            self._persist()

    def _close_and_save(self) -> None:
        self._persist()
        self.note["auto_open"] = False
        self.on_save()
        self.on_close_note(str(self.note.get("id") or ""), delete=False)
        self.hide()

    def _delete_note(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        title = self.title.text().strip() or "便签"
        reply = QMessageBox.question(
            self,
            "删除便签",
            f"确定永久删除「{title}」吗？内容不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        nid = str(self.note.get("id") or "")
        self.on_close_note(nid, delete=True)
        self.hide()


class NotesController:
    """Manages multiple sticky note windows. Each note has ＋ to create another."""

    def __init__(self, state: dict, on_save):
        self.state = state
        self.on_save = on_save
        self.mgr = NoteManager(state)
        self.windows: dict[str, StickyNoteWindow] = {}
        self.manager_win: NotesListWindow | None = None

    def show_manager(self) -> None:
        if self.manager_win is None:
            self.manager_win = NotesListWindow(self)
        self.manager_win.refresh()
        self.manager_win.show()
        self.manager_win.raise_()
        self.manager_win.activateWindow()

    def show_all(self) -> None:
        """Open at most ONE active note if none are currently visible."""
        visible_wins = [w for w in self.windows.values() if w.isVisible()]
        if visible_wins:
            for w in visible_wins:
                w.raise_()
                w.activateWindow()
            return

        notes = self.mgr.list_items()
        if notes:
            target = None
            for n in notes:
                if n.get("auto_open", True):
                    target = n
                    break
            if not target:
                target = notes[0]
            self._ensure_window(target)
        else:
            self.add_note()

    def add_note(self) -> None:
        n = len(self.mgr.list_items()) + 1
        note = self.mgr.add(f"便签 {n}", "")
        note["color"] = NOTE_COLORS[(n - 1) % len(NOTE_COLORS)]
        note["auto_open"] = True
        self.on_save()
        self._ensure_window(note)

    def _ensure_window(self, note: dict) -> None:
        nid = str(note.get("id") or "")
        if not nid:
            return
        note["auto_open"] = True
        if nid in self.windows:
            w = self.windows[nid]
            if not w.isVisible():
                w.show()
            w.raise_()
            w.activateWindow()
            return
        w = StickyNoteWindow(
            note,
            self.mgr,
            self.on_save,
            self._on_close,
            on_add_note=self.add_note,
            on_open_manager=self.show_manager,
        )
        off = 28 * (len(self.windows) % 10)
        w.move(140 + off, 140 + off)
        w.show()
        w.raise_()
        self.windows[nid] = w

    def _on_close(self, nid: str, delete: bool = False) -> None:
        w = self.windows.pop(nid, None)
        if w is not None:
            try:
                w.hide()
                w.deleteLater()
            except Exception:
                pass
        if delete and nid:
            self.mgr.remove(nid)
            self.on_save()


class NotesListWindow(QWidget):
    """Floating Note Manager dialog: View, search, edit, open, or delete all saved sticky notes."""

    def __init__(self, ctl: NotesController, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("📋 历史便签管理")
        self.resize(440, 540)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', Microsoft YaHei, sans-serif;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                color: #f8fafc;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QListWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 6px;
                outline: none;
            }
            QPushButton#primary {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#primary:hover {
                background-color: #1d4ed8;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        # Header bar
        head = QHBoxLayout()
        lbl_title = QLabel("📋 历史便签库")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38bdf8;")
        head.addWidget(lbl_title)
        head.addStretch()

        btn_new = QPushButton("➕ 新建便签", objectName="primary")
        btn_new.clicked.connect(self._create_new)
        head.addWidget(btn_new)
        lay.addLayout(head)

        # Search bar
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("🔍 搜索历史便签内容或标题…")
        self.search_inp.textChanged.connect(self.refresh)
        lay.addWidget(self.search_inp)

        # Notes list
        self.list_widget = QListWidget()
        lay.addWidget(self.list_widget, 1)

        self.refresh()

    def _create_new(self) -> None:
        self.ctl.add_note()
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        query = self.search_inp.text().strip().lower()
        items = self.ctl.mgr.list_items()

        for note in items:
            t = str(note.get("title") or "便签")
            b = str(note.get("body") or "")
            if query and query not in t.lower() and query not in b.lower():
                continue

            it = QListWidgetItem(self.list_widget)
            card = NoteCardRowWidget(note, self.ctl, on_refresh=self.refresh)
            sh = card.sizeHint()
            it.setSizeHint(QSize(sh.width(), max(76, sh.height())))
            self.list_widget.addItem(it)
            self.list_widget.setItemWidget(it, card)


class NoteCardRowWidget(QWidget):
    """Card item in Sticky Notes Manager."""

    def __init__(self, note: dict, ctl: NotesController, on_refresh=None, parent=None):
        super().__init__(parent)
        self.note = note
        self.ctl = ctl
        self.on_refresh = on_refresh
        self.setMinimumHeight(76)

        color_hex = str(note.get("color") or NOTE_COLORS[0])
        nid = str(note.get("id") or "")
        is_open = nid in ctl.windows and ctl.windows[nid].isVisible()

        self.setStyleSheet("""
            QWidget {
                background: #0f172a;
                border-radius: 8px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # Color Pill Indicator
        pill = QLabel()
        pill.setFixedSize(14, 14)
        pill.setStyleSheet(f"background-color: {color_hex}; border-radius: 7px;")
        lay.addWidget(pill)

        # Text Info Stack
        info = QVBoxLayout()
        info.setSpacing(2)

        lbl_title = QLabel(str(note.get("title") or "便签"))
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #f8fafc;")
        info.addWidget(lbl_title)

        snippet = str(note.get("body") or "").replace("\n", " ").strip()
        if len(snippet) > 40:
            snippet = snippet[:40] + "…"
        if not snippet:
            snippet = "（无内容）"
        lbl_body = QLabel(snippet)
        lbl_body.setStyleSheet("font-size: 12px; color: #94a3b8;")
        info.addWidget(lbl_body)

        updated = str(note.get("updated") or "")
        if updated and "T" in updated:
            updated = updated.replace("T", " ")[:16]
        status_str = f"🟢 桌面显示 · {updated}" if is_open else f"⚪ 已隐藏 · {updated}"
        lbl_status = QLabel(status_str)
        lbl_status.setStyleSheet("font-size: 11px; color: #64748b;")
        info.addWidget(lbl_status)

        lay.addLayout(info, 1)

        # Actions
        btn_open = QPushButton("👁️ 显示" if not is_open else "📌 前置")
        btn_open.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #38bdf8; border: 1px solid #334155;
                border-radius: 6px; padding: 5px 10px; font-weight: 700; font-size: 12px;
            }
            QPushButton:hover { background: #334155; color: #ffffff; }
        """)
        btn_open.clicked.connect(self._open_note)
        lay.addWidget(btn_open)

        btn_del = QPushButton("🗑️")
        btn_del.setToolTip("删除此便签")
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ef4444; border: none;
                font-weight: 700; font-size: 14px; padding: 4px;
            }
            QPushButton:hover { background: rgba(239,68,68,0.15); border-radius: 4px; }
        """)
        btn_del.clicked.connect(self._delete_note)
        lay.addWidget(btn_del)

    def _open_note(self) -> None:
        self.ctl._ensure_window(self.note)
        if callable(self.on_refresh):
            self.on_refresh()

    def _delete_note(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        title = str(self.note.get("title") or "便签")
        reply = QMessageBox.question(
            self,
            "删除便签",
            f"确定从历史库中删除「{title}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            nid = str(self.note.get("id") or "")
            self.ctl._on_close(nid, delete=True)
            if callable(self.on_refresh):
                self.on_refresh()


class TodoBoardsListWindow(QWidget):
    """Floating Todo Boards Manager dialog: View, open, or delete saved todo boards."""

    def __init__(self, ctl: TodosController, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("📋 待办清单管理")
        self.resize(440, 540)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', Microsoft YaHei, sans-serif;
            }
            QListWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 6px;
                outline: none;
            }
            QPushButton#primary {
                background-color: #10b981;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#primary:hover {
                background-color: #059669;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        # Header bar
        head = QHBoxLayout()
        lbl_title = QLabel("📋 待办清单库")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #34d399;")
        head.addWidget(lbl_title)
        head.addStretch()

        btn_new = QPushButton("➕ 新建待办板", objectName="primary")
        btn_new.clicked.connect(self._create_new)
        head.addWidget(btn_new)
        lay.addLayout(head)

        # List widget
        self.list_widget = QListWidget()
        lay.addWidget(self.list_widget, 1)

        self.refresh()

    def _create_new(self) -> None:
        self.ctl.add_board()
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        boards = self.ctl.store.list_boards()

        for b in boards:
            it = QListWidgetItem(self.list_widget)
            card = TodoBoardCardRowWidget(b, self.ctl, on_refresh=self.refresh)
            sh = card.sizeHint()
            it.setSizeHint(QSize(sh.width(), max(76, sh.height())))
            self.list_widget.addItem(it)
            self.list_widget.setItemWidget(it, card)


class TodoBoardCardRowWidget(QWidget):
    """Card item in Todo Boards Manager."""

    def __init__(self, board: dict, ctl: TodosController, on_refresh=None, parent=None):
        super().__init__(parent)
        self.board = board
        self.ctl = ctl
        self.on_refresh = on_refresh
        self.setMinimumHeight(76)

        color_hex = str(board.get("color") or "#fef08a")
        bid = str(board.get("id") or "")
        is_open = bid in ctl.windows and ctl.windows[bid].isVisible()

        items = board.get("items") or []
        done_cnt = sum(1 for i in items if i.get("done"))
        total_cnt = len(items)

        self.setStyleSheet("""
            QWidget {
                background: #0f172a;
                border-radius: 8px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # Color Pill Indicator
        pill = QLabel()
        pill.setFixedSize(14, 14)
        pill.setStyleSheet(f"background-color: {color_hex}; border-radius: 7px;")
        lay.addWidget(pill)

        # Info stack
        info = QVBoxLayout()
        info.setSpacing(2)

        lbl_title = QLabel(str(board.get("title") or "待办"))
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #f8fafc;")
        info.addWidget(lbl_title)

        lbl_progress = QLabel(f"已完成 {done_cnt} / {total_cnt} 项事项")
        lbl_progress.setStyleSheet("font-size: 12px; color: #94a3b8;")
        info.addWidget(lbl_progress)

        status_str = "🟢 桌面显示" if is_open else "⚪ 已隐藏"
        lbl_status = QLabel(status_str)
        lbl_status.setStyleSheet("font-size: 11px; color: #64748b;")
        info.addWidget(lbl_status)

        lay.addLayout(info, 1)

        # Actions
        btn_open = QPushButton("👁️ 显示" if not is_open else "📌 前置")
        btn_open.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #34d399; border: 1px solid #334155;
                border-radius: 6px; padding: 5px 10px; font-weight: 700; font-size: 12px;
            }
            QPushButton:hover { background: #334155; color: #ffffff; }
        """)
        btn_open.clicked.connect(self._open_board)
        lay.addWidget(btn_open)

        btn_del = QPushButton("🗑️")
        btn_del.setToolTip("删除此待办板")
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ef4444; border: none;
                font-weight: 700; font-size: 14px; padding: 4px;
            }
            QPushButton:hover { background: rgba(239,68,68,0.15); border-radius: 4px; }
        """)
        btn_del.clicked.connect(self._delete_board)
        lay.addWidget(btn_del)

    def _open_board(self) -> None:
        self.ctl._ensure_window(self.board)
        if callable(self.on_refresh):
            self.on_refresh()

    def _delete_board(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        title = str(self.board.get("title") or "待办")
        reply = QMessageBox.question(
            self,
            "删除待办板",
            f"确定从历史库中删除待办板「{title}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            bid = str(self.board.get("id") or "")
            self.ctl._on_close(bid, delete=True)
            if callable(self.on_refresh):
                self.on_refresh()
