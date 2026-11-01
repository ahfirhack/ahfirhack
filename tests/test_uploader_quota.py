"""Uploader idempotency tests that never contact YouTube."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules import uploader


CHANNEL = {
    "id": "channel_test",
    "name": "Test Channel",
    "category_id": "24",
    "client_secrets_file": "unused-client.json",
    "token_file": "unused-token.json",
    "strict_upload_dedup": True,
    "media_source": "meta_ai_browser",
}


class UploadReceiptTests(unittest.TestCase):
    def test_recorded_upload_returns_without_youtube_api_call(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "uploaded_titles.json"
            normalized = uploader._normalized_title("A Finished Story #Shorts")
            uploader._remember_upload(
                "channel_test",
                normalized,
                "A Finished Story #Shorts",
                "youtube-123",
                ledger,
            )
            with (
                patch.object(uploader, "UPLOADED_TITLES_FILE", str(ledger)),
                patch.object(
                    uploader,
                    "_get_authenticated_service",
                    side_effect=AssertionError("YouTube must not be contacted"),
                ),
            ):
                result = uploader.upload_video(
                    "already-uploaded.mp4",
                    "A Finished Story #Shorts",
                    [],
                    CHANNEL,
                )
            self.assertEqual("youtube-123", result)

    def test_successful_upload_uses_no_read_quota_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "uploaded_titles.json"
            video = Path(temp) / "short.mp4"
            video.write_bytes(b"test-video")
            insert_request = MagicMock()
            insert_request.next_chunk.return_value = (None, {"id": "youtube-456"})
            youtube = MagicMock()
            youtube.videos.return_value.insert.return_value = insert_request
            with (
                patch.object(uploader, "UPLOADED_TITLES_FILE", str(ledger)),
                patch.object(
                    uploader,
                    "_get_authenticated_service",
                    return_value=youtube,
                ),
                patch.object(uploader, "MediaFileUpload", return_value=MagicMock()),
            ):
                result = uploader.upload_video(
                    str(video),
                    "A New Story #Shorts",
                    ["story"],
                    CHANNEL,
                    script="A complete test story for upload.",
                )

            self.assertEqual("youtube-456", result)
            youtube.channels.assert_not_called()
            youtube.playlistItems.assert_not_called()
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            entries = payload["channels"]["channel_test"]
            self.assertEqual(
                "youtube-456",
                entries[uploader._normalized_title("A New Story #Shorts")]["video_id"],
            )


if __name__ == "__main__":
    unittest.main()
