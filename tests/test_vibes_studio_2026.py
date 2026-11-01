"""Offline routing/security regression checks: no Meta or YouTube network calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from modules import meta_ai_generator as meta
import switch_meta_account as auth

class StudioTests(unittest.TestCase):
    def test_four_account_slots_have_isolated_files_and_secrets(self):
        self.assertEqual(auth.STATE_PATH, auth._slot_state_path(1))
        self.assertEqual("meta_ai_storage_state_2.json", auth._slot_state_path(2).name)
        self.assertEqual("META_AI_STORAGE_STATE_B64", auth._slot_secret_name(1))
        self.assertEqual("META_AI_STORAGE_STATE_4_B64", auth._slot_secret_name(4))

    def test_create_is_the_only_production_default_and_studio_is_verified(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(meta._meta_surface_order(), ['create'])
        self.assertEqual(meta._META_SURFACE_URLS['studio'],'https://vibes.ai/')
        self.assertTrue(meta._meta_hostname('https://vibes.ai/'))
        self.assertFalse(meta._meta_hostname('https://vibes.ai.evil.org/'))

    def test_login_import_includes_vibes_but_rejects_other_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.json'
            path.write_text(json.dumps({'cookies':[
                {'name':'meta_session','domain':'.vibes.ai','value':'secret'},
                {'name':'else','domain':'.other.test','value':'unrelated'}
            ],'origins':[{'origin':'https://vibes.ai','localStorage':[]},
                         {'origin':'https://other.test','localStorage':[]}]}))
            saved=json.loads(auth._limited_meta_state(path))
            self.assertEqual([c['domain'] for c in saved['cookies']], ['.vibes.ai'])
            self.assertEqual([o['origin'] for o in saved['origins']],['https://vibes.ai'])

    def test_login_import_preserves_meta_indexeddb_but_rejects_other_origins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw.json'
            meta_db = [{'name': 'auth-store', 'objectStores': []}]
            path.write_text(json.dumps({
                'cookies': [{'name': 'session', 'domain': '.meta.ai', 'value': 'secret'}],
                'origins': [
                    {'origin': 'https://meta.ai', 'localStorage': [], 'indexedDB': meta_db},
                    {'origin': 'https://other.test', 'localStorage': [], 'indexedDB': [{'name': 'private'}]},
                ],
            }))
            saved = json.loads(auth._limited_meta_state(path))
            self.assertEqual(['https://meta.ai'], [o['origin'] for o in saved['origins']])
            self.assertEqual(meta_db, saved['origins'][0]['indexedDB'])

    def test_open_chrome_import_exports_indexeddb_instead_of_basic_state_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'profiles'
            state = Path(tmp) / 'active.json'
            calls = []
            filtered = json.dumps({
                'cookies': [{'name': 'session', 'domain': '.vibes.ai', 'value': 'secret'}],
                'origins': [{'origin': 'https://meta.ai', 'localStorage': [], 'indexedDB': []}],
            }).encode()

            def record(args, **_kwargs):
                calls.append(args)

            with patch.object(auth, 'PROFILE_ROOT', root), \
                 patch.object(auth, 'STATE_PATH', state), \
                 patch.object(auth, '_chrome_cli', side_effect=record), \
                 patch.object(auth, '_limited_meta_state', return_value=filtered), \
                 patch.object(auth, '_validate_state', return_value=filtered):
                auth._import_open_chrome()

            export = next(args for args in calls if 'run-code' in args)
            self.assertIn('indexedDB: true', export[-1])
            self.assertNotIn('state-save', [part for args in calls for part in args])
            opened = [args[-1] for args in calls if 'tab-new' in args]
            self.assertEqual(['https://meta.ai/create', 'https://vibes.ai/'], opened)
            self.assertTrue(state.is_file())

    def test_studio_redirecting_off_its_site_fails_closed(self):
        page=MagicMock();page.url='https://meta.ai/'
        with patch.object(meta,'_dismiss_consent'),patch.object(meta,'_looks_like_auth_gate', return_value=False):
            with self.assertRaisesRegex(meta.MetaAIEditorUnavailable,'redirected away'):
                meta._open_meta_surface(page,'studio')

    def test_projects_dashboard_create_new_opens_editor(self):
        class ProjectsPage:
            url = 'https://vibes.ai/'

            def get_by_role(self, _role, *, name):
                return name

            def wait_for_timeout(self, _milliseconds):
                return None

        control = MagicMock()
        control.is_enabled.return_value = True

        def visible(pattern):
            return control if pattern.fullmatch('Create new') else None

        with patch.object(meta, '_find_prompt_editor', side_effect=[None, object()]), \
             patch.object(meta, '_visible_last', side_effect=visible), \
             patch.object(meta, '_looks_like_auth_gate', return_value=False):
            self.assertTrue(meta._open_studio_composer(ProjectsPage()))
        control.click.assert_called_once()

    def test_under_18_vibes_screen_is_classified_as_ineligible(self):
        page = MagicMock()
        page.url = 'https://meta.ai/vibes'
        page.get_by_text.return_value = object()
        with patch.object(meta, '_dismiss_consent'), \
             patch.object(meta, '_looks_like_auth_gate', return_value=False), \
             patch.object(meta, '_visible_last_in_content', return_value=object()):
            with self.assertRaisesRegex(meta.MetaAIVideoUnavailable, 'under 18'):
                meta._open_meta_surface(page, 'vibes')

    def test_studio_editor_cannot_be_replaced_with_ordinary_chat(self):
        page=MagicMock();page.url='https://vibes.ai/'
        with patch.object(meta,'_dismiss_consent'),patch.object(meta,'_looks_like_auth_gate', return_value=False), \
             patch.object(meta,'_open_studio_composer',return_value=False), \
             patch.object(meta,'_select_video_mode',return_value=False):
            meta._open_meta_surface(page,'studio')
        # Discoverer must still find a real editor; navigation alone is not success.
        with tempfile.TemporaryDirectory() as tmp:
            context=MagicMock();context.new_page.return_value=page
            with patch.object(meta,'_open_meta_surface'), \
                 patch.object(meta,'_find_prompt_editor',return_value=None), \
                 patch.object(meta,'_meta_surface_order',return_value=['studio']), \
                 patch.object(meta,'_save_surface_diagnostic',return_value={'surface':'studio','site':'vibes.ai','route':'/','auth_gate_visible':False}):
                with self.assertRaises(meta.MetaAIEditorUnavailable):
                    meta._acquire_meta_editor(context,Path(tmp)/'test.png')

    def test_auth_failures_marked_even_without_visible_login_button(self):
        with tempfile.TemporaryDirectory() as tmp:
            context=MagicMock(); page=MagicMock(); context.new_page.return_value=page
            with patch.object(meta,'_meta_surface_order',return_value=['studio']), \
                 patch.object(meta,'_open_meta_surface', side_effect=meta.MetaAILoginRequired('sign in')), \
                 patch.object(meta,'_save_surface_diagnostic',return_value={'surface':'studio','site':'vibes.ai','route':'/','auth_gate_visible':False}):
                with self.assertRaises(meta.MetaAILoginRequired):
                    meta._acquire_meta_editor(context,Path(tmp)/'test.png')

    def test_studio_send_requires_explicit_generate(self):
        page=MagicMock();page.url='https://vibes.ai/'
        editor=MagicMock()
        with patch.object(meta,'_visible_last',return_value=None):
            with self.assertRaisesRegex(meta.MetaAIEditorUnavailable,'Generate Video control'):
                meta._submit_prompt(page,editor,'test video')

    def test_studio_selects_highest_visible_quality(self):
        page = MagicMock()
        page.url = 'https://vibes.ai/projects/test'
        advanced = MagicMock()
        low, high = MagicMock(), MagicMock()
        for control, label in ((low, '720p'), (high, '1080p')):
            control.is_visible.return_value = True
            control.is_enabled.return_value = True
            control.inner_text.return_value = label
        controls = MagicMock()
        controls.count.return_value = 2
        controls.nth.side_effect = [low, high]
        page.get_by_role.return_value = controls
        with patch.object(meta, '_visible_last', return_value=advanced):
            self.assertEqual(1080, meta._select_highest_studio_quality(page))
        self.assertEqual(2, advanced.click.call_count)
        high.click.assert_called_once()
        low.click.assert_not_called()

    def test_studio_rejects_720p_only_account_before_generation(self):
        page = MagicMock()
        page.url = 'https://vibes.ai/projects/test'
        option = MagicMock()
        option.is_visible.return_value = True
        option.is_enabled.return_value = True
        option.inner_text.return_value = '720p'
        controls = MagicMock()
        controls.count.return_value = 1
        controls.nth.return_value = option
        page.get_by_role.return_value = controls
        with patch.object(meta, '_visible_last', return_value=MagicMock()):
            with self.assertRaisesRegex(meta.MetaAIQualityUnavailable, 'at least 1080p'):
                meta._select_highest_studio_quality(page)

if __name__=='__main__': unittest.main()
