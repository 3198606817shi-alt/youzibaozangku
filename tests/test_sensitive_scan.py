import tempfile
import unittest
from pathlib import Path

from scripts.sensitive_scan import scan


class SensitiveScanTests(unittest.TestCase):
    def test_detects_secret_without_returning_secret_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
            (root / "bad.json").write_text(
                '{"siliconflow_api_key":"%s"}' % secret,
                encoding="utf-8",
            )

            findings = scan(root)

            self.assertTrue(findings)
            self.assertNotIn(secret, repr(findings))

    def test_safe_examples_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.example.json").write_text(
                '{"base_token":"","table_id":""}',
                encoding="utf-8",
            )
            self.assertEqual(scan(root), [])


if __name__ == "__main__":
    unittest.main()
