#!/usr/bin/env python3
"""Agent 工具调用闭环示例：请求 -> 收到 tool_calls -> 回填结果 -> 再请求。

运行:
    export PEOAI_BASE=http://127.0.0.1:5007
    export PEOAI_KEY=pk_xxx
    python examples/agent_tools.py
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

base = os.environ.get("PEOAI_BASE", "http://127.0.0.1:5007")
key = os.environ.get("PEOAI_KEY", "YOUR_API_KEY")
client = OpenAI(base_url=base + "/v1", api_key=key)

tools = [{
    "type": "function",
    "function": {
        "name": "search_tickets",
        "description": "在内网工单系统里按关键字检索工单",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "检索关键字"},
                "status": {"type": "string", "enum": ["open", "pending", "closed"]},
                "limit": {"type": "integer", "description": "返回条数"},
            },
            "required": ["keyword"],
        },
    },
}]


def fake_tool(args: dict) -> str:
    """真实场景里替换成你的业务调用。"""
    return json.dumps({
        "items": [
            {"id": "T-1024", "title": args.get("keyword", "") + " 相关超时告警", "status": "open"}
        ]
    }, ensure_ascii=False)


messages = [{"role": "user", "content": "最近有没有关于网关超时的工单？"}]

first = client.chat.completions.create(
    model="peo-human-code",
    messages=messages,
    tools=tools,
    tool_choice="auto",
)
message = first.choices[0].message
print("模型返回：", first.choices[0].finish_reason)

if message.tool_calls:
    messages.append({
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ],
    })
    for call in message.tool_calls:
        args = json.loads(call.function.arguments or "{}")
        print("调用工具：", call.function.name, args)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": fake_tool(args),
        })

    second = client.chat.completions.create(
        model="peo-human-code",
        messages=messages,
        tools=tools,
    )
    print("最终回答：", second.choices[0].message.content)
else:
    print("直接回答：", message.content)
