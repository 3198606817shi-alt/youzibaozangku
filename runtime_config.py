"""发布版配置：公开设置落盘，凭证只进Mac钥匙串。"""

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse


APP_NAME = "笔记视频提取器"
KEYCHAIN_SERVICE = "com.youzi.note-video-extractor"
SENSITIVE_KEYS = {
    "cookie",
    "xiaohongshu_cookie",
    "siliconflow_api_key",
    "api_key",
    "app_secret",
}
PUBLIC_DEFAULTS = {
    "base_token": "",
    "table_id": "",
    "model": "FunAudioLLM/SenseVoiceSmall",
    "transcribe_api": "https://api.siliconflow.cn/v1/audio/transcriptions",
}


def data_dir() -> Path:
    override = os.environ.get("NOTE_EXTRACTOR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / APP_NAME


def public_config_path() -> Path:
    return data_dir() / "settings.json"


def parse_feishu_url(url: str) -> dict:
    parsed = urlparse((url or "").strip())
    host = parsed.hostname or ""
    if not (host.endswith(".feishu.cn") or host.endswith(".larksuite.com")):
        raise ValueError("请填写飞书多维表格完整链接")
    match = re.search(r"/base/([^/?#]+)", parsed.path)
    table_id = (parse_qs(parsed.query).get("table") or [""])[0]
    if not match or not table_id:
        raise ValueError("飞书多维表格链接缺少Base或数据表标识")
    return {"base_token": match.group(1), "table_id": table_id}


def load_public_config(path: Path = None) -> dict:
    path = Path(path or public_config_path())
    values = dict(PUBLIC_DEFAULTS)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("公开配置格式错误")
        if SENSITIVE_KEYS.intersection(payload):
            raise ValueError("公开配置中不能保存敏感信息")
        for key in PUBLIC_DEFAULTS:
            if key in payload:
                values[key] = payload[key]
    return values


def save_public_config(values: dict, path: Path = None) -> Path:
    if SENSITIVE_KEYS.intersection(values):
        raise ValueError("敏感信息只能保存到Mac钥匙串")
    unknown = set(values) - set(PUBLIC_DEFAULTS)
    if unknown:
        raise ValueError("公开配置包含不支持的字段")
    path = Path(path or public_config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(PUBLIC_DEFAULTS)
    payload.update(values)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    os.chmod(path, 0o600)
    return path


class KeychainSecretStore:
    def __init__(self, backend=None):
        if backend is None:
            import keyring

            backend = keyring
        self.backend = backend

    def get(self, name: str) -> str:
        return self.backend.get_password(KEYCHAIN_SERVICE, name) or ""

    def set(self, name: str, value: str) -> None:
        if name not in {"xiaohongshu_cookie", "siliconflow_api_key"}:
            raise ValueError("不支持的凭证类型")
        self.backend.set_password(KEYCHAIN_SERVICE, name, (value or "").strip())


DEFAULT_SECRET_STORE = KeychainSecretStore()


def get_secret_store() -> KeychainSecretStore:
    return DEFAULT_SECRET_STORE


def load_runtime_config(path: Path = None, secret_store=None) -> dict:
    values = load_public_config(path)
    store = secret_store or get_secret_store()
    values["siliconflow_api_key"] = store.get("siliconflow_api_key")
    return values


def load_xhs_settings(secret_store=None) -> dict:
    store = secret_store or get_secret_store()
    root = data_dir()
    return {
        "mapping_data": {},
        "work_path": str(root / "downloads"),
        "folder_name": "Download",
        "name_format": "title",
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "cookie": store.get("xiaohongshu_cookie"),
        "browser_cookie": "",
        "proxy": None,
        "timeout": 10,
        "chunk": 1048576,
        "max_retry": 5,
        "record_data": True,
        "image_format": "PNG",
        "image_download": False,
        "video_download": True,
        "live_download": False,
        "folder_mode": False,
        "download_record": True,
        "author_archive": True,
        "write_mtime": True,
        "language": "zh_CN",
    }
