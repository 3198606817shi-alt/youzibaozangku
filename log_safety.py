"""避免把链接查询参数和临时令牌写入页面日志。"""

import re
from urllib.parse import urlsplit, urlunsplit


URL_PATTERN = re.compile(r"https?://[^\s<>\[\](){}\\\"]+")
HEADER_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:cookie|set-cookie|authorization)\s*:\s*[^\r\n]+"
)
NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b(cookie|siliconflow_api_key|api_key|app_secret)\b"
    r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def safe_display_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return "<链接已隐藏>"


def safe_error_text(value) -> str:
    text = str(value)
    text = URL_PATTERN.sub(lambda match: safe_display_url(match.group(0)), text)
    text = HEADER_SECRET_PATTERN.sub("凭证头: [已隐藏]", text)
    text = BEARER_PATTERN.sub("Bearer [已隐藏]", text)
    return NAMED_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[已隐藏]", text)
