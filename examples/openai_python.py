#!/usr/bin/env python3
"""OpenAI Python SDK 对接示例：文本、流式与多模态。

安装:
    pip install openai

运行:
    export PEOAI_BASE=http://127.0.0.1:5007
    export PEOAI_KEY=pk_xxx
    python examples/openai_python.py
"""
from __future__ import annotations

import base64
import os
import pathlib

from openai import OpenAI

base = os.environ.get("PEOAI_BASE", "http://127.0.0.1:5007")
key = os.environ.get("PEOAI_KEY", "YOUR_API_KEY")

client = OpenAI(base_url=base + "/v1", api_key=key)

# 1) 非流式
resp = client.chat.completions.create(
    model="peo-human-1",
    messages=[{"role": "user", "content": "用一句话解释什么是「人类即服务」。"}],
)
print("[非流式]", resp.choices[0].message.content)
print("[用量]", resp.usage)

# 2) 流式
print("[流式] ", end="", flush=True)
stream = client.chat.completions.create(
    model="peo-human-fast",
    stream=True,
    messages=[{"role": "user", "content": "数到五，每个数字一行。"}],
)
for chunk in stream:
    delta = chunk.choices[0].delta.content if chunk.choices else None
    if delta:
        print(delta, end="", flush=True)
print()

# 3) 多模态（把脚本换成你的图片路径）
image_path = pathlib.Path("screenshot.png")
if image_path.exists():
    encoded = base64.b64encode(image_path.read_bytes()).decode()
    vision = client.chat.completions.create(
        model="peo-human-vision",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "这张截图里有什么需要修复的问题？"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
            ],
        }],
    )
    print("[多模态]", vision.choices[0].message.content)
else:
    print("[多模态] 跳过：当前目录没有 screenshot.png")
