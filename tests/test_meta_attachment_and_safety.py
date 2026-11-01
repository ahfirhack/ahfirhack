"""Offline regressions for Meta frame attachments and safe public-record prompts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules import meta_ai_generator as meta


def _text_locator(visible: bool):
    locator = MagicMock()
    locator.count.return_value = 1 if visible else 0
    candidate = locator.nth.return_value
    candidate.is_visible.return_value = True
    candidate.bounding_box.return_value = {"x": 300, "y": 100}
    return locator


class MetaAttachmentAndSafetyTests(unittest.TestCase):
    def _response_page(self, response: str):
        page = MagicMock()
        page.url = "https://meta.ai/prompt/test"
        page.get_by_text.side_effect = lambda pattern: _text_locator(
            bool(pattern.search(response))
        )
        return page

    def test_missing_attachment_response_fails_immediately(self):
        page = self._response_page(
            "I can't access the attached PNG — it didn't arrive in the workspace "
            "(/mnt/data is empty), so please re-attach the PNG."
        )
        with patch.object(meta, "_media_sources", return_value=[]):
            with self.assertRaises(meta.MetaAIAttachmentError):
                meta._wait_for_media(page, "video", set())
        page.wait_for_timeout.assert_not_called()

    def test_content_refusal_fails_immediately(self):
        page = self._response_page(
            "I can't generate this exact clip because it centers on real, named individuals."
        )
        with patch.object(meta, "_media_sources", return_value=[]):
            with self.assertRaises(meta.MetaAIContentRejected):
                meta._wait_for_media(page, "video", set())
        page.wait_for_timeout.assert_not_called()

    def test_attachment_requires_stable_composer_evidence(self):
        page = MagicMock()

        def locator(selector):
            result = MagicMock()
            if selector == "input[type='file']":
                result.evaluate_all.return_value = True
            result.count.return_value = 0
            return result

        page.locator.side_effect = locator
        page.get_by_text.return_value = _text_locator(False)
        self.assertTrue(meta._wait_for_image_attachment(
            page, Path("scene_01_last.png"), baseline_markers=0,
            timeout_seconds=1,
        ))
        self.assertGreaterEqual(page.wait_for_timeout.call_count, 5)

    def test_channel_one_meta_prompt_omits_real_names_and_reenactment(self):
        story = {
            "title": "Named Officers Plead Guilty",
            "script": (
                "A Justice Department record says Zoltan Nagy and Glenn Laken "
                "pleaded guilty in a scheme causing over $1 million in losses."
            ),
            "search_query": "international securities case",
        }
        plan = meta._story_scene_plan(story, 5, channel_id="channel_1")
        prompt = meta._scene_prompt(
            2, plan[1]["dialogue"], story, {"id": "channel_1"},
            scene_plan=plan[1], episode_code="SCF-TEST",
        )
        self.assertNotIn("Zoltan", prompt)
        self.assertNotIn("Laken", prompt)
        self.assertNotIn("Named Officers", prompt)
        self.assertIn("fictional", prompt.lower())
        self.assertIn("No real person is shown", prompt)

    def test_cached_channel_one_job_is_upgraded_before_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "channel_1" / "old-job"
            job.mkdir(parents=True)
            story = {
                "title": "Named Defendant Charged",
                "script": "A record says Jane Example was charged in an alleged scheme.",
                "search_query": "corporate case",
            }
            manifest = {
                "job_id": "old-job",
                "channel_id": "channel_1",
                "channel_name": "Silicon Crime Files",
                "schema_version": meta.META_PROMPT_SCHEMA_VERSION,
                "render_backend": "meta_ai",
                "status": "rendering",
                "story": story,
                "scenes": [
                    {"index": number, "filename": f"scene_{number:02d}.mp4",
                     "prompt": "unsafe Jane Example prompt"}
                    for number in range(1, 6)
                ],
            }
            (job / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(meta, "META_AI_JOBS_DIR", temp):
                upgraded, directory = meta.find_active_job("channel_1")
            self.assertEqual(job, directory)
            self.assertEqual(2, upgraded["prompt_policy_version"])
            self.assertTrue(all(
                "Jane Example" not in scene["prompt"]
                for scene in upgraded["scenes"]
            ))
            self.assertTrue((job / "meta_prompts.txt").is_file())


if __name__ == "__main__":
    unittest.main()
