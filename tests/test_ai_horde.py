import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from modules import ai_horde
from modules import meta_ai_generator


def response(status=200, payload=None, content=b""):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    result.text = str(payload)
    result.content = content
    result.raise_for_status.side_effect = None
    return result


class AIHordeTests(unittest.TestCase):
    def test_choose_image_model_uses_known_safe_live_model(self):
        live = [
            {"name": "WAI-NSFW-illustrious-SDXL", "count": 20, "eta": 0},
            {"name": "stable_diffusion_2.1", "count": 1, "eta": 20},
        ]
        with patch.object(ai_horde, "_live_models", return_value=live):
            self.assertEqual(ai_horde._choose_model("image"), "stable_diffusion_2.1")

    def test_choose_text_model_prefers_general_qwen_over_coder(self):
        live = [
            {"name": "koboldcpp/Qwen2.5-Coder-3B-Instruct", "count": 2, "eta": 0},
            {"name": "Qwen/Qwen3.5-122B-A10B", "count": 1, "eta": 24},
        ]
        with patch.object(ai_horde, "_live_models", return_value=live):
            self.assertEqual(ai_horde._choose_model("text"), "Qwen/Qwen3.5-122B-A10B")

    def test_generate_text_parses_json_from_async_result(self):
        generated = {
            "done": True,
            "generations": [{"text": '```json\n{"title":"Test"}\n```'}],
        }
        with (
            patch.object(ai_horde, "_choose_model", return_value="Qwen/Test"),
            patch.object(ai_horde, "_submit", return_value="request-1"),
            patch.object(ai_horde, "_wait", return_value=generated),
        ):
            self.assertEqual(ai_horde.generate_text("prompt"), {"title": "Test"})

    def test_generate_image_downloads_remote_result(self):
        payload = b"x" * 12_000
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "scene.webp"
            with (
                patch.object(
                    ai_horde, "_choose_model", return_value="stable_diffusion_2.1"
                ),
                patch.object(ai_horde, "_submit", return_value="request-2"),
                patch.object(
                    ai_horde,
                    "_wait",
                    return_value={
                        "done": True,
                        "generations": [
                            {
                                "img": "https://example.test/scene.webp",
                                "censored": False,
                            }
                        ],
                    },
                ),
                patch.object(
                    ai_horde.requests,
                    "get",
                    return_value=response(content=payload),
                ),
            ):
                result = ai_horde.generate_image("prompt", target, seed="seed")

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), payload)

    def test_meta_quota_error_switches_to_free_motion_fallback(self):
        manifest = {"render_backend": "meta_ai"}
        expected = ["scene_01.mp4", "scene_02.mp4", "scene_03.mp4"]
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    meta_ai_generator,
                    "_ensure_meta_rendered_clips",
                    side_effect=meta_ai_generator.MetaAIVideoUnavailable(
                        "daily video generation limit reached"
                    ),
                ),
                patch.object(
                    ai_horde,
                    "generate_motion_fallback",
                    return_value=expected,
                ) as fallback,
            ):
                clips = meta_ai_generator.ensure_rendered_clips(
                    manifest,
                    Path(directory),
                )

                self.assertEqual(clips, expected)
                fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
