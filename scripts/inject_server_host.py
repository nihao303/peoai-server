#!/usr/bin/env python3
"""把后端服务器地址注入控制台页面，用于「前端与后端不同源」的部署。

控制台默认请求同源的 /peoai 前缀；如果页面放在别的域名/端口，
用本脚本生成一个注入地址的副本（页面仍是单文件）：

    python scripts/inject_server_host.py api.example.com -o /www/wwwroot/site/home/peoai.html

也可以手动在页面主 <script> 之前加一行：
    <script>window.PEOAI_SERVER_HOST = "api.example.com";</script>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MARKER = "<script>\n(function () {"


def normalize(host: str) -> str:
    value = host.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.split("/")[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成带固定后端地址的控制台页面")
    parser.add_argument("host", help="后端域名或 IP，例如 api.example.com")
    parser.add_argument("-i", "--input", default=str(BASE / "static" / "peoai.html"))
    parser.add_argument("-o", "--output", default=str(BASE / "static" / "peoai.deploy.html"))
    args = parser.parse_args(argv)

    host = normalize(args.host)
    if not host:
        print("host 不能为空")
        return 1
    source_path = Path(args.input)
    output_path = Path(args.output)
    if not source_path.exists():
        print("找不到输入文件：%s" % source_path)
        return 1
    source = source_path.read_text("utf-8")
    if MARKER not in source:
        print("页面结构不符合预期（未找到主脚本标记）")
        return 1
    snippet = '<script>window.PEOAI_SERVER_HOST = %s;</script>\n' % json.dumps(host)
    if "window.PEOAI_SERVER_HOST = " in source.split(MARKER)[0]:
        print("页面已经注入过服务器地址，未做修改")
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(source.replace(MARKER, snippet + MARKER, 1))
    print("已生成 %s（后端地址：%s）" % (output_path, host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
