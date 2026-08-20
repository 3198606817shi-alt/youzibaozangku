"""
小红书笔记抓取器（自研，替代 XHS-Downloader）
原理：请求笔记页面 HTML → 提取 window.__INITIAL_STATE__ → 容错转 JSON → 提取笔记数据
为什么不用 XHS-Downloader：2026年小红书前端改版，工具解析器（yaml.safe_load）无法处理
__INITIAL_STATE__ 中的 new Map([]) / undefined 等 JS 语法，v2.6/v2.7 均已失效。

用法：
    python fetch_note.py <笔记链接> [--outdir 输出目录]
    支持完整链接、xhslink 短链、explore/discovery 任意形式
输出：
    下载视频(mp4)、封面(jpg/png) 到输出目录
    打印结构化 JSON（标题/描述/互动/作者/时间/文件路径）
"""
import json
import re
import sys
import time
from pathlib import Path

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


def resolve_url(url: str) -> str:
    """短链(xhslink)解析为真实链接，普通链接原样返回"""
    if "xhslink" in url:
        resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
        return resp.url
    return url


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
    # 容错：小红书在 __INITIAL_STATE__ 里混入 JS 语法
    content = re.sub(r"new Map\(\[\]\)", "{}", content)  # 空 Map
    content = re.sub(r":undefined", ":null", content)  # undefined 值
    content = re.sub(r"\bundefined\b", "null", content)  # 兜底
    return json.loads(content)


def parse_note_data(state: dict) -> dict:
    """从 __INITIAL_STATE__ 提取笔记详情"""
    note_map = (state.get("note") or {}).get("noteDetailMap") or {}
    if not note_map:
        raise RuntimeError("页面数据中没有笔记详情(noteDetailMap)")
    note_id = list(note_map.keys())[0]
    detail = note_map[note_id]
    note = detail.get("note") or {}
    if not note:
        raise RuntimeError("笔记详情为空")

    interact = note.get("interactInfo") or {}
    user = note.get("user") or {}
    video = note.get("video") or {}
    media = video.get("media") or {}

    # 选最高清晰度视频流（EF4/EF5/EF6/EF7 等，取列表最后通常更高清）
    stream = media.get("stream") or {}
    video_url = None
    for fmt in stream.values():
        if isinstance(fmt, list) and fmt:
            fmt_sorted = sorted(
                fmt, key=lambda s: (s.get("height") or 0), reverse=True
            )
            video_url = fmt_sorted[0].get("masterUrl") or video_url
        elif isinstance(fmt, dict) and fmt.get("masterUrl"):
            video_url = fmt.get("masterUrl") or video_url

    # 封面：imageList 第一张的 WB_DFT 场景
    cover_url = ""
    image_list = note.get("imageList") or []
    if image_list:
        info_list = image_list[0].get("infoList") or []
        for info in info_list:
            if info.get("imageScene") == "WB_DFT" and info.get("url"):
                cover_url = info["url"]
                break
        if not cover_url:
            cover_url = image_list[0].get("url") or ""

    return {
        "note_id": note.get("noteId") or note_id,
        "title": note.get("title", ""),
        "desc": note.get("desc", ""),
        "type": note.get("type", ""),
        "liked_count": int(interact.get("likedCount") or 0),
        "collected_count": int(interact.get("collectedCount") or 0),
        "comment_count": int(interact.get("commentCount") or 0),
        "share_count": int(interact.get("shareCount") or 0),
        "nickname": user.get("nickname", ""),
        "user_id": user.get("userId", ""),
        "time": note.get("time"),
        "tags": [t.get("name", "") for t in (note.get("tagList") or [])],
        "video_url": video_url,
        "cover_url": cover_url,
    }


def download_file(url: str, dest: Path, max_size_mb: int = 500) -> bool:
    """下载文件，返回是否成功"""
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"  下载失败 {safe_display_url(url)[:80]}...: {safe_error_text(e)}")
        return False


def fetch(url: str, outdir: Path) -> dict:
    """主流程：解析链接 → 抓页面 → 解析数据 → 下载视频和封面"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    real_url = resolve_url(url)
    print(f"请求页面: {safe_display_url(real_url)[:100]}...")
    resp = requests.get(real_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    state = extract_initial_state(resp.text)
    data = parse_note_data(state)
    print(
        f"笔记: 《{data['title'][:40]}》 | {data['nickname']} | "
        f"赞{data['liked_count']} 藏{data['collected_count']} "
        f"评{data['comment_count']} 转{data['share_count']}"
    )

    # 下载视频
    if data["video_url"]:
        video_path = outdir / f"{data['note_id']}.mp4"
        if not video_path.exists():
            print("下载视频...")
            ok = download_file(data["video_url"], video_path)
            data["video_file"] = str(video_path) if ok else ""
        else:
            print("视频已存在，跳过下载")
            data["video_file"] = str(video_path)
    else:
        data["video_file"] = ""

    # 下载封面
    if data["cover_url"]:
        ext = ".jpg" if "jpg" in data["cover_url"] else ".png"
        cover_path = outdir / f"{data['note_id']}_cover{ext}"
        if not cover_path.exists():
            print("下载封面...")
            ok = download_file(data["cover_url"], cover_path)
            data["cover_file"] = str(cover_path) if ok else ""
        else:
            data["cover_file"] = str(cover_path)
    else:
        data["cover_file"] = ""

    # 保存元数据 JSON（供 pipeline 后续环节使用）
    meta_path = outdir / f"{data['note_id']}.json"
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    data["meta_file"] = str(meta_path)

    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python fetch_note.py <笔记链接> [--outdir 目录]")
        sys.exit(1)
    url = sys.argv[1]
    outdir = Path(sys.argv[sys.argv.index("--outdir") + 1]) if "--outdir" in sys.argv else (BASE_DIR / "downloads")
    t0 = time.time()
    result = fetch(url, outdir)
    print(f"\n完成，耗时 {time.time() - t0:.1f} 秒")
    print(json.dumps(result, ensure_ascii=False, indent=2))
