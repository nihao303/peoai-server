#!/usr/bin/env python3
"""Gemini generateContent 协议示例（直接走 REST，无需 Google SDK）。

运行:
    export PEOAI_BASE=http://127.0.0.1:5007
    export PEOAI_KEY=pk_xxx
    python examples/gemini.py
"""
from __future__ import annotations

import json
import os

import requests

base = os.environ.get("PEOAI_BASE", "http://127.0.0.1:5007")
key = os.environ.get("PEOAI_KEY", "YOUR_API_KEY")

url = base + "/v1beta/models/peo-human-1:generateContent"
resp = requests.post(
    url,
    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    json={
        "systemInstruction": {"parts": [{"text": "回答保持简短。"}]},
        "contents": [{"role": "user", "parts": [{"text": "用一句话解释 HTTP 502。"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 256},
    },
    timeout=600,
)
resp.raise_for_status()
data = resp.json()
print(json.dumps(data, ensure_ascii=False, indent=2))
print("文本：", data["candidates"][0]["content"]["parts"][0]["text"])
