
  /* ======================================================================
     设置视图
     ====================================================================== */
  function fieldRow(label, control, hint) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }),
      control,
      hint ? el('div', { class: 'desc', text: hint }) : null
    ]);
  }

  function textInput(value, attrs) {
    var options = attrs || {};
    return el('input', {
      class: 'input',
      type: options.type || 'text',
      value: value === null || value === undefined ? '' : String(value),
      placeholder: options.placeholder || '',
      spellcheck: options.spellcheck || 'false',
      autocomplete: 'off'
    });
  }

  function numberInput(value, attrs) {
    var options = attrs || {};
    return el('input', {
      class: 'input',
      type: 'number',
      value: value === null || value === undefined ? '' : String(value),
      min: options.min,
      max: options.max,
      step: options.step || '1'
    });
  }

  function switchRow(label, checked, onChange, hint) {
    var checkbox = el('input', { type: 'checkbox' });
    checkbox.checked = !!checked;
    checkbox.addEventListener('change', function () { onChange(checkbox.checked); });
    return el('div', { class: 'field' }, [
      el('label', { class: 'switch' }, [checkbox, el('i'), el('span', { text: label })]),
      hint ? el('div', { class: 'desc', text: hint }) : null
    ]);
  }

  function saveConfigPatch(patch, button) {
    if (button) button.disabled = true;
    return api('/api/admin/config', { method: 'PUT', body: patch, admin: true })
      .then(function () {
        toast('设置已保存', 'ok');
        return loadConfig();
      })
      .then(function () { renderView(); })
      .catch(function (error) {
        toast('保存失败：' + error.message, 'err');
        if (error.status === 403 || error.status === 401) {
          toast('需要管理员权限：请在「连接」卡片填写管理员令牌', 'info');
        }
      })
      .then(function () { if (button) button.disabled = false; });
  }

  function buildSettingsView() {
    var view = el('div', { class: 'view', id: 'viewAlt' });
    var inner = el('div', { class: 'view-inner' });
    inner.appendChild(el('div', { class: 'view-title' }, [
      el('h2', { text: '设置' }),
      el('p', { text: '连接、模型能力、API Key 与安全参数都在这里管理。修改即时生效，无需重启。' })
    ]));
    inner.appendChild(connectionCard());
    inner.appendChild(securityCard());
    inner.appendChild(keysCard());
    inner.appendChild(modelsCard());
    inner.appendChild(operatorCard());
    inner.appendChild(auditCard());
    view.appendChild(inner);
    return view;
  }

  function card(title, subtitle, children) {
    return el('section', { class: 'panel card-section' }, [
      el('h3', {}, [icon('gear', 16), title]),
      subtitle ? el('div', { class: 'sub', text: subtitle }) : null
    ].concat(children));
  }

  function connectionCard() {
    var baseInput = textInput(STORE.base, { placeholder: 'https://example.com/peoai' });
    var reconnect = el('button', { class: 'btn small primary', type: 'button' }, [icon('refresh', 14), '应用并重新连接']);
    reconnect.addEventListener('click', function () {
      var value = baseInput.value.trim().replace(/\/+$/, '');
      if (!value) {
        toast('请填写 API 地址', 'err');
        return;
      }
      STORE.base = value;
      localStorage.setItem('peoai_base', value);
      STORE.token = '';
      localStorage.removeItem('peoai_token');
      showLogin('地址已切换，请重新登录');
    });

    var adminInput = textInput(STORE.adminToken, { placeholder: 'adm_...（脚本/CI 使用，可选）', type: 'password' });
    adminInput.addEventListener('change', function () {
      STORE.adminToken = adminInput.value.trim();
      localStorage.setItem('peoai_admin_token', STORE.adminToken);
      toast('管理员令牌已保存在本机', 'info');
    });

    var tokenMasked = STORE.token ? STORE.token.slice(0, 8) + '••••••••' + STORE.token.slice(-4) : '未登录';
    var copyToken = el('button', { class: 'btn small ghost', type: 'button' }, [icon('copy', 14), '复制会话令牌']);
    copyToken.addEventListener('click', function () { copyText(STORE.token); });

    return card('连接', '控制台与服务的通信地址；跨域部署时请把网页域名加入白名单。', [
      el('div', { class: 'form-grid' }, [
        fieldRow('API 地址', baseInput, '默认与网页同源；独立部署时可填 http://host:5007'),
        fieldRow('管理员令牌', adminInput, '不填也可以：操作员会话默认具备管理权限')
      ]),
      el('div', { class: 'row-actions' }, [reconnect, copyToken]),
      el('div', { class: 'kv-grid', style: 'margin-top:14px' }, [
        el('dl', { class: 'kv' }, [el('dt', { text: '会话' }), el('dd', { text: tokenMasked })]),
        el('dl', { class: 'kv' }, [el('dt', { text: '服务版本' }), el('dd', { text: STORE.version || '—' })]),
        el('dl', { class: 'kv' }, [el('dt', { text: '实时通道' }), el('dd', { text: STORE.connected ? 'SSE 已连接' : '轮询模式' })])
      ])
    ]);
  }

  function securityCard() {
    var config = STORE.config || {};
    var security = config.security || {};
    var queueConfig = config.queue || {};

    var requireKey = security.require_api_key !== false;
    var allowRemote = !!security.allow_remote_images;
  var persistMedia = !!queueConfig.persist_media;
    var maxPending = numberInput(queueConfig.max_pending || 100, { min: 1, max: 5000 });
    var ttl = numberInput(queueConfig.request_ttl_seconds || 600, { min: 10, max: 86400 });
    var maxImages = numberInput(security.max_images || 4, { min: 1, max: 16 });
    var maxImageMb = numberInput(Math.round((security.max_image_bytes || 2097152) / 1048576), { min: 1, max: 16 });
    var maxBodyMb = numberInput(Math.round((security.max_body_bytes || 8388608) / 1048576), { min: 1, max: 32 });
    var maxReply = numberInput(security.max_reply_chars || 200000, { min: 256, max: 2000000 });
    var origins = textInput((security.allowed_origins || ['*']).join(','), { placeholder: '*' });

    var save = el('button', { class: 'btn primary small', type: 'button' }, [icon('check', 14), '保存安全设置']);
    save.addEventListener('click', function () {
      saveConfigPatch({
        security: {
          require_api_key: requireSwitch.checked,
          allow_remote_images: remoteSwitch.checked,
          max_images: Number(maxImages.value) || 4,
          max_image_bytes: (Number(maxImageMb.value) || 2) * 1048576,
          max_body_bytes: (Number(maxBodyMb.value) || 8) * 1048576,
          max_reply_chars: Number(maxReply.value) || 200000,
          allowed_origins: origins.value.split(',').map(function (item) { return item.trim(); }).filter(Boolean)
        },
        queue: {
          max_pending: Number(maxPending.value) || 100,
          request_ttl_seconds: Number(ttl.value) || 600,
          persist_media: persistSwitch.checked
        }
      }, save);
    });

    var requireSwitch = el('input', { type: 'checkbox' });
    requireSwitch.checked = requireKey;
    var remoteSwitch = el('input', { type: 'checkbox' });
    remoteSwitch.checked = allowRemote;
    var persistSwitch = el('input', { type: 'checkbox' });
    persistSwitch.checked = persistMedia;

    return card('安全与限额', '默认开启 API Key 校验、请求体限制与单请求图片上限。', [
      el('div', { class: 'form-grid' }, [
        el('div', { class: 'field' }, [
          el('label', { class: 'switch' }, [requireSwitch, el('i'), el('span', { text: '强制校验 API Key' })]),
          el('div', { class: 'desc', text: '关闭后任何人无需密钥即可调用，请仅在可信内网使用' })
        ]),
        el('div', { class: 'field' }, [
          el('label', { class: 'switch' }, [remoteSwitch, el('i'), el('span', { text: '自动加载远端图片' })]),
          el('div', { class: 'desc', text: '关闭时显示「加载图片」按钮，点击后才请求图片服务器' })
        ]),
        el('div', { class: 'field' }, [
          el('label', { class: 'switch' }, [persistSwitch, el('i'), el('span', { text: '持久化图片数据' })]),
          el('div', { class: 'desc', text: '开启后重启服务仍能查看历史图片；会占用更多磁盘' })
        ]),
        fieldRow('待处理队列上限', maxPending, '超过后新请求直接返回 503'),
        fieldRow('请求等待超时（秒）', ttl, '超时后客户端收到 504'),
        fieldRow('单请求图片数上限', maxImages),
        fieldRow('单张图片上限（MB）', maxImageMb),
        fieldRow('请求体上限（MB）', maxBodyMb),
        fieldRow('回复长度上限（字符）', maxReply),
        fieldRow('CORS 允许来源', origins, '逗号分隔；* 表示允许所有来源')
      ]),
      el('div', { class: 'row-actions' }, [save])
    ]);
  }

  function keysCard() {
    var config = STORE.config || {};
    var keys = config.api_keys || [];
    var list = el('div', { class: 'list-rows' });

    if (!keys.length) {
      list.appendChild(el('div', { class: 'hint', text: '还没有 API Key。创建后客户端即可调用 /v1/chat/completions。' }));
    }
    keys.forEach(function (key) {
      var enable = el('input', { type: 'checkbox' });
      enable.checked = key.enabled !== false;
      enable.addEventListener('change', function () {
        api('/api/admin/keys/' + encodeURIComponent(key.prefix) + '/toggle', {
          method: 'POST',
          body: { enabled: enable.checked },
          admin: true
        }).then(function () {
          toast('已更新密钥状态', 'ok');
          return loadConfig();
        }).then(renderView).catch(function (error) {
          toast('操作失败：' + error.message, 'err');
          enable.checked = !enable.checked;
        });
      });

      var remove = el('button', { class: 'btn small ghost', type: 'button' }, [icon('trash', 14)]);
      var armed = false;
      remove.addEventListener('click', function () {
        if (!armed) {
          armed = true;
          remove.textContent = '确认删除？';
          window.setTimeout(function () {
            armed = false;
            clear(remove);
            remove.appendChild(icon('trash', 14));
          }, 3000);
          return;
        }
        api('/api/admin/keys/' + encodeURIComponent(key.prefix), { method: 'DELETE', admin: true })
          .then(function () {
            toast('已删除密钥 ' + key.name, 'ok');
            return loadConfig();
          })
          .then(renderView)
          .catch(function (error) { toast('删除失败：' + error.message, 'err'); });
      });

      list.appendChild(el('div', { class: 'list-row' }, [
        el('div', { class: 'grow' }, [
          el('div', { class: 'title', text: key.name }),
          el('div', { class: 'meta', text: key.prefix + '… · ' + (key.rpm || 0) + ' 次/分 · 模型 ' + (key.models || ['*']).join(', ') + (key.last_used ? ' · 最近使用 ' + key.last_used : '') })
        ]),
        el('label', { class: 'switch' }, [enable, el('i'), el('span', { text: '启用' })]),
        remove
      ]));
    });

    var nameInput = textInput('', { placeholder: '例如：agent-prod' });
    var rpmInput = numberInput(60, { min: 0, max: 100000 });
    var modelsInput = textInput('*', { placeholder: '* 或 peo-human-1,peo-human-code' });
    var keyInput = textInput('', { placeholder: '留空自动生成；或输入自定义值（≥16 位）' });
    var create = el('button', { class: 'btn primary small', type: 'button' }, [icon('plus', 14), '创建 API Key']);
    var reveal = el('div', {});

    if (STORE.createdKey) {
      var created = STORE.createdKey;
      var createdCode = el('code', { text: created.key });
      var createdCopy = el('button', { class: 'btn small ghost', type: 'button' }, [icon('copy', 14), '复制 Key']);
      createdCopy.addEventListener('click', function () { copyText(created.key); });
      var dismiss = el('button', { class: 'btn small ghost', type: 'button' }, ['我已保存，关闭']);
      dismiss.addEventListener('click', function () {
        STORE.createdKey = null;
        renderView();
      });
      reveal.appendChild(el('div', { class: 'key-reveal' }, [
        el('div', { class: 'hint', text: '这是唯一一次显示明文，请立即复制保存；服务端只保存 SHA-256 摘要。' }),
        el('div', { class: 'meta', text: '名称：' + created.name + ' · 创建于 ' + created.at }),
        createdCode,
        el('div', { class: 'row-actions' }, [createdCopy, dismiss])
      ]));
    }

    create.addEventListener('click', function () {
      var name = nameInput.value.trim();
      if (!name) {
        toast('请填写密钥名称', 'err');
        return;
      }
      create.disabled = true;
      api('/api/admin/keys', {
        method: 'POST',
        admin: true,
        body: {
          name: name,
          key: keyInput.value.trim() || undefined,
          rpm: Number(rpmInput.value) || 0,
          models: modelsInput.value.split(',').map(function (item) { return item.trim(); }).filter(Boolean)
        }
      }).then(function (data) {
        STORE.createdKey = {
          name: data.name,
          key: data.key,
          rpm: data.rpm,
          models: data.models,
          at: new Date().toLocaleString()
        };
        nameInput.value = '';
        keyInput.value = '';
        toast('API Key 已创建，请立即复制保存', 'ok');
        return loadConfig();
      }).catch(function (error) {
        toast('创建失败：' + error.message, 'err');
      }).then(function () {
        create.disabled = false;
      });
    });

    return card('API Key', '支持随机生成或自定义 Key；服务端只存储 SHA-256 摘要，明文仅在创建时展示一次。', [
      el('div', { class: 'list-rows' }, [list]),
      el('div', { class: 'hint', style: 'margin-top:12px', text: '已创建 Key 的明文无法找回（服务端只存哈希）。忘记时请删除重建，或创建时自定义一个你记得的值。' }),
      el('div', { class: 'form-grid', style: 'margin-top:14px' }, [
        fieldRow('名称', nameInput),
        fieldRow('自定义 Key（可选）', keyInput, '留空随机生成；字母、数字、点、下划线、连字符，16~128 位'),
        fieldRow('每分钟请求数', rpmInput, '0 表示不限制'),
        fieldRow('可用模型', modelsInput, '逗号分隔，* 表示全部')
      ]),
      el('div', { class: 'row-actions' }, [create]),
      reveal
    ]);
  }

  function modelsCard() {
    var config = STORE.config || {};
    var models = config.models || STORE.models || [];
    var list = el('div', { class: 'list-rows' });

    models.forEach(function (model) {
      var caps = model.capabilities || {};
      var capChips = el('div', { class: 'cap-grid' });
      Object.keys(CAP_LABELS).forEach(function (name) {
        if (caps[name]) capChips.appendChild(el('span', { class: 'cap on', text: CAP_LABELS[name] }));
      });
      var edit = el('button', { class: 'btn small ghost', type: 'button' }, [icon('gear', 14), '编辑']);
      edit.addEventListener('click', function () {
        UI.editModelId = model.id;
        renderView();
      });
      list.appendChild(el('div', { class: 'list-row' }, [
        el('div', { class: 'grow' }, [
          el('div', { class: 'title', text: model.id }),
          el('div', { class: 'meta', text: (model.label || '') + ' · 上下文 ' + (model.context_window || 0) + ' · 输出 ' + (model.max_output_tokens || 0) }),
          capChips
        ]),
        el('span', { class: 'mini-badge ' + (model.enabled === false ? 'red' : 'green'), text: model.enabled === false ? '停用' : '启用' }),
        edit
      ]));
    });

    var editing = null;
    models.forEach(function (model) { if (model.id === UI.editModelId) editing = model; });

    var idInput = textInput(editing ? editing.id : 'peo-human-custom', { placeholder: '模型 ID' });
    if (editing) idInput.readOnly = true;
    var labelInput = textInput(editing ? editing.label : '', { placeholder: '显示名称' });
    var descInput = textInput(editing ? editing.description : '', { placeholder: '一句话说明' });
    var contextInput = numberInput(editing ? editing.context_window : 32000, { min: 1024, max: 4000000 });
    var outputInput = numberInput(editing ? editing.max_output_tokens : 4096, { min: 1, max: 1000000 });
    var aliasInput = textInput(editing ? (editing.aliases || []).join(',') : '', { placeholder: '别名，逗号分隔，例如 gpt-4o' });
    var defaultsInput = el('textarea', { class: 'textarea', id: 'modelDefaults', placeholder: '{"temperature": 0.7}' });
    defaultsInput.value = fmtJSON((editing && editing.default_params) || { temperature: 0.7, top_p: 1.0 }, 2);
    var enabledCheck = el('input', { type: 'checkbox' });
    enabledCheck.checked = !editing || editing.enabled !== false;

    var capInputs = {};
    var capGrid = el('div', { class: 'form-grid' });
    Object.keys(CAP_LABELS).forEach(function (name) {
      var checkbox = el('input', { type: 'checkbox' });
      checkbox.checked = !!(editing && editing.capabilities && editing.capabilities[name]);
      capInputs[name] = checkbox;
      capGrid.appendChild(el('div', { class: 'field' }, [
        el('label', { class: 'switch' }, [checkbox, el('i'), el('span', { text: CAP_LABELS[name] })]),
        el('div', { class: 'desc', text: name === 'vision' ? '开启后自动解析并展示请求中的图片' : '' })
      ]));
    });

    var save = el('button', { class: 'btn primary small', type: 'button' }, [icon('check', 14), editing ? '保存修改' : '创建模型']);
    save.addEventListener('click', function () {
      var capabilities = {};
      Object.keys(capInputs).forEach(function (name) { capabilities[name] = capInputs[name].checked; });
      var defaultsParsed = parseJSONSafe(defaultsInput.value || '{}');
      if (!defaultsParsed.ok || typeof defaultsParsed.value !== 'object' || Array.isArray(defaultsParsed.value)) {
        toast('默认参数必须是 JSON 对象', 'err');
        return;
      }
      var payload = {
        id: idInput.value.trim(),
        default_params: defaultsParsed.value,
        label: labelInput.value.trim(),
        description: descInput.value.trim(),
        enabled: enabledCheck.checked,
        aliases: aliasInput.value.split(',').map(function (item) { return item.trim(); }).filter(Boolean),
        capabilities: capabilities,
        context_window: Number(contextInput.value) || 32000,
        max_output_tokens: Number(outputInput.value) || 4096
      };
      if (!payload.id) {
        toast('请填写模型 ID', 'err');
        return;
      }
      save.disabled = true;
      api('/api/admin/models', { method: 'POST', body: payload, admin: true })
        .then(function () {
          toast('模型已保存', 'ok');
          UI.editModelId = null;
          return loadConfig();
        })
        .then(renderView)
        .catch(function (error) { toast('保存失败：' + error.message, 'err'); })
        .then(function () { save.disabled = false; });
    });

    var deleteBtn = el('button', { class: 'btn small danger', type: 'button' }, [icon('trash', 14), '删除该模型']);
    var deleteArmed = false;
    deleteBtn.addEventListener('click', function () {
      if (!editing) return;
      if (!deleteArmed) {
        deleteArmed = true;
        deleteBtn.textContent = '确认删除？';
        window.setTimeout(function () { deleteArmed = false; deleteBtn.textContent = '删除该模型'; }, 3000);
        return;
      }
      api('/api/admin/models/' + encodeURIComponent(editing.id), { method: 'DELETE', admin: true })
        .then(function () {
          toast('模型已删除', 'ok');
          UI.editModelId = null;
          return loadConfig();
        })
        .then(renderView)
        .catch(function (error) { toast('删除失败：' + error.message, 'err'); });
    });

    var reset = el('button', { class: 'btn small ghost', type: 'button' }, ['新建模型']);
    reset.addEventListener('click', function () {
      UI.editModelId = null;
      renderView();
    });

    return card('模型与能力', '能力开关会直接约束 API：未开启图片的模型拒绝图片输入，未开启工具的模型拒绝 tools 参数。', [
      list,
      el('div', { class: 'section-title', style: 'margin-top:18px', text: editing ? '编辑模型 ' + editing.id : '新建模型' }),
      el('div', { class: 'form-grid' }, [
        fieldRow('模型 ID', idInput),
        fieldRow('显示名称', labelInput),
        fieldRow('说明', descInput),
        fieldRow('上下文窗口', contextInput),
        fieldRow('最大输出', outputInput),
        fieldRow('别名', aliasInput),
        el('div', { class: 'field' }, [
          el('label', { text: '默认参数（JSON）' }),
          defaultsInput,
          el('div', { class: 'desc', text: '客户端未传 temperature / top_p / max_tokens / stop 时自动补齐' })
        ]),
        el('div', { class: 'field' }, [
          el('label', { class: 'switch' }, [enabledCheck, el('i'), el('span', { text: '启用该模型' })])
        ])
      ]),
      el('div', { style: 'margin-top:14px' }, [capGrid]),
      el('div', { class: 'row-actions' }, [save, reset, editing ? deleteBtn : null])
    ]);
  }

  function operatorCard() {
    var config = STORE.config || {};
    var operator = config.operator || {};
    var nameInput = textInput(operator.display_name || STORE.operatorName, { placeholder: '操作员名称' });
    var saveName = el('button', { class: 'btn small primary', type: 'button' }, [icon('check', 14), '保存名称']);
    saveName.addEventListener('click', function () {
      saveConfigPatch({ operator: { display_name: nameInput.value.trim() || '操作员' } }, saveName);
    });

    var currentInput = textInput('', { type: 'password', placeholder: '当前密码' });
    var newInput = textInput('', { type: 'password', placeholder: '新密码（至少 10 位）' });
    var changeBtn = el('button', { class: 'btn small primary', type: 'button' }, [icon('lock', 14), '修改密码']);
    changeBtn.addEventListener('click', function () {
      changeBtn.disabled = true;
      api('/api/admin/password', {
        method: 'POST',
        admin: true,
        body: { current: currentInput.value, password: newInput.value }
      }).then(function () {
        toast('密码已修改，请重新登录', 'ok');
        STORE.token = '';
        localStorage.removeItem('peoai_token');
        showLogin('密码已更新，请重新登录');
      }).catch(function (error) {
        toast('修改失败：' + error.message, 'err');
      }).then(function () { changeBtn.disabled = false; });
    });

    var revoke = el('button', { class: 'btn small ghost', type: 'button' }, [icon('power', 14), '吊销所有会话']);
    revoke.addEventListener('click', function () {
      api('/api/admin/sessions/revoke', { method: 'POST', admin: true })
        .then(function (data) {
          toast('已吊销 ' + data.revoked + ' 个会话', 'ok');
          STORE.token = '';
          localStorage.removeItem('peoai_token');
          showLogin('所有会话已失效');
        })
        .catch(function (error) { toast('操作失败：' + error.message, 'err'); });
    });

    var rotate = el('button', { class: 'btn small ghost', type: 'button' }, [icon('key', 14), '轮换管理员令牌']);
    var rotateResult = el('div', {});
    rotate.addEventListener('click', function () {
      api('/api/admin/admin-token', { method: 'POST', admin: true })
        .then(function (data) {
          clear(rotateResult);
          var code = el('code', { text: data.token });
          var copy = el('button', { class: 'btn small ghost', type: 'button' }, [icon('copy', 14), '复制']);
          copy.addEventListener('click', function () { copyText(data.token); });
          rotateResult.appendChild(el('div', { class: 'key-reveal' }, [
            el('div', { class: 'hint', text: '新的管理员令牌只显示一次，请更新你的脚本/CI 配置。' }),
            code,
            el('div', { class: 'row-actions' }, [copy])
          ]));
        })
        .catch(function (error) { toast('轮换失败：' + error.message, 'err'); });
    });

    return card('操作员与凭据', '单操作员部署默认拥有管理权限；管理员令牌用于脚本与 CI 调用管理接口。', [
      el('div', { class: 'form-grid' }, [
        fieldRow('操作员名称', nameInput),
        fieldRow('当前密码', currentInput),
        fieldRow('新密码', newInput)
      ]),
      el('div', { class: 'row-actions' }, [saveName, changeBtn, revoke, rotate]),
      rotateResult
    ]);
  }

  function auditCard() {
    var listHost = el('div', { class: 'list-rows' });
    var loadBtn = el('button', { class: 'btn small ghost', type: 'button' }, [icon('refresh', 14), '加载最近记录']);
    loadBtn.addEventListener('click', function () {
      loadBtn.disabled = true;
      api('/api/admin/audit?limit=30', { admin: true }).then(function (data) {
        clear(listHost);
        if (!data.records.length) {
          listHost.appendChild(el('div', { class: 'hint', text: '暂无审计记录。' }));
        }
        data.records.forEach(function (record) {
          listHost.appendChild(el('div', { class: 'list-row' }, [
            el('span', { class: 'mini-badge ' + (record.result === 'ok' ? 'green' : 'red'), text: record.result || 'ok' }),
            el('div', { class: 'grow' }, [
              el('div', { class: 'title', text: record.action }),
              el('div', {
                class: 'meta',
                text: [record.actor, record.target, record.ip].filter(Boolean).join(' · ') + ' · ' + fmtClock(record.ts)
              })
            ])
          ]));
        });
      }).catch(function (error) {
        toast('读取审计日志失败：' + error.message, 'err');
      }).then(function () { loadBtn.disabled = false; });
    });
    return card('审计日志', '登录、密钥、模型与安全设置的变更都会记录，不写入请求正文。', [
      loadBtn,
      el('div', { style: 'margin-top:12px' }, [listHost])
    ]);
  }
