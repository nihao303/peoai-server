#!/usr/bin/env python3
"""把 ui/ 片段拼装成单文件控制台 static/peoai.html。

用法:
    python scripts/build_ui.py
    python scripts/build_ui.py --check   # 仅校验产物是否为最新
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
OUTPUT = ROOT / "static" / "peoai.html"

PARTS = [
    "core.js",
    "workbench.js",
    "composer.js",
    "settings.js",
    "docs.js",
    "init.js",
]


def build() -> str:
    head = (UI_DIR / "head.html").read_text("utf-8")
    tail = (UI_DIR / "tail.html").read_text("utf-8")
    body = "".join((UI_DIR / name).read_text("utf-8") for name in PARTS)
    return head + body + tail


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    html = build()
    if "--check" in argv:
        current = OUTPUT.read_text("utf-8") if OUTPUT.exists() else ""
        if current != html:
            print("static/peoai.html 与 ui/ 源文件不一致，请重新运行 scripts/build_ui.py")
            return 1
        print("static/peoai.html 已是最新")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)
    print("已生成 %s（%d 字节）" % (OUTPUT, len(html)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
