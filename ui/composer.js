
  /* ======================================================================
     作答区
     ====================================================================== */
  function isTerminalStatus(status) {
    return ['answered', 'rejected', 'expired', 'cancelled'].indexOf(status) >= 0;
  }

  function renderComposer() {
    var job = STORE.job;
    var input = document.getElementById('replyInput');
    var reasoningInput = document.getElementById('reasoningInput');
    var badge = document.getElementById('composerBadge');
    var sub = document.getElementById('composerSub');
    var jobLine = document.getElementById('composerJob');
    var deltaBtn = document.getElementById('deltaBtn');
    var reasoningDeltaBtn = document.getElementById('reasoningDeltaBtn');
    var replyBtn = document.getElementById('replyBtn');
    var claimBtn = document.getElementById('claimBtn');
    var rejectBtn = document.getElementById('rejectBtn');
    var toolbox = document.getElementById('toolbox');
    var draftWrap = document.getElementById('draftWrap');
    if (!input || !badge) return;

    if (!job) {
      sub.textContent = '选择左侧请求开始';
      badge.textContent = '空闲';
      badge.className = 'pill';
      jobLine.textContent = '';
      input.disabled = true;
      input.placeholder = '先选择一个请求…';
      if (reasoningInput) {
        reasoningInput.disabled = true;
        reasoningInput.placeholder = '先选择一个请求…';
      }
      [deltaBtn, reasoningDeltaBtn, replyBtn, claimBtn, rejectBtn].forEach(function (button) {
        if (button) button.disabled = true;
      });
      if (toolbox) toolbox.style.display = 'none';
      if (draftWrap) clear(draftWrap);
      renderCallChips();
      updateCharCount();
      return;
    }

    var terminal = isTerminalStatus(job.status);
    var meta = statusMeta(job.status);
    badge.textContent = meta.label;
    badge.className = 'pill ' + meta.cls;
    sub.textContent = job.model + ' · ' + protocolShort(job.protocol);

    clear(jobLine);
    jobLine.appendChild(el('span', { class: 'mini-badge', text: job.id }));
    jobLine.appendChild(el('span', { class: 'mini-badge ' + (job.status === 'pending' ? 'amber' : 'primary'), text: meta.label }));
    if (job.typing) jobLine.appendChild(el('span', { class: 'mini-badge amber', text: '对方正在输入…' }));

    input.disabled = terminal;
    input.placeholder = terminal
      ? '该请求已经结束，选择其他请求继续。'
      : '输入要返回给客户端的内容，支持 Markdown 代码块…';
    if (reasoningInput) {
      reasoningInput.disabled = terminal;
      reasoningInput.placeholder = terminal
        ? '该请求已经结束。'
        : '思考内容（可选）：会作为 reasoning_content / thinking / thought 发给客户端';
    }

    if (deltaBtn) deltaBtn.disabled = terminal;
    if (reasoningDeltaBtn) reasoningDeltaBtn.disabled = terminal;
    if (replyBtn) replyBtn.disabled = terminal;
    if (claimBtn) claimBtn.disabled = terminal || job.status !== 'pending';
    if (rejectBtn) {
      rejectBtn.disabled = terminal;
      rejectBtn.textContent = '';
      rejectBtn.appendChild(icon('x', 15));
      rejectBtn.appendChild(document.createTextNode(UI.rejectArmed ? '确认拒绝？' : '拒绝'));
    }

    if (toolbox) {
      var hasTools = (job.tools || []).length > 0 && !terminal;
      toolbox.style.display = hasTools ? '' : 'none';
      var signature = job.id + ':' + (job.tools || []).map(function (tool) { return tool.name; }).join(',');
      if (hasTools && (UI.composerJobId !== job.id || UI.toolSignature !== signature)) {
        UI.composerJobId = job.id;
        UI.toolSignature = signature;
        UI.ageBase = Number(job.age_seconds) || 0;
        UI.ageAt = Date.now();
        buildToolbox(toolbox, job);
      }
    }

    if (draftWrap) {
      clear(draftWrap);
      if (STORE.draftReasoning) {
        draftWrap.appendChild(el('div', { class: 'draft-preview reasoning-draft' }, [
          el('div', { style: 'font-size:10.5px;font-weight:800;color:var(--violet);margin-bottom:4px', text: '已流式发送 · 思考' }),
          el('div', { text: STORE.draftReasoning })
        ]));
      }
      if (STORE.draft) {
        draftWrap.appendChild(el('div', { class: 'draft-preview' }, [
          el('div', { style: 'font-size:10.5px;font-weight:800;color:var(--green);margin-bottom:4px', text: '已流式发送 · 回答' }),
          el('div', { text: STORE.draft })
        ]));
      }
    }
    renderCallChips();
    updateCharCount();
  }

  function updateCharCount() {
    var input = document.getElementById('replyInput');
    var counter = document.getElementById('charCount');
    if (input && counter) {
      var total = (STORE.draft || '').length + (input.value || '').length;
      counter.textContent = String(total) + ' 字';
    }
    var reasoningInput = document.getElementById('reasoningInput');
    var reasoningCounter = document.getElementById('reasoningCount');
    if (reasoningInput && reasoningCounter) {
      var reasoningTotal = (STORE.draftReasoning || '').length + (reasoningInput.value || '').length;
      reasoningCounter.textContent = '思考 ' + String(reasoningTotal) + ' 字';
    }
  }

  function renderCallChips() {
    var host = document.getElementById('callChips');
    if (!host) return;
    clear(host);
    if (!STORE.toolCalls.length) return;
    var list = el('div', { class: 'call-chips' });
    list.appendChild(el('div', { class: 'hint', text: '本次回复将包含以下工具调用：' }));
    STORE.toolCalls.forEach(function (call, index) {
      var chip = el('div', { class: 'call-chip' }, [
        el('div', { class: 'call-body' }, [
          el('div', { class: 'call-name', text: call.name }),
          el('div', { class: 'call-args', text: fmtJSON(call.arguments, 0) })
        ])
      ]);
      var remove = el('button', { type: 'button', title: '移除该调用', 'aria-label': '移除该工具调用' }, [icon('trash', 14)]);
      remove.addEventListener('click', function () {
        STORE.toolCalls.splice(index, 1);
        renderCallChips();
        toast('已移除工具调用', 'info');
      });
      chip.appendChild(remove);
      list.appendChild(chip);
    });
    host.appendChild(list);
  }

  /* ======================================================================
     工具调用构建器
     ====================================================================== */
  function buildToolbox(host, job) {
    clear(host);
    host.appendChild(el('h3', {}, [icon('tool', 14), '工具调用']));
    var picker = el('div', { class: 'tool-picker' });
    (job.tools || []).forEach(function (tool) {
      var option = el('button', {
        class: 'tool-option' + (STORE.activeTool === tool.name ? ' is-active' : ''),
        type: 'button'
      }, [tool.name]);
      option.addEventListener('click', function () {
        STORE.activeTool = STORE.activeTool === tool.name ? null : tool.name;
        buildToolbox(host, job);
      });
      picker.appendChild(option);
    });
    host.appendChild(picker);

    var formHost = el('div', { class: 'tool-form', id: 'toolFormHost' });
    host.appendChild(formHost);
    if (STORE.activeTool) {
      var tool = null;
      (job.tools || []).forEach(function (item) {
        if (item.name === STORE.activeTool) tool = item;
      });
      if (tool) openToolForm(formHost, tool);
    } else {
      formHost.appendChild(el('div', { class: 'hint', text: '选择上方工具，填好参数后加入回复。' }));
    }
  }

  function openToolForm(host, tool) {
    clear(host);
    var entries = schemaEntries(tool.parameters);
    var fields = [];
    var errorLine = el('div', { class: 'form-error' });

    if (!entries.length) {
      host.appendChild(el('div', { class: 'hint', text: '该工具没有参数，可直接加入回复。' }));
    }

    entries.forEach(function (entry) {
      var field = buildField(entry);
      fields.push(field);
      host.appendChild(field.node);
    });

    host.appendChild(errorLine);

    var submit = el('button', { class: 'btn primary small', type: 'button' }, [icon('plus', 14), '加入回复']);
    submit.addEventListener('click', function () {
      errorLine.textContent = '';
      var args = {};
      var failed = false;
      fields.forEach(function (field) {
        var result = readField(field);
        if (result.error) {
          failed = true;
          field.node.classList.add('has-error');
          var errorNode = field.node.querySelector('.form-error');
          if (errorNode) errorNode.textContent = result.error;
          return;
        }
        field.node.classList.remove('has-error');
        var errorNode2 = field.node.querySelector('.form-error');
        if (errorNode2) errorNode2.textContent = '';
        if (result.skip) return;
        args[field.entry.name] = result.value;
      });
      if (failed) {
        errorLine.textContent = '请修正标红的参数';
        return;
      }
      STORE.toolCalls.push({
        id: 'call_' + Math.random().toString(36).slice(2, 10),
        name: tool.name,
        arguments: args
      });
      renderCallChips();
      toast('已加入工具调用：' + tool.name, 'ok');
    });
    host.appendChild(submit);

    var preview = el('pre', { class: 'code-block', text: '{}', style: 'margin-top:10px' });
    host.appendChild(preview);
    function refreshPreview() {
      var args = {};
      fields.forEach(function (field) {
        var result = readField(field);
        if (!result.error && !result.skip) args[field.entry.name] = result.value;
      });
      preview.textContent = fmtJSON(args, 2);
    }
    fields.forEach(function (field) {
      field.node.addEventListener('input', refreshPreview);
      field.node.addEventListener('change', refreshPreview);
    });
    refreshPreview();
  }

  function buildField(entry) {
    var prop = entry.prop || {};
    var type = typeLabel(prop);
    var wrapper = el('div', { class: 'field' });
    var controlId = 'tf_' + entry.name.replace(/[^a-zA-Z0-9_-]/g, '_');
    wrapper.appendChild(el('label', { for: controlId }, [
      el('span', { text: entry.name }),
      el('span', { class: 'type', text: type }),
      entry.required ? el('span', { class: 'req-dot', text: '*' }) : null
    ]));

    var kind = 'text';
    var node = null;

    if (prop.enum && prop.enum.length) {
      kind = 'enum';
      node = el('select', { class: 'select', id: controlId });
      node.appendChild(el('option', { value: '', text: '请选择…' }));
      prop.enum.forEach(function (value) {
        node.appendChild(el('option', { value: String(value), text: String(value) }));
      });
    } else if (prop.type === 'boolean') {
      kind = 'boolean';
      var checkbox = el('input', { type: 'checkbox', id: controlId });
      var labelText = el('span', { text: 'false' });
      checkbox.addEventListener('change', function () {
        labelText.textContent = checkbox.checked ? 'true' : 'false';
      });
      node = el('label', { class: 'switch' }, [checkbox, el('i'), labelText]);
      node._checkbox = checkbox;
    } else if (prop.type === 'number' || prop.type === 'integer') {
      kind = 'number';
      node = el('input', {
        class: 'input',
        id: controlId,
        type: 'number',
        step: prop.type === 'integer' ? '1' : 'any',
        placeholder: entry.required ? '必填' : '选填'
      });
    } else if (prop.type === 'array' || prop.type === 'object' || prop.anyOf) {
      kind = 'json';
      node = el('textarea', {
        class: 'textarea',
        id: controlId,
        placeholder: prop.type === 'array' ? '["a", "b"]' : '{"key": "value"}'
      });
    } else {
      node = el('input', {
        class: 'input',
        id: controlId,
        type: 'text',
        placeholder: entry.required ? '必填' : '选填'
      });
    }

    wrapper.appendChild(node);
    if (prop.description) wrapper.appendChild(el('div', { class: 'desc', text: prop.description }));
    if (prop.type === 'array' || prop.type === 'object') {
      wrapper.appendChild(el('div', { class: 'hint', text: '请填写合法 JSON' }));
    }
    wrapper.appendChild(el('div', { class: 'form-error' }));
    return { entry: entry, node: wrapper, kind: kind, control: node, required: entry.required };
  }

  function readField(field) {
    var entry = field.entry;
    var prop = entry.prop || {};
    if (field.kind === 'enum') {
      var value = field.control.value;
      if (!value) {
        if (entry.required) return { error: '该项为必填' };
        return { skip: true };
      }
      var matched = value;
      (prop.enum || []).forEach(function (item) {
        if (String(item) === value) matched = item;
      });
      return { value: matched };
    }
    if (field.kind === 'boolean') {
      return { value: !!(field.control._checkbox && field.control._checkbox.checked) };
    }
    if (field.kind === 'number') {
      var raw = field.control.value.trim();
      if (!raw) {
        if (entry.required) return { error: '该项为必填' };
        return { skip: true };
      }
      var number = Number(raw);
      if (!isFinite(number)) return { error: '请输入合法数字' };
      return { value: prop.type === 'integer' ? Math.trunc(number) : number };
    }
    if (field.kind === 'json') {
      var jsonText = field.control.value.trim();
      if (!jsonText) {
        if (entry.required) return { error: '该项为必填' };
        return { skip: true };
      }
      var parsed = parseJSONSafe(jsonText);
      if (!parsed.ok) return { error: 'JSON 解析失败：' + parsed.error.message };
      if (prop.type === 'array' && !Array.isArray(parsed.value)) return { error: '应为数组' };
      if (prop.type === 'object' && (Array.isArray(parsed.value) || typeof parsed.value !== 'object')) {
        return { error: '应为对象' };
      }
      return { value: parsed.value };
    }
    var textValue = field.control.value.trim();
    if (!textValue) {
      if (entry.required) return { error: '该项为必填' };
      return { skip: true };
    }
    return { value: textValue };
  }

  /* ======================================================================
     操作
     ====================================================================== */
  function setBusy(busy) {
    STORE.busy = !!busy;
    ['deltaBtn', 'reasoningDeltaBtn', 'replyBtn', 'claimBtn', 'rejectBtn'].forEach(function (id) {
      var button = document.getElementById(id);
      if (button) button.disabled = !!busy;
    });
  }

  function sendDelta(kind) {
    kind = kind === 'reasoning' ? 'reasoning' : 'text';
    var job = STORE.job;
    var input = document.getElementById(kind === 'reasoning' ? 'reasoningInput' : 'replyInput');
    if (!job || !input || STORE.busy) return;
    var value = input.value;
    if (!value.trim()) {
      toast(kind === 'reasoning' ? '先输入思考内容再发送' : '先输入内容再发送片段', 'err');
      return;
    }
    setBusy(true);
    api('/api/queue/' + encodeURIComponent(job.id) + '/delta', {
      method: 'POST',
      body: { text: value, kind: kind }
    }).then(function (data) {
      if (kind === 'reasoning') {
        STORE.draftReasoning = data.reply_reasoning || (STORE.draftReasoning + value);
      } else {
        STORE.draft = data.reply_text || (STORE.draft + value);
      }
      input.value = '';
      updateCharCount();
      toast(kind === 'reasoning' ? '思考片段已推送' : '回答片段已推送', 'ok');
      renderComposer();
      loadDetail(job.id, true);
    }).catch(function (error) {
      toast('发送失败：' + error.message, 'err');
    }).then(function () { setBusy(false); });
  }

  function sendReply() {
    var job = STORE.job;
    var input = document.getElementById('replyInput');
    var reasoningInput = document.getElementById('reasoningInput');
    if (!job || !input || STORE.busy) return;
    var full = (STORE.draft || '') + input.value;
    var reasoning = (STORE.draftReasoning || '') + (reasoningInput ? reasoningInput.value : '');
    if (!full.trim() && !reasoning.trim() && !STORE.toolCalls.length) {
      toast('内容为空：写点文字、思考内容或加入工具调用', 'err');
      return;
    }
    setBusy(true);
    api('/api/queue/' + encodeURIComponent(job.id) + '/reply', {
      method: 'POST',
      body: {
        text: full,
        reasoning: reasoning,
        tool_calls: STORE.toolCalls,
        finish_reason: STORE.toolCalls.length ? 'tool_calls' : undefined
      }
    }).then(function () {
      STORE.draft = '';
      STORE.draftReasoning = '';
      STORE.toolCalls = [];
      STORE.activeTool = null;
      input.value = '';
      if (reasoningInput) reasoningInput.value = '';
      UI.composerJobId = null;
      toast('已提交，客户端马上收到结果', 'ok');
      return refreshQueue();
    }).then(function () {
      return loadDetail(STORE.selectedId, true);
    }).catch(function (error) {
      toast('提交失败：' + error.message, 'err');
    }).then(function () {
      setBusy(false);
      renderComposer();
    });
  }

  function claimJob() {
    var job = STORE.job;
    if (!job || STORE.busy) return;
    setBusy(true);
    api('/api/queue/' + encodeURIComponent(job.id) + '/claim', { method: 'POST' })
      .then(function () {
        toast('已认领该请求', 'ok');
        return refreshQueue();
      })
      .then(function () { return loadDetail(job.id, true); })
      .catch(function (error) { toast('认领失败：' + error.message, 'err'); })
      .then(function () { setBusy(false); renderComposer(); });
  }

  function rejectJob() {
    var job = STORE.job;
    if (!job || STORE.busy) return;
    var button = document.getElementById('rejectBtn');
    if (!UI.rejectArmed) {
      UI.rejectArmed = true;
      if (button) {
        clear(button);
        button.appendChild(icon('alert', 15));
        button.appendChild(document.createTextNode('确认拒绝？'));
      }
      window.setTimeout(function () {
        UI.rejectArmed = false;
        renderComposer();
      }, 3200);
      return;
    }
    UI.rejectArmed = false;
    setBusy(true);
    api('/api/queue/' + encodeURIComponent(job.id) + '/reject', {
      method: 'POST',
      body: { reason: '操作员拒绝了该请求' }
    }).then(function () {
      toast('已拒绝，客户端会收到 503', 'ok');
      return refreshQueue();
    }).then(function () { return loadDetail(job.id, true); })
      .catch(function (error) { toast('操作失败：' + error.message, 'err'); })
      .then(function () { setBusy(false); renderComposer(); });
  }

  /* ======================================================================
     计时
     ====================================================================== */
  function startTick() {
    if (UI.tickTimer) window.clearInterval(UI.tickTimer);
    UI.tickTimer = window.setInterval(function () {
      var line = document.getElementById('elapsedLine');
      if (!line) return;
      if (!STORE.job) {
        line.textContent = '';
        return;
      }
      var base = Number(UI.ageBase) || Number(STORE.job.age_seconds) || 0;
      var since = UI.ageAt ? (Date.now() - UI.ageAt) / 1000 : 0;
      line.textContent = '等待 ' + fmtAge(base + since);
    }, 1000);
  }
