import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


FAKE_SERVER = r'''import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        if self.path == "/api/health":
            body = json.dumps({"service": "xhs-data-extractor", "ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            body = json.dumps({"service": "xhs-data-extractor", "current": None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def do_POST(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
'''


class LauncherTests(unittest.TestCase):
    def test_stop_script_only_removes_lock_after_process_has_exited(self):
        project = Path(__file__).resolve().parents[1]
        script = (project / "scripts" / "stop.sh").read_text(encoding="utf-8")
        self.assertIn("服务未能正常退出，已保留锁文件", script)
        self.assertIn("exit 1", script)

    def test_web_server_does_not_open_a_second_browser_tab(self):
        project = Path(__file__).resolve().parents[1]
        source = (project / "web_app.py").read_text(encoding="utf-8")
        self.assertNotIn("threading.Timer(1.0, webbrowser.open", source)

    def test_launch_is_single_instance_and_stop_cleans_pid_and_lock(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            app_root = home / "Library" / "Application Support" / "笔记视频提取器"
            code = app_root / "app"
            scripts = code / "scripts"
            venv_bin = app_root / "venv" / "bin"
            scripts.mkdir(parents=True)
            venv_bin.mkdir(parents=True)
            shutil.copy2(project / "scripts" / "launch.sh", scripts / "launch.sh")
            shutil.copy2(project / "scripts" / "stop.sh", scripts / "stop.sh")
            (code / "web_app.py").write_text(FAKE_SERVER, encoding="utf-8")
            (venv_bin / "python").symlink_to(Path(os.sys.executable))
            env = {**os.environ, "HOME": str(home), "NOTE_EXTRACTOR_NO_OPEN": "1"}

            first = subprocess.Popen([str(scripts / "launch.sh")], env=env)
            self.addCleanup(lambda: first.poll() is None and first.terminate())
            for _ in range(40):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8766/api/status", timeout=0.2) as response:
                        if json.load(response).get("service") == "xhs-data-extractor":
                            break
                except Exception:
                    time.sleep(0.1)
            else:
                self.fail("本机服务没有启动")

            pid = int((app_root / "service.lock" / "pid").read_text().strip())
            second = subprocess.run(
                [str(scripts / "launch.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(second.returncode, 0)
            self.assertEqual(int((app_root / "service.lock" / "pid").read_text().strip()), pid)

            stopped = subprocess.run(
                [str(scripts / "stop.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(stopped.returncode, 0)
            first.wait(timeout=5)
            self.assertFalse((app_root / "service.lock").exists())
            with self.assertRaises(Exception):
                urllib.request.urlopen("http://127.0.0.1:8766/api/status", timeout=0.2)


if __name__ == "__main__":
    unittest.main()
