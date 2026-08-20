"""
小红书达人主页抓取器：主页链接 -> 达人信息 + 笔记清单
用法：
    python fetch_profile.py <主页链接> [--outdir 目录] [--json-only]
输出：
    打印达人信息 + 笔记清单 JSON（每条含 noteId/title/time/type/xsecToken）
"""
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from log_safety import safe_display_url, safe_error_text
from runtime_config import load_xhs_settings

BASE_DIR = Path(__file__).parent
SETTINGS = load_xhs_settings()

UA = SETTINGS.get("user_agent") or (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Cookie": SETTINGS.get("cookie", ""),
    "Referer": "https://www.xiaohongshu.com/",
}


def _extract_user_id(url: str) -> str:
    """从达人主页链接提取 user_id"""
    # 先处理短链
    if "xhslink" in url:
        resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
        url = resp.url
    parsed = urlparse(url)
    m = re.search(r"/user/profile/([0-9a-f]+)", parsed.path or "")
    if not m:
        raise ValueError(f"无法从链接提取 user_id: {url}")
    return m.group(1)


def extract_initial_state(html: str) -> dict:
    """提取 __INITIAL_STATE__ 并容错解析为 dict"""
    start = html.find("window.__INITIAL_STATE__=")
    if start == -1:
        raise RuntimeError("页面中未找到 __INITIAL_STATE__，Cookie 可能已失效或被风控")
    start += len("window.__INITIAL_STATE__=")
    end = html.find("</script>", start)
    if end == -1:
        raise RuntimeError("__INITIAL_STATE__ 未正常闭合")
    content = html[start:end].rstrip().rstrip(";")
    content = re.sub(r"new Map\(\[\]\)", "{}", content)
    content = re.sub(r":undefined", ":null", content)
    content = re.sub(r"\bundefined\b", "null", content)
    return json.loads(content)


def parse_profile(state: dict) -> dict:
    """从 __INITIAL_STATE__ 提取达人信息"""
    user = state.get("user") or {}
    basic = (user.get("userPageData") or {}).get("basicInfo") or {}
    interactions = (user.get("userPageData") or {}).get("interactions") or []

    def _find_count(type_name: str) -> str:
        for item in interactions:
            if item.get("type") == type_name:
                return item.get("count", "0")
        return "0"

    return {
        "nickname": basic.get("nickname", ""),
        "desc": basic.get("desc", ""),
        "ip": basic.get("ipLocation", ""),
        "fans": _find_count("fans"),
        "follows": _find_count("follows"),
        "liked": _find_count("interaction"),
    }


def _xhshow_client():
    """懒加载 xhshow 签名客户端"""
    try:
        from xhshow import Xhshow
        return Xhshow()
    except Exception as e:
        raise RuntimeError(f"无法加载 xhshow 签名库: {e}")


def _fetch_notes_via_api(user_id: str, num: int = 30) -> list:
    """
    通过小红书签名接口 /api/sns/web/v1/user_posted 获取笔记列表。
    这是当前（2026）能拿到 note_id 的可靠方式。
    """
    client = _xhshow_client()
    # 只传最简参数：xhshow 签名对额外参数敏感，加 image_formats/xsec_source 会 406
    params = {
        "user_id": user_id,
        "num": str(num),
        "cursor": "",
    }
    signed_headers = client.sign_headers_get(
        uri="https://edith.xiaohongshu.com/api/sns/web/v1/user_posted",
        cookies=SETTINGS.get("cookie", ""),
        params=params,
    )
    req_headers = {**HEADERS, **signed_headers}
    url = "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted"
    resp = requests.get(url, params=params, headers=req_headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") == -100:
        raise RuntimeError("小红书登录已过期，请刷新 Cookie 后再试")
    if not data.get("success"):
        raise RuntimeError(f"接口返回异常: {data.get('msg', data)}")

    notes = (data.get("data") or {}).get("notes") or []
    result = []
    for note in notes:
        card = note.get("note_card") or {}
        interact = card.get("interact_info") or {}
        # API 返回字段是 snake_case
        result.append({
            "note_id": note.get("note_id") or card.get("note_id") or "",
            "title": card.get("title") or card.get("display_title") or "",
            "type": card.get("type", ""),
            "time": note.get("time") or card.get("time"),
            "cover": card.get("cover", {}),
            "xsec_token": note.get("xsec_token") or card.get("xsec_token") or "",
            "liked_text": interact.get("liked_count") or interact.get("likedCount", ""),
        })
    return result


def _fetch_notes_via_html(state: dict) -> list:
    """
    兜底：从主页 HTML 的 SSR 数据解析笔记列表。
    2026 年后小红书不再在 SSR 中返回 note_id，因此这里返回的 note_id 可能为空。
    """
    user = state.get("user") or {}
    raw_notes = user.get("notes") or []
    notes = []
    for group in raw_notes:
        if not isinstance(group, list):
            continue
        for item in group:
            card = item.get("noteCard") or {}
            notes.append({
                "note_id": item.get("id") or card.get("noteId") or "",
                "title": card.get("displayTitle") or card.get("title", ""),
                "type": card.get("type", ""),
                "time": card.get("time"),
                "cover": card.get("cover", {}),
                "xsec_token": item.get("xsecToken") or card.get("xsecToken", ""),
                "liked_text": (card.get("interactInfo") or {}).get("likedCount", ""),
            })
    return notes


def fetch_profile(url: str) -> dict:
    """主流程：请求主页拿达人信息 + 调用签名 API 拿笔记清单"""
    user_id = _extract_user_id(url)
    print(f"请求主页: {safe_display_url(url)[:100]}...")
    print(f"  user_id: {user_id}")

    # 1. 请求主页 HTML 拿达人信息
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    state = extract_initial_state(resp.text)
    profile = parse_profile(state)
    profile["user_id"] = user_id

    # 2. 用签名 API 拿笔记列表（带 note_id）
    notes = []
    api_error = ""
    try:
        notes = _fetch_notes_via_api(user_id)
        print(f"  通过 API 获取 {len(notes)} 条笔记")
    except Exception as e:
        api_error = safe_error_text(e)
        print(f"  [!] API 获取笔记失败: {api_error}")
        print("  [!] 尝试从主页 HTML 兜底解析（note_id 可能为空）...")
        notes = _fetch_notes_via_html(state)

    print(
        f"达人: {profile['nickname']} | 粉丝 {profile['fans']} | "
        f"获赞与收藏 {profile['liked']} | 主页笔记 {len(notes)} 条"
    )
    if api_error:
        print(f"  ⚠️ 注意: {api_error}")

    return {"profile": profile, "notes": notes, "api_error": api_error}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python fetch_profile.py <主页链接> [--json-only]")
        sys.exit(1)
    t0 = time.time()
    result = fetch_profile(sys.argv[1])
    print(f"\n耗时 {time.time() - t0:.1f} 秒")
    if "--json-only" not in sys.argv:
        for i, n in enumerate(result["notes"], 1):
            import datetime
            t = datetime.datetime.fromtimestamp(n["time"] / 1000).strftime("%Y-%m-%d") if n["time"] else "?"
            print(f"  {i:>2}. [{n['type']}] {n['title'][:30]} | {t} | 赞{n['liked_text']} | id={n['note_id'][:12] if n['note_id'] else 'NONE'}")
    print("\nJSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
