"""按达人管理飞书多维表格视图。"""

import json
import subprocess


def creator_view_filter(nickname: str) -> dict:
    nickname = (nickname or "").strip()
    if not nickname:
        raise ValueError("达人昵称为空，无法创建飞书视图")
    return {
        "logic": "and",
        "conditions": [
            ["达人昵称", "==", nickname],
            ["来源类型", "==", ["达人主页"]],
            ["笔记类型", "==", ["视频"]],
        ],
    }


def _run_json(command: list, runner) -> dict:
    result = runner(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("飞书视图操作失败，请检查飞书授权和表格权限")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("飞书视图操作返回了无法识别的数据") from exc
    if not payload.get("ok"):
        raise RuntimeError("飞书视图操作失败，请检查飞书授权和表格权限")
    return payload


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _views(payload: dict) -> list:
    found = []
    for item in _walk(payload.get("data") or {}):
        view_id = item.get("view_id") or item.get("id")
        name = item.get("view_name") or item.get("name")
        if view_id and name:
            found.append({"view_id": view_id, "name": name})
    unique = {}
    for item in found:
        unique[item["view_id"]] = item
    return list(unique.values())


def _first_view(payload: dict, fallback_name: str) -> dict:
    views = _views(payload)
    if not views:
        raise RuntimeError("飞书已创建视图，但没有返回视图标识")
    view = views[0]
    view["name"] = view.get("name") or fallback_name
    return view


def _filter_payload(payload: dict) -> dict:
    data = payload.get("data") or {}
    if isinstance(data.get("filter"), dict):
        return data["filter"]
    if isinstance(data, dict) and isinstance(data.get("conditions"), list):
        return data
    return {"conditions": []}


def _value_matches(actual, expected) -> bool:
    if isinstance(actual, list) and not isinstance(expected, list):
        return len(actual) == 1 and actual[0] == expected
    if not isinstance(actual, list) and isinstance(expected, list):
        return len(expected) == 1 and actual == expected[0]
    return actual == expected


def _is_creator_filter(filter_config: dict, nickname: str) -> bool:
    expected = creator_view_filter(nickname)
    conditions = filter_config.get("conditions") or []
    for wanted in expected["conditions"]:
        if not any(
            len(actual) >= 3
            and actual[0] == wanted[0]
            and actual[1] == wanted[1]
            and _value_matches(actual[2], wanted[2])
            for actual in conditions
            if isinstance(actual, list)
        ):
            return False
    return True


def _base_command(action: str, base_token: str, table_id: str) -> list:
    return [
        "lark-cli",
        "base",
        action,
        "--base-token",
        base_token,
        "--table-id",
        table_id,
    ]


def ensure_creator_view(
    base_token: str,
    table_id: str,
    nickname: str,
    runner=subprocess.run,
) -> dict:
    """创建或复用达人视频视图；已按该达人筛选的别名视图也会复用。"""
    nickname = (nickname or "").strip()
    desired_filter = creator_view_filter(nickname)

    list_command = _base_command("+view-list", base_token, table_id) + [
        "--as",
        "user",
        "--format",
        "json",
    ]
    existing_views = _views(_run_json(list_command, runner))
    exact_name_view = None

    for view in existing_views:
        if view["name"] == nickname:
            exact_name_view = view
        if view["name"] == "爆款视频":
            continue
        get_filter_command = _base_command("+view-get-filter", base_token, table_id) + [
            "--view-id",
            view["view_id"],
            "--as",
            "user",
            "--format",
            "json",
        ]
        current_filter = _filter_payload(_run_json(get_filter_command, runner))
        if _is_creator_filter(current_filter, nickname):
            return {"view_id": view["view_id"], "name": view["name"], "created": False}

    created = False
    if exact_name_view:
        target = exact_name_view
    else:
        create_command = _base_command("+view-create", base_token, table_id) + [
            "--json",
            json.dumps({"name": nickname, "type": "grid"}, ensure_ascii=False),
            "--as",
            "user",
            "--format",
            "json",
        ]
        target = _first_view(_run_json(create_command, runner), nickname)
        created = True

    set_filter_command = _base_command("+view-set-filter", base_token, table_id) + [
        "--view-id",
        target["view_id"],
        "--json",
        json.dumps(desired_filter, ensure_ascii=False),
        "--as",
        "user",
        "--format",
        "json",
    ]
    _run_json(set_filter_command, runner)
    return {"view_id": target["view_id"], "name": target["name"], "created": created}
