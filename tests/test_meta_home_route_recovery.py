"""Offline: Meta homepage redirects must never activate ordinary chat.

Does not contact Meta, retrieve cookies, generate video or upload anything.
"""
import unittest
from unittest.mock import MagicMock, patch
from modules import meta_ai_generator as meta


class HomepageRecoveryTests(unittest.TestCase):
    def test_root_with_explicit_video_button_is_eligible_for_editor_probe(self):
        page = MagicMock()
        page.url = "https://meta.ai/"
        with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate",return_value=False), \
             patch.object(meta, "_open_home_video_creator",return_value=True), \
             patch.object(meta, "_select_video_mode",return_value=False):
            meta._open_meta_surface(page, "create")

    def test_root_with_explicit_video_tab_is_eligible_for_editor_probe(self):
        page = MagicMock()
        page.url = "https://meta.ai/"
        with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate",return_value=False), \
             patch.object(meta, "_open_home_video_creator",return_value=False), \
             patch.object(meta, "_select_video_mode",return_value=True):
            meta._open_meta_surface(page, "vibes")

    def test_root_without_video_control_rejected(self):
        page = MagicMock()
        page.url = "https://meta.ai/"
        with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate",return_value=False), \
             patch.object(meta, "_open_home_video_creator",return_value=False), \
             patch.object(meta, "_select_video_mode",return_value=False):
            with self.assertRaisesRegex(meta.MetaAIEditorUnavailable, "homepage"):
                meta._open_meta_surface(page, "create")

    def test_visible_auth_gate_never_uses_root_chat(self):
        page = MagicMock()
        page.url = "https://meta.ai/"
        with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate",return_value=True), \
             patch.object(meta, "_open_home_video_creator") as navigate:
            with self.assertRaises(meta.MetaAILoginRequired):
                meta._open_meta_surface(page, "create")
            navigate.assert_not_called()

    def test_non_meta_redirect_is_rejected(self):
        page = MagicMock()
        page.url = "https://example.org/"
        with patch.object(meta, "_dismiss_consent"):
            with self.assertRaisesRegex(meta.MetaAIAutomationError, "unsupported website"):
                meta._open_meta_surface(page, "vibes")


if __name__ == "__main__":
    unittest.main()
