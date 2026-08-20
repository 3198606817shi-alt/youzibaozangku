import json
import tempfile
import unittest
from pathlib import Path

from runtime_config import (
    KeychainSecretStore,
    load_public_config,
    parse_feishu_url,
    save_public_config,
)


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[(service, account)] = value


class RuntimeConfigTests(unittest.TestCase):
    def test_parse_feishu_url_extracts_base_and_table_ids(self):
        parsed = parse_feishu_url(
            "https://example.feishu.cn/base/base_demo?table=tbl_demo&view=vew_demo"
        )
        self.assertEqual(
            parsed,
            {"base_token": "base_demo", "table_id": "tbl_demo"},
        )

    def test_parse_feishu_url_rejects_non_feishu_links(self):
        with self.assertRaisesRegex(ValueError, "飞书多维表格"):
            parse_feishu_url("https://example.com/base/base_demo?table=tbl_demo")

    def test_public_config_rejects_secrets_and_uses_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with self.assertRaisesRegex(ValueError, "敏感信息"):
                save_public_config({"cookie": "private"}, path)

            save_public_config(
                {
                    "base_token": "base_demo",
                    "table_id": "tbl_demo",
                    "model": "model-demo",
                    "transcribe_api": "https://api.example.test/transcribe",
                },
                path,
            )

            self.assertEqual(load_public_config(path)["table_id"], "tbl_demo")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("cookie", text.lower())
            self.assertNotIn("api_key", text.lower())

    def test_keychain_store_delegates_without_creating_files(self):
        backend = FakeKeyring()
        store = KeychainSecretStore(backend=backend)
        store.set("xiaohongshu_cookie", "cookie-value")
        store.set("siliconflow_api_key", "key-value")

        self.assertEqual(store.get("xiaohongshu_cookie"), "cookie-value")
        self.assertEqual(store.get("siliconflow_api_key"), "key-value")


if __name__ == "__main__":
    unittest.main()
