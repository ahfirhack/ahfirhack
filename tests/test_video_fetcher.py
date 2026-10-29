import unittest
from unittest.mock import Mock, patch

from modules import video_fetcher


class VideoFetcherApiTests(unittest.TestCase):
    def test_pixabay_compacts_long_visual_prompt(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"hits": []}
        prompt = (
            "Wide shot of person smiling calmly at desk, warm sunrise light "
            "through window, steady camera, peaceful mood"
        )

        with (
            patch.object(video_fetcher, "PIXABAY_API_KEY", "test-key"),
            patch.object(video_fetcher.requests, "get", return_value=response) as get,
        ):
            self.assertEqual(video_fetcher._fetch_pixabay(prompt, 1, set()), [])

        params = get.call_args.kwargs["params"]
        self.assertLessEqual(len(params["q"]), 100)
        self.assertNotIn("camera", params["q"])
        self.assertNotIn("lighting", params["q"])

    def test_coverr_reads_current_hits_response_and_mp4_url(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "page": 0,
            "pages": 1,
            "hits": [
                {
                    "id": "video-123",
                    "title": "Calm office",
                    "description": "A person breathing at a desk",
                    "duration": 12.5,
                    "urls": {"mp4": "https://cdn.example/video.mp4"},
                }
            ],
        }

        with (
            patch.object(video_fetcher, "COVERR_API_KEY", "test-key"),
            patch.object(video_fetcher.requests, "get", return_value=response) as get,
        ):
            results = video_fetcher._fetch_coverr("person at desk", 1, set())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "coverr_video-123")
        self.assertEqual(results[0]["url"], "https://cdn.example/video.mp4")
        self.assertEqual(get.call_args.args[0], "https://api.coverr.co/videos")
        self.assertEqual(get.call_args.kwargs["params"]["urls"], "true")

    def test_coverr_ignores_non_object_hits(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"page": 0, "hits": [1, None, "bad"]}

        with (
            patch.object(video_fetcher, "COVERR_API_KEY", "test-key"),
            patch.object(video_fetcher.requests, "get", return_value=response),
        ):
            self.assertEqual(video_fetcher._fetch_coverr("office", 1, set()), [])


if __name__ == "__main__":
    unittest.main()
