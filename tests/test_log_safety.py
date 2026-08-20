import unittest

from log_safety import safe_display_url, safe_error_text


class LogSafetyTests(unittest.TestCase):
    def test_display_url_removes_query_and_fragment_tokens(self):
        value = safe_display_url(
            "https://www.xiaohongshu.com/explore/demo?xsec_token=private#section"
        )
        self.assertEqual(value, "https://www.xiaohongshu.com/explore/demo")
        self.assertNotIn("private", value)

    def test_error_text_redacts_query_from_embedded_urls(self):
        value = safe_error_text(
            "请求 https://example.test/path?token=private&x=1 失败"
        )
        self.assertEqual(value, "请求 https://example.test/path 失败")
        self.assertNotIn("private", value)

    def test_error_text_redacts_common_credential_headers_and_fields(self):
        value = safe_error_text(
            "Cookie: session=private; Authorization: Bearer secret-token "
            "siliconflow_api_key=sk-private app_secret: hidden-value"
        )
        self.assertNotIn("session=private", value)
        self.assertNotIn("secret-token", value)
        self.assertNotIn("sk-private", value)
        self.assertNotIn("hidden-value", value)
        self.assertIn("[已隐藏]", value)


if __name__ == "__main__":
    unittest.main()
