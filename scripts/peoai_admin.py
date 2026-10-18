#!/usr/bin/env python3
"""命令行管理工具：忘记密码、创建 API Key、查看配置等。

用法:
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py show
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py set-password
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py add-key --name agent --rpm 60
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py list-keys
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py revoke-key --prefix pk_abcd
    PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py rotate-admin-token
"""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from peoai.config import ConfigStore  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def load() -> ConfigStore:
    root = Path(os.environ.get("PEOAI_HOME") or BASE)
    path = Path(os.environ.get("PEOAI_CONFIG") or (root / "config.json"))
    if not path.exists():
        print("配置文件不存在：%s" % path)
        print("先启动一次服务，或复制 config.example.json 为 config.json 后再执行。")
        raise SystemExit(1)
    return ConfigStore(path)


def cmd_show(config: ConfigStore) -> int:
    data = config.public_snapshot()
    server = data.get("server", {})
    security = data.get("security", {})
    print("配置文件: %s" % config.path)
    print("服务名称: %s" % server.get("name"))
    print("监听端口: %s" % server.get("port"))
    print("默认模型: %s" % server.get("default_model"))
    print("操作员密码已设置: %s" % security.get("operator_password_set"))
    print("管理令牌已设置: %s" % security.get("admin_token_set"))
    print("强制 API Key: %s" % security.get("require_api_key"))
    print("模型数量: %d" % len(data.get("models") or []))
    print("API Key 数量: %d" % len(data.get("api_keys") or []))
    for key in data.get("api_keys") or []:
        print("  - %-16s %s rpm=%s models=%s" % (
            key.get("name"), key.get("prefix"), key.get("rpm"), ",".join(key.get("models") or [])
        ))
    for model in data.get("models") or []:
        caps = [name for name, value in (model.get("capabilities") or {}).items() if value]
        print("  * %-18s %s" % (model.get("id"), ",".join(caps)))
    return 0


def cmd_set_password(config: ConfigStore) -> int:
    first = getpass.getpass("新密码（至少 10 位）: ")
    if len(first) < 10:
        print("密码太短")
        return 1
    second = getpass.getpass("再次输入: ")
    if first != second:
        print("两次输入不一致")
        return 1
    config.set_operator_password(first)
    print("已更新操作员密码；服务端需要重启或等待现有会话过期才会完全生效。")
    return 0


def cmd_add_key(config: ConfigStore, args) -> int:
    models = [item.strip() for item in (args.models or "*").split(",") if item.strip()]
    token = config.add_api_key(args.name, rpm=args.rpm, models=models or ["*"], note=args.note or "")
    print("已创建 API Key（只显示一次，请立即保存）:")
    print("  " + token)
    print("名称: %s  rpm=%d  模型=%s" % (args.name, args.rpm, ",".join(models)))
    return 0


def cmd_list_keys(config: ConfigStore) -> int:
    keys = config.public_snapshot().get("api_keys") or []
    if not keys:
        print("暂无 API Key")
        return 0
    for key in keys:
        print("%-16s %-12s rpm=%-6s enabled=%-5s models=%s last_used=%s" % (
            key.get("name"), key.get("prefix"), key.get("rpm"),
            key.get("enabled"), ",".join(key.get("models") or []), key.get("last_used") or "-",
        ))
    return 0


def cmd_revoke_key(config: ConfigStore, args) -> int:
    if config.remove_api_key(args.prefix):
        print("已删除 API Key %s" % args.prefix)
        return 0
    print("未找到该前缀的密钥")
    return 1


def cmd_rotate_admin(config: ConfigStore) -> int:
    token = "adm_" + secrets.token_urlsafe(24)
    config.set_admin_token(token)
    print("新的管理员令牌（只显示一次）:")
    print("  " + token)
    print("已写入配置文件的哈希；旧令牌立即失效。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="peoai_admin", description="PeoAI Server 命令行管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="查看配置摘要")
    sub.add_parser("set-password", help="交互式重置操作员密码")
    add = sub.add_parser("add-key", help="创建 API Key")
    add.add_argument("--name", default="cli", help="密钥名称")
    add.add_argument("--rpm", type=int, default=60, help="每分钟请求数，0 表示不限")
    add.add_argument("--models", default="*", help="可用模型，逗号分隔，* 表示全部")
    add.add_argument("--note", default="", help="备注")
    sub.add_parser("list-keys", help="列出 API Key（脱敏）")
    revoke = sub.add_parser("revoke-key", help="按前缀删除 API Key")
    revoke.add_argument("--prefix", required=True)
    sub.add_parser("rotate-admin-token", help="轮换管理员令牌")

    args = parser.parse_args(argv)
    config = load()
    handlers = {
        "show": lambda: cmd_show(config),
        "set-password": lambda: cmd_set_password(config),
        "add-key": lambda: cmd_add_key(config, args),
        "list-keys": lambda: cmd_list_keys(config),
        "revoke-key": lambda: cmd_revoke_key(config, args),
        "rotate-admin-token": lambda: cmd_rotate_admin(config),
    }
    return handlers[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
