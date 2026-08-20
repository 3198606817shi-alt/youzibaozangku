"""只读检查飞书数据表字段，不创建或修改云端资源。"""

import json
import subprocess


REQUIRED_FIELDS = (
    "笔记标题",
    "笔记类型",
    "达人昵称",
    "发布时间",
    "点赞数",
    "收藏数",
    "评论数",
    "逐字稿",
    "笔记链接",
    "达人主页链接",
    "来源类型",
    "封面图",
)


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _field_names(payload: dict) -> set:
    names = set()
    for item in _walk(payload):
        name = item.get("field_name") or item.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


def resolve_table_url(url: str, runner=subprocess.run) -> dict:
    command = [
        "lark-cli",
        "base",
        "+url-resolve",
        "--url",
        url,
        "--as",
        "user",
        "--format",
        "json",
    ]
    result = runner(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("飞书链接只读解析失败，请确认授权和表格访问权限")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("飞书链接解析返回了无法识别的数据") from exc
    base_token = ""
    table_id = ""
    for item in _walk(payload):
        base_token = base_token or item.get("base_token") or item.get("app_token") or ""
        table_id = table_id or item.get("table_id") or ""
    if not base_token or not table_id:
        raise RuntimeError("飞书链接解析结果缺少Base或数据表标识")
    return {"base_token": base_token, "table_id": table_id}


def check_table_schema(base_token: str, table_id: str, runner=subprocess.run) -> dict:
    command = [
        "lark-cli",
        "base",
        "+field-list",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
        "--as",
        "user",
        "--format",
        "json",
    ]
    result = runner(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("飞书字段只读检查失败，请确认授权和表格访问权限")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("飞书字段检查返回了无法识别的数据") from exc
    names = _field_names(payload)
    missing = [name for name in REQUIRED_FIELDS if name not in names]
    return {"ok": not missing, "missing_fields": missing, "field_names": sorted(names)}
