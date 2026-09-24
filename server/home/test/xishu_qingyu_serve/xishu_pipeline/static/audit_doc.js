/* 环评报告审核 · 原文批注视图
 *
 * 2026-09-22 用户交办：「导出的 json 之类的不好看，可以做一个类似修订之类的吗」。
 * 讨论后定的形态（用户逐条拍板）：
 *   · 左边章节树 / 中间报告原文 / 右边批注，批注与原文双向跳转；
 *   · 原文以**文本渲染为主**，扫描页（没有文本层）自动切成页面截图；
 *   · 定位分三档（精确 / 近似 / 仅页码），**档位必须显示给用户** ——
 *     实测 89 条有证据的批注里逐字精确的只有 29%，把"近似"装成"精确"
 *     比不标更糟：用户会以为高亮的地方就是报告原话。
 *
 * 与清单视图的关系：清单视图一行没改，这里只是多一个视图。
 * 所有结论、依据、理由、摘录**只显示服务端返回的内容**，前端不补写、不判断。
 */
const SEV = ['存在问题', '存在疑似问题', '优化调整建议', '无问题', '不适用'];
const SEV_CLS = {
  '存在问题': 'danger', '存在疑似问题': 'warn', '优化调整建议': 'sug',
  '无问题': 'ok', '不适用': 'na'
};
const LVL_CLS = { '精确': 'exact', '近似': 'near', '仅页码': 'page', '无证据': 'none' };
/* 「待复核」= 这三种结论。和清单视图的 NEED_REVIEW 是同一个口径。 */
const NEED_REVIEW_SEV = ['存在问题', '存在疑似问题', '优化调整建议'];

export function createDocView(host) {
  const req = host.req, enc = host.enc, esc = host.esc, API = host.API;
  const state = host.state;
  const setStatus = host.setStatus;
  const pages = {};            // 页号 → 页负载（懒加载缓存）
  let dom = null;

  function api(path) { return API + path; }

  /* ------------------------------------------------------------ 数据 */
  function fetchAnnot(parse) {
    setStatus(parse ? '正在解析报告并生成批注…' : '正在读取批注…');
    return req(api('/annot/' + enc(state.name)) + (parse ? '?parse=1' : '?parse=0'))
      .then(function (r) {
        if (r && r.ok) {
          state.annot = r;
          (r.anchors || []).forEach(function (a, i) { a.key = 'a' + i; });
          setStatus('');
          return r;
        }
        return r;                       // 交给调用方处理（need_parse / 报错）
      })
      .catch(function (e) {
        setStatus('读取批注失败：' + ((e && e.message) || e));
        return null;
      });
  }

  function fetchPage(n) {
    if (pages[n]) return Promise.resolve(pages[n]);
    return req(api('/page/' + enc(state.name) + '?n=' + n)).then(function (r) {
      if (!r || !r.ok) throw new Error((r && r.message) || '读取该页失败');
      pages[n] = r;
      return r;
    });
  }

  /* ------------------------------------------------------------ 挂载 */
  function mount(container) {
    container.innerHTML = '';
    dom = {};
    dom.wrap = document.createElement('div');
    dom.wrap.className = 'au-doc';
    dom.wrap.innerHTML =
      /* 左栏（2026-09-22 用户要求「左侧点哪个问题就跳转到哪里」）：
         默认是**问题清单**（一行一个审核项），章节树挪到第二个页签 ——
         点一行 = 跳到那条证据所在页 + 选中右侧批注卡 + 正文里那处高亮同时点亮。 */
      '<aside class="au-doc-side">' +
      '  <div class="au-doc-tabs">' +
      '    <button class="ghost au-side-tab on" data-side="items">问题清单</button>' +
      '    <button class="ghost au-side-tab" data-side="toc">章节</button>' +
      '  </div>' +
      '  <div class="au-doc-tocbody" id="auSideItems"></div>' +
      '  <div class="au-doc-tocbody" id="auToc" style="display:none"></div>' +
      '</aside>' +
      '<section class="au-doc-main">' +
      '  <div class="au-doc-tools">' +
      '    <button class="ghost" id="auPrev">← 上一页</button>' +
      '    <input type="text" id="auPageNo" class="au-pageinput" inputmode="numeric">' +
      '    <span class="au-meta" id="auPageMeta"></span>' +
      '    <button class="ghost" id="auNext">下一页 →</button>' +
      '    <span class="au-break"></span>' +
      '    <span class="au-meta" id="auAnnotStat"></span>' +
      '    <span class="au-grow"></span>' +
      '    <button class="ghost" id="auDocPvPdf">预览批注版</button>' +
      '    <button id="auDocPdf">下载批注版</button>' +
      '    <button class="ghost" id="auDocPvDocx">预览意见书</button>' +
      '    <button class="ghost" id="auDocDocx">下载意见书</button>' +
      '  </div>' +
      '  <div class="au-doc-page" id="auPage"></div>' +
      '</section>' +
      '<aside class="au-doc-notes">' +
      '  <div class="au-doc-tools">' +
      '    <label class="au-check"><input type="checkbox" id="auAllNotes"> 显示全部（不只本页）</label>' +
      '  </div>' +
      '  <div class="au-doc-notelist" id="auNotes"></div>' +
      '</aside>';
    container.appendChild(dom.wrap);
    dom.toc = dom.wrap.querySelector('#auToc');
    dom.items = dom.wrap.querySelector('#auSideItems');
    dom.page = dom.wrap.querySelector('#auPage');
    dom.notes = dom.wrap.querySelector('#auNotes');
    dom.meta = dom.wrap.querySelector('#auPageMeta');
    dom.stat = dom.wrap.querySelector('#auAnnotStat');
    dom.pageno = dom.wrap.querySelector('#auPageNo');

    Array.prototype.forEach.call(dom.wrap.querySelectorAll('.au-side-tab'), function (b) {
      b.onclick = function () { setSide(b.dataset.side); };
    });
    setSide('items');

    dom.wrap.querySelector('#auPrev').onclick = function () { goto(state.page - 1); };
    dom.wrap.querySelector('#auNext').onclick = function () { goto(state.page + 1); };
    /* 交付件：预览与下载都与清单视图共用同一个实现（host.exportDelivery /
       host.previewDelivery），免得两个视图各写一份、其中一份忘了提示"要等几十秒"。 */
    dom.wrap.querySelector('#auDocPvPdf').onclick = function () { host.previewDelivery('pdf'); };
    dom.wrap.querySelector('#auDocPdf').onclick = function () { host.exportDelivery('pdf'); };
    dom.wrap.querySelector('#auDocPvDocx').onclick = function () { host.previewDelivery('docx'); };
    dom.wrap.querySelector('#auDocDocx').onclick = function () { host.exportDelivery('docx'); };
    dom.pageno.onchange = function () {
      const v = parseInt(this.value, 10);
      if (v >= 1) goto(v);
    };
    dom.wrap.querySelector('#auAllNotes').onchange = function () {
      state.allNotes = this.checked;
      renderNotes();
    };
    dom.wrap.querySelector('#auAllNotes').checked = !!state.allNotes;

    setStatus('');
    renderShell();
    if (state.annot) { renderAll(); return Promise.resolve(state.annot); }
    return fetchAnnot(false).then(function (r) {
      if (r && r.ok) { renderAll(); return r; }
      renderNeedParse(r);
      return r;
    });
  }

  function renderNeedParse(r) {
    dom.page.innerHTML = '';
    const box = document.createElement('div');
    box.className = 'au-empty';
    const msg = (r && r.message) || '还没有这份报告的解析缓存';
    box.innerHTML = '<b>' + esc(msg) + '</b><br>解析一次之后可以反复查看（结果会缓存）。';
    const btn = document.createElement('button');
    btn.textContent = '解析并打开批注视图';
    btn.style.marginTop = '10px';
    btn.onclick = function () {
      btn.disabled = true;
      btn.textContent = '解析中…（大报告可能要一分钟）';
      fetchAnnot(true).then(function (rr) {
        if (rr && rr.ok) renderAll();
        else { btn.disabled = false; btn.textContent = '重试'; }
      });
    };
    box.appendChild(btn);
    dom.page.appendChild(box);
    dom.notes.innerHTML = '';
    dom.toc.innerHTML = '';
    dom.items.innerHTML = '';
  }

  /* ------------------------------------------------------------ 渲染 */
  function anchorsOfPage(n) {
    return (state.annot.anchors || []).filter(function (a) { return a.page === n; });
  }

  function renderShell() {
    if (!state.annot) return;
    dom.stat.textContent = '批注 ' + (state.annot.anchors || []).length + ' 条 · 定位 '
      + ['精确', '近似', '仅页码'].map(function (k) {
        return k + ' ' + ((state.annot['定位统计'] || {})[k] || 0);
      }).join(' / ');
    renderItems();
    renderToc();
  }

  /* ------------------------------------------------------------ 左栏：问题清单 */
  let side = 'items';

  function setSide(which) {
    side = (which === 'toc') ? 'toc' : 'items';
    if (!dom) return;
    dom.items.style.display = (side === 'items') ? '' : 'none';
    dom.toc.style.display = (side === 'toc') ? '' : 'none';
    Array.prototype.forEach.call(dom.wrap.querySelectorAll('.au-side-tab'), function (b) {
      b.classList.toggle('on', b.dataset.side === side);
    });
  }

  /* 一个审核项一行：同一审核项可能有多条证据（多个批注），页号取最靠前的那条。
     行的颜色取该项里**最严重**的结论 —— 一条"存在问题"不能因为后面跟了
     一条"优化建议"就显示成建议色。 */
  function itemGroups() {
    const pass = function (a) { return !state.filterState || a['结论'] === state.filterState; };
    const g = {};
    (state.annot.anchors || []).filter(pass).forEach(function (a) {
      const k = a['审核项'] || '（未命名）';
      const it = g[k] || (g[k] = { name: k, item: a.item, sev: a['结论'], page: 0, anchors: [] });
      it.anchors.push(a);
      if (sevRank(a['结论']) < sevRank(it.sev)) it.sev = a['结论'];
      if (a.page && (!it.page || a.page < it.page)) it.page = a.page;
    });
    return Object.keys(g).map(function (k) { return g[k]; }).sort(function (a, b) {
      return sevRank(a.sev) - sevRank(b.sev) || (a.page || 0) - (b.page || 0);
    });
  }

  function renderItems() {
    if (!dom) return;
    dom.items.innerHTML = '';
    const list = itemGroups();
    const h = document.createElement('div');
    h.className = 'au-doc-h';
    const bad = list.filter(function (g) { return NEED_REVIEW_SEV.indexOf(g.sev) >= 0; }).length;
    h.textContent = '待复核 ' + bad + ' 项 / 共 ' + list.length + ' 项';
    dom.items.appendChild(h);
    if (!list.length) {
      const e = document.createElement('div');
      e.className = 'au-meta';
      e.style.padding = '8px 10px';
      e.textContent = state.filterState ? '当前筛选下没有问题项' : '这份报告没有批注';
      dom.items.appendChild(e);
      return;
    }
    const frag = document.createDocumentFragment();
    list.forEach(function (g) {
      const d = document.createElement('div');
      d.className = 'au-item sev-' + (SEV_CLS[g.sev] || 'na');
      d.dataset.item = g.name;
      d.title = '第 ' + g.item + ' 条　' + g.name + '（' + g.sev + '）' +
        (g.page ? '　证据页 P' + g.page : '　无证据页码') +
        '　' + g.anchors.length + ' 条证据';
      const dot = document.createElement('span');
      dot.className = 'au-item-dot';
      const nm = document.createElement('span');
      nm.className = 'au-item-name';
      nm.textContent = g.name;
      const pg = document.createElement('span');
      pg.className = 'au-item-pg';
      pg.textContent = g.page ? 'P' + g.page : '—';
      d.appendChild(dot); d.appendChild(nm); d.appendChild(pg);
      d.onclick = function () { selectAnchor(g.anchors[0]); };
      frag.appendChild(d);
    });
    dom.items.appendChild(frag);
    syncSideActive();
  }

  /* 选中态两边同步：正文里点高亮、右侧点批注卡、左侧点问题行，三个方向都走这里。
     不这么做的话，用户在正文里点了某处，左栏还停在上一条问题上，两边说法不一致。 */
  function syncSideActive() {
    if (!dom || !dom.items || !state.annot) return;
    const cur = (state.annot.anchors || []).filter(function (a) {
      return a.key === state.activeNote;
    })[0];
    const name = cur ? (cur['审核项'] || '') : '';
    Array.prototype.forEach.call(dom.items.querySelectorAll('.au-item'), function (d) {
      d.classList.toggle('on', !!name && d.dataset.item === name);
    });
  }

  function selectAnchor(a) {
    state.activeNote = a.key;
    if (a.page && a.page !== state.page) goto(a.page);
    else { renderNotes(); }
    const card = dom.notes.querySelector('[data-note="' + a.key + '"]');
    if (card) card.scrollIntoView({ block: 'center' });
  }

  function renderToc() {
    const toc = state.annot.toc || [];
    dom.toc.innerHTML = '';
    if (!toc.length) {
      dom.toc.innerHTML = '<div class="au-meta" style="padding:8px">这份报告没有可用的目录</div>';
      return;
    }
    const frag = document.createDocumentFragment();
    toc.forEach(function (c) {
      const d = document.createElement('div');
      d.className = 'au-toc-item lv' + (c.level || 1);
      d.textContent = c.title + (c.page ? '  P' + c.page : '');
      d.title = c.title;
      if (c.page) { d.onclick = function () { goto(c.page); }; }
      frag.appendChild(d);
    });
    dom.toc.appendChild(frag);
  }

  function renderAll() {
    renderShell();
    const total = state.annot.pages || 1;
    if (!state.page || state.page < 1 || state.page > total) {
      // 打开时先落在"第一条有问题的批注"上 —— 用户看批注视图不是为了从封面读起
      const first = (state.annot.anchors || []).filter(function (a) {
        return a.page && (a['结论'] === '存在问题' || a['结论'] === '存在疑似问题'
          || a['结论'] === '优化调整建议');
      })[0];
      state.page = first ? first.page : 1;
    }
    goto(state.page);
  }

  function goto(n) {
    if (!state.annot) return;
    const total = state.annot.pages || 1;
    n = Math.max(1, Math.min(n || 1, total));
    state.page = n;
    dom.pageno.value = n + ' / ' + total;
    dom.meta.textContent = '正在读取第 ' + n + ' 页…';
    fetchPage(n).then(function (p) {
      if (state.page !== n) return;          // 用户已经翻走了，迟到的响应丢掉
      renderPage(p);
      fetchPage(n + 1).catch(function () { });   // 顺手预取下一页
    }).catch(function (e) {
      dom.meta.textContent = '';
      dom.page.innerHTML = '';
      const d = document.createElement('div');
      d.className = 'au-empty';
      d.textContent = '读取第 ' + n + ' 页失败：' + ((e && e.message) || e);
      dom.page.appendChild(d);
    });
    renderNotes();
  }

  /* 把一段正文按批注区间切成 文本节点 + <mark>。
     一律用 DOM 节点构造（不用 innerHTML 拼正文）：报告正文里什么字符都有，
     拼字符串迟早被某个引号或尖括号弄坏，也是注入面。 */
  function textWithMarks(text, marks) {
    const frag = document.createDocumentFragment();
    const items = (marks || []).filter(function (m) { return m.span; })
      .slice().sort(function (a, b) { return a.span[0] - b.span[0]; });
    let pos = 0;
    items.forEach(function (m) {
      const s = m.span[0], e = m.span[1];
      if (e <= pos) return;                 // 与前一条重叠：跳过，不硬塞
      const from = Math.max(pos, s);
      if (from > pos) frag.appendChild(document.createTextNode(text.slice(pos, from)));
      const mk = document.createElement('mark');
      mk.className = 'au-hl au-hl-' + (LVL_CLS[m.level] || 'page')
        + (m.key === state.activeNote ? ' on' : '');
      mk.dataset.note = m.key;
      mk.title = '第 ' + m.item + ' 条：' + m['审核项'] + '（' + m['结论'] + '·定位' + m.level + '）';
      mk.textContent = text.slice(from, e);
      frag.appendChild(mk);
      pos = e;
    });
    if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
    return frag;
  }

  function renderPage(p) {
    dom.meta.textContent = '第 ' + p.n + ' 页' + (p.printed ? '（印刷页 ' + p.printed + '）' : '')
      + (p.empty ? ' · 无文本层（截图显示）' : '');
    const marks = anchorsOfPage(p.n);
    dom.page.innerHTML = '';

    if (p.empty) {
      const img = document.createElement('img');
      img.className = 'au-pageimg';
      img.alt = '第 ' + p.n + ' 页（扫描页）';
      img.src = api('/pageimg/' + enc(state.name) + '?n=' + p.n);
      dom.page.appendChild(img);
      const tip = document.createElement('div');
      tip.className = 'au-meta';
      tip.style.padding = '6px 2px';
      tip.textContent = marks.length
        ? '本页有 ' + marks.length + ' 条批注；该页是扫描页，无法在正文里高亮，请看右侧批注。'
        : '该页是扫描页（没有文本层）。';
      dom.page.appendChild(tip);
      return;
    }

    const pre = document.createElement('div');
    pre.className = 'au-doc-text';
    pre.appendChild(textWithMarks(p.text || '', marks.filter(function (m) { return m.span; })));
    dom.page.appendChild(pre);
    dom.page.scrollTop = 0;         // 翻页后回到页首（否则停在上一页的滚动位置，像"没翻动"）

    (p.tables || []).forEach(function (t, i) {
      const hit = marks.some(function (m) { return m.table === i; });
      const wrap = document.createElement('div');
      wrap.className = 'au-doc-table' + (hit ? ' hit' : '');
      const head = document.createElement('div');
      head.className = 'au-meta';
      head.textContent = '本页表格 ' + (i + 1) + (hit ? ' · 有批注指向本表' : '');
      wrap.appendChild(head);
      const tb = document.createElement('table');
      (t.rows || []).forEach(function (row, ri) {
        const tr = document.createElement('tr');
        row.forEach(function (c) {
          const td = document.createElement(ri === 0 ? 'th' : 'td');
          td.textContent = c || '';
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      wrap.appendChild(tb);
      dom.page.appendChild(wrap);
    });

    Array.prototype.forEach.call(dom.page.querySelectorAll('.au-hl'), function (mk) {
      mk.onclick = function () {
        /* 正文里点高亮 = 选中这条批注；左栏问题行与右侧批注卡同时点亮（走同一处） */
        const a = (state.annot.anchors || []).filter(function (x) {
          return x.key === mk.dataset.note;
        })[0];
        if (a) selectAnchor(a);
        else { state.activeNote = mk.dataset.note; renderNotes(); }
      };
    });
  }

  function sevRank(s) {
    const i = SEV.indexOf(s);
    return i < 0 ? 9 : i;
  }

  function noteCard(a) {
    const box = document.createElement('div');
    box.className = 'au-note au-note-' + (SEV_CLS[a['结论']] || 'na')
      + (a.key === state.activeNote ? ' on' : '');
    box.dataset.note = a.key;

    const head = document.createElement('div');
    head.className = 'au-note-h';
    head.innerHTML = '<b>' + esc(a['审核项']) + '</b>' +
      '<span class="au-tag" data-state="' + esc(a['结论']) + '">' + esc(a['结论']) + '</span>' +
      (a['置信度'] ? '<span class="au-meta">置信度 ' + esc(a['置信度']) + '</span>' : '');
    box.appendChild(head);

    const meta = document.createElement('div');
    meta.className = 'au-meta';
    meta.textContent = '第 ' + a.item + ' 条 · ' + (a['类别'] || '') +
      (a.page ? ' · 物理页 P' + a.page + (a.printed ? '（印刷页 ' + a.printed + '）' : '') : ' · 无证据页码');
    box.appendChild(meta);

    if (a.quote) {
      const q = document.createElement('div');
      q.className = 'au-note-quote';
      q.textContent = '证据摘录：' + a.quote;
      box.appendChild(q);
    }
    const lv = document.createElement('div');
    lv.className = 'au-lvl au-lvl-' + (LVL_CLS[a.level] || 'page');
    lv.textContent = '定位：' + a.level + ' · ' + (a.why || '');
    box.appendChild(lv);

    if (a['参考依据']) {
      const d = document.createElement('div');
      d.className = 'au-note-body';
      d.textContent = '参考依据：' + a['参考依据'];
      box.appendChild(d);
    }
    if (a['理由']) {
      const d = document.createElement('div');
      d.className = 'au-note-body';
      d.textContent = '理由：' + a['理由'];
      box.appendChild(d);
    }
    if ((a['需人工确认'] || []).length) {
      const d = document.createElement('div');
      d.className = 'au-note-body';
      d.textContent = '需人工确认：' + a['需人工确认'].join('；');
      box.appendChild(d);
    }

    /* 人工复核：与清单视图共用同一份存储（/api/save），同一份 state.review */
    const row = document.createElement('div');
    row.className = 'au-note-review';
    const cur = (state.review[a['审核项']] || {});
    const sel = document.createElement('select');
    sel.dataset.human = a['审核项'];
    sel.innerHTML = '<option value="">（未复核）</option>' + SEV.map(function (s) {
      return '<option value="' + esc(s) + '"' + (cur['人工修改'] === s ? ' selected' : '') +
        '>' + esc(s) + '</option>';
    }).join('');
    const note = document.createElement('input');
    note.type = 'text';
    note.placeholder = '复核备注';
    note.dataset.note = a['审核项'];
    note.value = cur['备注'] || '';
    row.appendChild(sel);
    row.appendChild(note);
    box.appendChild(row);

    if (a.page) {
      const go = document.createElement('button');
      go.className = 'ghost au-note-go';
      go.textContent = '在原文中查看';
      go.onclick = function () { selectAnchor(a); };
      box.appendChild(go);
    }
    box.onclick = function (e) {
      if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT'
        || e.target.tagName === 'BUTTON') return;
      selectAnchor(a);
    };
    return box;
  }

  function renderNotes() {
    if (!state.annot || !dom) return;
    const all = state.annot.anchors || [];
    /* 顶部的结论卡片在批注视图里也生效：用户在清单视图点了「存在问题 1」，
       切过来应当还是只看那一条，两个视图的筛选口径不能各说各话。 */
    const pass = function (a) { return !state.filterState || a['结论'] === state.filterState; };
    const list = state.allNotes ? all.filter(pass).sort(function (a, b) {
      return sevRank(a['结论']) - sevRank(b['结论']) || (a.page || 0) - (b.page || 0);
    }) : anchorsOfPage(state.page).filter(pass);

    dom.notes.innerHTML = '';
    const h = document.createElement('div');
    h.className = 'au-doc-h';
    h.textContent = state.allNotes
      ? '全部批注（' + list.length + ' 条，按结论严重度排序）'
      : '本页批注（' + list.length + ' 条）';
    dom.notes.appendChild(h);
    if (!list.length) {
      const e = document.createElement('div');
      e.className = 'au-meta';
      e.style.padding = '8px';
      e.textContent = state.allNotes ? '没有批注' : '本页没有批注';
      dom.notes.appendChild(e);
      return;
    }
    list.forEach(function (a) { dom.notes.appendChild(noteCard(a)); });
    syncSideActive();
  }

  function destroy() { dom = null; }

  return {
    mount: mount,
    /* 作废缓存：换报告、或重跑审核之后都走这里。
       连 state.page 一起归零 —— 归零后 renderAll() 会落在"第一条待复核的问题"上
       （用户看批注视图不是为了从封面读起，尤其现在跑完审核会自动切进来）。 */
    reload: function () {
      state.annot = null; state.activeNote = ''; state.page = 0;
      Object.keys(pages).forEach(function (k) { delete pages[k]; });
    },
    renderNotes: renderNotes,
    destroy: destroy
  };
}
