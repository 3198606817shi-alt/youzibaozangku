#!/usr/bin/env python3
"""小红书数据提取 · 本地网页版后端

由桌面应用启动，浏览器打开 http://127.0.0.1:8766
粘贴链接 → 一键自动跑完：抓取 → 转写 → 写飞书 → 传封面
"""
import argparse
import contextlib
import io
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import pipeline          # noqa: E402  主流水线（复用）
import fetch_note        # noqa: E402  单条抓取
import fetch_profile     # noqa: E402  主页抓取
from log_safety import safe_display_url, safe_error_text  # noqa: E402
from runtime_config import get_secret_store  # noqa: E402

# 抑制噪音日志，避免混入任务日志
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

HOST = "127.0.0.1"
PORT = 8766
URL = f"http://{HOST}:{PORT}"

app = Flask(__name__)


# ---------- LogBus 日志总线 ----------
class LogBus:
    """环形日志缓冲 + 线程安全，print 输出经 redirect 后写入这里"""

    def __init__(self, maxlen=5000):
        self.lines = deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self.stream = _LogStream(self)

    def append(self, s):
        if not s:
            return
        with self.lock:
            self.lines.append(safe_error_text(s))

    def total(self):
        with self.lock:
            return len(self.lines)

    def get_since(self, idx):
        with self.lock:
            return list(self.lines)[idx:]


class _LogStream(io.TextIOBase):
    def __init__(self, bus):
        self.bus = bus

    def write(self, s):
        if s:
            self.bus.append(s)
        return len(s)

    def flush(self):
        pass


bus = LogBus()


# ---------- Cookie 保存（写文件 + 同步内存） ----------
def save_cookie(new_cookie: str) -> None:
    new_cookie = new_cookie.strip()
    get_secret_store().set("xiaohongshu_cookie", new_cookie)
    fetch_note.SETTINGS["cookie"] = new_cookie
    fetch_note.HEADERS["Cookie"] = new_cookie
    fetch_profile.SETTINGS["cookie"] = new_cookie
    fetch_profile.HEADERS["Cookie"] = new_cookie


@app.before_request
def require_local_origin_for_changes():
    if request.method == "POST" and request.headers.get("Origin") != URL:
        return jsonify({"ok": False, "error": "本机请求校验失败"}), 403


@app.after_request
def protect_local_data(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ---------- 任务执行 ----------
def process_profile_web(url, args, stop_event=None, on_item=None):
    """主页批量处理（web 版）：逐条实时回报结果，可中途停止"""
    info = fetch_profile.fetch_profile(url)
    profile = info["profile"]
    notes = info["notes"]
    profile_info = {"nickname": profile["nickname"], "profile_url": url}

    since_ms = None
    if args.since:
        since_ms = pipeline.parse_since(args.since)
        before = len(notes)
        notes = pipeline.filter_by_time(notes, since_ms)
        print(f"  时间过滤（{args.since}）: {before} -> {len(notes)} 条")

    results = []
    for i, n in enumerate(notes, 1):
        if stop_event and stop_event.is_set():
            print("  ⏹ 已收到停止指令，中止后续处理")
            break
        print(f"\n[{i}/{len(notes)}] {n['title'][:40]}...")
        note_id = n.get("note_id", "")
        if not note_id:
            err = "跳过：未获取到笔记 ID（Cookie 可能已过期，或小红书接口返回了降级数据）"
            print(f"  ✗ {err}")
            r = {"url": "", "ok": False, "error": err, "title": n.get("title", ""), "steps": []}
            results.append(r)
            if on_item:
                on_item(r)
            continue
        # 带上 API 返回的 xsec_token（与当前 Cookie 同时签发、匹配），
        # 2026 年起小红书单条笔记页不带 token 会返回空数据（noteDetailMap 为空）
        xsec_token = n.get("xsec_token", "")
        if xsec_token:
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
        else:
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        r = pipeline.process_note(note_url, args, profile_info, source_type="达人主页")
        status = "✓" if r["ok"] else "✗"
        steps = " → ".join(r["steps"]) if r["ok"] else r.get("error", "失败")
        print(f"  {status} {steps}")
        results.append(r)
        if on_item:
            on_item(r)
        time.sleep(1)  # 控制请求频率，降低风控风险

    return results


def run_task(urls, since, no_transcribe, cleanup, stop_event=None, on_item=None):
    """执行一批链接，逐项实时回报。返回逐条结果列表"""
    args = argparse.Namespace(
        since=since or None,
        no_transcribe=bool(no_transcribe),
        cleanup=bool(cleanup),
        dry_run=False,
    )
    expanded = pipeline.expand_links(urls)
    all_items = []
    for url, kind, label in expanded:
        if stop_event and stop_event.is_set():
            print("⏹ 已收到停止指令，中止后续处理")
            break
        print(f"\n===== {label}: {safe_display_url(url)[:80]}... =====")
        try:
            if kind == "profile":
                results = process_profile_web(url, args, stop_event, on_item)
                all_items.extend(results)
            elif kind == "note":
                r = pipeline.process_note(url, args, source_type="爆款视频")
                print(f"  {'✓' if r['ok'] else '✗'} "
                      f"{' → '.join(r['steps']) if r['ok'] else r.get('error', '失败')}")
                all_items.append(r)
                if on_item:
                    on_item(r)
            else:
                print(f"  [!] 无法识别链接类型，跳过: {safe_display_url(url)}")
                r = {"url": url, "ok": False, "error": "无法识别链接类型", "title": "", "steps": []}
                all_items.append(r)
                if on_item:
                    on_item(r)
        except Exception as e:
            clean_error = safe_error_text(e)
            print(f"  ✗ 处理失败: {clean_error}")
            r = {"url": safe_display_url(url), "ok": False, "error": clean_error, "title": "", "steps": []}
            all_items.append(r)
            if on_item:
                on_item(r)
        time.sleep(0.2)

    ok = sum(1 for r in all_items if r.get("ok"))
    fail = len(all_items) - ok
    print(f"\n完成。成功 {ok} 条，失败 {fail} 条")
    return all_items


# ---------- 任务队列 ----------
class TaskManager:
    """单 worker + FIFO 队列"""

    def __init__(self):
        self.queue = deque()
        self.lock = threading.Lock()
        self.current = None
        self.last = None
        self._seq = 0
        self._stop_events = {}
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, urls, since, no_transcribe, cleanup):
        with self.lock:
            self._seq += 1
            task = {
                "task_id": self._seq,
                "state": "queued",          # queued | running | done | failed
                "urls": urls,
                "since": since,
                "no_transcribe": no_transcribe,
                "cleanup": cleanup,
                "created_at": time.time(),
                "started_at": None,
                "finished_at": None,
                "items": [],                 # 逐条结果（实时追加）
                "summary": None,             # {"ok","fail","seconds"}
                "error": None,
                "stopped": False,
            }
            self.queue.append(task)
            position = len(self.queue)
            return task, position

    def stop_current(self):
        with self.lock:
            cur = self.current
            if cur:
                ev = self._stop_events.get(cur["task_id"])
                if ev:
                    ev.set()
                    return True
        return False

    def status(self):
        with self.lock:
            return {
                "queue_length": len(self.queue),
                "current": self.current,
                "last": self.last,
            }

    def _loop(self):
        while True:
            with self.lock:
                if self.queue:
                    task = self.queue.popleft()
                    self.current = task
                else:
                    task = None
            if task is None:
                time.sleep(0.3)
                continue

            ev = threading.Event()
            with self.lock:
                self._stop_events[task["task_id"]] = ev

            task["state"] = "running"
            task["started_at"] = time.time()
            t0 = time.time()

            def on_item(r):
                with self.lock:
                    task["items"].append(r)

            try:
                with contextlib.redirect_stdout(bus.stream), contextlib.redirect_stderr(bus.stream):
                    run_task(
                        task["urls"], task["since"],
                        task["no_transcribe"], task["cleanup"],
                        stop_event=ev, on_item=on_item,
                    )
                with self.lock:
                    items = task["items"]
                    ok = sum(1 for r in items if r.get("ok"))
                    fail = len(items) - ok
                    task["summary"] = {"ok": ok, "fail": fail, "seconds": round(time.time() - t0)}
                    task["state"] = "done"
                    task["finished_at"] = time.time()
                    task["stopped"] = ev.is_set()
                    self.last = task
                    self.current = None
                    self._stop_events.pop(task["task_id"], None)
            except Exception as e:
                with self.lock:
                    task["error"] = safe_error_text(e)
                    task["state"] = "failed"
                    task["finished_at"] = time.time()
                    self.last = task
                    self.current = None
                    self._stop_events.pop(task["task_id"], None)


tm = TaskManager()


def public_task(task):
    """返回供页面显示的任务副本，不暴露链接查询参数或临时令牌。"""
    if not task:
        return None
    view = dict(task)
    view["urls"] = [safe_display_url(str(url)) for url in task.get("urls", [])]
    view["items"] = []
    for item in task.get("items", []):
        clean_item = dict(item)
        if clean_item.get("url"):
            clean_item["url"] = safe_display_url(str(clean_item["url"]))
        if clean_item.get("error"):
            clean_item["error"] = safe_error_text(clean_item["error"])
        view["items"].append(clean_item)
    if view.get("error"):
        view["error"] = safe_error_text(view["error"])
    return view


# ---------- API 路由 ----------
@app.get("/")
def index():
    return send_from_directory(BASE_DIR / "templates", "index.html")


@app.get("/api/status")
def api_status():
    st = tm.status()
    return jsonify({
        "server_time": time.time(),
        "queue_length": st["queue_length"],
        "current": public_task(st["current"]),
        "last": public_task(st["last"]),
    })


@app.get("/api/health")
def api_health():
    return jsonify({"service": "xhs-data-extractor", "ok": True})


@app.get("/api/logs")
def api_logs():
    try:
        since = max(0, int(request.args.get("since", 0)))
    except ValueError:
        since = 0
    lines = bus.get_since(since)
    return jsonify({"total": bus.total(), "lines": lines})


@app.post("/api/start")
def api_start():
    body = request.get_json(silent=True) or {}
    raw = body.get("urls") or []
    if isinstance(raw, str):
        urls = [u.strip() for u in raw.splitlines() if u.strip()]
    else:
        urls = [str(u).strip() for u in raw if str(u).strip()]
    if not urls:
        return jsonify({"ok": False, "error": "请先粘贴链接"}), 400
    since = (body.get("since") or "").strip()
    task, position = tm.submit(
        urls, since,
        bool(body.get("no_transcribe")),
        bool(body.get("cleanup")),
    )
    return jsonify({"ok": True, "task_id": task["task_id"], "queue_position": position})


@app.post("/api/stop")
def api_stop():
    stopped = tm.stop_current()
    return jsonify({"ok": True, "stopped": stopped})


@app.post("/api/cookie")
def api_cookie():
    body = request.get_json(silent=True) or {}
    cookie = (body.get("cookie") or "").strip()
    if not cookie:
        return jsonify({"ok": False, "error": "Cookie 不能为空"}), 400
    try:
        save_cookie(cookie)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"保存失败：{safe_error_text(e)}"}), 500


if __name__ == "__main__":
    # 浏览器只由桌面启动器打开，避免首次启动出现两个页面标签。
    app.run(host=HOST, port=PORT, threaded=True, debug=False, use_reloader=False)
