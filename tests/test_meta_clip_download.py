"""Local browser download tests; never contact Meta, YouTube or other websites."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from modules.meta_ai_generator import _validate_meta_clip
from modules.meta_clip_download import MetaClipDownloadError, save_generated_clip


class MetaClipDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise unittest.SkipTest("ffmpeg/ffprobe unavailable")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("playwright unavailable")
        cls.work = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.work.name) / "generated_10s.mp4"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:size=1080x1920:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
            "-t", "10", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+faststart", str(cls.fixture),
        ]
        completed = subprocess.run(command, capture_output=True, timeout=90)
        if completed.returncode != 0:
            raise unittest.SkipTest("ffmpeg could not create local fixture")
        cls.b64 = base64.b64encode(cls.fixture.read_bytes()).decode("ascii")
        cls.playwright_cm = sync_playwright()
        cls.playwright = cls.playwright_cm.__enter__()
        try:
            # Uses system Chromium when installed; otherwise installed Playwright Chromium.
            system = shutil.which("chromium") or shutil.which("google-chrome")
            if system:
                cls.browser = cls.playwright.chromium.launch(
                    headless=True, executable_path=system, args=["--no-sandbox"])
            else:
                cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception:
            cls.playwright_cm.__exit__(None, None, None)
            raise unittest.SkipTest("Chromium not installed; offline browser tests skipped")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "playwright_cm") and hasattr(cls, "browser"):
            cls.playwright_cm.__exit__(None, None, None)
        if hasattr(cls, "work"):
            cls.work.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.target = Path(self.work.name) / (self._testMethodName + ".mp4")
        self.debug = Path(self.work.name) / (self._testMethodName + ".json")

    def tearDown(self):
        self.context.close()

    def _script(self):
        return """const bytes = Uint8Array.from(atob('""" + self.b64 + """'),c=>c.charCodeAt(0));
            const blob = new Blob([bytes], {type:'video/mp4'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href=url; a.download='meta-generated.mp4';
            document.body.appendChild(a); a.click(); a.remove();"""

    def test_download_button_creates_real_valid_clip(self):
        self.page.set_content("<button id='d'>Download Video</button><script>document.querySelector('#d').onclick=()=>{" + self._script() + "}</script>")
        save_generated_clip(self.context, self.page, "blob:unreachable", self.target,
                            _validate_meta_clip, diagnostic_path=self.debug,
                            max_wait_seconds=3)
        self.assertTrue(self.target.is_file())
        _validate_meta_clip(self.target)
        self.assertEqual(json.loads(self.debug.read_text())["method"], "browser-download")

    def test_export_dialog_downloads_after_second_click(self):
        self.page.set_content("""<button id='export'>Export</button><div id='modal'></div><script>
            document.querySelector('#export').onclick = () => {
                const btn=document.createElement('button');
                btn.id='d'; btn.textContent='Download video';
                document.querySelector('#modal').appendChild(btn);
            };
            </script>""")
        self.page.evaluate("""(code) => {
            document.querySelector('#export').addEventListener('click', () => {
                setTimeout(() => {document.querySelector('#d').onclick = () => {eval(code)};}, 0);
            });
        }""", self._script())
        save_generated_clip(self.context, self.page, "", self.target,
                            _validate_meta_clip, diagnostic_path=self.debug,
                            max_wait_seconds=6)
        self.assertTrue(self.target.exists())
        log = json.loads(self.debug.read_text())
        self.assertIn("export", log["ui_actions"])
        self.assertIn("download", log["ui_actions"])

    def test_blob_player_fallback(self):
        self.page.set_content("<div>Finished video preview</div>")
        src = self.page.evaluate("""(b64) => {
            const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
            const blob=new Blob([bytes],{type:'video/mp4'});
            return URL.createObjectURL(blob);
        }""", self.b64)
        save_generated_clip(self.context, self.page, src, self.target,
                            _validate_meta_clip, diagnostic_path=self.debug,
                            max_wait_seconds=1.5)
        self.assertTrue(self.target.exists())
        self.assertEqual(json.loads(self.debug.read_text())["method"], "media-source")

    def test_html_download_is_rejected_and_not_committed(self):
        self.page.set_content("""<button id='d'>Download Video</button><script>
            document.querySelector('#d').onclick = () => {
              const a=document.createElement('a');
              a.href='data:text/html,'+'<html>Not a clip</html>';
              a.download='fake.mp4'; a.click();
            };
            </script>""")
        with self.assertRaises(MetaClipDownloadError):
            save_generated_clip(self.context, self.page, "", self.target,
                                _validate_meta_clip, diagnostic_path=self.debug,
                                max_wait_seconds=1.5)
        self.assertFalse(self.target.exists())
        log = self.debug.read_text()
        self.assertNotIn("base64", log)
        self.assertNotIn("cookie", log)


if __name__ == "__main__":
    unittest.main()
