"""Offline validation diagnostics and paused-job recovery tests."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import meta_ai_generator as meta
from modules.meta_clip_download import (
    MetaClipDownloadError,
    _commit_valid_bytes,
    _video_metadata,
    _validation_label,
)
from modules.meta_ai_generator import _validate_meta_clip
from recover_meta_scene import recover


class DiagnosticRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('ffmpeg and ffprobe required')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.good = cls.root / 'good.mp4'
        cls.silent = cls.root / 'silent.mp4'
        for path, audio in ((cls.good, True), (cls.silent, False)):
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y',
                '-f','lavfi','-i','testsrc2=size=1080x1920:rate=1']
            if audio:
                cmd += ['-f','lavfi','-i','sine=frequency=330:sample_rate=16000']
            cmd += ['-t','10','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p']
            if audio:
                cmd += ['-c:a','aac','-b:a','64k']
            cmd += [str(path)]
            result = subprocess.run(cmd, capture_output=True, timeout=50)
            if result.returncode:
                raise unittest.SkipTest('could not build local test fixture')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_invalid_audio_reason_is_visible_and_video_retained(self):
        target = self.root / 'job1' / 'renders' / 'scene_01.mp4'
        target.parent.mkdir(parents=True, exist_ok=True)
        events = []
        success = _commit_valid_bytes(self.silent.read_bytes(), target,
                                      _validate_meta_clip, events.append)
        self.assertFalse(success)
        self.assertEqual(events[0]['reason'], 'missing_native_audio_or_video_track')
        self.assertFalse(target.exists())
        self.assertEqual(events[0]['media']['audio_track'], False)
        self.assertTrue((target.parent.parent / 'debug' / 'scene_01_rejected_export.mp4').is_file())

    def test_valid_clip_commits_atomically(self):
        target = self.root / 'job2' / 'renders' / 'scene_01.mp4'
        target.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(_commit_valid_bytes(self.good.read_bytes(), target, _validate_meta_clip))
        _validate_meta_clip(target)
        self.assertFalse((target.with_name(target.name + '.download-part')).exists())

    def test_manual_recovery_into_paused_scene(self):
        root = self.root / 'jobs'
        job = root / 'channel_2' / 'episode-test'
        (job / 'debug').mkdir(parents=True, exist_ok=True)
        (job / 'manifest.json').write_text(json.dumps({
            'channel_id':'channel_2','render_backend':'meta_ai',
            'scenes':[{'index':1,'filename':'scene_01.mp4'}]
        }), encoding='utf-8')
        marker = job / 'debug' / 'scene_01_download_pending.json'
        marker.write_text('{}')
        clip = recover(2, self.good, jobs_root=root)
        self.assertTrue(clip.is_file())
        self.assertTrue(marker.is_file())
        _validate_meta_clip(clip)

    def test_bad_recovery_leaves_marker_and_renders_untouched(self):
        root = self.root / 'jobs2'
        job = root / 'channel_2' / 'episode-test'
        (job / 'debug').mkdir(parents=True, exist_ok=True)
        (job / 'manifest.json').write_text(json.dumps({
            'channel_id':'channel_2','render_backend':'meta_ai',
            'scenes':[{'index':1,'filename':'scene_01.mp4'}]
        }), encoding='utf-8')
        marker = job / 'debug' / 'scene_01_download_pending.json'
        marker.write_text('{}')
        with self.assertRaises(Exception):
            recover(2, self.silent, jobs_root=root)
        self.assertTrue(marker.exists())
        self.assertFalse((job / 'renders' / 'scene_01.mp4').exists())

    def test_safe_validation_categories(self):
        self.assertEqual(_validation_label(Exception('scene_01.mp4 missing video or Meta-native audio; no fallback')),
                         'missing_native_audio_or_video_track')
        self.assertEqual(_validation_label(Exception('scene_04.mp4 duplicates an earlier scene')),
                         'duplicate_earlier_scene')
        self.assertEqual(_validation_label(Exception('sensitive https://example/?access_token=abcd')),
                         'validation_rejected')

    def test_confirmed_below_720p_continues_account_failover(self):
        debug = self.root / 'quality' / 'scene_01.png'
        error = MetaClipDownloadError(
            'rendered below policy',
            rejection_reasons={'source_resolution_below_720p'},
        )
        with patch.object(meta, 'save_generated_clip', side_effect=error):
            with self.assertRaises(meta.MetaAIQualityUnavailable):
                meta._save_media_source(None, None, 'https://meta.invalid/video',
                                        self.root / 'quality' / 'scene_01.mp4', debug)
        self.assertFalse(
            debug.with_name('scene_01_download_pending.json').exists()
        )

    def test_duplicate_export_retries_instead_of_pausing_as_download_pending(self):
        debug = self.root / 'duplicate' / 'scene_04.png'
        error = MetaClipDownloadError(
            'rendered duplicate',
            rejection_reasons={'duplicate_earlier_scene'},
        )
        with patch.object(meta, 'save_generated_clip', side_effect=error):
            with self.assertRaises(meta.MetaAIDuplicateScene):
                meta._save_media_source(
                    None, None, 'https://meta.invalid/video',
                    self.root / 'duplicate' / 'scene_04.mp4', debug,
                )
        self.assertFalse(
            debug.with_name('scene_04_download_pending.json').exists()
        )


if __name__ == '__main__':
    unittest.main()
