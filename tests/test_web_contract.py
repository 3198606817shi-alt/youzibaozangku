import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[(service, account)] = value


class FakeTaskManager:
    def __init__(self):
        self.submissions = []
        self.stopped = False

    def submit(self, urls, since, no_transcribe, cleanup):
        self.submissions.append((urls, since, no_transcribe, cleanup))
        return {"task_id": 7}, 1

    def stop_current(self):
        self.stopped = True
        return True

    def status(self):
        return {"queue_length": 0, "current": None, "last": None}


class WebContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"NOTE_EXTRACTOR_DATA_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

        import runtime_config
        importlib.reload(runtime_config)
        runtime_config.DEFAULT_SECRET_STORE = runtime_config.KeychainSecretStore(
            backend=FakeKeyring()
        )
        import fetch_note
        import fetch_profile
        import pipeline
        import transcribe
        import web_app

        for module in (fetch_note, fetch_profile, transcribe, pipeline, web_app):
            importlib.reload(module)
        self.web_app = web_app
        self.client = web_app.app.test_client()

    def test_original_page_controls_are_preserved(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for visible_text in (
            "小红书数据提取",
            "更新 Cookie",
            "开始提取",
            "转写后删除视频",
            "不转写，只要基础数据",
            "运行日志",
        ):
            self.assertIn(visible_text, html)
        self.assertNotIn("配置自己的凭证", html)
        self.assertNotIn("准备自己的飞书表格", html)
        response.close()

    def test_unlimited_time_option_is_labeled_as_all_works(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertIn('<option value="">全部作品</option>', html)
        response.close()

    def test_post_routes_reject_requests_without_exact_local_origin(self):
        for path in ("/api/start", "/api/stop", "/api/cookie"):
            response = self.client.post(path, json={})
            self.assertEqual(response.status_code, 403, path)
            response = self.client.post(
                path,
                json={},
                headers={"Origin": "https://attacker.example"},
            )
            self.assertEqual(response.status_code, 403, path)

    def test_cookie_route_keeps_response_shape_and_updates_keychain_backed_state(self):
        response = self.client.post(
            "/api/cookie",
            json={"cookie": "cookie-value"},
            headers={"Origin": "http://127.0.0.1:8766"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertEqual(self.web_app.fetch_note.SETTINGS["cookie"], "cookie-value")
        self.assertEqual(self.web_app.fetch_profile.SETTINGS["cookie"], "cookie-value")
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_start_stop_and_logs_keep_original_response_contracts(self):
        tasks = FakeTaskManager()
        self.web_app.tm = tasks
        self.web_app.bus.append("模拟日志")

        started = self.client.post(
            "/api/start",
            json={
                "urls": ["https://www.xiaohongshu.com/explore/demo"],
                "since": "30d",
                "no_transcribe": True,
                "cleanup": False,
            },
            headers={"Origin": "http://127.0.0.1:8766"},
        )
        stopped = self.client.post(
            "/api/stop",
            json={},
            headers={"Origin": "http://127.0.0.1:8766"},
        )
        logs = self.client.get("/api/logs?since=0")

        self.assertEqual(
            started.get_json(),
            {"ok": True, "task_id": 7, "queue_position": 1},
        )
        self.assertEqual(stopped.get_json(), {"ok": True, "stopped": True})
        self.assertIn("模拟日志", logs.get_json()["lines"])
        self.assertEqual(
            tasks.submissions,
            [(["https://www.xiaohongshu.com/explore/demo"], "30d", True, False)],
        )

    def test_log_bus_redacts_credentials_before_storing(self):
        self.web_app.bus.append("Authorization: Bearer should-not-remain")
        lines = self.client.get("/api/logs?since=0").get_json()["lines"]
        self.assertNotIn("should-not-remain", "".join(lines))

    def test_status_returns_redacted_link_without_changing_internal_task(self):
        internal = {
            "task_id": 3,
            "urls": ["https://www.xiaohongshu.com/explore/demo?xsec_token=private"],
            "items": [
                {"url": "https://example.test/note?token=private", "ok": False}
            ],
        }

        class StatusTaskManager:
            def status(self):
                return {"queue_length": 0, "current": internal, "last": None}

        self.web_app.tm = StatusTaskManager()
        payload = self.client.get("/api/status").get_json()
        rendered = str(payload)
        self.assertEqual(
            set(payload),
            {"server_time", "queue_length", "current", "last"},
        )
        self.assertNotIn("private", rendered)
        self.assertIn("private", internal["urls"][0])

    def test_health_marker_is_separate_from_original_status_contract(self):
        self.assertEqual(
            self.client.get("/api/health").get_json(),
            {"service": "xhs-data-extractor", "ok": True},
        )


if __name__ == "__main__":
    unittest.main()
