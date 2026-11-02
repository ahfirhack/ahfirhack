"""Offline policy tests for 4-channel Meta-only 5x10s scheduled pipeline."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import CHANNELS, META_SCENE_COUNT, META_SCENE_DURATION, UPLOAD_INTERVAL_HOURS
from modules import meta_ai_generator as meta
from modules import script_generator
from modules import video_assembler


STORY = {
    "title": "The Locked Train Door",
    "script": (
        "Mara found a locked train door just as the lights dimmed. "
        "She checked the window and saw a shadow on the platform. "
        "A small note warned her that someone was waiting outside. "
        "She kept calm, found an emergency latch, and revealed the truth. "
        "It was a staged test, and she had solved it with seconds left."
    ),
    "tags": ["fiction", "shorts"],
    "search_query": "locked train door",
}


class MetaOnlyPolicyTests(unittest.TestCase):
    def test_four_channels_are_meta_only_with_native_audio(self):
        self.assertEqual(4, len(CHANNELS))
        self.assertEqual(5, META_SCENE_COUNT)
        self.assertEqual(10, META_SCENE_DURATION)
        self.assertEqual(6, UPLOAD_INTERVAL_HOURS)
        for channel in CHANNELS:
            with self.subTest(channel=channel["id"]):
                self.assertEqual("meta_ai_browser", channel["media_source"])
                self.assertTrue(channel["native_clip_audio"])
                self.assertTrue(channel["seamless_scenes"])
                self.assertFalse(channel["use_voice"])
                self.assertFalse(channel["use_music"])
                self.assertFalse(channel["show_overlays"])
                self.assertEqual(50, channel["target_duration"])

    def test_every_channel_creates_five_unique_native_audio_video_prompts(self):
        for channel in CHANNELS:
            with self.subTest(channel=channel["id"]):
                with tempfile.TemporaryDirectory() as temp:
                    with patch.object(meta, "META_AI_JOBS_DIR", temp):
                        manifest, job_dir = meta.create_job(channel, STORY)
                    self.assertEqual(5, len(manifest["scenes"]))
                    self.assertEqual("meta_ai", manifest["render_backend"])
                    self.assertTrue(manifest["native_audio"])
                    self.assertEqual(50, manifest["target_duration_seconds"])
                    self.assertEqual(4, manifest["schema_version"])
                    self.assertRegex(manifest["episode_code"], r"^[A-Z]{3}-[0-9A-F]{6}$")
                    for index, scene in enumerate(manifest["scenes"], start=1):
                        self.assertEqual(index, scene["index"])
                        self.assertEqual(10, scene["duration_seconds"])
                        self.assertIn("VIDEO GENERATION ONLY", scene["prompt"])
                        self.assertIn("NATIVE", scene["prompt"].upper())
                        self.assertIn(f"SCENE {index}/5", scene["prompt"])
                        self.assertIn("ABSOLUTE EPISODE TIME", scene["prompt"])
                        self.assertIn("FIXED VOICE ID", scene["prompt"])
                        self.assertIn("10-SECOND STORYBOARD", scene["prompt"])
                        self.assertIn("LOCK LAST FRAME", scene["prompt"])
                        self.assertIn("STITCH REQUIREMENT", scene["prompt"])
                        self.assertIn("says EXACTLY", scene["prompt"])
                        self.assertIn("never display them as text", scene["prompt"])
                        self.assertTrue(scene["action"])
                        self.assertTrue(scene["end_frame"])
                        if index > 1:
                            self.assertIn("ATTACHED", scene["prompt"])
                            self.assertIn("previous Meta video", scene["prompt"])
                    self.assertIn("\f", (job_dir / "meta_prompts.txt").read_text())

    def test_legacy_story_is_split_on_complete_sentence_boundaries(self):
        beats = meta._split_narration(STORY["script"], 5)
        self.assertEqual(5, len(beats))
        self.assertTrue(all(beat.endswith((".", "!", "?")) for beat in beats))
        self.assertEqual(STORY["script"], " ".join(beats))

    def test_text_generator_requires_five_precise_production_rows(self):
        prompt = script_generator._build_prompt("cinematic storytelling", "seed")
        self.assertIn("scene_plan with EXACTLY five rows", prompt)
        self.assertIn("dialogue", prompt)
        self.assertIn("action", prompt)
        self.assertIn("end_frame", prompt)
        valid = {
            "scene_plan": [
                {
                    "dialogue": f"The lead completes precise action number {index} now.",
                    "action": f"The lead moves prop number {index} toward the marked doorway.",
                    "end_frame": f"Lead left, prop {index} centered, doorway visible behind them.",
                }
                for index in range(1, 6)
            ]
        }
        self.assertEqual(5, len(script_generator._normalized_scene_plan(valid)))
        valid["scene_plan"][2]["action"] = "vague"
        self.assertIsNone(script_generator._normalized_scene_plan(valid))

    def test_health_check_has_no_legacy_stock_visual_requirement(self):
        source = Path("check_script_generators.py").read_text(encoding="utf-8")
        self.assertIn("result['scene_plan']", source)
        self.assertNotIn("result['visual_queries']", source)

    def test_expired_or_quota_limited_meta_never_switches_to_image_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = {"render_backend": "meta_ai"}
            error = meta.MetaAIVideoUnavailable("Meta quota exceeded")
            with patch.object(meta, "_ensure_meta_rendered_clips", side_effect=error):
                with self.assertRaises(meta.MetaAIVideoUnavailable):
                    meta.ensure_rendered_clips(manifest, Path(temp))

    def test_new_sidebar_generation_limit_is_keyed_by_conversation(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        matches = MagicMock()
        matches.count.return_value = 3
        visible = [MagicMock(), MagicMock(), MagicMock()]
        for candidate, state in zip(visible, (True, False, True)):
            candidate.is_visible.return_value = state
        visible[0].evaluate.return_value = "/prompt/old-limit"
        visible[2].evaluate.return_value = "/prompt/new-limit"
        matches.nth.side_effect = visible
        page.get_by_text.return_value = matches
        self.assertEqual(
            {"route:/prompt/old-limit", "route:/prompt/new-limit"},
            meta._generation_limit_keys(page, "video"),
        )
        matches.nth.side_effect = visible
        self.assertEqual(2, meta._generation_limit_count(page, "video"))

    def test_alternative_media_backends_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(meta.MetaAIAutomationError):
                meta.ensure_rendered_clips({"render_backend": "ai_horde_motion"}, Path(temp))

    def test_assembler_rejects_anything_other_than_five_clips(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "exactly five"):
                video_assembler.assemble_meta_short([], "empty.mp4", Path(temp))

    def test_meta_source_accepts_720p_and_final_master_stays_above_1080p(self):
        self.assertGreaterEqual(video_assembler.WIDTH, 1080)
        self.assertGreaterEqual(video_assembler.HEIGHT, 1920)
        with tempfile.TemporaryDirectory() as temp:
            clip = Path(temp) / "native-720p.mp4"
            clip.write_bytes(b"v" * 12_000)
            probe = {
                "format": {"duration": "10.0"},
                "streams": [
                    {"codec_type": "video", "width": 720, "height": 1280},
                    {"codec_type": "audio", "duration": "10.0"},
                ],
            }
            with patch.object(meta, "_probe_video", return_value=probe):
                meta._validate_meta_clip(clip)

            probe["streams"][0].update(width=480, height=854)
            with patch.object(meta, "_probe_video", return_value=probe):
                with self.assertRaisesRegex(meta.MetaAIAutomationError, "below the required 720x1280"):
                    meta._validate_meta_clip(clip)

    def test_existing_three_scene_jobs_cannot_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            channel_dir = Path(temp) / "channel_3" / "old-3-scene"
            channel_dir.mkdir(parents=True)
            (channel_dir / "manifest.json").write_text(json.dumps({
                "status": "rendering", "scenes": [{"index": n} for n in (1, 2, 3)],
            }))
            with patch.object(meta, "META_AI_JOBS_DIR", temp):
                self.assertIsNone(meta.find_active_job("channel_3"))

    def test_workflow_is_every_six_hours_all_channels_and_has_no_stock_secrets(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/daily_upload.yml").read_text()
        self.assertIn('cron: "13 */6 * * *"', workflow)
        self.assertIn("${{ inputs.channel || 'all' }}", workflow)
        for secret in (
            "META_AI_STORAGE_STATE_B64",
            "META_AI_STORAGE_STATE_2_B64",
            "META_AI_STORAGE_STATE_3_B64",
            "META_AI_STORAGE_STATE_4_B64",
            "META_AI_STORAGE_STATE_5_B64",
        ):
            self.assertIn(secret, workflow)
        self.assertIn("META_AI_STORAGE_STATE_FILES", workflow)
        self.assertIn('META_MAX_HANDOFF_DELTA: "0.20"', workflow)
        self.assertIn('META_MAX_DUPLICATE_DELTA: "0.025"', workflow)
        self.assertIn('AI_HORDE_ENABLED: "false"', workflow)
        for forbidden in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", "DEEPGRAM_API_KEY"):
            self.assertNotIn(forbidden, workflow)


    def test_meta_create_never_calls_vibes_eligibility(self):
        """Stop regression to the preflight that incorrectly blocked Create."""
        import inspect
        source = inspect.getsource(meta)
        self.assertIn("https://meta.ai/vibes", source)
        self.assertNotIn("_require_video_eligible_account", source)

    def test_meta_create_accepts_only_create_urls(self):
        for valid in (
            "https://meta.ai/create",
            "https://www.meta.ai/create",
            "https://meta.ai/create/my-video",
        ):
            self.assertTrue(meta._is_meta_create_url(valid), valid)
        for invalid in (
            "https://meta.ai/vibes", "http://meta.ai/create",
            "https://meta.ai.evil.test/create", "https://meta.ai/chat",
            "https://another.example/create", "https://meta.ai/create-something",
        ):
            self.assertFalse(meta._is_meta_create_url(invalid), invalid)

    def test_create_page_opens_without_vibes_check(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.url = "https://meta.ai/create"
        with patch.object(meta, "META_AI_CREATE_URL", "https://meta.ai/create"):
            with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate", return_value=False):
                meta._open_create_page(page)
        page.goto.assert_called_once_with(
            "https://meta.ai/create", wait_until="domcontentloaded", timeout=120_000
        )

    def test_create_redirect_to_vibes_is_allowed_for_fallback(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.url = "https://meta.ai/vibes"
        with patch.object(meta, "META_AI_CREATE_URL", "https://meta.ai/create"):
            with patch.object(meta, "_dismiss_consent"), patch.object(meta, "_looks_like_auth_gate", return_value=False):
                with patch.object(meta, "_open_vibes_composer"), patch.object(meta, "_select_video_mode"):
                    meta._open_create_page(page)
        page.goto.assert_called_once()


if __name__ == "__main__":
    unittest.main()
