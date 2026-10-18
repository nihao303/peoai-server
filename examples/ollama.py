#!/usr/bin/env python3
"""Ollama /api/chat 协议示例（NDJSON 流）。

运行:
    export PEOAI_BASE=http://127.0.0.1:5007
    export PEOAI_KEY=pk_xxx
    python examples/ollama.py
"""
from __future__ import annotations

import json
import os

import requests

base = os.environ.get("PEOAI_BASE", "http://127.0.0.1:5007")
key = os.environ.get("PEOAI_KEY", "YOUR_API_KEY")

with requests.post(
    base + "/api/chat",
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    json={
        "model": "peo-human-mini",
        "stream": True,
        "messages": [{"role": "user", "content": "用一句话介绍你自己。"}],
    },
    stream=True,
    timeout=600,
) as resp:
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        chunk = json.loads(line)
        if chunk.get("message", {}).get("content"):
            print(chunk["message"]["content"], end="", flush=True)
        if chunk.get("done"):
            print()
            print("done_reason:", chunk.get("done_reason"))
            print("eval_count:", chunk.get("eval_count"))
