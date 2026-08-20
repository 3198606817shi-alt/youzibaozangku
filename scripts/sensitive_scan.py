#!/usr/bin/env python3
"""发布前敏感信息扫描。"""

import argparse
import re
import sys
from pathlib import Path


SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".icns", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".dmg", ".pyc"}
PATTERNS = [
    ("API密钥", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Feishu App Secret", re.compile(r"\b[A-Za-z0-9_-]{32,}\b\s*(?:#\s*)?app[_ -]?secret", re.I)),
    ("Cookie头", re.compile(r"(?im)^\s*cookie\s*:\s*[^<\n]{20,}$")),
    ("Cookie配置", re.compile(r'(?i)"(?:xiaohongshu_)?cookie"\s*:\s*"(?!示例|请填|安装)[^"\n]{20,}"')),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("飞书令牌", re.compile(r"\b(?:t-|u-|a-)[A-Za-z0-9_-]{30,}\b")),
]


def should_scan(path: Path) -> bool:
    return not SKIP_PARTS.intersection(path.parts) and path.suffix.lower() not in SKIP_SUFFIXES


def scan(root: Path):
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not should_scan(path.relative_to(root)):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((path.relative_to(root), line_number, name))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = scan(root)
    if findings:
        print("发现可疑敏感信息：")
        for path, line_number, name in findings:
            print("- %s:%d [%s]" % (path, line_number, name))
        return 1
    print("敏感信息扫描通过：未发现已知凭证格式。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
