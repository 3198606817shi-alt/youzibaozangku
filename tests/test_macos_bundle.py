import plistlib
import platform
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(platform.system() == "Darwin", "只在Mac上验证应用包")
class MacBundleTests(unittest.TestCase):
    def test_built_app_is_universal_stay_open_launcher_with_custom_icon(self):
        project = Path(__file__).resolve().parents[1]
        subprocess.run(
            [str(project / "scripts" / "build_macos_app.sh")],
            check=True,
            capture_output=True,
            text=True,
        )
        app = project / "dist" / "笔记视频提取器.app"
        with (app / "Contents" / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        executable = app / "Contents" / "MacOS" / info["CFBundleExecutable"]
        result = subprocess.run(
            ["file", "-b", str(executable)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(info["CFBundleName"], "笔记视频提取器")
        self.assertIn("Mach-O", result.stdout)
        self.assertIn("arm64", result.stdout)
        self.assertIn("x86_64", result.stdout)
        self.assertTrue((app / "Contents" / "Resources" / "AppIcon.icns").exists())
        self.assertNotIn("CFBundleIconName", info)


if __name__ == "__main__":
    unittest.main()
