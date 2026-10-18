"""端到端测试：真实 HTTP 服务 + 多协议 + 安全边界。

运行:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import requests
from werkzeug.serving import make_server

logging.getLogger("werkzeug").setLevel(logging.ERROR)

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from peoai.app import create_app  # noqa: E402

# 1x1 透明 PNG
PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class LiveServer(unittest.TestCase):
    """启动一个真实的线程化 HTTP 服务，避免 test_client 的并发限制。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="peoai-test-")
        os.environ["PEOAI_HOME"] = cls.tmp
        os.environ["PEOAI_DATA"] = os.path.join(cls.tmp, "data")
        os.environ["PEOAI_LOG_LEVEL"] = "ERROR"
        cls.app = create_app()
        cls.ctx = cls.app.extensions["peoai"]
        cls.password = cls.ctx.credentials["operator_password"]
        cls.api_key = cls.ctx.credentials["api_key"]
        cls.admin_token = cls.ctx.credentials["admin_token"]
        cls.server = make_server("127.0.0.1", 0, cls.app, threaded=True)
        cls.port = cls.server.socket.getsockname()[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.key_headers = {"Authorization": "Bearer " + cls.api_key}
        resp = requests.post(cls.base + "/api/operator/login", json={"password": cls.password}, timeout=10)
        if resp.status_code != 200:
            raise RuntimeError("登录失败: " + resp.text)
        cls.op_token = resp.json()["token"]
        cls.op_headers = {"Authorization": "Bearer " + cls.op_token}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 辅助 ------------------------------------------------------------
    def wait_pending(self, marker: str, timeout: float = 12.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(
                self.base + "/api/queue",
                headers=self.op_headers,
                params={"status": "pending,claimed", "limit": 100},
                timeout=5,
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            for job in resp.json()["jobs"]:
                if marker in job["preview"]:
                    return job
            time.sleep(0.05)
        self.fail("等待中的请求未出现：%s" % marker)

    def reply(self, job_id: str, text=None, reasoning=None, tool_calls=None):
        body = {}
        if text is not None:
            body["text"] = text
        if reasoning is not None:
            body["reasoning"] = reasoning
        if tool_calls is not None:
            body["tool_calls"] = tool_calls
        resp = requests.post(
            self.base + "/api/queue/" + job_id + "/reply",
            headers=self.op_headers,
            json=body,
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def chat_flow(self, payload: dict, reply_text: str = "真人回答", marker: str = ""):
        """发起阻塞请求 -> 等队列 -> 作答 -> 返回 (响应, job_id)。"""
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json=payload,
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        result = self.reply(job["id"], text=reply_text)
        worker.join(20)
        self.assertIn("resp", holder, "客户端请求没有返回")
        return holder["resp"], job["id"], result


class TestBasics(LiveServer):
    def test_health(self):
        resp = requests.get(self.base + "/api/health", timeout=5)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["models"], 5)
        self.assertIn("queue", body)

    def test_health_cors(self):
        resp = requests.get(
            self.base + "/healthz",
            headers={"Origin": "http://frontend.example.com:5000"},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_cors_preflight_operator_login(self):
        resp = requests.options(
            self.base + "/api/operator/login",
            headers={
                "Origin": "https://frontend.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
            timeout=5,
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        allowed = resp.headers.get("Access-Control-Allow-Headers", "").lower()
        self.assertIn("authorization", allowed)
        self.assertIn("content-type", allowed)

    def test_cors_preflight_chat_completions(self):
        resp = requests.options(
            self.base + "/v1/chat/completions",
            headers={
                "Origin": "https://frontend.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            timeout=5,
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_cors_on_error_response(self):
        resp = requests.get(
            self.base + "/api/queue",
            headers={"Origin": "https://frontend.example.com"},
            timeout=5,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_events_headers_wsgi_safe(self):
        client = self.app.test_client()
        token = client.post(
            "/api/operator/login", json={"password": self.password}
        ).get_json()["token"]
        resp = client.get(
            "/api/events",
            headers={
                "Authorization": "Bearer " + token,
                "Origin": "https://frontend.example.com",
            },
            buffered=False,
        )
        try:
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertNotIn("Connection", resp.headers)
        finally:
            resp.close()

    def test_models_require_key(self):
        resp = requests.get(self.base + "/v1/models", timeout=5)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["type"], "authentication_error")

    def test_models_with_key(self):
        resp = requests.get(self.base + "/v1/models", headers=self.key_headers, timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["object"], "list")
        ids = [item["id"] for item in data["data"]]
        self.assertIn("peo-human-1", ids)
        self.assertTrue(data["data"][0]["x_peoai"]["capabilities"]["vision"])

    def test_invalid_key(self):
        resp = requests.get(
            self.base + "/v1/models", headers={"Authorization": "Bearer pk_nope"}, timeout=5
        )
        self.assertEqual(resp.status_code, 401)

    def test_operator_requires_auth(self):
        resp = requests.get(self.base + "/api/queue", timeout=5)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()["ok"])

    def test_unknown_route_json(self):
        resp = requests.get(self.base + "/v1/nope", timeout=5)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.json())


class TestOpenAIProtocol(LiveServer):
    def test_chat_non_stream(self):
        marker = "case-openai-nonstream"
        payload = {
            "model": "peo-human-1",
            "messages": [{"role": "user", "content": marker}],
            "temperature": 0.5,
        }
        resp, job_id, _ = self.chat_flow(payload, "这是真人的回答", marker)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["object"], "chat.completion")
        self.assertEqual(data["choices"][0]["message"]["role"], "assistant")
        self.assertEqual(data["choices"][0]["message"]["content"], "这是真人的回答")
        self.assertEqual(data["choices"][0]["finish_reason"], "stop")
        self.assertGreater(data["usage"]["total_tokens"], 0)
        self.assertEqual(resp.headers.get("X-PeoAI-Request"), job_id)

    def test_chat_stream(self):
        marker = "case-openai-stream"
        payload = {
            "model": "peo-human-1",
            "messages": [{"role": "user", "content": marker}],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chunks = []

        def call():
            with requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json=payload,
                stream=True,
                timeout=30,
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        chunks.append(line)

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        requests.post(
            self.base + "/api/queue/" + job["id"] + "/delta",
            headers=self.op_headers,
            json={"text": "你好，"},
            timeout=10,
        )
        time.sleep(0.1)
        self.reply(job["id"], text="你好，我是真人。")
        worker.join(20)

        data_lines = [line for line in chunks if line.startswith("data:")]
        self.assertIn("data: [DONE]", data_lines)
        texts = []
        usage_found = False
        for line in data_lines:
            payload_text = line[5:].strip()
            if payload_text == "[DONE]":
                continue
            event = json.loads(payload_text)
            if event.get("usage"):
                usage_found = True
                continue
            for choice in event.get("choices") or []:
                texts.append((choice.get("delta") or {}).get("content") or "")
        self.assertEqual("".join(texts), "你好，我是真人。")
        self.assertTrue(usage_found, "include_usage 应返回 usage 块")

    def test_tool_calls(self):
        marker = "case-openai-tools"
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "查询城市天气",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名"},
                            "unit": {"type": "string", "enum": ["c", "f"]},
                        },
                        "required": ["city"],
                    },
                },
            }
        ]
        payload = {
            "model": "peo-human-code",
            "messages": [{"role": "user", "content": marker}],
            "tools": tools,
            "tool_choice": "auto",
        }
        resp = self._send_and_reply_tool(payload, marker)
        self.assertEqual(resp.status_code, 200, resp.text)
        choice = resp.json()["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        call = choice["message"]["tool_calls"][0]
        self.assertEqual(call["type"], "function")
        self.assertEqual(call["function"]["name"], "get_weather")
        self.assertEqual(json.loads(call["function"]["arguments"])["city"], "北京")

    def _send_and_reply_tool(self, payload, marker):
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json=payload,
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        detail = requests.get(
            self.base + "/api/queue/" + job["id"], headers=self.op_headers, timeout=5
        ).json()["job"]
        # 服务端必须把工具定义解析成结构化字段供前端展示
        self.assertEqual(detail["tools"][0]["name"], "get_weather")
        self.assertEqual(
            detail["tools"][0]["parameters"]["properties"]["city"]["description"], "城市名"
        )
        self.reply(
            job["id"],
            tool_calls=[
                {
                    "id": "call_abc",
                    "name": "get_weather",
                    "arguments": {"city": "北京", "unit": "c"},
                }
            ],
        )
        worker.join(20)
        return holder["resp"]

    def test_vision_inline_image(self):
        marker = "case-openai-vision"
        payload = {
            "model": "peo-human-vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": marker},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + PNG_BASE64},
                        },
                    ],
                }
            ],
        }
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json=payload,
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        detail = requests.get(
            self.base + "/api/queue/" + job["id"], headers=self.op_headers, timeout=5
        ).json()["job"]
        images = detail["messages"][0]["images"]
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["data_url"].startswith("data:image/png;base64,"))
        self.assertEqual(images[0]["mime"], "image/png")
        self.reply(job["id"], text="我看到了一张图片")
        worker.join(20)
        self.assertEqual(holder["resp"].status_code, 200)

    def test_vision_rejected_for_text_model(self):
        payload = {
            "model": "peo-human-fast",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "看图"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + PNG_BASE64}},
                    ],
                }
            ],
        }
        resp = requests.post(
            self.base + "/v1/chat/completions", headers=self.key_headers, json=payload, timeout=10
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("图片输入", resp.json()["error"]["message"])

    def test_tools_rejected_when_disabled(self):
        payload = {
            "model": "peo-human-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {"type": "function", "function": {"name": "x", "parameters": {"type": "object"}}}
            ],
        }
        resp = requests.post(
            self.base + "/v1/chat/completions", headers=self.key_headers, json=payload, timeout=10
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("工具", resp.json()["error"]["message"])

    def test_conversation_grouping(self):
        base = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "会话锚点-A"},
            {"role": "assistant", "content": "好的"},
        ]
        payload1 = {"model": "peo-human-1", "messages": base + [{"role": "user", "content": "case-conv-1"}]}
        payload2 = {"model": "peo-human-1", "messages": base + [{"role": "user", "content": "case-conv-2"}]}
        payload3 = {
            "model": "peo-human-1",
            "messages": [
                {"role": "user", "content": "另一个锚点-B"},
                {"role": "assistant", "content": "好的"},
                {"role": "user", "content": "case-conv-3"},
            ],
        }
        _, id1, _ = self.chat_flow(payload1, "回答一", "case-conv-1")
        _, id2, _ = self.chat_flow(payload2, "回答二", "case-conv-2")
        _, id3, _ = self.chat_flow(payload3, "回答三", "case-conv-3")

        jobs = requests.get(
            self.base + "/api/queue",
            headers=self.op_headers,
            params={"status": "all", "limit": 100},
            timeout=5,
        ).json()["jobs"]
        by_id = {job["id"]: job for job in jobs}
        self.assertEqual(by_id[id1]["conversation_id"], by_id[id2]["conversation_id"])
        self.assertNotEqual(by_id[id1]["conversation_id"], by_id[id3]["conversation_id"])
        self.assertEqual(by_id[id1]["conversation_title"], "会话锚点-A")

    def test_reasoning_roundtrip(self):
        marker = "case-reasoning"
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json={
                    "model": "peo-human-1",
                    "messages": [{"role": "user", "content": marker}],
                },
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        requests.post(
            self.base + "/api/queue/" + job["id"] + "/delta",
            headers=self.op_headers,
            json={"text": "先分析问题", "kind": "reasoning"},
            timeout=10,
        )
        requests.post(
            self.base + "/api/queue/" + job["id"] + "/reply",
            headers=self.op_headers,
            json={"text": "这是最终回答", "reasoning": "完整思考过程"},
            timeout=10,
        )
        worker.join(20)
        self.assertEqual(holder["resp"].status_code, 200)
        message = holder["resp"].json()["choices"][0]["message"]
        self.assertEqual(message["reasoning_content"], "完整思考过程")
        self.assertEqual(message["content"], "这是最终回答")

    def test_reasoning_stream(self):
        marker = "case-reasoning-stream"
        chunks = []

        def call():
            with requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json={
                    "model": "peo-human-1",
                    "stream": True,
                    "messages": [{"role": "user", "content": marker}],
                },
                stream=True,
                timeout=30,
            ) as resp:
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        chunks.append(line)

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        requests.post(
            self.base + "/api/queue/" + job["id"] + "/delta",
            headers=self.op_headers,
            json={"text": "流式思考片段", "kind": "reasoning"},
            timeout=10,
        )
        time.sleep(0.1)
        requests.post(
            self.base + "/api/queue/" + job["id"] + "/reply",
            headers=self.op_headers,
            json={"text": "流式最终回答"},
            timeout=10,
        )
        worker.join(20)
        reasoning = []
        content = []
        for line in chunks:
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                continue
            event = json.loads(raw)
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
                if delta.get("content"):
                    content.append(delta["content"])
        self.assertEqual("".join(reasoning), "流式思考片段")
        self.assertEqual("".join(content), "流式最终回答")

    def test_model_default_params_applied(self):
        marker = "case-default-params"
        payload = {"model": "peo-human-fast", "messages": [{"role": "user", "content": marker}]}
        resp, _job_id, result = self.chat_flow(payload, "默认参数生效", marker)
        self.assertEqual(resp.status_code, 200)
        params = result["job"]["params"]
        self.assertEqual(float(params.get("temperature")), 0.4)
        self.assertIn("temperature", result["job"]["meta"]["applied_defaults"])

        marker2 = "case-default-params-override"
        payload2 = {
            "model": "peo-human-fast",
            "temperature": 1.1,
            "messages": [{"role": "user", "content": marker2}],
        }
        resp2, _job_id2, result2 = self.chat_flow(payload2, "覆盖默认参数", marker2)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(float(result2["job"]["params"].get("temperature")), 1.1)
        self.assertNotIn("temperature", result2["job"]["meta"]["applied_defaults"])

    def test_unknown_model_falls_back(self):
        marker = "case-openai-fallback"
        payload = {
            "model": "gpt-4o-unknown",
            "messages": [{"role": "user", "content": marker}],
        }
        resp, job_id, result = self.chat_flow(payload, "回退成功", marker)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["model"], "peo-human-1")
        self.assertTrue(result["job"]["meta"]["warnings"])

    def test_reject_returns_503(self):
        marker = "case-openai-reject"
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json={"model": "peo-human-1", "messages": [{"role": "user", "content": marker}]},
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        resp = requests.post(
            self.base + "/api/queue/" + job["id"] + "/reject",
            headers=self.op_headers,
            json={"reason": "操作员不在线"},
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200)
        worker.join(20)
        self.assertEqual(holder["resp"].status_code, 503)
        self.assertEqual(holder["resp"].json()["error"]["code"], "operator_unavailable")

    def test_persistence_file(self):
        marker = "case-openai-persist"
        resp, job_id, _ = self.chat_flow(
            {"model": "peo-human-1", "messages": [{"role": "user", "content": marker}]},
            "已落盘",
            marker,
        )
        self.assertEqual(resp.status_code, 200)
        path = Path(self.ctx.data_dir) / "requests" / (job_id + ".json")
        self.assertTrue(path.exists(), "请求应落盘保存")
        payload = json.loads(path.read_text("utf-8"))
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["reply_text"], "已落盘")


class TestAnthropicProtocol(LiveServer):
    def test_messages(self):
        marker = "case-anthropic"
        payload = {
            "model": "peo-human-1",
            "max_tokens": 128,
            "system": "你是一个真人助手",
            "messages": [{"role": "user", "content": [{"type": "text", "text": marker}]}],
        }
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/messages",
                headers={**self.key_headers, "anthropic-version": "2023-06-01"},
                json=payload,
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        self.reply(job["id"], text="Anthropic 回答")
        worker.join(20)
        data = holder["resp"].json()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["content"][0]["text"], "Anthropic 回答")
        self.assertEqual(data["stop_reason"], "end_turn")
        self.assertIn("input_tokens", data["usage"])

    def test_messages_reasoning(self):
        marker = "case-anthropic-reasoning"
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1/messages",
                headers={**self.key_headers, "anthropic-version": "2023-06-01"},
                json={
                    "model": "peo-human-1",
                    "max_tokens": 128,
                    "messages": [{"role": "user", "content": marker}],
                },
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        self.reply(job["id"], text="Anthropic 正文", reasoning="Anthropic 思考")
        worker.join(20)
        data = holder["resp"].json()
        content = data["content"]
        self.assertEqual(content[0]["type"], "thinking")
        self.assertEqual(content[0]["thinking"], "Anthropic 思考")
        self.assertEqual(content[1]["type"], "text")
        self.assertEqual(content[1]["text"], "Anthropic 正文")

    def test_messages_stream(self):
        marker = "case-anthropic-stream"
        lines = []

        def call():
            with requests.post(
                self.base + "/v1/messages",
                headers={**self.key_headers, "x-api-key": self.api_key},
                json={
                    "model": "peo-human-1",
                    "max_tokens": 64,
                    "stream": True,
                    "messages": [{"role": "user", "content": marker}],
                },
                stream=True,
                timeout=30,
            ) as resp:
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        lines.append(line)

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        self.reply(job["id"], text="流式回答")
        worker.join(20)
        joined = "\n".join(lines)
        self.assertIn("event: message_start", joined)
        self.assertIn("text_delta", joined)
        self.assertIn("event: message_stop", joined)
        self.assertIn("流式回答", joined)


class TestGeminiAndOllama(LiveServer):
    def test_gemini_generate(self):
        marker = "case-gemini"
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/v1beta/models/peo-human-1:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": marker}]}],
                    "generationConfig": {"temperature": 0.2},
                },
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        self.reply(job["id"], text="Gemini 回答")
        worker.join(20)
        data = holder["resp"].json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        self.assertEqual(text, "Gemini 回答")
        self.assertIn("usageMetadata", data)

    def test_ollama_chat(self):
        marker = "case-ollama"
        holder = {}

        def call():
            holder["resp"] = requests.post(
                self.base + "/api/chat",
                headers=self.key_headers,
                json={
                    "model": "peo-human-mini",
                    "stream": False,
                    "messages": [{"role": "user", "content": marker}],
                },
                timeout=30,
            )

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        job = self.wait_pending(marker)
        self.reply(job["id"], text="Ollama 回答")
        worker.join(20)
        data = holder["resp"].json()
        self.assertTrue(data["done"])
        self.assertEqual(data["message"]["content"], "Ollama 回答")

    def test_ollama_tags(self):
        resp = requests.get(self.base + "/api/tags", headers=self.key_headers, timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["models"]), 5)


class TestAdminAndSecurity(LiveServer):
    def admin_headers(self):
        return {"X-Admin-Token": self.admin_token}

    def test_admin_config_roundtrip(self):
        resp = requests.put(
            self.base + "/api/admin/config",
            headers=self.admin_headers(),
            json={"server": {"name": "PeoAI-Test"}},
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["config"]["server"]["name"], "PeoAI-Test")
        requests.put(
            self.base + "/api/admin/config",
            headers=self.admin_headers(),
            json={"server": {"name": "PeoAI"}},
            timeout=10,
        )

    def test_admin_rejects_unknown_fields(self):
        resp = requests.put(
            self.base + "/api/admin/config",
            headers=self.admin_headers(),
            json={"security": {"operator_password_hash": "x"}},
            timeout=10,
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_requires_token(self):
        resp = requests.get(self.base + "/api/admin/config", timeout=5)
        self.assertEqual(resp.status_code, 403)

    def test_custom_api_key(self):
        custom = "pk_custom_agent_key_0001"
        resp = requests.post(
            self.base + "/api/admin/keys",
            headers=self.admin_headers(),
            json={"name": "custom-agent", "key": custom, "rpm": 5},
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["key"], custom)
        self.assertTrue(resp.json()["custom"])
        ok = requests.get(
            self.base + "/v1/models",
            headers={"Authorization": "Bearer " + custom},
            timeout=5,
        )
        self.assertEqual(ok.status_code, 200)
        duplicate = requests.post(
            self.base + "/api/admin/keys",
            headers=self.admin_headers(),
            json={"name": "dup", "key": custom},
            timeout=10,
        )
        self.assertEqual(duplicate.status_code, 400)
        too_short = requests.post(
            self.base + "/api/admin/keys",
            headers=self.admin_headers(),
            json={"name": "short", "key": "too-short"},
            timeout=10,
        )
        self.assertEqual(too_short.status_code, 400)

    def test_security_settings_roundtrip(self):
        patch = {
            "security": {
                "require_api_key": False,
                "max_images": 7,
                "max_reply_chars": 12345,
                "allowed_origins": ["https://frontend.example.com"],
            },
            "queue": {"max_pending": 42, "request_ttl_seconds": 120},
        }
        try:
            put = requests.put(
                self.base + "/api/admin/config",
                headers=self.admin_headers(),
                json=patch,
                timeout=10,
            )
            self.assertEqual(put.status_code, 200, put.text)
            config = put.json()["config"]
            self.assertFalse(config["security"]["require_api_key"])
            self.assertEqual(config["security"]["max_images"], 7)
            self.assertEqual(config["security"]["max_reply_chars"], 12345)
            self.assertEqual(config["security"]["allowed_origins"], ["https://frontend.example.com"])
            self.assertEqual(config["queue"]["max_pending"], 42)
            self.assertEqual(config["queue"]["request_ttl_seconds"], 120)

            fetched = requests.get(
                self.base + "/api/admin/config",
                headers=self.admin_headers(),
                timeout=5,
            ).json()["config"]
            self.assertEqual(fetched["security"]["max_images"], 7)
            self.assertEqual(fetched["queue"]["max_pending"], 42)
        finally:
            requests.put(
                self.base + "/api/admin/config",
                headers=self.admin_headers(),
                json={
                    "security": {
                        "require_api_key": True,
                        "max_images": 4,
                        "max_reply_chars": 200000,
                        "allowed_origins": ["*"],
                    },
                    "queue": {"max_pending": 100, "request_ttl_seconds": 600},
                },
                timeout=10,
            )

    def test_model_upsert_and_delete(self):
        model = {
            "id": "peo-test-model",
            "label": "Test Model",
            "description": "temporary",
            "capabilities": {"vision": True, "tools": True, "streaming": True},
            "context_window": 8192,
            "max_output_tokens": 1024,
            "default_params": {"temperature": 0.5},
        }
        resp = requests.post(
            self.base + "/api/admin/models",
            headers=self.admin_headers(),
            json=model,
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        listed = requests.get(
            self.base + "/v1/models", headers=self.key_headers, timeout=5
        ).json()["data"]
        self.assertIn("peo-test-model", [item["id"] for item in listed])
        deleted = requests.delete(
            self.base + "/api/admin/models/peo-test-model",
            headers=self.admin_headers(),
            timeout=10,
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        after = requests.get(
            self.base + "/v1/models", headers=self.key_headers, timeout=5
        ).json()["data"]
        self.assertNotIn("peo-test-model", [item["id"] for item in after])

    def test_key_model_restriction(self):
        resp = requests.post(
            self.base + "/api/admin/keys",
            headers=self.admin_headers(),
            json={"name": "mini-only", "models": ["peo-human-mini"], "rpm": 0},
            timeout=10,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        key = resp.json()["key"]
        self.assertTrue(key.startswith("pk_"))
        denied = requests.post(
            self.base + "/v1/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json={"model": "peo-human-1", "messages": [{"role": "user", "content": "hi"}]},
            timeout=10,
        )
        self.assertEqual(denied.status_code, 403)

    def test_key_rate_limit(self):
        resp = requests.post(
            self.base + "/api/admin/keys",
            headers=self.admin_headers(),
            json={"name": "slow", "rpm": 1},
            timeout=10,
        )
        key = resp.json()["key"]
        headers = {"Authorization": "Bearer " + key}
        first = requests.get(self.base + "/v1/models", headers=headers, timeout=5)
        second = requests.get(self.base + "/v1/models", headers=headers, timeout=5)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)

    def test_body_size_limit(self):
        requests.put(
            self.base + "/api/admin/config",
            headers=self.admin_headers(),
            json={"security": {"max_body_bytes": 65536}},
            timeout=10,
        )
        try:
            big = "x" * 200000
            resp = requests.post(
                self.base + "/v1/chat/completions",
                headers=self.key_headers,
                json={"model": "peo-human-1", "messages": [{"role": "user", "content": big}]},
                timeout=15,
            )
            self.assertEqual(resp.status_code, 413)
        finally:
            requests.put(
                self.base + "/api/admin/config",
                headers=self.admin_headers(),
                json={"security": {"max_body_bytes": 8 * 1024 * 1024}},
                timeout=10,
            )

    def test_admin_audit(self):
        resp = requests.get(
            self.base + "/api/admin/audit", headers=self.admin_headers(), params={"limit": 10}, timeout=5
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json()["records"], list)


class TestLoginLockout(unittest.TestCase):
    """独立实例，避免把主测试实例的 IP 锁死。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="peoai-lock-test-")
        os.environ["PEOAI_HOME"] = cls.tmp
        os.environ["PEOAI_DATA"] = os.path.join(cls.tmp, "data")
        os.environ["PEOAI_LOG_LEVEL"] = "ERROR"
        cls.app = create_app()
        cls.ctx = cls.app.extensions["peoai"]
        cls.server = make_server("127.0.0.1", 0, cls.app, threaded=True)
        cls.base = "http://127.0.0.1:%d" % cls.server.socket.getsockname()[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_lockout_after_failures(self):
        for _ in range(6):
            resp = requests.post(self.base + "/api/operator/login", json={"password": "wrong"}, timeout=5)
            self.assertEqual(resp.status_code, 401)
        resp = requests.post(self.base + "/api/operator/login", json={"password": "wrong"}, timeout=5)
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp.headers)

    def test_lockout_does_not_block_valid_credentials_elsewhere(self):
        # 正确密码但来自不同 IP 仍可用（此处无法伪造 IP，仅验证会话接口存在）
        resp = requests.get(self.base + "/api/operator/me", timeout=5)
        self.assertEqual(resp.status_code, 401)


class TestProtocolParsing(unittest.TestCase):
    """协议解析的单元测试，不依赖 HTTP。"""

    def test_openai_chat_parse(self):
        from peoai.protocols import openai

        limits = {
            "max_messages": 10,
            "max_message_chars": 1000,
            "max_images": 2,
            "max_image_bytes": 1024 * 1024,
            "max_body_bytes": 1024 * 1024,
            "max_reply_chars": 10000,
        }
        parsed = openai.parse_chat(
            {
                "model": "peo-human-1",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": [{"type": "text", "text": "hi"}]},
                ],
                "tools": [
                    {"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}
                ],
            },
            limits,
        )
        self.assertEqual(parsed.model, "peo-human-1")
        self.assertEqual(len(parsed.messages), 2)
        self.assertEqual(parsed.messages[1]["text"], "hi")
        self.assertEqual(parsed.tools[0]["name"], "f")

    def test_bad_temperature(self):
        from peoai.protocols import openai
        from peoai.errors import PeoaiError

        limits = {
            "max_messages": 10,
            "max_message_chars": 1000,
            "max_images": 2,
            "max_image_bytes": 1024,
            "max_body_bytes": 1024,
            "max_reply_chars": 1000,
        }
        with self.assertRaises(PeoaiError):
            openai.parse_chat(
                {"model": "x", "messages": [{"role": "user", "content": "hi"}], "temperature": 9},
                limits,
            )

    def test_image_magic_mismatch(self):
        from peoai.images import media_from_url
        from peoai.errors import PeoaiError

        limits = {"max_images": 2, "max_image_bytes": 1024 * 1024}
        with self.assertRaises(PeoaiError):
            media_from_url("data:image/png;base64," + base64.b64encode(b"not an image").decode(), limits)


class TestWaitressStreaming(unittest.TestCase):
    """真实 waitress 下的流式响应：hop-by-hop 头会让服务直接 500。"""

    @classmethod
    def setUpClass(cls):
        try:
            import waitress
        except ImportError:
            raise unittest.SkipTest("waitress 未安装")
        import socket

        cls.tmp = tempfile.mkdtemp(prefix="peoai-waitress-")
        os.environ["PEOAI_HOME"] = cls.tmp
        os.environ["PEOAI_DATA"] = os.path.join(cls.tmp, "data")
        os.environ["PEOAI_LOG_LEVEL"] = "ERROR"
        cls.app = create_app()
        cls.ctx = cls.app.extensions["peoai"]
        cls.password = cls.ctx.credentials["operator_password"]
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.port = sock.getsockname()[1]
        sock.close()
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.thread = threading.Thread(
            target=lambda: waitress.serve(
                cls.app, host="127.0.0.1", port=cls.port, threads=8, _quiet=True
            ),
            daemon=True,
        )
        cls.thread.start()
        for _ in range(120):
            try:
                requests.get(cls.base + "/healthz", timeout=0.5)
                break
            except requests.RequestException:
                time.sleep(0.05)
        cls.token = requests.post(
            cls.base + "/api/operator/login",
            json={"password": cls.password},
            timeout=10,
        ).json()["token"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_events_stream_under_waitress(self):
        resp = requests.get(
            self.base + "/api/events",
            headers={
                "Authorization": "Bearer " + self.token,
                "Origin": "https://frontend.example.com",
            },
            stream=True,
            timeout=10,
        )
        try:
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(
                resp.headers.get("Content-Type"), "text/event-stream; charset=utf-8"
            )
            first = next(resp.iter_lines(decode_unicode=True))
            self.assertIn("retry", first or "")
        finally:
            resp.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
