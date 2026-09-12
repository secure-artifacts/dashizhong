import os
import unittest
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from media_player_ui import (
    MediaPlayerWindow,
    matches_search,
    to_simplified,
    to_traditional,
)


class TestMediaPlayerFavoritesAndSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_simplified_traditional_conversion_and_search(self):
        # 1. Direct conversion
        s = "盡本分"
        simp = to_simplified(s)
        self.assertEqual(simp, "尽本分")

        t = "教会"
        trad = to_traditional(t)
        self.assertEqual(trad, "教會")

        # 2. Search matching
        # Traditional query matching simplified text
        self.assertTrue(matches_search("盡本分", "每日尽本分合神心意"))
        # Simplified query matching traditional text
        self.assertTrue(matches_search("尽本分", "每日盡本分合神心意"))
        # Case-insensitive English matching
        self.assertTrue(matches_search("bEsT", "The Best Song Ever"))
        # Partial match
        self.assertTrue(matches_search("教會", "基督教会视频合辑"))
        # Non-matching
        self.assertFalse(matches_search("敬拜", "每日尽本分合神心意"))

    def test_favorites_toggle_and_persistence(self):
        saved_state = {
            "media": {
                "playlist": [
                    {"title": "Song 1", "url": "https://example.com/1"},
                    {"title": "Song 2", "url": "https://example.com/2"},
                ],
                "favorites": [],
            }
        }
        saved_calls = []

        def fake_save():
            saved_calls.append(True)

        win = MediaPlayerWindow(state=saved_state, save_state=fake_save)

        # Initially no favorites
        self.assertEqual(len(win.favorites), 0)
        self.assertFalse(win.is_favorite("https://example.com/1"))

        # Toggle favorite on Song 1
        win.toggle_favorite("Song 1", "https://example.com/1")
        self.assertTrue(win.is_favorite("https://example.com/1"))
        self.assertEqual(len(win.favorites), 1)
        self.assertEqual(win.favorites[0], ("Song 1", "https://example.com/1"))
        self.assertIn("https://example.com/1", win.favorite_urls)
        self.assertEqual(len(saved_state["media"]["favorites"]), 1)
        self.assertTrue(len(saved_calls) > 0)

        # Toggle favorite off
        win.toggle_favorite("Song 1", "https://example.com/1")
        self.assertFalse(win.is_favorite("https://example.com/1"))
        self.assertEqual(len(win.favorites), 0)
        self.assertEqual(len(saved_state["media"]["favorites"]), 0)

        win.close()

    def test_favorites_auto_seeding_on_upgrade(self):
        # When favorites is None (first upgrade from older version)
        # Non-update songs should be auto-seeded into favorites to prevent loss
        state = {
            "media": {
                "playlist": [
                    {"title": "My Favorite Song", "url": "https://example.com/fav"},
                    {"title": "[更新 · Channel] New Video", "url": "https://example.com/new"},
                ],
            }
        }
        win = MediaPlayerWindow(state=state)
        self.assertEqual(len(win.favorites), 1)
        self.assertEqual(win.favorites[0], ("My Favorite Song", "https://example.com/fav"))
        self.assertTrue(win.is_favorite("https://example.com/fav"))
        self.assertFalse(win.is_favorite("https://example.com/new"))
        win.close()

    def test_dual_list_playback_modes(self):
        state = {
            "media": {
                "playlist": [
                    {"title": "P1", "url": "https://example.com/p1"},
                    {"title": "P2", "url": "https://example.com/p2"},
                ],
                "favorites": [
                    {"title": "F1", "url": "https://example.com/f1"},
                    {"title": "F2", "url": "https://example.com/f2"},
                    {"title": "F3", "url": "https://example.com/f3"},
                ],
            }
        }
        win = MediaPlayerWindow(state=state)

        # Playlist tab active
        win._set_active_tab("playlist")
        current_list = win._get_active_playback_list()
        self.assertEqual(len(current_list), 2)
        self.assertEqual(current_list[0][0], "P1")

        # Favorites tab active
        win._set_active_tab("favorites")
        fav_list = win._get_active_playback_list()
        self.assertEqual(len(fav_list), 3)
        self.assertEqual(fav_list[0][0], "F1")

        # Playback navigation in favorites tab
        win.current_index = 0
        win.play_mode = "loop"
        # Mock play_index to verify next index computation
        win.play_index = MagicMock()
        win.play_next()
        win.play_index.assert_called_with(1)

        win.current_index = 2
        win.play_next()
        win.play_index.assert_called_with(0)  # looped back to 0 in favorites list of len 3

        win.close()

    def test_smart_feed_trimming_preserves_favorites(self):
        state = {
            "media": {
                "playlist_limit": 3,
                "playlist": [
                    {"title": "User Song 1", "url": "https://example.com/user1"},
                    {"title": "[更新 · Ch] Feed 1", "url": "https://example.com/feed1"},
                ],
                "favorites": [
                    {"title": "User Song 1", "url": "https://example.com/user1"},
                ],
            }
        }
        win = MediaPlayerWindow(state=state)

        # Add 3 new feed videos, pushing total count beyond limit of 3
        new_feeds = [
            {"channel_title": "Ch", "title": "Feed 2", "url": "https://example.com/feed2"},
            {"channel_title": "Ch", "title": "Feed 3", "url": "https://example.com/feed3"},
            {"channel_title": "Ch", "title": "Feed 4", "url": "https://example.com/feed4"},
        ]
        win.add_feed_videos(new_feeds)

        # Check that total items do not exceed 3, and User Song 1 (favorited) was NOT pruned
        self.assertLessEqual(len(win.playlist), 3)
        urls = [u for _, u in win.playlist]
        self.assertIn("https://example.com/user1", urls)
        self.assertIn("https://example.com/feed4", urls)
        self.assertNotIn("https://example.com/feed1", urls)  # Oldest non-favorited feed video dropped

        win.close()

    def test_audio_output_rebind(self):
        state = {"media": {}}
        win = MediaPlayerWindow(state=state)
        # Calling _rebind_audio_output directly should not raise exceptions
        win._rebind_audio_output()
        self.assertIsNotNone(win.audio_output)
        win.close()


if __name__ == "__main__":
    unittest.main()
