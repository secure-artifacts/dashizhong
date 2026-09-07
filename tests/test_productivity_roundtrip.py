import os
import tempfile
import unittest
from unittest.mock import patch

from productivity import TodoBoardsStore, TodoManager, NoteManager
from storage import JsonStore


class ProductivityRoundtripTests(unittest.TestCase):
    def test_todos_notes_and_other_settings_survive_save_reload(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CLOCK_ALARM_DATA_DIR': folder}):
            store = JsonStore()
            store.state['alarms'] = [{'id': 'alarm-test', 'enabled': True, 'time': '08:00'}]
            boards = TodoBoardsStore(store.state)
            first = boards.list_boards()[0]
            todos = TodoManager(first)
            todos.add('测试待办')
            item = todos.list_items()[0]
            todos.toggle(item['id'])
            other = boards.add_board('第二块清单')
            TodoManager(other).add('保留项目')
            notes = NoteManager(store.state)
            note = notes.add('测试便签', '第一行\n第二行')
            notes.update(note['id'], '更新标题', '新内容')
            store.save_state()
            restored = JsonStore()
            self.assertTrue(restored.state['todo_lists'][0]['items'][0]['done'])
            self.assertEqual(NoteManager(restored.state).get(note['id'])['body'], '新内容')
            self.assertEqual(restored.state['alarms'], store.state['alarms'])
            todos.clear_done()
            notes.remove(note['id'])
            store.save_state()
            final = JsonStore()
            self.assertEqual(final.state['todo_lists'][0]['items'], [])
            self.assertEqual(final.state['todo_lists'][1]['items'][0]['text'], '保留项目')
            self.assertEqual(final.state['notes'], [])
