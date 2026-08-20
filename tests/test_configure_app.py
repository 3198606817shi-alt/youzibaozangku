import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from configure_app import configure_values, migrate_legacy_config
from runtime_config import KeychainSecretStore, load_public_config


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[(service, account)] = value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConfigureAppTests(unittest.TestCase):
    def test_configure_values_saves_public_ids_and_keychain_secret_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = KeychainSecretStore(backend=FakeKeyring())

            configure_values(
                {"base_token": "base_demo", "table_id": "tbl_demo"},
                "secret-value",
                config_path=path,
                secret_store=store,
            )

            public = load_public_config(path)
            self.assertEqual(public["base_token"], "base_demo")
            self.assertEqual(public["table_id"], "tbl_demo")
            self.assertEqual(store.get("siliconflow_api_key"), "secret-value")
            self.assertNotIn("secret-value", path.read_text(encoding="utf-8"))

    def test_legacy_migration_is_read_only_and_never_copies_secrets_to_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "legacy"
            legacy.mkdir()
            old_config = legacy / "config.json"
            old_settings = legacy / "settings.json"
            old_config.write_text(
                json.dumps(
                    {
                        "base_token": "base_old",
                        "table_id": "tbl_old",
                        "siliconflow_api_key": "old-secret",
                        "transcribe_api": "https://api.example.test/transcribe",
                        "model": "old-model",
                    }
                ),
                encoding="utf-8",
            )
            old_settings.write_text(json.dumps({"cookie": "old-cookie"}), encoding="utf-8")
            before = (digest(old_config), digest(old_settings))
            target = root / "new" / "settings.json"
            store = KeychainSecretStore(backend=FakeKeyring())

            result = migrate_legacy_config(
                legacy,
                confirmed=True,
                config_path=target,
                secret_store=store,
            )

            self.assertEqual(result["base_token"], "base_old")
            self.assertEqual(store.get("siliconflow_api_key"), "old-secret")
            self.assertEqual(store.get("xiaohongshu_cookie"), "old-cookie")
            self.assertEqual((digest(old_config), digest(old_settings)), before)
            new_text = target.read_text(encoding="utf-8")
            self.assertNotIn("old-secret", new_text)
            self.assertNotIn("old-cookie", new_text)

    def test_declined_legacy_migration_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "new" / "settings.json"
            store = KeychainSecretStore(backend=FakeKeyring())

            result = migrate_legacy_config(
                root,
                confirmed=False,
                config_path=target,
                secret_store=store,
            )

            self.assertEqual(result, {})
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
