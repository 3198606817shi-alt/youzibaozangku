"""安装阶段配置使用者自己的飞书表格与转写密钥。"""

import argparse
import getpass
import json
from pathlib import Path

from feishu_check import check_table_schema, resolve_table_url
from runtime_config import (
    KeychainSecretStore,
    load_public_config,
    public_config_path,
    save_public_config,
)


def configure_values(resolved, api_key, config_path=None, secret_store=None):
    path = Path(config_path or public_config_path())
    store = secret_store or KeychainSecretStore()
    current = load_public_config(path)
    current.update(
        {
            "base_token": resolved["base_token"],
            "table_id": resolved["table_id"],
        }
    )
    save_public_config(current, path)
    if api_key:
        store.set("siliconflow_api_key", api_key)
    return {"base_token": current["base_token"], "table_id": current["table_id"]}


def migrate_legacy_config(
    legacy_dir,
    confirmed,
    config_path=None,
    secret_store=None,
):
    if not confirmed:
        return {}
    legacy_dir = Path(legacy_dir)
    old_config_path = legacy_dir / "config.json"
    old_settings_path = legacy_dir / "settings.json"
    if not old_config_path.exists():
        return {}
    old_config = json.loads(old_config_path.read_text(encoding="utf-8"))
    old_settings = {}
    if old_settings_path.exists():
        old_settings = json.loads(old_settings_path.read_text(encoding="utf-8"))
    public = {
        key: old_config.get(key, load_public_config(config_path).get(key, ""))
        for key in ("base_token", "table_id", "model", "transcribe_api")
    }
    save_public_config(public, config_path)
    store = secret_store or KeychainSecretStore()
    api_key = old_config.get("siliconflow_api_key") or ""
    cookie = old_settings.get("cookie") or old_config.get("cookie") or ""
    if api_key:
        store.set("siliconflow_api_key", api_key)
    if cookie:
        store.set("xiaohongshu_cookie", cookie)
    return {"base_token": public["base_token"], "table_id": public["table_id"]}


def interactive_configure(legacy_dir=None):
    if legacy_dir and (Path(legacy_dir) / "config.json").exists():
        reply = input("检测到旧版配置，是否只读迁移？输入 y 继续：").strip().lower()
        if reply == "y":
            migrated = migrate_legacy_config(legacy_dir, confirmed=True)
            if migrated:
                print("旧配置已安全迁移，原文件未修改。")
                return migrated
    url = input("请粘贴你自己的飞书多维表格完整链接：").strip()
    resolved = resolve_table_url(url)
    api_key = getpass.getpass("请输入你自己的硅基流动API密钥（输入内容不会显示）：").strip()
    if not api_key:
        raise ValueError("转写密钥不能为空")
    configure_values(resolved, api_key)
    print("飞书表格标识已保存，转写密钥已存入Mac钥匙串。")
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-dir")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        public = load_public_config()
        result = check_table_schema(public["base_token"], public["table_id"])
        if not result["ok"]:
            print("飞书表格缺少字段：" + "、".join(result["missing_fields"]))
            raise SystemExit(2)
        print("飞书表格只读检查通过。")
        return
    interactive_configure(args.legacy_dir)


if __name__ == "__main__":
    main()
