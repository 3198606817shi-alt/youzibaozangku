#!/usr/bin/env python3
"""小红书笔记全流程流水线：抓取 -> 下载 -> 转写 -> 写入飞书多维表格

用法：
    python pipeline.py <链接...>                          # 笔记/主页/短链 混合输入
    python pipeline.py --file links.txt                   # 从文件读链接（每行一个）
    python pipeline.py <链接> --since 30d                 # 只处理近30天（支持 7d/30d/90d/YYYY-MM-DD）
    python pipeline.py <链接> --no-transcribe             # 不转写，只抓数据+下载+写飞书
    python pipeline.py <链接> --dry-run                   # 只列清单，不执行
    python pipeline.py <链接> --cleanup                   # 转写完成后删除视频文件（省空间）
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import fetch_note
import fetch_profile
import feishu_views
from log_safety import safe_display_url, safe_error_text
from runtime_config import data_dir, load_runtime_config
from transcribe import video_to_text

CONFIG = load_runtime_config()
LARK_CLI = "lark-cli"


# ---------- 链接解析 ----------

URL_RE = re.compile(r"https?://[^\s<>\[\](){}\\\"]+")


def _extract_urls(text: str) -> list:
    """从任意文本中提取 http(s) URL，兼容小红书"分享文本"（含标题、表情）"""
    return URL_RE.findall(text)


def _clean_xhs_url(url: str) -> str:
    """
    清洗小红书 URL：去掉查询参数，避免导航栏长链接里的 xsec_token
    与当前 Cookie 不匹配导致返回空页面。
    保留标准路径结构，让服务端用当前会话重新签发 token。
    """
    try:
        parsed = urlparse(url)
        path = parsed.path or ""

        # 达人主页：/user/profile/{user_id}
        m = re.search(r"/user/profile/([^/]+)", path)
        if m:
            user_id = m.group(1)
            return urlunparse((
                parsed.scheme or "https",
                parsed.netloc,
                f"/user/profile/{user_id}",
                "", "", ""
            ))

        # 单条笔记：/explore/{note_id} 或 /discovery/item/{note_id}
        m = re.search(r"/explore/([^/]+)", path)
        if m:
            note_id = m.group(1)
            return urlunparse((
                parsed.scheme or "https",
                parsed.netloc,
                f"/explore/{note_id}",
                "", "", ""
            ))
        m = re.search(r"/discovery/item/([^/]+)", path)
        if m:
            note_id = m.group(1)
            return urlunparse((
                parsed.scheme or "https",
                parsed.netloc,
                f"/discovery/item/{note_id}",
                "", "", ""
            ))
    except Exception:
        pass
    return url


def expand_links(urls: list) -> list:
    """展开短链、清洗参数、识别链接类型，返回 (原始链接, 类型, 显示名) 列表"""
    import requests
    results = []
    headers = {"User-Agent": fetch_note.UA, "Cookie": fetch_note.SETTINGS.get("cookie", "")}
    for raw in urls:
        raw = raw.strip()
        if not raw:
            continue
        found = _extract_urls(raw)
        if not found:
            print(f"  [!] 该行未识别到链接，跳过: {raw[:80]}")
            continue
        for url in found:
            if "xhslink" in url:
                try:
                    resp = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
                    url = resp.url
                except Exception as e:
                    print(f"  [!] 短链解析失败 {safe_display_url(url)}: {safe_error_text(e)}")
            # 清洗掉可能和当前 Cookie 不匹配的 xsec_token 等参数
            original = url
            url = _clean_xhs_url(url)
            if url != original:
                print(f"  已清洗链接参数: {safe_display_url(url)}")
            if "/user/profile/" in url:
                results.append((url, "profile", "达人主页"))
            elif re.search(r"/(explore|discovery/item)/", url):
                results.append((url, "note", "单条笔记"))
            else:
                results.append((url, "unknown", "未知类型"))
    return results


# ---------- 时间过滤 ----------

def parse_since(value: str) -> float:
    """--since 参数 -> 毫秒时间戳"""
    m = re.match(r"^(\d+)([dDwWmM])$", value)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = n * (7 if unit == "w" else 30 if unit == "m" else 1)
        return (datetime.now() - timedelta(days=days)).timestamp() * 1000
    try:
        return datetime.strptime(value, "%Y-%m-%d").timestamp() * 1000
    except ValueError:
        raise ValueError(f"--since 格式错误: {value}（支持 7d/30d/YYYY-MM-DD）")


def filter_by_time(notes: list, since_ms: float) -> list:
    keep = []
    for n in notes:
        t = n.get("time")
        if t and since_ms and t < since_ms:
            continue
        keep.append(n)
    return keep


def profile_video_notes(notes: list) -> list:
    """达人主页当前只处理视频，不把图文笔记写入飞书。"""
    return [note for note in notes if note.get("type") == "video"]


def ensure_profile_view(nickname: str) -> dict:
    """为达人主页创建或复用只显示该达人视频的飞书视图。"""
    result = feishu_views.ensure_creator_view(
        CONFIG["base_token"],
        CONFIG["table_id"],
        nickname,
    )
    action = "已新建" if result["created"] else "已复用"
    print(f"  飞书达人视图：{action}「{result['name']}」")
    return result


# ---------- 飞书写入 ----------

def build_record(data: dict, profile_url: str = "", source_type: str = "") -> dict:
    """构造飞书记录字段映射；source_type: 达人主页 / 爆款视频"""
    note_type = "视频" if data.get("type") == "video" else "图文"
    pub_time = ""
    if data.get("time"):
        pub_time = datetime.fromtimestamp(data["time"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    note_url = f"https://www.xiaohongshu.com/explore/{data['note_id']}"
    record = {
        "笔记标题": data.get("title", ""),
        "笔记类型": note_type,
        "达人昵称": data.get("nickname", ""),
        "发布时间": pub_time,
        "点赞数": data.get("liked_count", 0),
        "收藏数": data.get("collected_count", 0),
        "评论数": data.get("comment_count", 0),
        "逐字稿": data.get("transcript", ""),
        "笔记链接": note_url,
        "达人主页链接": profile_url,
    }
    if source_type:
        record["来源类型"] = source_type
    return record


def check_exists(note_id: str) -> bool:
    """按笔记链接字段查重：note_id 已存在于飞书表则返回 True"""
    if not note_id:
        return False
    cmd = [
        LARK_CLI, "base", "+record-search",
        "--base-token", CONFIG["base_token"],
        "--table-id", CONFIG["table_id"],
        "--keyword", note_id,
        "--search-field", "笔记链接",
        "--as", "user",
        "--format", "json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        out = json.loads(result.stdout)
        rows = (out.get("data") or {}).get("data") or []
        return len(rows) > 0
    except Exception as e:
        print(f"  [!] 查重失败（按不重复处理）: {e}")
        return False


def create_record(record: dict) -> str:
    """创建飞书记录，返回 record_id"""
    body = json.dumps({"create_records": [record]}, ensure_ascii=False)
    cmd = [
        LARK_CLI, "base", "+record-batch-create",
        "--base-token", CONFIG["base_token"],
        "--table-id", CONFIG["table_id"],
        "--json", body,
        "--as", "user",
        "--format", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        out = json.loads(result.stdout)
        if out.get("ok"):
            rec_list = out.get("data", {}).get("record_id_list") or []
            if rec_list:
                return rec_list[0]
            records = out.get("data", {}).get("records") or []
            if records:
                return records[0].get("record_id", "")
    except Exception:
        pass
    print(f"  [飞书] 创建记录失败（exit={result.returncode}），请检查授权、字段和表格权限")
    return ""


def upload_cover(record_id: str, cover_file: str) -> bool:
    """上传封面图到记录的封面图字段"""
    if not record_id or not cover_file or not os.path.exists(cover_file):
        return False
    # lark-cli --file 只接受当前工作目录下的相对路径。
    # 发布版下载目录在Application Support，因此切换到封面所在目录再上传。
    cover_path = Path(cover_file).resolve()
    cmd = [
        LARK_CLI, "base", "+record-upload-attachment",
        "--base-token", CONFIG["base_token"],
        "--table-id", CONFIG["table_id"],
        "--record-id", record_id,
        "--field-id", "封面图",
        "--file", cover_path.name,
        "--as", "user",
        "--format", "json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cover_path.parent),
    )
    try:
        out = json.loads(result.stdout)
        return bool(out.get("ok"))
    except Exception:
        print(f"  [飞书] 封面上传失败（exit={result.returncode}），请检查附件字段和上传权限")
        return False


# ---------- 单条笔记处理 ----------

def process_note(url: str, args, profile_info: dict = None, source_type: str = "") -> dict:
    """处理单条笔记：抓取->转写->写飞书。返回结果摘要
    source_type: 达人主页 / 爆款视频（空=不写来源类型字段）"""
    outdir = data_dir() / "downloads"
    profile_url = ""
    profile_name = ""
    if profile_info:
        profile_url = profile_info.get("profile_url", "")
        profile_name = profile_info.get("nickname", "")

    result = {"url": url, "ok": False, "steps": []}

    # 0. 预查重：从链接直接提取 note_id，已入库则秒跳过（不下载、不转写）
    pre_match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]{20,32})", url)
    if pre_match and check_exists(pre_match.group(1)):
        result["skipped"] = True
        result["ok"] = True
        result["steps"].append("查重命中，已跳过写入")
        return result

    # 1. 抓取 + 下载
    try:
        data = fetch_note.fetch(url, outdir)
        result["title"] = data.get("title", "")
        result["note_id"] = data.get("note_id", "")
        result["steps"].append("抓取")
        if profile_name and not data.get("nickname"):
            data["nickname"] = profile_name
    except Exception as e:
        result["error"] = f"抓取失败: {e}"
        return result

    # 2. 查重：以抓取到的权威 note_id 兜底再查一次
    note_id = data.get("note_id", "")
    if check_exists(note_id):
        result["skipped"] = True
        result["ok"] = True
        result["steps"].append("查重命中，已跳过写入")
        if args.cleanup and data.get("video_file") and os.path.exists(data["video_file"]):
            os.remove(data["video_file"])
            result["steps"].append("删视频")
        return result

    # 3. 转写
    transcript = ""
    if not args.no_transcribe and data.get("video_file"):
        print(f"  转写中（视频 {os.path.getsize(data['video_file'])/1024/1024:.0f}MB）...")
        try:
            transcript = video_to_text(data["video_file"])
            data["transcript"] = transcript
            result["steps"].append(f"转写({len(transcript)}字)")
        except Exception as e:
            result["steps"].append(f"转写失败:{e}")
    else:
        data["transcript"] = ""

    # 4. 写飞书
    record = build_record(data, profile_url, source_type)
    record_id = create_record(record)
    if record_id:
        result["steps"].append("写飞书")
        if upload_cover(record_id, data.get("cover_file", "")):
            result["steps"].append("传封面")
        result["ok"] = True
        result["record_id"] = record_id
    else:
        result["error"] = result.get("error", "") + " 飞书写入失败"

    # 5. 清理
    if args.cleanup and data.get("video_file") and os.path.exists(data["video_file"]):
        os.remove(data["video_file"])
        result["steps"].append("删视频")

    return result


# ---------- 主页批量处理 ----------

def process_profile(url: str, args) -> list:
    """处理达人主页：拉清单 -> 过滤 -> 逐条处理"""
    outdir = data_dir() / "downloads"
    try:
        info = fetch_profile.fetch_profile(url)
    except Exception as e:
        print(f"[!] 主页抓取失败: {e}")
        return []

    profile = info["profile"]
    profile_info = {
        "nickname": profile["nickname"],
        "profile_url": url,
    }
    notes = profile_video_notes(info["notes"])
    ensure_profile_view(profile["nickname"])

    since_ms = None
    if args.since:
        since_ms = parse_since(args.since)
        before = len(notes)
        notes = filter_by_time(notes, since_ms)
        print(f"  时间过滤（{args.since}）: {before} -> {len(notes)} 条")

    if args.dry_run:
        print(f"\n[{profile['nickname']}] 将处理 {len(notes)} 条:")
        for i, n in enumerate(notes, 1):
            t = datetime.fromtimestamp(n["time"] / 1000).strftime("%Y-%m-%d") if n.get("time") else "?"
            print(f"  {i:>2}. [{n['type']}] {n['title'][:40]} | {t}")
        return []

    results = []
    for i, n in enumerate(notes, 1):
        print(f"\n[{i}/{len(notes)}] {n['title'][:40]}...")
        note_id = n.get("note_id", "")
        if not note_id:
            err = "跳过：未获取到笔记 ID（Cookie 可能已过期，或小红书接口返回了降级数据）"
            print(f"  ✗ {err}")
            results.append({"url": "", "ok": False, "error": err, "title": n.get("title", ""), "steps": []})
            continue
        # 带上 API 返回的 xsec_token（与当前 Cookie 同时签发、匹配），
        # 2026 年起小红书单条笔记页不带 token 会返回空数据（noteDetailMap 为空）
        xsec_token = n.get("xsec_token", "")
        if xsec_token:
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
        else:
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        r = process_note(note_url, args, profile_info, source_type="达人主页")
        status = "✓" if r["ok"] else "✗"
        steps = " → ".join(r["steps"]) if r["ok"] else r.get("error", "失败")
        print(f"  {status} {steps}")
        results.append(r)
        time.sleep(1)  # 控制请求频率，降低风控风险

    return results


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="小红书笔记流水线")
    parser.add_argument("urls", nargs="*", help="链接（笔记/主页/短链）")
    parser.add_argument("--file", help="从文件读链接，每行一个")
    parser.add_argument("--since", help="时间过滤: 7d/30d/YYYY-MM-DD")
    parser.add_argument("--no-transcribe", action="store_true", help="不转写")
    parser.add_argument("--dry-run", action="store_true", help="只列清单不执行")
    parser.add_argument("--cleanup", action="store_true", help="转写后删除视频文件")
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            urls += [line.strip() for line in f if line.strip()]

    if not urls:
        parser.print_help()
        return

    print(f"解析 {len(urls)} 个链接...")
    expanded = expand_links(urls)

    all_results = []
    t0 = time.time()
    for url, kind, label in expanded:
        print(f"\n===== {label}: {safe_display_url(url)[:80]}... =====")
        if kind == "profile":
            results = process_profile(url, args)
            all_results.extend(results)
        elif kind == "note":
            r = process_note(url, args, source_type="爆款视频")
            status = "✓" if r["ok"] else "✗"
            print(f"  {status} {' → '.join(r['steps']) if r['ok'] else r.get('error','失败')}")
            all_results.append(r)
        else:
            print(f"  [!] 无法识别链接类型，跳过: {safe_display_url(url)}")

    # 汇总
    ok = sum(1 for r in all_results if r.get("ok"))
    fail = len(all_results) - ok
    print(f"\n{'='*50}")
    print(f"完成。成功 {ok} 条，失败 {fail} 条，耗时 {time.time()-t0:.0f} 秒")
    for r in all_results:
        if not r.get("ok"):
            print(f"  ✗ {r.get('title', r['url'][:50])}: {r.get('error', '未知错误')}")


if __name__ == "__main__":
    main()
