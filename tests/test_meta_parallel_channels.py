"""Offline deterministic checks of 3 concurrent channels and session isolation."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Only the upload interface is required for importing main.py; offline unit
# tests should not require Google API SDKs or an authenticated YouTube client.
if importlib.util.find_spec("httplib2") is None:
    stub = types.ModuleType("modules.uploader")
    stub.upload_video = lambda *a, **kw: None
    sys.modules["modules.uploader"] = stub

import main
import test_pipeline
from modules import meta_ai_generator as meta


class ParallelChannelsTests(unittest.TestCase):
    def test_local_numbered_account_files_are_discovered_automatically(self):
        with tempfile.TemporaryDirectory() as root:
            primary = Path(root) / "meta_ai_storage_state.json"
            third = Path(root) / "meta_ai_storage_state_3.json"
            primary.write_text("{}")
            third.write_text("{}")
            with patch.dict("os.environ", {"META_AI_STORAGE_STATE_FILES": ""}), \
                 patch.object(meta, "META_AI_STORAGE_STATE_FILE", str(primary)):
                self.assertEqual(
                    [(1, primary.resolve()), (3, third.resolve())],
                    meta._storage_state_slots(required=True),
                )

    def test_meta_accounts_fail_over_in_primary_then_secondary_order(self):
        with tempfile.TemporaryDirectory() as root:
            primary = Path(root) / "account-1.json"
            secondary = Path(root) / "account-2.json"
            primary.write_text("{}")
            secondary.write_text("{}")
            manifest = {"render_backend": "meta_ai"}
            with meta._ACCOUNT_FAILURE_LOCK:
                meta._UNAVAILABLE_ACCOUNT_STATES.clear()
            with patch.object(meta, "_profile_dir", return_value=None), \
                 patch.object(meta, "_storage_state_slots", return_value=[
                     (1, primary), (2, secondary),
                 ]), \
                 patch.object(
                     meta, "_ensure_meta_rendered_clips",
                     side_effect=[meta.MetaAIVideoUnavailable("quota"), ["scene.mp4"]],
                 ) as render:
                result = meta.ensure_rendered_clips(manifest, Path(root), isolated_browser=True)
            self.assertEqual(["scene.mp4"], result)
            self.assertEqual(primary, render.call_args_list[0].kwargs["storage_state_path"])
            self.assertEqual(1, render.call_args_list[0].kwargs["account_slot"])
            self.assertEqual(secondary, render.call_args_list[1].kwargs["storage_state_path"])
            self.assertEqual(2, render.call_args_list[1].kwargs["account_slot"])

    def test_download_pending_never_generates_again_on_fallback_account(self):
        with tempfile.TemporaryDirectory() as root:
            states = []
            for number in (1, 2):
                path = Path(root) / f"account-{number}.json"
                path.write_text("{}")
                states.append((number, path))
            with patch.object(meta, "_profile_dir", return_value=None), \
                 patch.object(meta, "_storage_state_slots", return_value=states), \
                 patch.object(
                     meta, "_ensure_meta_rendered_clips",
                     side_effect=meta.MetaAIDownloadPending("already rendered"),
                 ) as render:
                with self.assertRaises(meta.MetaAIDownloadPending):
                    meta.ensure_rendered_clips(
                        {"render_backend": "meta_ai"}, Path(root),
                        isolated_browser=True,
                    )
            self.assertEqual(1, render.call_count)

    def test_fanout_is_three_and_fourth_starts_when_a_worker_frees(self):
        barrier = threading.Barrier(3, timeout=5)
        lock = threading.Lock()
        counters = {"active": 0, "peak": 0}
        launches = []

        def fake_video(ch, idx, scripts, prompts, *, isolated_browser):
            self.assertTrue(isolated_browser)
            with lock:
                counters["active"] += 1
                counters["peak"] = max(counters["active"], counters["peak"])
                launches.append(ch["id"])
            if ch["id"] in ("channel_1", "channel_2", "channel_3"):
                barrier.wait()
            with lock:
                counters["active"] -= 1
            return "video-" + ch["id"]

        with patch.object(main, "clean_temp"), \
             patch.object(main, "_load_used_scripts", return_value=set()), \
             patch.object(main, "_load_used_prompts", return_value=set()), \
             patch.object(meta, "_storage_state_path", return_value=Path("/placeholder/session.json")), \
             patch.object(main, "process_video", side_effect=fake_video):
            self.assertTrue(main.run_channel_batch(workers=3))

        self.assertEqual(3, counters["peak"])
        self.assertEqual(0, counters["active"])
        self.assertCountEqual(launches, [f"channel_{i}" for i in range(1, 5)])

    def test_one_failure_does_not_cancel_other_channels(self):
        launches = []

        def fake_video(ch, idx, scripts, prompts, *, isolated_browser):
            launches.append(ch["id"])
            if ch["id"] == "channel_2":
                raise meta.MetaAIEditorUnavailable("Video creation not available")
            return "id-" + ch["id"]

        with patch.object(main, "clean_temp"), \
             patch.object(main, "_load_used_scripts", return_value=set()), \
             patch.object(main, "_load_used_prompts", return_value=set()), \
             patch.object(meta, "_storage_state_path", return_value=Path("/placeholder/session.json")), \
             patch.object(main, "process_video", side_effect=fake_video):
            self.assertFalse(main.run_channel_batch(workers=3))
        self.assertCountEqual(launches, [f"channel_{i}" for i in range(1, 5)])

    def test_isolated_generator_does_not_write_to_shared_login_file(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "renders").mkdir()
            (base / "continuity").mkdir()
            state = base / "meta_ai_storage_state.json"
            original = '{"cookies": [], "origins": []}'
            state.write_text(original, encoding="utf-8")
            manifest = {
                "render_backend": "meta_ai", "status": "awaiting_meta_ai",
                "scenes": [
                    {"index": n, "filename": f"scene_{n:02d}.mp4", "prompt": "original scene prompt"}
                    for n in range(1, 6)
                ],
            }
            context, browser = MagicMock(), MagicMock()
            shared_project = MagicMock()
            project_pages = []
            pw = MagicMock()
            pw.__enter__.return_value = MagicMock()

            def write_scene(_, __, target, ___, ____, _____, *,
                            project_page=None, keep_project_open=False):
                project_pages.append(project_page)
                Path(target).write_bytes(b"v" * 12000)
                return shared_project if keep_project_open else None

            with patch.object(meta, "_profile_dir", side_effect=AssertionError("profile must not open")), \
                 patch.object(meta, "_storage_state_path", return_value=state) as state_path, \
                 patch.object(meta, "_load_playwright", return_value=lambda: pw), \
                 patch.object(meta, "_launch_context", return_value=(context, browser)) as launch, \
                 patch.object(meta, "_generate_media", side_effect=write_scene), \
                 patch.object(meta, "_validate_meta_clip"), \
                 patch.object(meta, "_check_scene_handoff"), \
                 patch.object(meta, "_extract_last_frame"), \
                 patch.object(meta, "collect_rendered_clips", return_value=["meta-video"] * 5):
                output = meta._ensure_meta_rendered_clips(
                    manifest, base, isolated_browser=True,
                )
            self.assertEqual(["meta-video"] * 5, output)
            self.assertEqual(original, state.read_text(encoding="utf-8"))
            self.assertEqual(5, len(manifest["scenes"]))
            self.assertEqual("rendering", manifest["status"])
            self.assertEqual(5, sum(bool(scene.get("rendered")) for scene in manifest["scenes"]))
            self.assertIsNone(project_pages[0])
            self.assertTrue(all(page is shared_project for page in project_pages[1:]))
            self.assertTrue(shared_project.close.called)
            self.assertFalse(context.storage_state.called)
            self.assertTrue(context.close.called)
            self.assertTrue(browser.close.called)
            self.assertIsNone(launch.call_args.args[1])
            state_path.assert_called_once_with(required=True)

    def test_preview_has_parallel_cli_and_keeps_channel_2_only(self):
        with patch.object(test_pipeline, "_preview_worker", return_value={
            "channel": "StoryFuse", "ok": True, "output": "preview.mp4",
        }) as worker:
            self.assertEqual(0, test_pipeline.main(["2"]))
            self.assertEqual(1, worker.call_count)
            self.assertEqual("StoryFuse", worker.call_args.args[0]["name"])
            self.assertFalse(worker.call_args.kwargs["isolated_browser"])

    def test_parallel_requires_saved_session_before_spending_credits(self):
        with patch.object(meta, "_storage_state_path", side_effect=meta.MetaAIAutomationError("no session")), \
             patch.object(main, "process_video") as generate:
            with self.assertRaisesRegex(meta.MetaAIAutomationError, "no session"):
                main.run_channel_batch(workers=3)
            generate.assert_not_called()

    def test_worker_count_capped_to_three(self):
        self.assertEqual(3, main._worker_count(3, 4))
        self.assertEqual(2, main._worker_count(3, 2))
        self.assertEqual(1, main._worker_count(3, 1))
        for requested in (0, -1, 4, 100):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                main._worker_count(requested, 4)

    def test_workflow_enables_three_windows_and_keeps_6_hour_cron(self):
        text = (Path(__file__).parents[1] / ".github/workflows/daily_upload.yml").read_text()
        self.assertIn('cron: "13 */6 * * *"', text)
        self.assertIn('META_CHANNEL_WORKERS: "3"', text)
        self.assertIn('META_AI_SURFACES: "create"', text)
        self.assertIn('args=(--once --workers 3)', text)


if __name__ == "__main__":
    unittest.main()
