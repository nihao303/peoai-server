
  /* ======================================================================
     接入文档视图
     ====================================================================== */
  function docsBase() {
    return STORE.base || window.location.origin;
  }

  function buildDocsView() {
    var view = el('div', { class: 'view', id: 'viewAlt' });
    var inner = el('div', { class: 'view-inner' });
    inner.appendChild(el('div', { class: 'view-title' }, [
      el('h2', { text: '接入文档' }),
      el('p', { text: '同一套人类操作员，四种主流调用方式。把下面地址里的示例参数换成你的真实密钥即可。' })
    ]));
    inner.appendChild(docsBaseCard());
    inner.appendChild(docsEndpointsCard());
    inner.appendChild(docsSamplesCard());
    inner.appendChild(docsModelsCard());
    inner.appendChild(docsSecurityCard());
    view.appendChild(inner);
    return view;
  }

  function docsBaseCard() {
    var baseLine = docsBase();
    var copyBase = el('button', { class: 'btn small ghost', type: 'button' }, [icon('copy', 14), '复制地址']);
    copyBase.addEventListener('click', function () { copyText(baseLine); });
    var copyKey = el('button', { class: 'btn small ghost', type: 'button' }, [icon('key', 14), '去创建 API Key']);
    copyKey.addEventListener('click', function () { setView('settings'); });

    return card('服务地址', '把 YOUR_API_KEY 换成设置页生成的 pk_ 开头的密钥。', [
      el('pre', { class: 'code-block', text: baseLine }),
      el('div', { class: 'row-actions' }, [copyBase, copyKey])
    ]);
  }

  function docsEndpointsCard() {
    var rows = [
      ['POST', '/v1/chat/completions', 'OpenAI Chat Completions（流式 / 非流式、工具调用、图片）'],
      ['POST', '/v1/completions', 'OpenAI 旧版补全接口（自动转成对话）'],
      ['POST', '/v1/responses', 'OpenAI Responses API 核心子集'],
      ['GET', '/v1/models', '模型列表（含 x_peoai 能力字段）'],
      ['POST', '/v1/messages', 'Anthropic Messages（含 message_start 事件流）'],
      ['POST', '/v1/messages/count_tokens', 'Anthropic token 估算'],
      ['POST', '/v1beta/models/{model}:generateContent', 'Gemini generateContent'],
      ['POST', '/api/chat', 'Ollama Chat（NDJSON 流）'],
      ['GET', '/api/tags', 'Ollama 模型列表']
    ];
    var table = el('table', { class: 'data' });
    table.appendChild(el('thead', {}, [
      el('tr', {}, [
        el('th', { text: '方法' }),
        el('th', { text: '路径' }),
        el('th', { text: '说明' })
      ])
    ]));
    var tbody = el('tbody');
    rows.forEach(function (row) {
      tbody.appendChild(el('tr', {}, [
        el('td', { text: row[0] }),
        el('td', {}, [el('code', { text: row[1] })]),
        el('td', { text: row[2] })
      ]));
    });
    table.appendChild(tbody);
    return card('端点一览', '认证方式：Authorization: Bearer、x-api-key、x-goog-api-key 或 ?key=。', [
      el('div', { class: 'table-wrap' }, [table])
    ]);
  }

  function sampleCode(kind) {
    var base = docsBase();
    if (kind === 'openai-curl') {
      return [
        'curl -N ' + base + '/v1/chat/completions \\',
        '  -H "Authorization: Bearer YOUR_API_KEY" \\',
        '  -H "Content-Type: application/json" \\',
        '  -d ' + '\'{"model":"peo-human-1","stream":true,"messages":[{"role":"user","content":"你好，人类。"}]}\''
      ].join('\n');
    }
    if (kind === 'openai-python') {
      return [
        'from openai import OpenAI',
        '',
        'client = OpenAI(',
        '    base_url="' + base + '/v1",',
        '    api_key="YOUR_API_KEY",',
        ')',
        'resp = client.chat.completions.create(',
        '    model="peo-human-1",',
        '    messages=[{"role": "user", "content": "你好，人类。"}],',
        ')',
        'print(resp.choices[0].message.content)'
      ].join('\n');
    }
    if (kind === 'openai-image') {
      return [
        'python - <<PY',
        'import base64, pathlib',
        'from openai import OpenAI',
        '',
        'image = base64.b64encode(pathlib.Path("shot.png").read_bytes()).decode()',
        'client = OpenAI(base_url="' + base + '/v1", api_key="YOUR_API_KEY")',
        'resp = client.chat.completions.create(',
        '    model="peo-human-vision",',
        '    messages=[{"role": "user", "content": [',
        '        {"type": "text", "text": "这张截图里有什么问题？"},',
        '        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}},',
        '    ]}],',
        ')',
        'print(resp.choices[0].message.content)',
        'PY'
      ].join('\n');
    }
    if (kind === 'agent-tools') {
      return [
        'tools = [{',
        '  "type": "function",',
        '  "function": {',
        '    "name": "run_sql",',
        '    "description": "在只读副本上执行 SQL",',
        '    "parameters": {',
        '      "type": "object",',
        '      "properties": {',
        '        "sql": {"type": "string", "description": "要执行的查询"},',
        '        "limit": {"type": "integer", "description": "返回行数上限"}',
        '      },',
        '      "required": ["sql"]',
        '    }',
        '  }',
        '}]',
        '',
        'resp = client.chat.completions.create(',
        '    model="peo-human-code",',
        '    messages=[{"role": "user", "content": "统计昨天的订单量"}],',
        '    tools=tools, tool_choice="auto",',
        ')',
        'call = resp.choices[0].message.tool_calls[0]',
        'print(call.function.name, call.function.arguments)'
      ].join('\n');
    }
    if (kind === 'anthropic') {
      return [
        'from anthropic import Anthropic',
        '',
        'client = Anthropic(',
        '    base_url="' + base + '",',
        '    api_key="YOUR_API_KEY",',
        ')',
        'msg = client.messages.create(',
        '    model="peo-human-1",',
        '    max_tokens=1024,',
        '    messages=[{"role": "user", "content": "写一句欢迎语"}],',
        ')',
        'print(msg.content[0].text)'
      ].join('\n');
    }
    if (kind === 'gemini') {
      return [
        'curl ' + base + '/v1beta/models/peo-human-1:generateContent \\',
        '  -H "x-goog-api-key: YOUR_API_KEY" \\',
        '  -H "Content-Type: application/json" \\',
        '  -d ' + '\'{"contents":[{"role":"user","parts":[{"text":"你好"}]}],"generationConfig":{"temperature":0.4}}\''
      ].join('\n');
    }
    if (kind === 'ollama') {
      return [
        'curl ' + base + '/api/chat \\',
        '  -H "Authorization: Bearer YOUR_API_KEY" \\',
        '  -H "Content-Type: application/json" \\',
        '  -d ' + '\'{"model":"peo-human-mini","stream":false,"messages":[{"role":"user","content":"你好"}]}\''
      ].join('\n');
    }
    return '';
  }

  var DOC_SAMPLES = [
    { id: 'openai-curl', label: 'OpenAI · cURL', code: 'openai-curl' },
    { id: 'openai-python', label: 'OpenAI · Python', code: 'openai-python' },
    { id: 'openai-image', label: '多模态 · Python', code: 'openai-image' },
    { id: 'agent-tools', label: 'Agent 工具 · Python', code: 'agent-tools' },
    { id: 'anthropic', label: 'Anthropic · Python', code: 'anthropic' },
    { id: 'gemini', label: 'Gemini · cURL', code: 'gemini' },
    { id: 'ollama', label: 'Ollama · cURL', code: 'ollama' }
  ];

  function docsSamplesCard() {
    var active = UI.docsTab || 'openai-curl';
    var tabs = el('div', { class: 'docs-tabs' });
    DOC_SAMPLES.forEach(function (sample) {
      var chip = el('button', {
        class: 'chip' + (active === sample.id ? ' is-active' : ''),
        type: 'button'
      }, [sample.label]);
      chip.addEventListener('click', function () {
        UI.docsTab = sample.id;
        renderView();
      });
      tabs.appendChild(chip);
    });

    var current = DOC_SAMPLES.filter(function (sample) { return sample.id === active; })[0] || DOC_SAMPLES[0];
    var codeText = sampleCode(current.code);
    var copy = el('button', { class: 'btn small ghost copy-btn', type: 'button' }, [icon('copy', 14), '复制']);
    copy.addEventListener('click', function () { copyText(codeText); });
    var sample = el('div', { class: 'code-sample' }, [copy, el('pre', { class: 'code-block', text: codeText })]);

    return card('调用示例', '流式接口在响应结束前会周期性发送注释行保活，客户端按正常 SSE 解析即可。', [
      tabs,
      sample
    ]);
  }

  function docsModelsCard() {
    var models = (STORE.config && STORE.config.models) || STORE.models || [];
    var table = el('table', { class: 'data' });
    table.appendChild(el('thead', {}, [
      el('tr', {}, [
        el('th', { text: '模型' }),
        el('th', { text: '能力' }),
        el('th', { text: '上下文' }),
        el('th', { text: '最大输出' })
      ])
    ]));
    var tbody = el('tbody');
    models.forEach(function (model) {
      var caps = model.capabilities || {};
      var capText = Object.keys(CAP_LABELS).filter(function (name) { return caps[name]; })
        .map(function (name) { return CAP_LABELS[name]; }).join(' / ') || '—';
      tbody.appendChild(el('tr', {}, [
        el('td', {}, [el('code', { text: model.id }), el('div', { class: 'meta', text: model.label || '' })]),
        el('td', { text: capText }),
        el('td', { text: String(model.context_window || '—') }),
        el('td', { text: String(model.max_output_tokens || '—') })
      ]));
    });
    table.appendChild(tbody);
    return card('模型能力', '能力由配置决定：未开启对应能力的模型会在请求阶段直接返回 400。', [
      el('div', { class: 'table-wrap' }, [table])
    ]);
  }

  function docsSecurityCard() {
    var items = [
      '所有 API Key 只保存 SHA-256 摘要，创建时一次性返回明文。',
      '请求图片只接受白名单 MIME，并校验文件魔数；单图与单请求大小受限。',
      '远端图片默认不在浏览器加载，避免通过图片请求泄漏操作员出口 IP。',
      '操作员会话使用 Bearer 令牌，不使用 Cookie，天然免疫 CSRF；登录失败按 IP 锁定。',
      '服务端不抓取任何外部 URL，避免 SSRF；前端渲染全部走 DOM 节点，不使用 innerHTML。',
      '请求内容会落盘到 data/requests/ 便于审计，请为磁盘做好权限与备份策略。'
    ];
    return card('安全说明', '上线前请逐条确认。', [
      el('ul', { class: 'list-rows' }, items.map(function (item) {
        return el('div', { class: 'list-row' }, [
          icon('shield', 16),
          el('div', { class: 'grow' }, [el('div', { class: 'meta', text: item })])
        ]);
      }))
    ]);
  }
