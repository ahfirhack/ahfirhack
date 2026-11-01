import unittest
from unittest.mock import patch

from modules import ai_horde


class AIHordeTests(unittest.TestCase):
    def test_non_text_media_generation_is_rejected(self):
        with self.assertRaisesRegex(ai_horde.AIHordeError, "Only text"):
            ai_horde._choose_model("image")

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

if __name__ == "__main__":
    unittest.main()
