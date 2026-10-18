#!/usr/bin/env python3
"""Anthropic Python SDK 对接示例。

安装:
    pip install anthropic

运行:
    export PEOAI_BASE=http://127.0.0.1:5007
    export PEOAI_KEY=pk_xxx
    python examples/anthropic_python.py
"""
from __future__ import annotations

import os

from anthropic import Anthropic

base = os.environ.get("PEOAI_BASE", "http://127.0.0.1:5007")
key = os.environ.get("PEOAI_KEY", "YOUR_API_KEY")

client = Anthropic(base_url=base, api_key=key)

message = client.messages.create(
    model="peo-human-1",
    max_tokens=1024,
    system="你是一个语气温和的真人客服。",
    messages=[{"role": "user", "content": "我的订单一直没发货，能帮我看看吗？"}],
)
print("[非流式]", message.content[0].text)
print("[stop_reason]", message.stop_reason)
print("[usage]", message.usage)

print("[流式] ", end="", flush=True)
with client.messages.stream(
    model="peo-human-fast",
    max_tokens=512,
    messages=[{"role": "user", "content": "用三行诗描述下雨天。"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
