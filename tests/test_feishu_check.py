import json
import subprocess
import unittest

from feishu_check import REQUIRED_FIELDS, check_table_schema, resolve_table_url


class FeishuSchemaTests(unittest.TestCase):
    def test_url_resolution_uses_official_read_only_shortcut(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            payload = {
                "ok": True,
                "data": {"base_token": "base_demo", "table_id": "tbl_demo"},
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        result = resolve_table_url(
            "https://example.feishu.cn/base/base_demo?table=tbl_demo",
            runner=runner,
        )

        self.assertEqual(result, {"base_token": "base_demo", "table_id": "tbl_demo"})
        self.assertIn("+url-resolve", calls[0])
        self.assertIn("--as", calls[0])
        self.assertNotIn("create", " ".join(calls[0]))

    def test_schema_check_is_read_only_and_accepts_required_fields(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            payload = {"ok": True, "data": {"items": [{"field_name": name} for name in REQUIRED_FIELDS]}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        result = check_table_schema("base_demo", "tbl_demo", runner=runner)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_fields"], [])
        self.assertIn("+field-list", calls[0])
        self.assertNotIn("create", " ".join(calls[0]))
        self.assertNotIn("update", " ".join(calls[0]))

    def test_schema_check_reports_missing_fields_without_writing(self):
        def runner(command, **kwargs):
            payload = {"ok": True, "data": {"items": [{"field_name": "笔记标题"}]}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        result = check_table_schema("base_demo", "tbl_demo", runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("笔记类型", result["missing_fields"])


if __name__ == "__main__":
    unittest.main()
