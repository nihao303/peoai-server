
  /* ======================================================================
     初始化
     ====================================================================== */
  function paintStaticIcons() {
    var brand = document.getElementById('brandMark');
    if (brand) { clear(brand); brand.appendChild(icon('logo', 22)); }
    var loginMark = document.getElementById('loginMark');
    if (loginMark) { clear(loginMark); loginMark.appendChild(icon('logo', 26)); }
    var themeBtn = document.getElementById('themeBtn');
    if (themeBtn) { clear(themeBtn); themeBtn.appendChild(icon(STORE.theme === 'dark' ? 'sun' : 'moon', 18)); }
    var refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) { clear(refreshBtn); refreshBtn.appendChild(icon('refresh', 18)); }
    var logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) { clear(logoutBtn); logoutBtn.appendChild(icon('logout', 18)); }
    var lightboxClose = document.getElementById('lightboxClose');
    if (lightboxClose) { clear(lightboxClose); lightboxClose.appendChild(icon('x', 18)); }
  }

  function bindTopbar() {
    var tabs = document.querySelectorAll('#viewTabs .tab');
    Array.prototype.forEach.call(tabs, function (tab) {
      tab.addEventListener('click', function () { setView(tab.dataset.view); });
    });
    document.getElementById('themeBtn').addEventListener('click', toggleTheme);
    document.getElementById('refreshBtn').addEventListener('click', function () {
      refreshQueue().then(function () { toast('队列已刷新', 'info'); });
      if (STORE.selectedId) loadDetail(STORE.selectedId, true);
    });
    document.getElementById('logoutBtn').addEventListener('click', function () {
      api('/api/operator/logout', { method: 'POST' }).catch(function () { /* 忽略 */ });
      STORE.token = '';
      STORE.job = null;
      STORE.selectedId = null;
      STORE.draft = '';
      STORE.toolCalls = [];
      localStorage.removeItem('peoai_token');
      if (STORE.eventAbort) {
        try { STORE.eventAbort.abort(); } catch (e) { /* 忽略 */ }
        STORE.eventAbort = null;
      }
      stopPolling();
      setConnected(false);
      showLogin('已退出登录');
    });
  }

  function bindLogin() {
    var form = document.getElementById('loginForm');
    var errorNode = document.getElementById('loginError');
    var submit = document.getElementById('loginSubmit');
    var passwordInput = document.getElementById('loginPassword');

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var password = passwordInput.value;
      var base = (STORE.base || detectBase()).trim().replace(/\/+$/, '');
      if (!password) {
        errorNode.textContent = '请输入密码';
        return;
      }
      if (!/^https?:\/\//.test(base)) {
        errorNode.textContent = 'API 地址需要以 http:// 或 https:// 开头';
        return;
      }
      STORE.base = base;
      submit.disabled = true;
      errorNode.textContent = '';
      fetch(base + '/api/operator/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: password })
      }).then(function (response) {
        return response.text().then(function (raw) {
          var data = null;
          try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
          if (!response.ok) {
            var message = (data && data.error && data.error.message) || ('HTTP ' + response.status);
            var failure = new Error(message);
            failure.status = response.status;
            throw failure;
          }
          return data;
        });
      }).then(function (data) {
        STORE.token = data.token;
        STORE.operatorName = data.name || '操作员';
        localStorage.setItem('peoai_token', data.token);
        passwordInput.value = '';
        enterApp({ name: data.name, server: { version: STORE.version } });
        toast('欢迎回来，' + STORE.operatorName, 'ok');
      }).catch(function (error) {
        var message = (error && error.message) ? error.message : '登录失败';
        if (!error || !error.status) {
          message = '无法连接 ' + base + '：请确认该地址可访问、Nginx 已反代 /peoai/，并且服务端 CORS 允许本页来源';
        }
        errorNode.textContent = message;
      }).then(function () {
        submit.disabled = false;
      });
    });
  }

  function bindLightbox() {
    var overlay = document.getElementById('lightbox');
    document.getElementById('lightboxClose').addEventListener('click', closeLightbox);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) closeLightbox();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        if (overlay.classList.contains('is-open')) closeLightbox();
      }
    });
  }

  var booted = false;

  function boot() {
    if (booted) return;
    booted = true;
    var savedTheme = localStorage.getItem('peoai_theme') || localStorage.getItem('site_theme') || 'light';
    applyTheme(savedTheme);
    STORE.base = detectBase();
    STORE.token = localStorage.getItem('peoai_token') || '';
    paintStaticIcons();
    bindTopbar();
    bindLogin();
    bindLightbox();
    updateTopbar();
    refineBase();

    if (STORE.token) {
      api('/api/operator/me').then(function (info) {
        enterApp(info);
      }).catch(function (error) {
        if (error.status === 401) showLogin('会话已过期，请重新登录');
        else showLogin('无法连接服务：' + error.message);
      });
    } else {
      showLogin('');
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    boot();
  }
