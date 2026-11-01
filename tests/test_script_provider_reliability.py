"""Offline tests for paid-provider wiring and per-run failure cooldowns."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from modules import script_generator as scripts


class PaidScriptProviderTests(unittest.TestCase):
    def setUp(self):
        with scripts._PROVIDER_STATE_LOCK:
            scripts._PROVIDER_COOLDOWN_UNTIL.clear()

    def test_openai_uses_responses_structured_output(self):
        response = MagicMock()
        response.json.return_value = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"title":"A Complete Structured Story"}',
                        }
                    ],
                }
            ],
        }
        with (
            patch.object(scripts, "OPENAI_API_KEY", "test-key"),
            patch.object(scripts.requests, "post", return_value=response) as post,
        ):
            result = scripts._try_openai("make a story")

        self.assertEqual("A Complete Structured Story", result["title"])
        request = post.call_args.kwargs["json"]
        self.assertEqual(scripts.SCRIPT_MAX_OUTPUT_TOKENS, request["max_output_tokens"])
        output_format = request["text"]["format"]
        self.assertEqual("json_schema", output_format["type"])
        self.assertTrue(output_format["strict"])
        self.assertEqual(5, output_format["schema"]["properties"]["scene_plan"]["minItems"])

    def test_replicate_uses_existing_paid_key_and_full_token_budget(self):
        response = MagicMock()
        response.json.return_value = {
            "status": "succeeded",
            "output": ['{"title":"A Replicate Story"}'],
        }
        with (
            patch.object(scripts, "REPLICATE_API_KEY", "test-key"),
            patch.object(scripts.requests, "post", return_value=response) as post,
        ):
            result = scripts._try_replicate("make a story")

        self.assertEqual("A Replicate Story", result["title"])
        request = post.call_args.kwargs["json"]
        self.assertEqual(
            scripts.SCRIPT_MAX_OUTPUT_TOKENS,
            request["input"]["max_tokens"],
        )
        self.assertEqual("wait=60", post.call_args.kwargs["headers"]["Prefer"])

    def test_invalid_provider_is_not_retried_during_cooldown(self):
        provider = MagicMock(return_value={"title": "missing everything else"})
        with patch.object(
            scripts,
            "_configured_provider_chain",
            return_value=[(provider, "Broken Provider")],
        ):
            for _ in range(2):
                with self.assertRaises(scripts.ScriptGenerationError):
                    scripts.generate_script(
                        "cinematic storytelling",
                        allow_fallback=False,
                    )

        provider.assert_called_once()
        self.assertTrue(scripts._provider_is_cooling_down("Broken Provider"))

    def test_specific_short_title_is_not_discarded(self):
        self.assertFalse(
            scripts._reject_generic_title("Hidden Passenger", "storytelling")
        )
        self.assertTrue(
            scripts._reject_generic_title("What Happened Next", "storytelling")
        )

    def test_story_prompt_allows_natural_reaction_time(self):
        prompt = scripts._build_prompt("cinematic storytelling", "seed")
        self.assertIn("Script must be 55-110 TOTAL spoken words", prompt)

    def test_complete_scene_plan_survives_missing_trailing_metadata(self):
        candidate = {
            "title": "The Silver Station Key",
            "scene_plan": [
                {
                    "dialogue": (
                        "Mara follows the silver key while the station lights "
                        f"flicker around her {index}."
                    ),
                    "action": (
                        f"Mara carries the silver key toward doorway number {index}."
                    ),
                    "end_frame": (
                        f"Mara stands left, key centered, doorway {index} behind her."
                    ),
                }
                for index in range(1, 6)
            ],
        }
        provider = MagicMock(return_value=candidate)
        with patch.object(
            scripts,
            "_configured_provider_chain",
            return_value=[(provider, "Complete Story Provider")],
        ):
            result = scripts.generate_script(
                "cinematic storytelling",
                allow_fallback=False,
            )

        self.assertEqual(5, len(result["tags"]))
        self.assertIn("Silver Station Key", result["search_query"])
        self.assertGreaterEqual(len(result["script"].split()), 55)


if __name__ == "__main__":
    unittest.main()
