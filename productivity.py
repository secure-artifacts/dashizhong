"""Local todo-list and sticky-note data helpers."""

from __future__ import annotations

import uuid
from datetime import datetime


def _uid() -> str:
    return uuid.uuid4().hex[:12]


class TodoManager:
    """Manage the items belonging to one todo board."""

    def __init__(self, board: dict) -> None:
        self.board = board
        self.board.setdefault("items", [])

    def list_items(self) -> list[dict]:
        return list(self.board.get("items") or [])

    def add(self, text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return "请填写待办内容。"
        item = {
            "id": _uid(),
            "text": cleaned[:200],
            "done": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        self.board.setdefault("items", []).insert(0, item)
        return f"已添加待办：{cleaned[:40]}"

    def toggle(self, item_id: str) -> str:
        for item in self.board.get("items") or []:
            if item.get("id") == item_id:
                item["done"] = not bool(item.get("done"))
                return "已完成。" if item["done"] else "已重新打开。"
        return "未找到该待办。"

    def remove(self, item_id: str) -> str:
        before = len(self.board.get("items") or [])
        self.board["items"] = [
            item for item in (self.board.get("items") or []) if item.get("id") != item_id
        ]
        return "已删除待办。" if len(self.board["items"]) < before else "未找到该待办。"

    def clear_done(self) -> str:
        items = self.board.get("items") or []
        kept = [item for item in items if not item.get("done")]
        removed = len(items) - len(kept)
        self.board["items"] = kept
        return f"已清除 {removed} 条已完成。"


class TodoBoardsStore:
    """Manage multiple floating todo boards."""

    DEFAULT_COLORS = [
        "#fef08a",
        "#bbf7d0",
        "#bfdbfe",
        "#fecaca",
        "#e9d5ff",
        "#fed7aa",
    ]

    def __init__(self, state: dict) -> None:
        self.state = state
        self._migrate()

    def _migrate(self) -> None:
        boards = self.state.get("todo_lists")
        if isinstance(boards, list) and boards:
            return
        legacy_items = list(self.state.get("todos") or [])
        color = str((self.state.get("todo_board") or {}).get("color") or "#fef08a")
        self.state["todo_lists"] = [
            {
                "id": _uid(),
                "title": "待办",
                "color": color,
                "items": legacy_items,
            }
        ]

    def list_boards(self) -> list[dict]:
        self._migrate()
        return list(self.state.get("todo_lists") or [])

    def add_board(self, title: str | None = None) -> dict:
        self._migrate()
        number = len(self.list_boards()) + 1
        board = {
            "id": _uid(),
            "title": (title or "").strip() or f"待办 {number}",
            "color": self.DEFAULT_COLORS[(number - 1) % len(self.DEFAULT_COLORS)],
            "items": [],
        }
        self.state.setdefault("todo_lists", []).append(board)
        return board

    def get_board(self, board_id: str) -> dict | None:
        for board in self.list_boards():
            if board.get("id") == board_id:
                return board
        return None

    def remove_board(self, board_id: str) -> None:
        self.state["todo_lists"] = [
            board
            for board in (self.state.get("todo_lists") or [])
            if board.get("id") != board_id
        ]


class NoteManager:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.state.setdefault("notes", [])

    def list_items(self) -> list[dict]:
        return list(self.state.get("notes") or [])

    def add(self, title: str, body: str = "") -> dict:
        title = (title or "").strip()[:80] or "便签"
        body = (body or "").strip()[:4000]
        item = {
            "id": _uid(),
            "title": title,
            "body": body,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        self.state.setdefault("notes", []).insert(0, item)
        return item

    def get(self, note_id: str) -> dict | None:
        for item in self.state.get("notes") or []:
            if item.get("id") == note_id:
                return item
        return None

    def update(self, note_id: str, title: str, body: str) -> str:
        for item in self.state.get("notes") or []:
            if item.get("id") == note_id:
                item["title"] = (title or "").strip()[:80] or "便签"
                item["body"] = (body or "").strip()[:4000]
                item["updated"] = datetime.now().isoformat(timespec="seconds")
                return "便签已更新。"
        return "未找到该便签。"

    def remove(self, note_id: str) -> str:
        before = len(self.state.get("notes") or [])
        self.state["notes"] = [
            item for item in (self.state.get("notes") or []) if item.get("id") != note_id
        ]
        return "已删除便签。" if len(self.state["notes"]) < before else "未找到该便签。"
