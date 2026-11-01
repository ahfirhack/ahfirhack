"""Offline regression tests; no browser, Meta generation or uploads."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from modules import meta_ai_generator as mod


class DualSurfaceTests(unittest.TestCase):
    def test_create_is_the_only_production_default(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(mod._meta_surface_order(), ['create'])

    def test_vibes_first_override_and_dedupe(self):
        with patch.dict('os.environ', {'META_AI_SURFACES':'vibes,create,vibes'}):
            self.assertEqual(mod._meta_surface_order(), ['vibes','create'])

    def test_reject_untrusted_surface(self):
        with patch.dict('os.environ', {'META_AI_SURFACES':'other'}):
            with self.assertRaises(mod.MetaAIAutomationError):
                mod._meta_surface_order()

    def test_safe_location_strips_query_and_ids(self):
        page=MagicMock()
        page.url='https://meta.ai/create/abcd?access_token=SECRET'
        self.assertEqual(mod._safe_page_location(page), {'site':'meta.ai','route':'/create'})

    def test_fallback_to_vibes_when_create_has_no_editor(self):
        with tempfile.TemporaryDirectory() as temp:
            first=MagicMock(); second=MagicMock(); third=MagicMock()
            ctx=MagicMock();ctx.new_page.side_effect=[first,second,third]
            editor=object()
            with patch.dict('os.environ', {'META_AI_SURFACES':'studio,create,vibes'}), \
                 patch.object(mod, '_open_meta_surface') as open_fn, \
                 patch.object(mod,'_find_prompt_editor',side_effect=[None,None,editor]), \
                 patch.object(mod,'_save_surface_diagnostic',side_effect=lambda page,path,surface: {'surface':surface,'site':'meta.ai','route':'/'+surface,'auth_gate_visible':False}):
                page, found, surface=mod._acquire_meta_editor(ctx,Path(temp)/'debug.png')
                self.assertIs(page,third)
                self.assertIs(found,editor)
                self.assertEqual(surface,'vibes')
                self.assertTrue(first.close.called and second.close.called)
                self.assertFalse(third.close.called)
                self.assertEqual(open_fn.call_count,3)

    def test_no_editor_writes_nonsecret_diagnostics_and_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            one=MagicMock(); two=MagicMock(); three=MagicMock()
            ctx=MagicMock();ctx.new_page.side_effect=[one,two,three]
            def diagnostic(page, path, surface):
                return {'surface':surface,'site':'meta.ai','route':'/'+surface,'auth_gate_visible':False}
            with patch.dict('os.environ', {'META_AI_SURFACES':'studio,create,vibes'}), \
                 patch.object(mod, '_open_meta_surface'), \
                 patch.object(mod,'_find_prompt_editor',return_value=None), \
                 patch.object(mod,'_save_surface_diagnostic',side_effect=diagnostic):
                with self.assertRaises(mod.MetaAIAutomationError):
                    mod._acquire_meta_editor(ctx,Path(temp)/'debug.png')
            result=Path(temp)/'debug_editor_check.json'
            self.assertTrue(result.is_file())
            self.assertEqual(len(json.loads(result.read_text())['results']),3)
            self.assertTrue(one.close.called and two.close.called and three.close.called)

    def test_editor_unavailable_fails_fast_and_is_classified(self):
        self.assertTrue(issubclass(mod.MetaAIEditorUnavailable,mod.MetaAIAutomationError))

    def test_only_meta_host_and_no_password_inputs(self):
        self.assertTrue(mod._meta_hostname('https://meta.ai/create'))
        self.assertFalse(mod._meta_hostname('https://meta.ai.evil.test/create'))
        editor=MagicMock(); editor.is_visible.return_value=True; editor.is_enabled.return_value=True
        editor.get_attribute.side_effect=lambda name: {'placeholder':'Search videos'}.get(name,'')
        self.assertFalse(mod._valid_prompt_editor(editor))

    def test_do_not_use_chat_route_as_video_editor(self):
        page=MagicMock();page.url='https://meta.ai/chat'
        with patch.object(mod, "_dismiss_consent"), patch.object(mod, "_looks_like_auth_gate", return_value=False):
            with self.assertRaises(mod.MetaAIEditorUnavailable):
                mod._open_meta_surface(page,"create")

    def test_video_only_generator_rejects_image_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(mod.MetaAIAutomationError,'VIDEO'):
                mod._generate_media(MagicMock(),'prompt',Path(temp)/'media.mp4','image',None,Path(temp)/'debug.png')


if __name__=='__main__': unittest.main()
