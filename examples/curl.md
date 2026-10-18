# cURL 示例

先把两个环境变量换掉：

~~~bash
export PEOAI_BASE="http://127.0.0.1:5007"
export PEOAI_KEY="pk_xxxxxxxxxxxxxxxx"
~~~

## OpenAI：非流式

~~~bash
curl -sS "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "peo-human-1",
    "messages": [{"role": "user", "content": "用三句话解释什么是人类即服务。"}]
  }'
~~~

## OpenAI：流式（SSE）

~~~bash
curl -N "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "peo-human-1",
    "stream": true,
    "stream_options": {"include_usage": true},
    "messages": [{"role": "user", "content": "讲个冷笑话。"}]
  }'
~~~

## 多模态：图片走 data URL

~~~bash
IMG=$(base64 -w0 screenshot.png)
curl -sS "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \\"model\\": \\"peo-human-vision\\",
    \\"messages\\": [{\\"role\\": \\"user\\", \\"content\\": [
      {\\"type\\": \\"text\\", \\"text\\": \\"这张图里有什么问题？\\"},
      {\\"type\\": \\"image_url\\", \\"image_url\\": {\\"url\\": \\"data:image/png;base64,$IMG\\"}}
    ]}]
  }"
~~~

## 工具调用（Agent）

~~~bash
curl -sS "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "peo-human-code",
    "messages": [{"role": "user", "content": "查一下昨天北京天气"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "查询城市天气",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string", "description": "城市"},
            "unit": {"type": "string", "enum": ["c", "f"]}
          },
          "required": ["city"]
        }
      }
    }],
    "tool_choice": "auto"
  }'
~~~

## Anthropic Messages

~~~bash
curl -sS "$PEOAI_BASE/v1/messages" \
  -H "x-api-key: $PEOAI_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "peo-human-1",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "写一句欢迎语"}]
  }'
~~~

## Gemini generateContent

~~~bash
curl -sS "$PEOAI_BASE/v1beta/models/peo-human-1:generateContent" \
  -H "x-goog-api-key: $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"role": "user", "parts": [{"text": "你好"}]}],
    "generationConfig": {"temperature": 0.4}
  }'
~~~

## Ollama Chat（NDJSON）

~~~bash
curl -N "$PEOAI_BASE/api/chat" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "peo-human-mini",
    "stream": false,
    "messages": [{"role": "user", "content": "你好"}]
  }'
~~~

## 健康检查

~~~bash
curl -sS "$PEOAI_BASE/healthz"
~~~
