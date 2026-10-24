<div align="center">

# PeoAI Server

**Put a human behind any AI API**

An OpenAI / Anthropic / Gemini / Ollama compatible "human-as-a-service" bridge

[![license](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![protocols](https://img.shields.io/badge/protocols-OpenAI%20%7C%20Anthropic%20%7C%20Gemini%20%7C%20Ollama-0d84ff)](#supported-protocols)
[![dependencies](https://img.shields.io/badge/dependencies-Flask%20%2B%20Waitress-000000)](#installation)

[**English**](README.en.md) | [简体中文](README.md)

</div>

Your client thinks it is talking to a model. In reality, the request lands in a clean operator console where a real person reads the context, looks at the images, inspects the tool schemas, and writes the answer. The client receives a standards-compliant response in the protocol it already speaks.

> Built for human evaluation, labeling and expert review, agent fallbacks, demos, internal approval flows — anywhere a human judgement is required.

## Contents

- [Why](#why)
- [Features](#features)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Supported protocols](#supported-protocols)
- [Models and capabilities](#models-and-capabilities)
- [API keys and limits](#api-keys-and-limits)
- [Operator console](#operator-console)
- [Reasoning messages](#reasoning-messages)
- [Security](#security)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Open source and repository setup](#open-source-and-repository-setup)
- [FAQ](#faq)
- [Development and tests](#development-and-tests)
- [License](#license)

## Why

Many systems need a step that understands context, reads screenshots and makes a judgement, but a real model is not always the right tool:

- **Human labeling or expert review** while existing agents, IDE plugins and SDKs keep working unchanged;
- **A predictable fallback** when a model is wrong or unavailable;
- **An auditable record** of who saw what and who answered;
- **One bridge for four protocols**, so OpenAI, Anthropic, Gemini and Ollama clients all hit the same humans.

PeoAI wraps a person in a standard API: requests are queued, you answer in the console, and the client gets the response format it expects.

## Features

| Capability | Details |
| --- | --- |
| Four protocols | OpenAI Chat Completions / Completions / Responses, Anthropic Messages, Gemini generateContent, Ollama Chat |
| Streaming | OpenAI SSE, Anthropic event stream, Gemini alt=sse, Ollama NDJSON; the operator can push text while typing |
| Tool calls | Parses OpenAI / Anthropic / Gemini tool definitions, renders a schema-driven form, returns standard tool_calls |
| Multimodal | Decodes data URLs and vendor image fields, validates magic bytes and size limits, renders images with a lightbox |
| Conversation grouping | Requests are grouped by conversation; expand a group to see every request and open any one for answering |
| Reasoning messages | Send separate thinking content mapped to reasoning_content / thinking blocks / thought parts / message.thinking |
| Model registry | Custom model IDs, aliases, context/output limits, and vision / tools / streaming / reasoning / json_mode / code switches |
| Capability enforcement | A text-only model rejects images, a tool-less model rejects tools, all at request time with HTTP 400 |
| API keys | Per-key RPM limits and model allowlists; only SHA-256 digests are stored |
| Queue protection | Pending queue cap, per-key concurrency, request TTL, restart recovery, history pruning |
| Secure defaults | API key required by default, body/image limits, login lockout, no Cookie sessions, no server-side URL fetching |
| Audit log | Login, key, model and security changes are recorded without request bodies |
| Frontend | Single-file console, Miuix design language, light/dark themes, no external assets, hand-drawn inline SVG icons |

## Architecture

~~~text
                   +--------------------------------------------+
   OpenAI SDK ----> |  /v1/chat/completions                      |
   Anthropic SDK -> |  /v1/messages                              |  protocol adapters
   Gemini client -> |  /v1beta/models/{model}:generateContent    |  peoai/protocols/
   Ollama CLI ----> |  /api/chat                                 |
                   +----------------------+---------------------+
                                          | normalize messages / tools / params / images
                                          v
                   +--------------------------------------------+
                   |  JobStore request queue                    |
                   |  pending -> claimed -> answered / rejected |
                   |  persisted to data/requests/*.json         |
                   +----------------------+---------------------+
                     SSE push             |            wait for terminal state
                                          v
                   +--------------------------------------------+
                   |  Operator console (static/peoai.html)      |
                   |  conversations - requests - images - tools |
                   +--------------------------------------------+
~~~

## Quick start

### Requirements

- Python 3.9+
- Linux, macOS or Windows

### Installation

~~~bash
git clone https://github.com/nihao303/peoai-server.git
cd peoai-server

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
~~~

### Run

~~~bash
PEOAI_HOME=. ./venv/bin/python peoai_server.py --port 5007
~~~

On first start the server generates:

- an operator password;
- an admin token;
- a default API key.

They are written to `data/bootstrap.txt` (mode 0600) and printed in the log. **Change the password and delete that file after signing in.**

### Sign in

Open <http://127.0.0.1:5007/> and use the operator password from `data/bootstrap.txt`.

### First call

~~~bash
export PEOAI_BASE=http://127.0.0.1:5007
export PEOAI_KEY=pk_xxxxxxxxxxxxxxxx   # api key from data/bootstrap.txt

curl -sS "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"peo-human-1","messages":[{"role":"user","content":"Hello, human."}]}'
~~~

The request blocks (600 seconds by default). It appears in the console queue; once you answer, the client receives a regular response:

~~~json
{
  "id": "chatcmpl-5b80023bcf400f4a4c",
  "object": "chat.completion",
  "created": 1792250159,
  "model": "peo-human-1",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello, I am a real person."},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 6, "completion_tokens": 8, "total_tokens": 14}
}
~~~

More clients: `examples/` and [docs/API.md](docs/API.md).

## Supported protocols

| Protocol | Endpoint | Streaming | Tools | Images | Notes |
| --- | --- | :---: | :---: | :---: | --- |
| OpenAI Chat Completions | `POST /v1/chat/completions` | SSE | yes | yes | primary protocol |
| OpenAI Completions | `POST /v1/completions` | SSE | - | - | prompt is wrapped as a user message |
| OpenAI Responses | `POST /v1/responses` | SSE | yes | yes | core subset, see [PROTOCOLS](docs/PROTOCOLS.md) |
| OpenAI Models | `GET /v1/models` | - | - | - | includes x_peoai capability fields |
| Anthropic Messages | `POST /v1/messages` | events | yes | yes | full message_start event flow |
| Anthropic Count Tokens | `POST /v1/messages/count_tokens` | - | - | - | estimated |
| Gemini | `POST /v1beta/models/{model}:generateContent` | alt=sse | yes | yes | also streamGenerateContent |
| Ollama Chat | `POST /api/chat` | NDJSON | yes | yes | stream defaults to true, like Ollama |
| Ollama metadata | `GET /api/tags`, `/api/version`, `/api/show`, `/api/ps` | - | - | - | drop-in for Ollama tooling |

Authentication works with `Authorization: Bearer`, `x-api-key`, `x-goog-api-key` and `?key=`.

## Models and capabilities

Models are configuration, not code. Five are provided by default:

| Model ID | Role | Default capabilities |
| --- | --- | --- |
| `peo-human-1` | general flagship | vision / tools / streaming / reasoning / json_mode / code |
| `peo-human-fast` | low latency | tools / streaming |
| `peo-human-vision` | screenshots, charts, exams | vision / tools / streaming / reasoning |
| `peo-human-code` | agents and code | tools / streaming / json_mode / code |
| `peo-human-mini` | connectivity tests | streaming |

Three ways to change them:

1. Console: Settings -> Models and capabilities;
2. Edit the `models` array in `config.json` (restart required);
3. Admin API: `POST /api/admin/models` (applies immediately).

Capabilities are enforced: sending an image to a model without vision returns 400; sending `tools` to a model without tools returns 400; requesting `stream` on a non-streaming model returns 400.

Each model can also define `default_params` (temperature / top_p / max_tokens / stop). They are applied when the client omits them and are shown in the console under "Model parameters".

Unknown model names fall back to `server.default_model` when `server.allow_fallback_model` is enabled, so clients that send `gpt-4o` or other arbitrary names still work.

## API keys and limits

- Create keys in the console (Settings -> API Key) or with `POST /api/admin/keys`. You can let the server generate one or provide your own (16-128 chars, letters, digits, `.`, `_`, `-`).
- The plaintext is shown **once**. The server stores only a SHA-256 digest; if you lose it, delete the key and create another one (or use a custom value you remember).
- Each key has an RPM limit (0 = unlimited) and a model allowlist.
- `queue.max_concurrent_per_key` limits parallel requests per key.
- When `queue.max_pending` is reached the API returns 503 instead of exhausting the server.
- Command line helpers:

~~~bash
PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py add-key --name agent --rpm 60
PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py set-password
~~~

## Operator console

One HTML file ([static/peoai.html](static/peoai.html)); sources live in [ui/](ui/) and are assembled with `python scripts/build_ui.py`.

- **Conversation-grouped queue**: requests are grouped by conversation. Expand a group to list every request with status, model, turn number and preview; click a request to open its own answer window. The detail header has a switcher for other requests in the same conversation. Single-request conversations are shown inline.
- **Conversation identity**: uses the client's `user` field (OpenAI / Anthropic metadata) or the `X-PeoAI-Conversation` / `X-Conversation-Id` header when present; otherwise a fingerprint of the system prompt plus the first user message.
- **Messages**: role-aware rendering with Markdown code blocks, inline code and safe links. No untrusted HTML is injected.
- **Images**: for vision-capable models, request images are decoded and shown in a grid with size metadata and a lightbox. Remote URLs show a **Load image** button instead of loading automatically, to avoid leaking the operator's IP. Whether historical requests keep image data is controlled by `queue.persist_media` (toggle in Settings).
- **Tools**: OpenAI `function.parameters`, Anthropic `input_schema` and Gemini `functionDeclarations` are normalized into a parameter table (required, type, enum, description) plus the raw JSON Schema. A schema-driven form lets you build a tool call and include it in the answer.
- **Reasoning**: a separate thinking box with "Send reasoning fragment" streams reasoning content to clients that support it; the detail view shows the thinking text separately from the answer.
- **Streaming**: "Send answer fragment" and "Send reasoning fragment" push chunks live; "Submit" finalizes the request. Shortcuts: `Ctrl+Enter` submit, `Ctrl+Shift+Enter` send a text fragment.
- **Design**: Miuix-style surfaces, light/dark themes, inline SVG icons only (no emoji, no external fonts or icon packs).

## Reasoning messages

The operator can send thinking content separately from the answer. Mapping by protocol:

| Protocol | Non-stream | Stream |
| --- | --- | --- |
| OpenAI Chat | `message.reasoning_content` | `delta.reasoning_content` |
| Anthropic | `{"type":"thinking","thinking":"...","signature":""}` block | `thinking_delta` events |
| Gemini | `{"text":"...","thought":true}` part | same, per chunk |
| Ollama | `message.thinking` | same, per line |

Reasoning never mixes into `content`. Anthropic signatures are empty strings; clients that validate signatures must handle that themselves. OpenAI Responses does not emit reasoning items yet.

## Security

Defaults are chosen for a service that may be exposed to the internet:

- API keys are required by default and generated once at first start;
- Operator sessions use random bearer tokens stored in memory (revocable, 12-hour TTL) and **no cookies**, so there is no CSRF surface;
- Login failures are counted per IP and locked out;
- Request body, message count/length, image count and image size are all capped;
- Images are validated against a MIME allowlist and magic bytes before/after base64 decoding;
- The server never fetches external URLs, so there is no SSRF entry point;
- The frontend builds DOM nodes with `textContent` (no `innerHTML` for request data) and adds a CSP;
- Audit records contain actions and metadata only, never request bodies or keys;
- Security headers: `nosniff`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, optional HSTS.

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) for the threat model and go-live checklist.

## Deployment

### systemd + Nginx

~~~bash
sudo useradd --system --create-home --home-dir /opt/peoai_server --shell /usr/sbin/nologin peoai
sudo rsync -a ./ /opt/peoai_server/
sudo chown -R peoai:peoai /opt/peoai_server

sudo -u peoai python3 -m venv /opt/peoai_server/venv
sudo -u peoai /opt/peoai_server/venv/bin/pip install -r /opt/peoai_server/requirements.txt

sudo cp /opt/peoai_server/peoai_server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now peoai_server
sudo journalctl -u peoai_server -f

sudo nginx -t && sudo systemctl reload nginx
~~~

Use [deploy/peoai.nginx.conf](deploy/peoai.nginx.conf) for the `/peoai/` location. SSE requires `proxy_buffering off` and a generous `proxy_read_timeout`.

### Frontend on a different origin

The console requests `/peoai` on its own origin by default. If the page is served from another domain, inject the backend host:

~~~bash
python scripts/inject_server_host.py api.example.com -o /www/wwwroot/site/home/peoai.html
~~~

This adds a single `window.PEOAI_SERVER_HOST` line to the page. HTTPS pages require an HTTPS backend.

Full steps (HTTPS, ports, backups, upgrades, uninstall, troubleshooting): [docs/DEPLOY.md](docs/DEPLOY.md).

## Configuration

`config.json` sections (full field list in [config.example.json](config.example.json)):

| Section | Key fields | Purpose |
| --- | --- | --- |
| server | name / port / default_model / allow_fallback_model / console_enabled | identity and default model |
| security | require_api_key / max_body_bytes / max_images / max_image_bytes / allowed_origins / session_ttl_seconds / allow_remote_images | access control, limits, CORS |
| queue | max_pending / request_ttl_seconds / max_concurrent_per_key / supersede_same_conversation / history_limit / persist_media | queue and history; `supersede_same_conversation` auto-cancels a stale request when the same conversation sends a new one |
| models | id / label / aliases / capabilities / context_window / max_output_tokens / default_params | model registry |
| api_keys | name / prefix / hash / rpm / models | keys (digest only) |
| operator | display_name / show_client_ip | console behavior |
| logging | level / audit / max_bytes / backups | logs and audit |

Environment variables override listen settings: `PEOAI_HOME`, `PEOAI_CONFIG`, `PEOAI_DATA`, `PEOAI_HOST`, `PEOAI_PORT`, `PEOAI_THREADS`, `PEOAI_LOG_LEVEL`.

## Project layout

~~~text
peoai-server/
├── peoai_server.py                 # entry point (--host/--port/--root/--no-waitress)
├── peoai/
│   ├── app.py                      # app factory, security headers, error handling
│   ├── config.py                   # config, model registry, API keys
│   ├── store.py                    # job state machine, queue, persistence, events
│   ├── protocols/                  # OpenAI / Anthropic / Gemini / Ollama adapters
│   ├── api_v1.py                   # public protocol routes
│   ├── api_operator.py             # console API and SSE
│   ├── api_admin.py                # admin API
│   ├── auth.py                     # sessions, login lockout, key checks
│   ├── images.py                   # image decoding and validation
│   ├── ratelimit.py                # sliding-window limits
│   ├── tokens.py                   # token estimation
│   └── audit.py                    # audit log
├── ui/                             # console source fragments
├── static/peoai.html               # assembled single-file console
├── scripts/build_ui.py             # assemble / --check
├── scripts/inject_server_host.py   # inject backend host for cross-origin pages
├── scripts/peoai_admin.py          # CLI admin tool
├── tests/test_api.py               # 46 end-to-end tests
├── deploy/peoai.nginx.conf         # reverse proxy snippet
├── peoai_server.service            # systemd unit
├── examples/                       # protocol examples
└── docs/                           # API / deployment / architecture / security / protocols / GitHub setup
~~~

## Open source and repository setup

Released under the **MIT License** (see [LICENSE](LICENSE)). Details on license choice, repository About, topics, branch protection and releases are in [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md).

Repository checklist:

- **About**: `Human-in-the-loop AI API bridge: a real human answers behind OpenAI, Anthropic, Gemini and Ollama compatible endpoints. Conversation-grouped operator console, configurable models, API keys, vision, tool calls and reasoning messages.`
- **Topics**: `openai-api`, `anthropic`, `gemini`, `ollama`, `human-in-the-loop`, `llm`, `flask`, `self-hosted`, `api-bridge`, `multimodal`, `tool-calling`
- **Never commit**: `config.json`, `data/`, `*.log` or any key material (already covered by `.gitignore`).

## FAQ

**The client hangs forever.** It is waiting for a human. Check the console queue, `request_ttl_seconds` and the Nginx `proxy_read_timeout` (SSE needs buffering disabled).

**401 invalid_api_key.** Send the `pk_` key from `data/bootstrap.txt` via `Authorization: Bearer`, `x-api-key` or `x-goog-api-key`.

**Can a real model be used as fallback?** Yes. Route to PeoAI only when a human is needed; the bridge itself is just another model endpoint.

**Do multiple operators conflict?** Requests can be claimed by anyone; the last submitter finalizes. Final state is synced over SSE; per-keystroke mirroring is intentionally not done to keep traffic low.

**Are token counts accurate?** No tokenizer exists for a human. `usage` is a stable estimate (CJK characters count as one token, others as ~4 characters per token).

**Can authentication be disabled?** Yes: `security.require_api_key = false`. Only do this on an isolated network.

## Development and tests

~~~bash
python -m venv venv
./venv/bin/pip install -r requirements.txt requests
./venv/bin/python -m unittest discover -s tests -v   # 46 tests
./venv/bin/python scripts/build_ui.py --check        # verify console build
~~~

Edit files under `ui/` and rebuild; do not edit `static/peoai.html` directly.

## Maintainers and governance

Current maintainers and their areas are listed in [MAINTAINERS.md](MAINTAINERS.md). Decision making, joining/leaving the team and release cadence are in [GOVERNANCE.md](GOVERNANCE.md). Important changes need two maintainer approvals; routine fixes need one.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2025 nihao303

> Deployers are responsible for ensuring that human answers and business workflows comply with local laws, privacy rules and platform terms.
