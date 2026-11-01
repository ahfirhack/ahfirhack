"""Offline regression tests for repeated scenes and seam-free assembly."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import meta_ai_generator as meta
from modules import video_assembler as assembler


class SceneIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg"):
            raise unittest.SkipTest("ffmpeg unavailable")

    @staticmethod
    def _color_clip(path: Path, color: str) -> None:
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:size=180x320:rate=2",
            "-t", "10", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(path),
        ], capture_output=True, timeout=60)
        if result.returncode:
            raise unittest.SkipTest("could not build duplicate-scene fixture")

    def test_duplicate_scene_is_rejected_even_under_another_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "scene_01.mp4"
            repeated = root / "scene_04.mp4"
            different = root / "scene_05.mp4"
            self._color_clip(first, "blue")
            shutil.copyfile(first, repeated)
            self._color_clip(different, "red")

            with self.assertRaisesRegex(meta.MetaAIDuplicateScene, "duplicates"):
                meta._check_scene_unique([first], repeated)
            meta._check_scene_unique([first], different)

    def test_assembler_uses_only_real_frames_and_time_fits_native_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clips = [root / f"scene_{number:02d}.mp4" for number in range(1, 6)]
            captured = {}

            def fake_ffmpeg(args, label=""):
                captured["args"] = list(args)
                captured["label"] = label
                Path(args[-1]).write_bytes(b"m" * 20_000)

            with patch.object(assembler, "OUTPUT_DIR", str(root / "output")), \
                 patch.object(assembler, "_audio_duration", return_value=9.82), \
                 patch.object(assembler, "_ffmpeg", side_effect=fake_ffmpeg), \
                 patch.object(assembler, "_dur", return_value=50.0), \
                 patch.object(assembler, "_has_audio", return_value=True), \
                 patch.object(assembler, "_dimensions", return_value=(1440, 2560)), \
                 patch.object(meta, "_validate_meta_clip"), \
                 patch.object(meta, "_check_scene_unique") as unique, \
                 patch.object(meta, "_check_scene_handoff") as handoff, \
                 patch.object(meta, "_extract_last_frame"):
                output = assembler.assemble_meta_short(
                    clips, "seamless.mp4", root / "continuity",
                )

            self.assertTrue(Path(output).is_file())
            self.assertEqual(9, captured["args"].count("-i"))
            graph = captured["args"][captured["args"].index("-filter_complex") + 1]
            self.assertNotIn("overlay=", graph)
            self.assertEqual(4, graph.count(
                "xfade=transition=fade:duration=0.25:offset=0"
            ))
            self.assertNotIn("pad_dur=0.2", graph)
            self.assertEqual(4, graph.count(
                "acrossfade=d=0.25:c1=tri:c2=tri"
            ))
            self.assertIn("concat=n=5:v=1:a=0[outv]", graph)
            self.assertNotIn("concat=n=5:v=1:a=1", graph)
            self.assertIn("atempo=0.823045267", graph)
            self.assertIn("atempo=0.917431193", graph)
            self.assertIn("pad_dur=0.03", graph)
            self.assertEqual(5, unique.call_count)
            self.assertEqual(4, handoff.call_count)


if __name__ == "__main__":
    unittest.main()
