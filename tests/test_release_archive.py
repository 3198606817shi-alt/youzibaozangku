import platform
import subprocess
import unittest
import zipfile
from pathlib import Path


@unittest.skipUnless(platform.system() == "Darwin", "只在Mac上验证发布包")
class ReleaseArchiveTests(unittest.TestCase):
    def test_release_archive_contains_original_ui_and_excludes_private_files(self):
        project = Path(__file__).resolve().parents[1]
        subprocess.run(
            [str(project / "scripts" / "build_release.sh")],
            check=True,
            capture_output=True,
            text=True,
        )
        archive = project / "dist" / "笔记视频提取器-v1.0.1-mac.zip"
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()

        self.assertTrue(any(name.endswith("/templates/index.html") for name in names))
        self.assertTrue(any(name.endswith("/安装.command") for name in names))
        self.assertTrue(any("笔记视频提取器.app/Contents/MacOS/" in name for name in names))
        forbidden = (
            "__MACOSX",
            "__pycache__",
            ".pyc",
            ".pyo",
            "/venv/",
            "/downloads/",
            "/server.log",
            "/config.json",
            "/settings.json",
            "/_internal/",
        )
        self.assertFalse(any(any(part in name for part in forbidden) for name in names))


if __name__ == "__main__":
    unittest.main()
