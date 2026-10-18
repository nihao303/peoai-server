#!/usr/bin/env python3
"""PeoAI Server 入口。

用法:
    python3 peoai_server.py                  # 使用 config.json 中的 host/port
    python3 peoai_server.py --port 5007      # 覆盖端口
    PEOAI_HOME=/opt/peoai_server python3 peoai_server.py
    python3 peoai_server.py --no-waitress    # 调试时使用 Flask 内置服务器

环境变量:
    PEOAI_HOME      运行目录（默认本文件所在目录）
    PEOAI_CONFIG    配置文件路径（默认 $PEOAI_HOME/config.json）
    PEOAI_DATA      数据目录（默认 $PEOAI_HOME/data）
    PEOAI_HOST      监听地址
    PEOAI_PORT      监听端口
    PEOAI_THREADS   waitress 工作线程数（默认 24）
    PEOAI_LOG_LEVEL 日志级别（默认 INFO）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from peoai import __version__  # noqa: E402
from peoai.app import create_app  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="peoai_server",
        description="PeoAI Server - 把真人接入任何 AI API 的桥接服务",
    )
    parser.add_argument("--host", help="监听地址，默认取 config.server.host")
    parser.add_argument("--port", type=int, help="监听端口，默认取 config.server.port")
    parser.add_argument("--root", help="运行目录（包含 config.json 与 data/）")
    parser.add_argument("--threads", type=int, help="waitress 线程数，默认 24")
    parser.add_argument("--debug", action="store_true", help="开启 Flask 调试模式（仅内置服务器）")
    parser.add_argument("--no-waitress", action="store_true", help="不使用 waitress")
    parser.add_argument("--print-config", action="store_true", help="打印配置路径后退出")
    parser.add_argument("--version", action="version", version="PeoAI " + __version__)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.root:
        os.environ["PEOAI_HOME"] = str(Path(args.root).expanduser().resolve())
    app = create_app()
    ctx = app.extensions["peoai"]

    if args.print_config:
        print("root:   %s" % ctx.root)
        print("config: %s" % ctx.config.path)
        print("data:   %s" % ctx.data_dir)
        print("models: %d" % len(ctx.config.models()))
        return 0

    host = args.host or os.environ.get("PEOAI_HOST") or ctx.config.get("server.host") or "0.0.0.0"
    port = args.port or int(os.environ.get("PEOAI_PORT") or ctx.config.get("server.port") or 5007)
    threads = args.threads or int(os.environ.get("PEOAI_THREADS") or 24)
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    print("=" * 68)
    print("  %s v%s  %s" % (ctx.config.get("server.name", "PeoAI"), __version__, ctx.config.get("server.tagline", "")))
    print("  控制台:   http://%s:%d/" % (display_host, port))
    print("  OpenAI:   http://%s:%d/v1/chat/completions" % (display_host, port))
    print("  Anthropic:http://%s:%d/v1/messages" % (display_host, port))
    print("  Gemini:   http://%s:%d/v1beta/models/<model>:generateContent" % (display_host, port))
    print("  Ollama:   http://%s:%d/api/chat" % (display_host, port))
    print("  模型数量: %d 个" % len(ctx.config.models()))
    if ctx.credentials:
        print("  初始凭据: %s" % (ctx.data_dir / "bootstrap.txt"))
    print("=" * 68)

    if not args.no_waitress:
        try:
            from waitress import serve

            ctx.logger.info("使用 waitress 启动 %s:%d（线程 %d）", host, port, threads)
            serve(app, host=host, port=port, threads=max(4, threads), ident="PeoAI")
            return 0
        except ImportError:
            ctx.logger.warning("未安装 waitress，回退到 Flask 内置服务器（生产环境建议 pip install waitress）")

    app.run(host=host, port=port, threaded=True, debug=args.debug)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止")
        raise SystemExit(130)
