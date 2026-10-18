
  /* ======================================================================
     常量与图标
     ====================================================================== */
  var BT = String.fromCharCode(96);

  /* 后端服务器地址（可选项）。
     默认留空 = 使用页面同源的 /peoai 前缀（Nginx 反代或 Flask 控制台都适用）。
     前端与后端不同源时，在页面里设置 window.PEOAI_SERVER_HOST = 'api.example.com'，
     或直接在这里填写服务器域名/IP。 */
  var SERVER_HOST = (window.PEOAI_SERVER_HOST || '').trim();

  function serverBase() {
    var protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    if (SERVER_HOST) return protocol + '//' + SERVER_HOST + '/peoai';
    return window.location.origin + '/peoai';
  }

  var ICONS = {
    logo: [
      { t: 'circle', cx: 11, cy: 8.5, r: 3.1 },
      { t: 'path', d: 'M4.8 19.4c.6-3.2 3.2-5.1 6.3-5.1 2 0 3.7.7 4.9 2' },
      { t: 'path', d: 'M18.6 4.2l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z' }
    ],
    queue: [
      { t: 'rect', x: 3.5, y: 4.5, width: 17, height: 4.4, rx: 2 },
      { t: 'rect', x: 3.5, y: 10.2, width: 17, height: 4.4, rx: 2 },
      { t: 'rect', x: 3.5, y: 15.9, width: 11, height: 4.4, rx: 2 }
    ],
    send: [
      { t: 'path', d: 'M4.2 11.6L19.6 4.8l-6.2 15.4-2.9-6.1z' },
      { t: 'path', d: 'M10.5 14.1l9.1-9.3' }
    ],
    check: [{ t: 'path', d: 'M5 12.5l4.4 4.4L19 7.6' }],
    bolt: [{ t: 'path', d: 'M13.4 3.2L6.6 13.1h4.6l-1 7.7 6.9-10.2h-4.6z' }],
    tool: [
      { t: 'path', d: 'M9.4 4.5a4 4 0 0 0 5.3 5.3l5.1 5.1-2.4 2.4-5.2-5.2a4 4 0 0 0-5.2-5.2z' },
      { t: 'path', d: 'M6.4 17.6l3-3' }
    ],
    image: [
      { t: 'rect', x: 3.5, y: 4.5, width: 17, height: 15, rx: 3 },
      { t: 'circle', cx: 9, cy: 10, r: 1.6 },
      { t: 'path', d: 'M4.5 17.6l4.6-4.6 3.6 3.6 2.5-2.5 4.1 3.5' }
    ],
    copy: [
      { t: 'rect', x: 9, y: 9, width: 10.5, height: 11, rx: 2.4 },
      { t: 'path', d: 'M15 6.4v-1a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h1.4' }
    ],
    gear: [
      { t: 'circle', cx: 12, cy: 12, r: 3.1 },
      { t: 'path', d: 'M12 3v2.2M12 18.8V21M4.6 7.4l1.9 1.1M17.5 15.5l1.9 1.1M4.6 16.6l1.9-1.1M17.5 8.5l1.9-1.1M3 12h2.2M18.8 12H21' }
    ],
    refresh: [
      { t: 'path', d: 'M20 12a8 8 0 1 1-2.6-5.9' },
      { t: 'path', d: 'M20 4.6v4.2h-4.2' }
    ],
    logout: [
      { t: 'path', d: 'M14.5 5H7.5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h7' },
      { t: 'path', d: 'M17.8 12H9.6' },
      { t: 'path', d: 'M14.8 8.8L18 12l-3.2 3.2' }
    ],
    lock: [
      { t: 'rect', x: 4.8, y: 10.6, width: 14.4, height: 9.4, rx: 2.6 },
      { t: 'path', d: 'M8.4 10.6V8a3.6 3.6 0 0 1 7.2 0v2.6' }
    ],
    eye: [
      { t: 'path', d: 'M2.6 12S6.1 6.2 12 6.2 21.4 12 21.4 12 17.9 17.8 12 17.8 2.6 12 2.6 12z' },
      { t: 'circle', cx: 12, cy: 12, r: 2.6 }
    ],
    chevron: [{ t: 'path', d: 'M9.5 6.5l5.5 5.5-5.5 5.5' }],
    x: [{ t: 'path', d: 'M6.2 6.2l11.6 11.6M17.8 6.2L6.2 17.8' }],
    plus: [{ t: 'path', d: 'M12 5.2v13.6M5.2 12h13.6' }],
    trash: [
      { t: 'path', d: 'M4.4 7h15.2M9.2 7V4.6h5.6V7' },
      { t: 'path', d: 'M6.6 7l.8 12a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9l.8-12' }
    ],
    shield: [
      { t: 'path', d: 'M12 3.4l7 3v5.3c0 4.1-3 7.4-7 8.9-4-1.5-7-4.8-7-8.9V6.4z' },
      { t: 'path', d: 'M9 12l2.1 2.1L15.2 10' }
    ],
    code: [
      { t: 'path', d: 'M8.6 8.2L4.6 12l4 3.8M15.4 8.2L19.4 12l-4 3.8' },
      { t: 'path', d: 'M13.4 5.2l-2.8 13.6' }
    ],
    clock: [
      { t: 'circle', cx: 12, cy: 12, r: 8.2 },
      { t: 'path', d: 'M12 7.4V12l3.2 2' }
    ],
    sun: [
      { t: 'circle', cx: 12, cy: 12, r: 4 },
      { t: 'path', d: 'M12 2.6v2.1M12 19.3v2.1M2.6 12h2.1M19.3 12h2.1M5.2 5.2l1.5 1.5M17.3 17.3l1.5 1.5M18.8 5.2l-1.5 1.5M6.7 17.3l-1.5 1.5' }
    ],
    moon: [{ t: 'path', d: 'M20.2 14.6A8.6 8.6 0 0 1 9.4 3.8a8.6 8.6 0 1 0 10.8 10.8z' }],
    search: [
      { t: 'circle', cx: 11, cy: 11, r: 6.4 },
      { t: 'path', d: 'M15.8 15.8L20 20' }
    ],
    terminal: [
      { t: 'rect', x: 3.4, y: 4.4, width: 17.2, height: 15.2, rx: 3 },
      { t: 'path', d: 'M7.4 9.6l3 2.4-3 2.4M13.2 15h4' }
    ],
    alert: [
      { t: 'path', d: 'M12 4.2l8.4 14.9H3.6z' },
      { t: 'path', d: 'M12 9.6v4.1M12 16.6v.6' }
    ],
    user: [
      { t: 'circle', cx: 12, cy: 8.2, r: 3.4 },
      { t: 'path', d: 'M5.2 20c.6-3.4 3.4-5.4 6.8-5.4s6.2 2 6.8 5.4' }
    ],
    key: [
      { t: 'circle', cx: 8.2, cy: 15.8, r: 3.9 },
      { t: 'path', d: 'M11 13l8.2-8.2M16.4 7.6l2.2 2.2M18.8 5.2l2.2 2.2' }
    ],
    book: [
      { t: 'path', d: 'M5 5.2h6.4a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H5z' },
      { t: 'path', d: 'M19 5.2h-3.6a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2H19z' }
    ],
    power: [
      { t: 'path', d: 'M12 3.6v8' },
      { t: 'path', d: 'M7.2 6.4a7.6 7.6 0 1 0 9.6 0' }
    ],
    layers: [
      { t: 'path', d: 'M12 3.6l8.2 4.6-8.2 4.6L3.8 8.2z' },
      { t: 'path', d: 'M3.8 12.4l8.2 4.6 8.2-4.6' }
    ],
    dot: [{ t: 'circle', cx: 12, cy: 12, r: 3.2 }]
  };

  function icon(name, size) {
    var spec = ICONS[name] || ICONS.dot;
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', size || 18);
    svg.setAttribute('height', size || 18);
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.75');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    spec.forEach(function (part) {
      var node = document.createElementNS('http://www.w3.org/2000/svg', part.t);
      Object.keys(part).forEach(function (key) {
        if (key !== 't') node.setAttribute(key, part[key]);
      });
      svg.appendChild(node);
    });
    return svg;
  }

  /* ======================================================================
     DOM 与格式化工具
     ====================================================================== */
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined) return;
        if (key === 'class') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key === 'dataset') {
          Object.keys(value).forEach(function (k) { node.dataset[k] = value[k]; });
        } else if (key.indexOf('on') === 0 && typeof value === 'function') {
          node.addEventListener(key.slice(2), value);
        } else node.setAttribute(key, value);
      });
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      if (typeof child === 'string' || typeof child === 'number') {
        node.appendChild(document.createTextNode(String(child)));
      } else {
        node.appendChild(child);
      }
    });
    return node;
  }

  function clear(node) {
    if (!node) return node;
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function text(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  function fmtBytes(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024) return value + ' B';
    var units = ['KB', 'MB', 'GB'];
    for (var i = 0; i < units.length; i += 1) {
      value /= 1024;
      if (value < 1024) return value.toFixed(1) + ' ' + units[i];
    }
    return value.toFixed(1) + ' TB';
  }

  function fmtAge(seconds) {
    var value = Math.max(0, Math.round(Number(seconds) || 0));
    if (value < 60) return value + ' 秒';
    if (value < 3600) return Math.floor(value / 60) + ' 分钟';
    if (value < 86400) return Math.floor(value / 3600) + ' 小时';
    return Math.floor(value / 86400) + ' 天';
  }

  function fmtClock(ts) {
    if (!ts) return '';
    try {
      return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
    } catch (e) {
      return '';
    }
  }

  function fmtJSON(value, indent) {
    try {
      return JSON.stringify(value, null, indent === undefined ? 2 : indent);
    } catch (e) {
      return String(value);
    }
  }

  function parseJSONSafe(value) {
    try {
      return { ok: true, value: JSON.parse(value) };
    } catch (e) {
      return { ok: false, error: e };
    }
  }

  function statusMeta(status) {
    switch (status) {
      case 'pending': return { label: '待处理', cls: 'amber' };
      case 'claimed': return { label: '进行中', cls: 'primary' };
      case 'answered': return { label: '已回答', cls: 'green' };
      case 'rejected': return { label: '已拒绝', cls: 'red' };
      case 'expired': return { label: '已超时', cls: 'red' };
      case 'cancelled': return { label: '已取消', cls: 'red' };
      default: return { label: status || '未知', cls: '' };
    }
  }

  function protocolShort(protocol) {
    if (!protocol) return 'API';
    if (protocol.indexOf('openai') === 0) return 'OpenAI';
    if (protocol.indexOf('anthropic') === 0) return 'Anthropic';
    if (protocol.indexOf('gemini') === 0) return 'Gemini';
    if (protocol.indexOf('ollama') === 0) return 'Ollama';
    return protocol;
  }

  var CAP_LABELS = {
    vision: '图片',
    tools: '工具',
    streaming: '流式',
    reasoning: '推理',
    json_mode: 'JSON',
    code: '代码',
    audio: '音频',
    embeddings: '向量'
  };

  function copyText(value) {
    var textValue = text(value);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(textValue).then(function () {
        toast('已复制到剪贴板', 'ok');
      }).catch(function () {
        fallbackCopy(textValue);
      });
    }
    fallbackCopy(textValue);
    return Promise.resolve();
  }

  function fallbackCopy(value) {
    var area = document.createElement('textarea');
    area.value = value;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
      toast('已复制到剪贴板', 'ok');
    } catch (e) {
      toast('复制失败，请手动选择文本', 'err');
    }
    document.body.removeChild(area);
  }

  function toast(message, kind) {
    var host = document.getElementById('toasts');
    if (!host) return;
    var name = kind === 'ok' ? 'check' : kind === 'err' ? 'alert' : 'shield';
    var node = el('div', { class: 'toast ' + (kind || 'info') }, [
      icon(name, 16),
      el('div', { text: message })
    ]);
    host.appendChild(node);
    window.setTimeout(function () {
      node.style.opacity = '0';
      node.style.transform = 'translateY(6px)';
      node.style.transition = 'opacity .3s ease, transform .3s ease';
    }, 3600);
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 4100);
  }

  /* ======================================================================
     全局状态
     ====================================================================== */
  var STORE = {
    base: '',
    token: '',
    operatorName: '操作员',
    version: '',
    view: 'workbench',
    tab: 'chat',
    jobs: [],
    stats: {},
    filter: 'pending',
    search: '',
    selectedId: null,
    job: null,
    draft: '',
    draftReasoning: '',
    expandedConversations: {},
    toolCalls: [],
    activeTool: null,
    config: null,
    models: [],
    createdKey: null,
    busy: false,
    connected: false,
    pollTimer: null,
    eventAbort: null,
    detailTimer: null,
    lastDetailAt: 0,
    remoteImages: false,
    theme: 'light',
    adminToken: localStorage.getItem('peoai_admin_token') || '',
    serverName: 'PeoAI',
    tagline: ''
  };

  function detectBase() {
    var saved = localStorage.getItem('peoai_base');
    if (saved) return saved.replace(/\/+$/, '');
    var path = window.location.pathname;
    // 页面本身就是 Flask 控制台（直接访问 127.0.0.1:5007 或 /static/peoai.html）
    if (path === '/' || path.indexOf('/static/') === 0) return window.location.origin;
    // 页面挂在 /peoai/ 下（Nginx 反代），同源即可
    if (path.indexOf('/peoai/') === 0) return window.location.origin + '/peoai';
    // 其余情况（前端由其他站点托管，例如 /home/peoai.html）使用配置的服务器地址或同源 /peoai
    return serverBase();
  }

  function checkHealth(base) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 2000);
    return fetch(base.replace(/\/+$/, '') + '/healthz', {
      cache: 'no-store',
      signal: controller.signal
    }).then(function (response) {
      window.clearTimeout(timer);
      return response.ok;
    }).catch(function () {
      window.clearTimeout(timer);
      return false;
    });
  }

  function refineBase() {
    if (STORE.token || localStorage.getItem('peoai_base')) return;
    var candidates = [];
    [STORE.base, window.location.origin + '/peoai', window.location.origin].forEach(function (value) {
      var base = (value || '').replace(/\/+$/, '');
      if (base && candidates.indexOf(base) < 0) candidates.push(base);
    });
    var settled = false;
    candidates.forEach(function (base) {
      checkHealth(base).then(function (ok) {
        if (!ok || settled) return;
        settled = true;
        STORE.base = base;
        var overlay = document.getElementById('loginOverlay');
        var label = document.getElementById('loginBaseText');
        if (label && overlay && overlay.classList.contains('is-open')) {
          label.textContent = base;
          label.title = base;
        }
        if (base !== candidates[0]) toast('已自动切换到可用接口：' + base, 'info');
      });
    });
  }

  function api(path, options) {
    options = options || {};
    var headers = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (STORE.token) headers.Authorization = 'Bearer ' + STORE.token;
    if (options.admin && STORE.adminToken) headers['X-Admin-Token'] = STORE.adminToken;
    var url = STORE.base.replace(/\/+$/, '') + path;
    return fetch(url, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      cache: 'no-store',
      mode: 'cors'
    }).then(function (response) {
      return response.text().then(function (raw) {
        var data = null;
        if (raw) {
          try { data = JSON.parse(raw); } catch (e) { data = null; }
        }
        if (!response.ok) {
          var message = 'HTTP ' + response.status;
          if (data && data.error && data.error.message) message = data.error.message;
          else if (data && data.message) message = data.message;
          var error = new Error(message);
          error.status = response.status;
          error.payload = data;
          if (response.status === 401 && !options.allow401) onUnauthorized();
          throw error;
        }
        return data;
      });
    });
  }

  /* ======================================================================
     主题
     ====================================================================== */
  function applyTheme(theme) {
    STORE.theme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', STORE.theme);
    localStorage.setItem('peoai_theme', STORE.theme);
    try { localStorage.setItem('site_theme', STORE.theme); } catch (e) { /* ignore */ }
    var btn = document.getElementById('themeBtn');
    if (btn) {
      clear(btn);
      btn.appendChild(icon(STORE.theme === 'dark' ? 'sun' : 'moon', 18));
    }
  }

  function toggleTheme() {
    applyTheme(STORE.theme === 'dark' ? 'light' : 'dark');
  }

  /* ======================================================================
     登录 / 会话
     ====================================================================== */
  function showLogin(message) {
    var overlay = document.getElementById('loginOverlay');
    if (!overlay) return;
    overlay.classList.add('is-open');
    var error = document.getElementById('loginError');
    if (error) error.textContent = message || '';
    var baseLabel = document.getElementById('loginBaseText');
    if (baseLabel) {
      baseLabel.textContent = STORE.base || detectBase();
      baseLabel.title = baseLabel.textContent;
    }
    var password = document.getElementById('loginPassword');
    if (password) {
      password.value = '';
      window.setTimeout(function () { password.focus(); }, 60);
    }
  }

  function hideLogin() {
    var overlay = document.getElementById('loginOverlay');
    if (overlay) overlay.classList.remove('is-open');
  }

  function onUnauthorized() {
    STORE.token = '';
    localStorage.removeItem('peoai_token');
    setConnected(false);
    showLogin('会话已过期，请重新登录');
  }

  function setConnected(isConnected) {
    STORE.connected = !!isConnected;
    var node = document.getElementById('connStatus');
    if (!node) return;
    node.className = 'status ' + (isConnected ? 'is-live' : 'is-off');
    var label = node.querySelector('span');
    if (label) label.textContent = isConnected ? '实时连接' : '轮询模式';
  }

  function updateTopbar() {
    var stats = STORE.stats || {};
    var pill = document.getElementById('queuePill');
    if (pill) {
      pill.textContent = '待处理 ' + (stats.pending || 0) + ' · 进行中 ' + (stats.claimed || 0);
    }
  }

  /* ======================================================================
     事件流（SSE over fetch）+ 轮询兜底
     ====================================================================== */
  function connectEvents() {
    if (!STORE.token) return;
    if (STORE.eventAbort) {
      try { STORE.eventAbort.abort(); } catch (e) { /* ignore */ }
    }
    var controller = new AbortController();
    STORE.eventAbort = controller;
    var url = STORE.base.replace(/\/+$/, '') + '/api/events';
    fetch(url, {
      headers: { Authorization: 'Bearer ' + STORE.token, Accept: 'text/event-stream' },
      signal: controller.signal,
      cache: 'no-store'
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      if (!response.body || !response.body.getReader) {
        startPolling();
        return null;
      }
      var reader = response.body.getReader();
      var decoder = new TextDecoder('utf-8');
      var buffer = '';
      setConnected(true);
      stopPolling();
      function pump() {
        return reader.read().then(function (result) {
          if (result.done) throw new Error('closed');
          buffer += decoder.decode(result.value, { stream: true });
          var blocks = buffer.split('\n\n');
          buffer = blocks.pop();
          blocks.forEach(handleEventBlock);
          setConnected(true);
          return pump();
        });
      }
      return pump();
    }).catch(function (error) {
      if (controller.signal.aborted) return;
      setConnected(false);
      startPolling();
      window.setTimeout(function () {
        if (STORE.token) connectEvents();
      }, 6000);
    });
  }

  function handleEventBlock(block) {
    var lines = block.split('\n');
    var payload = [];
    lines.forEach(function (line) {
      if (line.indexOf('data:') === 0) payload.push(line.slice(5).trim());
    });
    if (!payload.length) return;
    var data = parseJSONSafe(payload.join('\n'));
    if (!data.ok) return;
    onServerEvent(data.value);
  }

  function onServerEvent(event) {
    if (!event || !event.type) return;
    if (event.type === 'queue' || event.type === 'state') {
      STORE.jobs = event.jobs || STORE.jobs;
      STORE.stats = event.stats || STORE.stats;
      updateTopbar();
      renderQueue();
      if (STORE.selectedId) {
        var summary = findJob(STORE.selectedId);
        var currentVersion = STORE.job ? STORE.job.version : -1;
        if (!summary || summary.version !== currentVersion) scheduleDetailRefresh();
      }
      return;
    }
    if (event.type === 'delta') {
      if (event.id === STORE.selectedId) {
        STORE.liveDeltas = true;
        scheduleDetailRefresh(180);
      }
      return;
    }
    if (event.type === 'typing') {
      if (event.id === STORE.selectedId) scheduleDetailRefresh(120);
    }
  }

  function startPolling() {
    if (STORE.pollTimer) return;
    STORE.pollTimer = window.setInterval(function () {
      refreshQueue();
      if (STORE.selectedId) loadDetail(STORE.selectedId, true);
    }, 3000);
    setConnected(false);
  }

  function stopPolling() {
    if (STORE.pollTimer) {
      window.clearInterval(STORE.pollTimer);
      STORE.pollTimer = null;
    }
  }

  function scheduleDetailRefresh(delay) {
    if (STORE.detailTimer) return;
    var wait = Math.max(120, delay || 250);
    STORE.detailTimer = window.setTimeout(function () {
      STORE.detailTimer = null;
      if (STORE.selectedId) loadDetail(STORE.selectedId, true);
    }, wait);
  }

  /* ======================================================================
     数据加载
     ====================================================================== */
  function findJob(jobId) {
    for (var i = 0; i < STORE.jobs.length; i += 1) {
      if (STORE.jobs[i].id === jobId) return STORE.jobs[i];
    }
    return null;
  }

  function refreshQueue() {
    if (!STORE.token) return Promise.resolve();
    return api('/api/queue?status=all&limit=100').then(function (data) {
      STORE.jobs = data.jobs || [];
      STORE.stats = data.stats || {};
      updateTopbar();
      renderQueue();
      if (STORE.selectedId) {
        var summary = findJob(STORE.selectedId);
        if (summary && (!STORE.job || summary.version !== STORE.job.version)) {
          loadDetail(STORE.selectedId, true);
        }
      }
    }).catch(function (error) {
      if (error.status !== 401) toast('队列刷新失败：' + error.message, 'err');
    });
  }

  function loadDetail(jobId, silent) {
    if (!jobId) return Promise.resolve();
    var now = Date.now();
    if (silent && now - STORE.lastDetailAt < 250) return Promise.resolve();
    STORE.lastDetailAt = now;
    return api('/api/queue/' + encodeURIComponent(jobId)).then(function (data) {
      if (STORE.selectedId !== jobId) return;
      STORE.job = data.job;
      renderDetail();
      renderComposer();
    }).catch(function (error) {
      if (error.status === 404) {
        selectJob(null);
        toast('该请求已被清理', 'info');
      } else if (error.status !== 401 && !silent) {
        toast('读取请求失败：' + error.message, 'err');
      }
    });
  }

  function loadConfig() {
    return api('/api/config').then(function (data) {
      STORE.config = data.config || {};
      STORE.models = (data.config && data.config.models) || [];
      STORE.remoteImages = !!(STORE.config.security && STORE.config.security.allow_remote_images);
      STORE.serverName = (STORE.config.server && STORE.config.server.name) || STORE.serverName;
      if (STORE.view === 'settings') renderView();
    }).catch(function (error) {
      if (error.status !== 401) toast('读取配置失败：' + error.message, 'err');
    });
  }

  function selectJob(jobId) {
    var summary = findJob(jobId);
    if (summary && summary.conversation_id) {
      STORE.expandedConversations[summary.conversation_id] = true;
    }
    STORE.selectedId = jobId;
    STORE.job = null;
    STORE.draft = '';
    STORE.toolCalls = [];
    STORE.activeTool = null;
    STORE.tab = 'chat';
    renderQueue();
    renderDetail();
    renderComposer();
    if (jobId) loadDetail(jobId);
  }

  /* ======================================================================
     视图切换
     ====================================================================== */
  function setView(view) {
    STORE.view = view;
    var tabs = document.querySelectorAll('#viewTabs .tab');
    Array.prototype.forEach.call(tabs, function (tab) {
      tab.classList.toggle('is-active', tab.dataset.view === view);
    });
    renderView();
  }

  function renderView() {
    var root = document.getElementById('viewRoot');
    if (!root) return;
    var workbench = document.getElementById('workbench');
    var alt = document.getElementById('viewAlt');
    if (STORE.view === 'workbench') {
      if (alt) alt.parentNode.removeChild(alt);
      if (!workbench) buildWorkbench();
      else workbench.style.display = '';
      renderQueue();
      renderDetail();
      renderComposer();
      return;
    }
    if (workbench) workbench.style.display = 'none';
    if (alt) alt.parentNode.removeChild(alt);
    root.appendChild(STORE.view === 'docs' ? buildDocsView() : buildSettingsView());
  }

  function enterApp(info) {
    STORE.operatorName = (info && info.name) || '操作员';
    STORE.version = (info && info.server && info.server.version) || '';
    hideLogin();
    document.getElementById('loginOverlay').classList.remove('is-open');
    if (!document.getElementById('workbench')) buildWorkbench();
    setView('workbench');
    setConnected(false);
    connectEvents();
    refreshQueue();
    loadConfig();
    loadBootstrapInfo();
  }

  function loadBootstrapInfo() {
    return fetch(STORE.base.replace(/\/+$/, '') + '/api/operator/bootstrap')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data || !data.ok) return;
        STORE.serverName = data.name || STORE.serverName;
        STORE.tagline = data.tagline || '';
        STORE.models = data.models || STORE.models;
        if (data.version) STORE.version = data.version;
      })
      .catch(function () { /* 忽略 */ });
  }
