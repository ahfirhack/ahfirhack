"""Offline tests for the standalone GitHub Actions Meta smoke test.

No real browser, Meta generation, video downloads, or YouTube uploads.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import meta_github_smoke as smoke


class GitHubSmokeTests(unittest.TestCase):
    def test_workflow_job_env_uses_dispatch_supported_context(self):
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" /
            "meta_ai_smoke_test.yml"
        ).read_text(encoding="utf-8")
        job_header = workflow.split("    steps:", 1)[0]
        self.assertNotIn("runner.temp", job_header)
        self.assertIn("${{ github.workspace }}/.meta-ai-session/", job_header)
        self.assertIn("mkdir -p", workflow)

    def test_prompt_has_five_beats_and_no_user_secrets(self):
        from modules.meta_ai_generator import _split_narration
        beats = _split_narration(smoke.STORY, 5)
        self.assertEqual(len(beats), 5)
        self.assertTrue(all(len(beat.split()) >= 5 for beat in beats))
        self.assertNotIn('token', smoke.STORY.lower())

    def test_only_one_or_five_scenes(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                smoke.run_smoke(3, Path(temp))

    def _browser_mocks(self):
        manager = MagicMock()
        manager.return_value.__enter__.return_value = object()
        context, browser = MagicMock(), MagicMock()
        return manager, context, browser

    def test_one_scene_creates_and_downloads_once_without_assembly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / 'jobs' / 'channel_2' / 'smoke'
            for sub in ('renders', 'continuity', 'debug'):
                (job / sub).mkdir(parents=True, exist_ok=True)
            scene = {'index': 1, 'filename': 'scene_01.mp4', 'prompt': 'Test video'}
            manifest = {'scenes': [scene]}
            context_manager, context, browser = self._browser_mocks()

            def generate(_context, _prompt, target, _kind, attachment, _debug):
                self.assertIsNone(attachment)
                Path(target).write_bytes(b'0' * 20000)

            def last_frame(_video, image):
                Path(image).write_bytes(b'png')

            with patch.object(smoke, '_storage_state_path', return_value=root / 'session.json'), \
                 patch.object(smoke, '_storage_state_slots', return_value=[(1, root / 'session.json')]), \
                 patch.object(smoke, 'create_job', return_value=(manifest, job)), \
                 patch.object(smoke, '_load_playwright', return_value=context_manager), \
                 patch.object(smoke, '_launch_context', return_value=(context, browser)), \
                 patch.object(smoke, '_generate_media', side_effect=generate) as generated, \
                 patch.object(smoke, '_validate_meta_clip') as validate, \
                 patch.object(smoke, '_extract_last_frame', side_effect=last_frame), \
                 patch.object(smoke, '_video_metadata', return_value={'readable': True, 'audio_track': True}) as metadata, \
                 patch.object(smoke, 'assemble_meta_short') as assembly:
                success = smoke.run_smoke(1, root / 'artifacts')
            self.assertTrue(success)
            self.assertEqual(generated.call_count, 1)
            self.assertEqual(validate.call_count, 1)
            self.assertEqual(metadata.call_count, 1)
            assembly.assert_not_called()
            self.assertTrue((root / 'artifacts' / 'clips' / 'scene_01.mp4').is_file())
            self.assertEqual(json.loads((root / 'artifacts' / 'result.json').read_text())['result'], 'passed')
            self.assertFalse((root / 'artifacts' / 'short').exists())
            self.assertTrue(context.close.called)
            self.assertTrue(browser.close.called)

    def test_failed_download_is_reported_and_never_resubmits_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / 'jobs' / 'channel_2' / 'smoke'
            for sub in ('renders', 'continuity', 'debug'):
                (job / sub).mkdir(parents=True, exist_ok=True)
            (job / 'debug' / 'scene_01_download.json').write_text(json.dumps({
                'download_events': 1, 'saved': False,
                'source_scheme': 'blob', 'private_media_url': 'SECRET',
                'rejections': [{'method': 'browser-download', 'reason': 'SECRET'}],
            }))
            context_manager, context, browser = self._browser_mocks()
            with patch.object(smoke, '_storage_state_path', return_value=root / 'session.json'), \
                 patch.object(smoke, '_storage_state_slots', return_value=[(1, root / 'session.json')]), \
                 patch.object(smoke, 'create_job', return_value=({'scenes': [
                     {'index': 1, 'filename': 'scene_01.mp4', 'prompt': 'Test'}]}, job)), \
                 patch.object(smoke, '_load_playwright', return_value=context_manager), \
                 patch.object(smoke, '_launch_context', return_value=(context, browser)), \
                 patch.object(smoke, '_generate_media', side_effect=RuntimeError('browser failed SECRET')) as generated:
                success = smoke.run_smoke(1, root / 'artifacts')
            self.assertFalse(success)
            self.assertEqual(generated.call_count, 1)
            report = json.loads((root / 'artifacts' / 'result.json').read_text())
            self.assertEqual(report['result'], 'failed')
            self.assertEqual(report['failure']['stage'], 'scene_01_generate_download')
            diagnostic = (root / 'artifacts' / 'diagnostics' / 'scene_01_download.json').read_text()
            self.assertNotIn('SECRET', diagnostic)
            self.assertNotIn('SECRET', (root / 'artifacts' / 'summary.md').read_text())
            self.assertFalse((root / 'artifacts' / 'clips').exists())

    def test_five_scenes_exercise_handoffs_and_assembly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / 'jobs' / 'channel_2' / 'smoke'
            for sub in ('renders', 'continuity', 'debug'):
                (job / sub).mkdir(parents=True, exist_ok=True)
            scenes = [{'index': i, 'filename': f'scene_{i:02d}.mp4', 'prompt': 'Test'} for i in range(1, 6)]
            context_manager, context, browser = self._browser_mocks()
            references = []

            def generate(_context, _prompt, target, _kind, attachment, _debug):
                references.append(attachment)
                Path(target).write_bytes(b'0' * 20000)

            def last_frame(_video, image):
                Path(image).write_bytes(b'png')

            def assembly(clip_paths, output_filename, continuity_dir, scene_seconds=10):
                out = root / output_filename
                out.write_bytes(b'1' * 20000)
                return str(out)

            with patch.object(smoke, '_storage_state_path', return_value=root / 'session.json'), \
                 patch.object(smoke, '_storage_state_slots', return_value=[(1, root / 'session.json')]), \
                 patch.object(smoke, 'create_job', return_value=({'scenes': scenes}, job)), \
                 patch.object(smoke, '_load_playwright', return_value=context_manager), \
                 patch.object(smoke, '_launch_context', return_value=(context, browser)), \
                 patch.object(smoke, '_generate_media', side_effect=generate) as generated, \
                 patch.object(smoke, '_validate_meta_clip'), \
                 patch.object(smoke, '_check_scene_handoff') as handoff, \
                 patch.object(smoke, '_extract_last_frame', side_effect=last_frame), \
                 patch.object(smoke, '_video_metadata', return_value={'readable': True, 'audio_track': True}), \
                 patch.object(smoke, 'assemble_meta_short', side_effect=assembly) as assembled:
                success = smoke.run_smoke(5, root / 'artifacts')
            self.assertTrue(success)
            self.assertEqual(generated.call_count, 5)
            self.assertEqual(handoff.call_count, 4)
            self.assertEqual(assembled.call_count, 1)
            self.assertIsNone(references[0])
            self.assertTrue(all(path is not None for path in references[1:]))
            self.assertTrue((root / 'artifacts' / 'short' / 'META_GITHUB_SMOKE_50S.mp4').is_file())
            self.assertEqual(len(list((root / 'artifacts' / 'clips').glob('scene_*.mp4'))), 5)


if __name__ == '__main__':
    unittest.main()
