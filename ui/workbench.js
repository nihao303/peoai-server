
  /* ======================================================================
     工作台骨架
     ====================================================================== */
  var UI = {
    detailJobId: null,
    detailTab: null,
    tickTimer: null,
    rejectArmed: false
  };

  function buildWorkbench() {
    var root = document.getElementById('viewRoot');
    var wrap = el('div', { class: 'workspace', id: 'workbench' });

    var queuePanel = el('aside', { class: 'panel queue-panel' }, [
      el('div', { class: 'panel-head' }, [
        el('div', {}, [
          el('h2', { text: '请求队列' }),
          el('p', { text: '等待真人作答的 API 调用' })
        ]),
        el('span', { class: 'pill', id: 'queueCount', text: '0' })
      ]),
      el('div', { class: 'filters', id: 'filters' }),
      el('div', { class: 'search' }, [
        icon('search', 15),
        el('input', { id: 'searchInput', type: 'search', placeholder: '搜索模型 / 内容 / 请求 ID' })
      ]),
      el('div', { class: 'queue-list', id: 'queueList' }),
      el('div', { class: 'panel-foot' }, [
        el('span', { id: 'queueFootLeft', text: '实时同步' }),
        el('span', { id: 'queueFootRight', text: '' })
      ])
    ]);

    var detailPanel = el('section', { class: 'panel detail-panel' }, [
      el('div', { class: 'detail-head', id: 'detailHead' }),
      el('div', { class: 'detail-tabs', id: 'detailTabs' }),
      el('div', { class: 'detail-body', id: 'detailBody' })
    ]);

    var composerPanel = el('aside', { class: 'panel composer-panel' }, [
      el('div', { class: 'panel-head' }, [
        el('div', {}, [
          el('h2', { text: '作答' }),
          el('p', { id: 'composerSub', text: '选择左侧请求开始' })
        ]),
        el('span', { class: 'pill', id: 'composerBadge', text: '空闲' })
      ]),
      el('div', { class: 'composer-body', id: 'composerBody' }, [
        el('div', { class: 'composer-job', id: 'composerJob' }),
        el('div', { class: 'reply-box reasoning-box' }, [
          el('textarea', {
            id: 'reasoningInput',
            placeholder: '思考内容（可选）：会作为 reasoning_content / thinking / thought 发给客户端',
            spellcheck: 'false'
          }),
          el('div', { class: 'reply-meta' }, [
            el('span', { id: 'reasoningCount', text: '思考 0 字' }),
            el('span', { text: '仅支持推理的客户端会展示' })
          ])
        ]),
        el('div', { class: 'reply-box' }, [
          el('textarea', {
            id: 'replyInput',
            placeholder: '输入要返回给客户端的内容…',
            spellcheck: 'false'
          }),
          el('div', { class: 'reply-meta' }, [
            el('span', { id: 'charCount', text: '0 字' }),
            el('span', { id: 'elapsedLine', text: '' })
          ])
        ]),
        el('div', { id: 'draftWrap' }),
        el('div', { class: 'actions' }, [
          el('button', { class: 'btn ghost', id: 'deltaBtn', type: 'button' }, [icon('bolt', 15), '发送回答片段']),
          el('button', { class: 'btn ghost', id: 'reasoningDeltaBtn', type: 'button' }, [icon('user', 15), '发送思考片段']),
          el('button', { class: 'btn primary', id: 'replyBtn', type: 'button' }, [icon('send', 15), '提交完成']),
          el('button', { class: 'btn ghost', id: 'claimBtn', type: 'button' }, [icon('user', 15), '认领']),
          el('button', { class: 'btn danger wide', id: 'rejectBtn', type: 'button' }, [icon('x', 15), '拒绝'])
        ]),
        el('div', { class: 'hint' }, [
          el('kbd', { text: 'Ctrl' }), ' + ', el('kbd', { text: 'Enter' }), ' 提交完成 · ',
          el('kbd', { text: 'Ctrl' }), ' + ', el('kbd', { text: 'Shift' }), ' + ', el('kbd', { text: 'Enter' }), ' 发送片段'
        ]),
        el('div', { id: 'callChips' }),
        el('div', { class: 'toolbox', id: 'toolbox' })
      ])
    ]);

    wrap.appendChild(queuePanel);
    wrap.appendChild(detailPanel);
    wrap.appendChild(composerPanel);
    root.appendChild(wrap);

    var searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', function () {
      STORE.search = searchInput.value;
      renderQueue();
    });
    document.getElementById('replyInput').addEventListener('input', updateCharCount);
    document.getElementById('reasoningInput').addEventListener('input', updateCharCount);
    document.getElementById('deltaBtn').addEventListener('click', function () { sendDelta('text'); });
    document.getElementById('reasoningDeltaBtn').addEventListener('click', function () { sendDelta('reasoning'); });
    document.getElementById('replyBtn').addEventListener('click', sendReply);
    document.getElementById('claimBtn').addEventListener('click', claimJob);
    document.getElementById('rejectBtn').addEventListener('click', rejectJob);
    document.getElementById('replyInput').addEventListener('keydown', function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        if (event.shiftKey) sendDelta('text');
        else sendReply();
      }
    });
    startTick();
    return wrap;
  }

  /* ======================================================================
     队列
     ====================================================================== */
  var FILTERS = [
    { id: 'pending', label: '待处理' },
    { id: 'claimed', label: '进行中' },
    { id: 'all', label: '全部' },
    { id: 'done', label: '已完成' }
  ];

  function jobMatchesFilter(job, filter) {
    if (filter === 'all') return true;
    if (filter === 'pending') return job.status === 'pending';
    if (filter === 'claimed') return job.status === 'claimed';
    if (filter === 'done') return ['answered', 'rejected', 'expired', 'cancelled'].indexOf(job.status) >= 0;
    return true;
  }

  function filterCount(filter) {
    var count = 0;
    STORE.jobs.forEach(function (job) {
      if (jobMatchesFilter(job, filter)) count += 1;
    });
    return count;
  }

  function conversationMap(jobs) {
    var map = {};
    jobs.forEach(function (job) {
      var id = job.conversation_id || ('conv_' + job.id);
      if (!map[id]) {
        map[id] = { id: id, title: job.conversation_title || job.preview || job.id, jobs: [] };
      }
      map[id].jobs.push(job);
      if (job.conversation_title) map[id].title = job.conversation_title;
    });
    Object.keys(map).forEach(function (id) {
      var group = map[id];
      group.jobs.sort(function (a, b) { return a.created_at - b.created_at; });
      group.jobs.forEach(function (job, index) { job._turn = index + 1; });
      group.latest = group.jobs[group.jobs.length - 1];
      group.total = group.jobs.length;
      group.pending = group.jobs.filter(function (job) { return job.status === 'pending'; }).length;
      group.active = group.jobs.filter(function (job) {
        return job.status === 'pending' || job.status === 'claimed';
      }).length;
      group.models = [];
      group.jobs.forEach(function (job) {
        if (group.models.indexOf(job.model) < 0) group.models.push(job.model);
      });
    });
    return map;
  }

  function conversationIsOpen(group) {
    var manual = STORE.expandedConversations[group.id];
    if (typeof manual === 'boolean') return manual;
    if (group.jobs.some(function (job) { return job.id === STORE.selectedId; })) return true;
    return group.active > 0;
  }

  function requestRow(job) {
    var meta = statusMeta(job.status);
    var row = el('button', {
      class: 'req-row' + (job.id === STORE.selectedId ? ' is-active' : ''),
      type: 'button'
    }, [
      el('div', { class: 'req-top' }, [
        el('span', { class: 'req-turn', text: '#' + (job._turn || 1) }),
        el('span', { class: 'mini-badge ' + meta.cls, text: meta.label }),
        el('span', { class: 'req-model', text: job.model }),
        el('span', { class: 'req-time', text: fmtAge(job.age_seconds) })
      ]),
      el('div', { class: 'req-preview', text: job.preview }),
      el('div', { class: 'req-meta' }, [
        el('span', { class: 'mini-badge', text: protocolShort(job.protocol) }),
        job.stream ? el('span', { class: 'mini-badge blue' }, [icon('bolt', 11), '流式']) : null,
        job.image_count ? el('span', { class: 'mini-badge violet' }, [icon('image', 11), String(job.image_count)]) : null,
        job.tool_count ? el('span', { class: 'mini-badge' }, [icon('tool', 11), String(job.tool_count)]) : null
      ])
    ]);
    row.addEventListener('click', function (event) {
      event.stopPropagation();
      selectJob(job.id);
    });
    return row;
  }

  function renderQueue() {
    var listNode = document.getElementById('queueList');
    var filtersNode = document.getElementById('filters');
    if (!listNode || !filtersNode) return;

    clear(filtersNode);
    FILTERS.forEach(function (filter) {
      var chip = el('button', {
        class: 'chip' + (STORE.filter === filter.id ? ' is-active' : ''),
        type: 'button'
      }, [filter.label, el('span', { class: 'count', text: String(filterCount(filter.id)) })]);
      chip.addEventListener('click', function () {
        STORE.filter = filter.id;
        renderQueue();
      });
      filtersNode.appendChild(chip);
    });

    var countPill = document.getElementById('queueCount');
    if (countPill) {
      var pending = (STORE.stats && STORE.stats.pending) || 0;
      countPill.textContent = String(pending) + ' 待处理';
      countPill.className = 'pill ' + (pending ? 'amber' : '');
    }
    var footRight = document.getElementById('queueFootRight');
    if (footRight) {
      footRight.textContent = '平均 ' + ((STORE.stats && STORE.stats.avg_reply_seconds) || 0) + ' 秒';
    }

    var groups = conversationMap(STORE.jobs || []);
    var needle = (STORE.search || '').toLowerCase();
    var visibleGroups = [];
    Object.keys(groups).forEach(function (id) {
      var group = groups[id];
      var visibleJobs = group.jobs.filter(function (job) {
        if (!jobMatchesFilter(job, STORE.filter)) return false;
        if (!needle) return true;
        return (
          job.id + ' ' + job.model + ' ' + job.preview + ' ' + job.protocol + ' ' +
          (job.conversation_title || '')
        ).toLowerCase().indexOf(needle) >= 0;
      });
      if (!visibleJobs.length) return;
      group.visibleJobs = visibleJobs;
      visibleGroups.push(group);
    });
    visibleGroups.sort(function (a, b) { return b.latest.created_at - a.latest.created_at; });

    clear(listNode);
    if (!visibleGroups.length) {
      listNode.appendChild(el('div', { class: 'empty' }, [
        icon('queue', 34),
        el('div', { text: needle ? '没有匹配的请求' : '这里还很安静，等待新的调用' })
      ]));
      return;
    }

    visibleGroups.forEach(function (group) {
      if (group.total <= 1) {
        var single = requestRow(group.visibleJobs[0] || group.latest);
        single.classList.add('conv-single');
        listNode.appendChild(single);
        return;
      }
      var open = conversationIsOpen(group);
      if (needle) open = true;
      var latestMeta = statusMeta(group.latest.status);
      var head = el('button', { class: 'conv-head', type: 'button' }, [
        el('span', { class: 'conv-chevron' }, [icon('chevron', 14)]),
        el('div', { class: 'conv-headtext' }, [
          el('div', { class: 'conv-title', text: group.title, title: group.title }),
          el('div', { class: 'conv-meta' }, [
            el('span', { text: group.total + ' 次请求' }),
            el('span', { text: ' · ' + group.models.join(' / ') }),
            group.pending ? el('span', { class: 'mini-badge amber', text: '待回复 ' + group.pending }) : null,
            group.active && !group.pending ? el('span', { class: 'mini-badge primary', text: '进行中' }) : null
          ])
        ]),
        el('span', { class: 'mini-badge ' + latestMeta.cls, text: latestMeta.label })
      ]);
      head.addEventListener('click', function () {
        STORE.expandedConversations[group.id] = !open;
        renderQueue();
      });

      var card = el('div', { class: 'conv' + (open ? ' is-open' : '') }, [head]);
      if (open) {
        var rows = el('div', { class: 'conv-requests' });
        group.visibleJobs.slice().sort(function (a, b) { return b.created_at - a.created_at; })
          .forEach(function (job) { rows.appendChild(requestRow(job)); });
        card.appendChild(rows);
      }
      listNode.appendChild(card);
    });
  }

  /* ======================================================================
     详情面板
     ====================================================================== */
  function renderDetail() {
    var head = document.getElementById('detailHead');
    var tabs = document.getElementById('detailTabs');
    var body = document.getElementById('detailBody');
    if (!head || !tabs || !body) return;

    if (!STORE.job) {
      UI.detailJobId = null;
      UI.detailTab = null;
      clear(head);
      clear(tabs);
      head.appendChild(el('div', { class: 'detail-title' }, [
        el('div', {}, [
          el('h2', { text: '请求详情' }),
          el('div', { class: 'detail-id', text: '从左侧队列选择一个请求' })
        ])
      ]));
      clear(body);
      body.appendChild(el('div', { class: 'empty', style: 'padding:60px 20px' }, [
        icon('layers', 46),
        el('div', { text: '对方正在等待。选择一个请求，理解上下文后作答。' })
      ]));
      return;
    }

    var job = STORE.job;
    var same = UI.detailJobId === job.id && UI.detailTab === STORE.tab;
    if (!same) {
      UI.detailJobId = job.id;
      UI.detailTab = STORE.tab;
      renderDetailHead(head, job);
      renderDetailTabs(tabs, job);
      renderDetailBody(body, job);
    } else {
      renderDetailHead(head, job);
      renderDetailTabs(tabs, job);
      updateDetailDynamic(job);
    }
  }

  function conversationSiblings(job) {
    var cid = job.conversation_id;
    var list = (STORE.jobs || []).filter(function (item) {
      return (item.conversation_id || ('conv_' + item.id)) === cid;
    });
    return list.sort(function (a, b) { return a.created_at - b.created_at; });
  }

  function renderDetailHead(head, job) {
    clear(head);
    var meta = statusMeta(job.status);
    var siblings = conversationSiblings(job);
    var turn = 0;
    siblings.forEach(function (item, index) {
      if (item.id === job.id) turn = index + 1;
    });
    var title = job.conversation_title || job.preview || job.id;
    head.appendChild(el('div', { class: 'detail-title' }, [
      el('div', { style: 'min-width:0;flex:1' }, [
        el('h2', { text: title, title: title }),
        el('div', {
          class: 'detail-id',
          text: '第 ' + (turn || 1) + ' / ' + Math.max(1, siblings.length) + ' 次请求 · ' + job.id
        })
      ]),
      el('span', { class: 'pill ' + meta.cls, id: 'detailStatus', text: meta.label })
    ]));

    var badges = el('div', { class: 'detail-badges' });
    badges.appendChild(el('span', { class: 'mini-badge' }, [icon('layers', 11), job.model]));
    badges.appendChild(el('span', { class: 'mini-badge', text: protocolShort(job.protocol) }));
    if (job.stream) badges.appendChild(el('span', { class: 'mini-badge blue' }, [icon('bolt', 11), '流式']));
    if (job.image_count) badges.appendChild(el('span', { class: 'mini-badge violet' }, [icon('image', 11), '图片 ' + job.image_count]));
    if (job.tool_count) badges.appendChild(el('span', { class: 'mini-badge' }, [icon('tool', 11), '工具 ' + job.tool_count]));
    badges.appendChild(el('span', { class: 'mini-badge' }, [icon('key', 11), job.api_key || 'anonymous']));
    if (job.client_ip) badges.appendChild(el('span', { class: 'mini-badge' }, [icon('terminal', 11), job.client_ip]));
    badges.appendChild(el('span', { class: 'mini-badge' }, [icon('clock', 11), fmtClock(job.created_at)]));
    if (job.typing) badges.appendChild(el('span', { class: 'mini-badge amber', text: '对方正在输入…' }));
    head.appendChild(badges);

    if (siblings.length > 1) {
      var switcher = el('select', {
        class: 'select',
        id: 'jobSwitcher',
        style: 'margin-top:10px;max-width:100%'
      });
      siblings.forEach(function (item, index) {
        var option = el('option', { value: item.id }, [
          '#' + (index + 1) + ' · ' + fmtClock(item.created_at) + ' · ' + statusMeta(item.status).label + ' · ' + item.model
        ]);
        if (item.id === job.id) option.selected = true;
        switcher.appendChild(option);
      });
      switcher.addEventListener('change', function () { selectJob(switcher.value); });
      head.appendChild(switcher);
    }

    var warnings = (job.meta && job.meta.warnings) || [];
    warnings.forEach(function (message) {
      head.appendChild(el('div', { class: 'notice', style: 'margin:10px 0 0' }, [
        icon('alert', 16),
        el('div', { text: message })
      ]));
    });
  }

  function renderDetailTabs(tabs, job) {
    clear(tabs);
    var entries = [
      { id: 'chat', label: '对话', count: job.messages.length },
      { id: 'tools', label: '工具', count: (job.tools || []).length },
      { id: 'raw', label: '原始请求', count: 0 }
    ];
    entries.forEach(function (entry) {
      var tab = el('button', {
        class: 'dtab' + (STORE.tab === entry.id ? ' is-active' : ''),
        type: 'button'
      }, [entry.label + (entry.count ? ' ' + entry.count : '')]);
      tab.addEventListener('click', function () {
        STORE.tab = entry.id;
        UI.detailTab = null;
        renderDetail();
      });
      tabs.appendChild(tab);
    });
  }

  function renderDetailBody(body, job) {
    clear(body);
    if (STORE.tab === 'tools') {
      renderToolsTab(body, job);
      return;
    }
    if (STORE.tab === 'raw') {
      renderRawTab(body, job);
      return;
    }
    renderChatTab(body, job);
  }

  function renderChatTab(body, job) {
    body.appendChild(el('div', { class: 'section' }, [
      el('div', { class: 'section-title', text: '对话上下文' })
    ]));
    var list = el('div', {});
    (job.messages || []).forEach(function (message) {
      list.appendChild(renderMessage(message));
    });
    body.appendChild(list);

    body.appendChild(el('div', { class: 'section', id: 'replySection' }, [
      el('div', { class: 'section-title', text: '当前回复' })
    ]));
    renderReplySection(job);
    updateDetailParams(job);
  }

  function renderReplySection(job) {
    var section = document.getElementById('replySection');
    if (!section) return;
    var existing = section.querySelector('.reply-current');
    if (existing) section.removeChild(existing);

    var wrap = el('div', { class: 'reply-current' });
    var reply = job.reply || {};
    if (reply.reasoning) {
      var thinking = el('details', { class: 'thinking-block', open: 'open' });
      thinking.appendChild(el('summary', { text: '思考过程 · ' + reply.reasoning.length + ' 字' }));
      thinking.appendChild(el('div', { class: 'thinking-content', text: reply.reasoning }));
      wrap.appendChild(thinking);
    }
    if (reply.text) {
      wrap.appendChild(el('div', { class: 'msg' }, [
        el('div', { class: 'msg-head' }, [
          el('span', { class: 'role-badge assistant', text: 'assistant' }),
          el('span', { class: 'msg-name', text: '已发送 ' + reply.text.length + ' 字 · ' + (reply.deltas || 0) + ' 个片段' })
        ]),
        renderRich(reply.text)
      ]));
    } else if (reply.reasoning) {
      wrap.appendChild(el('div', { class: 'hint', text: '已发送思考内容，尚未发送正文。' }));
    } else if (job.status === 'pending') {
      wrap.appendChild(el('div', { class: 'notice info' }, [
        icon('clock', 16),
        el('div', { text: '对方仍在等待。可以先发送片段让流式客户端看到进度，最后再提交完成。' })
      ]));
    } else if (job.status === 'claimed') {
      wrap.appendChild(el('div', { class: 'hint', text: '已认领，等待你提交内容…' }));
    } else {
      wrap.appendChild(el('div', { class: 'hint', text: '没有文本回复。' }));
    }

    if ((reply.tool_calls || []).length) {
      reply.tool_calls.forEach(function (call) {
        wrap.appendChild(renderCallCard(call, '工具调用'));
      });
    }
    if (job.status === 'rejected' || job.status === 'expired' || job.status === 'cancelled') {
      wrap.appendChild(el('div', { class: 'notice danger' }, [
        icon('alert', 16),
        el('div', { text: '该请求已结束：' + (job.finish_reason || job.status) })
      ]));
    }
    section.appendChild(wrap);
  }

  function updateDetailDynamic(job) {
    var status = document.getElementById('detailStatus');
    var meta = statusMeta(job.status);
    if (status) {
      status.className = 'pill ' + meta.cls;
      status.textContent = meta.label;
    }
    renderReplySection(job);
  }

  function renderMessage(message) {
    var role = message.role || 'user';
    var node = el('div', { class: 'msg is-' + role });
    var head = el('div', { class: 'msg-head' }, [
      el('span', { class: 'role-badge ' + role, text: role })
    ]);
    if (message.name) head.appendChild(el('span', { class: 'msg-name', text: message.name }));
    if (message.tool_call_id) head.appendChild(el('span', { class: 'msg-name', text: 'tool_call_id: ' + message.tool_call_id }));
    if (message.text) head.appendChild(el('span', { class: 'msg-name', text: message.text.length + ' 字' }));
    node.appendChild(head);

    if (message.text) node.appendChild(renderRich(message.text));
    if ((message.images || []).length) node.appendChild(renderMediaGrid(message.images));
    if ((message.tool_calls || []).length) {
      message.tool_calls.forEach(function (call) {
        node.appendChild(renderCallCard(call, '历史工具调用'));
      });
    }
    if (!message.text && !(message.images || []).length && !(message.tool_calls || []).length) {
      node.appendChild(el('div', { class: 'msg-empty', text: '(空消息)' }));
    }
    return node;
  }

  function renderCallCard(call, label) {
    var argumentsValue = call.arguments_json;
    var argsText = argumentsValue !== undefined && argumentsValue !== null
      ? fmtJSON(argumentsValue)
      : text(call.arguments || '{}');
    return el('div', { class: 'tool-card' }, [
      el('div', { class: 'tool-card-head' }, [
        el('span', { class: 'tool-name', text: call.name || '(未命名)' }),
        el('span', { class: 'mini-badge blue', text: label }),
        call.id ? el('span', { class: 'mini-badge', text: call.id }) : null
      ]),
      el('pre', { class: 'code-block', text: argsText })
    ]);
  }

  /* ======================================================================
     富文本（全部走 DOM 节点，不拼 innerHTML）
     ====================================================================== */
  function renderRich(value) {
    var source = text(value);
    var fence = BT + BT + BT;
    var wrap = el('div', { class: 'rich' });
    var last = 0;
    var index = source.indexOf(fence);
    while (index >= 0) {
      var close = source.indexOf(fence, index + fence.length);
      if (close < 0) break;
      if (index > last) appendParagraphs(wrap, source.slice(last, index));
      var body = source.slice(index + fence.length, close);
      var newline = body.indexOf('\n');
      var info = newline >= 0 ? body.slice(0, newline).trim() : body.trim();
      var codeText = newline >= 0 ? body.slice(newline + 1) : '';
      if (info && !/^[a-zA-Z0-9_+-]*$/.test(info)) {
        codeText = body;
      }
      var pre = el('pre', { class: 'code-block' });
      pre.appendChild(el('code', { text: codeText.replace(/\n$/, '') }));
      wrap.appendChild(pre);
      last = close + fence.length;
      index = source.indexOf(fence, last);
    }
    if (last < source.length) appendParagraphs(wrap, source.slice(last));
    if (!wrap.childNodes.length) wrap.appendChild(el('div', { class: 'msg-empty', text: '(空内容)' }));
    return wrap;
  }

  function appendParagraphs(host, raw) {
    raw.split(/\n{2,}/).forEach(function (chunk) {
      if (!chunk.trim()) return;
      var p = el('p');
      var lines = chunk.split('\n');
      lines.forEach(function (line, index) {
        if (index) p.appendChild(el('br'));
        appendInline(p, line);
      });
      host.appendChild(p);
    });
  }

  function appendInline(host, line) {
    var pattern = new RegExp(
      '(' + BT + '[^' + BT + ']+' + BT + '|\\*\\*[^*]+\\*\\*|https?:\\/\\/[^\\s<>]+)',
      'g'
    );
    var last = 0;
    var match;
    while ((match = pattern.exec(line))) {
      if (match.index > last) host.appendChild(document.createTextNode(line.slice(last, match.index)));
      var token = match[0];
      if (token.charAt(0) === BT) {
        host.appendChild(el('code', { text: token.slice(1, -1) }));
      } else if (token.indexOf('**') === 0) {
        host.appendChild(el('strong', { text: token.slice(2, -2) }));
      } else {
        var cleaned = token.replace(/[.,;:!?)\]"'<>]+$/, '');
        var trailing = token.slice(cleaned.length);
        host.appendChild(el('a', {
          href: cleaned,
          target: '_blank',
          rel: 'noopener noreferrer nofollow',
          text: cleaned
        }));
        if (trailing) host.appendChild(document.createTextNode(trailing));
      }
      last = match.index + match[0].length;
    }
    if (last < line.length) host.appendChild(document.createTextNode(line.slice(last)));
  }

  /* ======================================================================
     图片
     ====================================================================== */
  function renderMediaGrid(images) {
    var grid = el('div', { class: 'media-grid' });
    images.forEach(function (media) { grid.appendChild(renderMedia(media)); });
    return grid;
  }

  function remoteImagesAllowed() {
    if (STORE.remoteImages) return true;
    var security = (STORE.config && STORE.config.security) || {};
    return !!security.allow_remote_images;
  }

  function mediaImage(src, media) {
    var img = el('img', {
      src: src,
      alt: media.name || '请求中的图片',
      loading: 'lazy',
      referrerpolicy: 'no-referrer',
      decoding: 'async'
    });
    img.addEventListener('click', function () { openLightbox(src, media); });
    img.addEventListener('error', function () {
      img.style.display = 'none';
      var parent = img.parentNode;
      if (parent) parent.appendChild(el('div', { class: 'media-error', text: '图片加载失败' }));
    });
    return img;
  }

  function mountMediaImage(fig, src, media) {
    clear(fig);
    fig.classList.remove('is-remote');
    fig.appendChild(mediaImage(src, media));
    fig.appendChild(el('figcaption', {}, [
      el('span', { text: (media.mime || '图片') }),
      el('span', { text: media.bytes ? fmtBytes(media.bytes) : '—' })
    ]));
  }

  function renderMedia(media) {
    var fig = el('figure', { class: 'media' });
    var isRemote = media.kind === 'remote';
    var src = isRemote ? media.url : media.data_url;

    if (isRemote && !remoteImagesAllowed()) {
      fig.classList.add('is-remote');
      var load = el('button', { class: 'btn ghost small media-load', type: 'button' }, [icon('image', 14), '加载图片']);
      load.addEventListener('click', function () {
        load.disabled = true;
        mountMediaImage(fig, src, media);
      });
      fig.appendChild(el('div', { class: 'media-link' }, [
        el('a', { href: src, target: '_blank', rel: 'noopener noreferrer nofollow', text: media.name || src })
      ]));
      fig.appendChild(el('div', { class: 'media-actions' }, [load]));
      fig.appendChild(el('div', { class: 'hint', text: '远端图片默认不自动加载，点击「加载图片」后才会请求图片服务器。' }));
      return fig;
    }
    if (!src) {
      fig.appendChild(el('div', {
        class: 'media-error',
        text: media.sha256 ? '图片未持久化：历史请求仅保留摘要' : '图片数据缺失'
      }));
      return fig;
    }

    mountMediaImage(fig, src, media);
    return fig;
  }

  function openLightbox(src, media) {
    var overlay = document.getElementById('lightbox');
    var img = document.getElementById('lightboxImg');
    var meta = document.getElementById('lightboxMeta');
    if (!overlay || !img) return;
    img.src = src;
    img.alt = (media && media.name) || '';
    meta.textContent = [
      media && media.mime ? media.mime : '',
      media && media.bytes ? fmtBytes(media.bytes) : '',
      media && media.sha256 ? 'sha256:' + media.sha256 : ''
    ].filter(Boolean).join(' · ');
    overlay.classList.add('is-open');
  }

  function closeLightbox() {
    var overlay = document.getElementById('lightbox');
    var img = document.getElementById('lightboxImg');
    if (overlay) overlay.classList.remove('is-open');
    if (img) img.removeAttribute('src');
  }

  /* ======================================================================
     工具解析与展示
     ====================================================================== */
  function schemaEntries(schema) {
    var properties = (schema && schema.properties) || {};
    var required = (schema && schema.required) || [];
    return Object.keys(properties).map(function (name) {
      var prop = properties[name] || {};
      return {
        name: name,
        prop: prop,
        required: required.indexOf(name) >= 0
      };
    });
  }

  function typeLabel(prop) {
    if (!prop) return 'any';
    var type = prop.type;
    if (Array.isArray(type)) return type.join(' | ');
    if (!type && prop.enum) return 'enum';
    if (!type && prop.anyOf) return 'any';
    return type || 'any';
  }

  function renderToolsTab(body, job) {
    var tools = job.tools || [];
    if (!tools.length) {
      body.appendChild(el('div', { class: 'empty', style: 'padding:40px 20px' }, [
        icon('tool', 40),
        el('div', { text: '该请求没有携带工具定义。' })
      ]));
      return;
    }
    body.appendChild(el('div', { class: 'notice info' }, [
      icon('tool', 16),
      el('div', { text: '这些工具由调用方（Agent / SDK）传入，已解析为参数表。可以据此在作答区构造工具调用。' })
    ]));
    if (job.tool_choice) {
      body.appendChild(el('div', { class: 'section' }, [
        el('div', { class: 'section-title', text: '工具选择策略' }),
        el('pre', { class: 'code-block', text: fmtJSON(job.tool_choice) })
      ]));
    }
    tools.forEach(function (tool) {
      body.appendChild(renderToolCard(tool));
    });
  }

  function renderToolCard(tool) {
    var card = el('div', { class: 'tool-card' });
    var entries = schemaEntries(tool.parameters);
    card.appendChild(el('div', { class: 'tool-card-head' }, [
      el('span', { class: 'tool-name', text: tool.name }),
      el('span', { class: 'mini-badge blue', text: tool.source || 'openai' }),
      el('span', { class: 'mini-badge', text: entries.length + ' 个参数' }),
      tool.strict ? el('span', { class: 'mini-badge green', text: 'strict' }) : null
    ]));
    if (tool.description) card.appendChild(el('div', { class: 'tool-desc', text: tool.description }));

    if (entries.length) {
      var table = el('table', { class: 'schema-table' });
      table.appendChild(el('thead', {}, [
        el('tr', {}, [
          el('th', { text: '参数' }),
          el('th', { text: '类型' }),
          el('th', { text: '说明' })
        ])
      ]));
      var tbody = el('tbody');
      entries.forEach(function (entry) {
        var typeCell = el('td', {}, [el('span', { class: 'type', text: typeLabel(entry.prop) })]);
        if (entry.prop.enum && entry.prop.enum.length) {
          var enumList = el('div', { class: 'enum-list' });
          entry.prop.enum.forEach(function (value) {
            enumList.appendChild(el('span', { text: String(value) }));
          });
          typeCell.appendChild(enumList);
        }
        tbody.appendChild(el('tr', {}, [
          el('td', {}, [
            el('span', { class: 'field', text: entry.name }),
            entry.required ? el('span', { class: 'req', text: ' *' }) : null
          ]),
          typeCell,
          el('td', { text: entry.prop.description || (entry.prop.items && entry.prop.items.description) || '—' })
        ]));
      });
      table.appendChild(tbody);
      card.appendChild(table);
    } else {
      card.appendChild(el('div', { class: 'hint', text: '该工具没有声明参数。' }));
    }

    var details = el('details', {});
    details.appendChild(el('summary', { text: '查看原始 JSON Schema' }));
    details.appendChild(el('pre', { class: 'code-block', text: fmtJSON(tool.parameters, 2) }));
    card.appendChild(details);
    return card;
  }

  /* ======================================================================
     原始请求 / 参数
     ====================================================================== */
  function renderRawTab(body, job) {
    var section = el('div', { class: 'section' }, [
      el('div', { class: 'section-title', text: '原始请求体' })
    ]);
    var copyBtn = el('button', { class: 'btn small ghost', type: 'button' }, [icon('copy', 14), '复制 JSON']);
    copyBtn.addEventListener('click', function () { copyText(fmtJSON(job.raw, 2)); });
    section.appendChild(el('div', { class: 'row-actions', style: 'margin:0 0 10px' }, [copyBtn]));
    section.appendChild(el('pre', { class: 'code-block', text: fmtJSON(job.raw || {}, 2) }));
    body.appendChild(section);

    body.appendChild(el('div', { class: 'section' }, [
      el('div', { class: 'section-title', text: '请求元信息' }),
      renderKV([
        ['协议', job.protocol],
        ['模型', job.model],
        ['请求模型', job.request_model],
        ['流式', job.stream ? '是' : '否'],
        ['API Key', job.api_key],
        ['客户端 IP', job.client_ip || '—'],
        ['User-Agent', job.user_agent || '—'],
        ['创建时间', fmtClock(job.created_at)],
        ['完成时间', job.completed_at ? fmtClock(job.completed_at) : '—'],
        ['耗时', job.age_seconds + ' 秒']
      ])
    ]));

    body.appendChild(el('div', { class: 'section' }, [
      el('div', { class: 'section-title', text: '实时回复' }),
      el('pre', { class: 'code-block', text: fmtJSON({ text: job.reply && job.reply.text, tool_calls: job.reply && job.reply.tool_calls }, 2) })
    ]));
  }

  function renderKV(pairs) {
    var grid = el('div', { class: 'kv-grid' });
    pairs.forEach(function (pair) {
      grid.appendChild(el('dl', { class: 'kv' }, [
        el('dt', { text: pair[0] }),
        el('dd', { text: pair[1] === null || pair[1] === undefined || pair[1] === '' ? '—' : String(pair[1]) })
      ]));
    });
    return grid;
  }

  var PARAM_ORDER = [
    'temperature', 'top_p', 'max_tokens', 'stop', 'tool_choice', 'response_format',
    'reasoning_effort', 'seed', 'presence_penalty', 'frequency_penalty', 'top_k',
    'num_predict', 'stopSequences', 'maxOutputTokens', 'candidateCount', 'stream_options'
  ];

  function formatParamValue(value) {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') return fmtJSON(value, 0);
    if (typeof value === 'boolean') return value ? '是' : '否';
    return String(value);
  }

  function updateDetailParams(job) {
    var existing = document.getElementById('paramsSection');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    var params = job.params || {};
    var keys = PARAM_ORDER.filter(function (key) { return params[key] !== undefined; });
    Object.keys(params).forEach(function (key) {
      if (keys.indexOf(key) < 0) keys.push(key);
    });
    if (!keys.length) return;

    var section = el('div', { class: 'section', id: 'paramsSection' }, [
      el('div', { class: 'section-title', text: '模型参数' })
    ]);
    section.appendChild(renderKV(keys.map(function (key) {
      return [key, formatParamValue(params[key])];
    })));
    var body = document.getElementById('detailBody');
    if (body) body.appendChild(section);
  }
