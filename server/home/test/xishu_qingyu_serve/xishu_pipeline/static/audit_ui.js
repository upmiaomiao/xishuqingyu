/* 环评报告审核工作台 · 前端模块
 *
 * 为什么做成"可挂载模块"而不是一个页面：
 *   审核界面要在两个地方用 —— ① 问答首页内嵌（原生渲染，不要 iframe 套一层页头）；
 *   ② 独立页 /audit（可直接分享链接 / 新窗口打开）。逻辑只写这一份，
 *   两处都调用 mountAuditUI(容器)，避免以后两边功能走偏。
 *
 * 约定：
 *   · ES 模块，只导出 mountAuditUI 一个入口，其余全部模块内私有；
 *   · 所有 DOM 都在传入的容器里生成，类名一律 au- 前缀；
 *   · 结论与证据**只显示服务端返回的内容**，前端不做任何判断或补写。
 *
 * 2026-09-18 重构（阶段 3）：由 IIFE 传统脚本改为 ES 模块，
 *   var 全部改为 const/let（AST 逐节点验证等价），
 *   挂载入口由 window.* 改为 export。
 *
 * 2026-09-22 新增「原文批注」视图（audit_doc.js）：左边章节树、中间报告原文、
 *   右边批注，与清单视图共用同一份 state 与同一份人工复核存储。
 *   清单视图的逻辑这一轮**一行没改**，只是多了一个视图入口。
 */
import { createDocView } from './audit_doc.js';

const API = '/audit/api';
const STATES = ['存在问题', '存在疑似问题', '优化调整建议', '无问题', '不适用'];
const GROUPS = ['法规符合性', '技术导则符合性', '环境风险（HJ 169）', '报告质量'];
const NEED_REVIEW = { '存在问题': 1, '存在疑似问题': 1, '优化调整建议': 1 };

function esc(s) {
  return (s === null || s === undefined ? '' : String(s))
    .replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
}
function el(tag, cls, html) {
  const d = document.createElement(tag);
  if (cls) d.className = cls;
  if (html !== undefined) d.innerHTML = html;
  return d;
}
function enc(s) { return encodeURIComponent(s); }

/* ------------------------------------------------------------------ 错误解析
   改动前本文件的 4 处请求都是**先 r.json() 再判 r.ok**，而后端 500 回的是纯文本
   "Internal Server Error"，r.json() 当场抛 SyntaxError，`r.detail` 那一行根本
   执行不到 —— 用户看到的是 JSON 解析器报错原文（kg.js 那边也一样）。
   另外 FastAPI 422 的 detail 是**数组**，`new Error(数组)` 会显示 [object Object]。
   现在统一：先取原文 → 尝试解析 → 不是 JSON 就保留原文 → 再按 r.ok 判。
   错误对象上带 code / status / requestId，便于按类型分支和对照服务端日志。 */
function errText(d, status) {
  if (d && typeof d === "object") {
    if (typeof d.message === "string" && d.message) return d.message;
    if (typeof d.detail === "string" && d.detail) return d.detail;
    if (Array.isArray(d.detail)) return "请求参数有误";
    return "HTTP " + status;
  }
  if (typeof d === "string" && d.trim() && d.length <= 200) return d.trim();
  return "HTTP " + status;
}
function httpErr(d, status) {
  const e = new Error(errText(d, status));
  e.code = (d && typeof d === "object" && d.code) || ("E_HTTP_" + status);
  e.status = status;
  e.requestId = (d && typeof d === "object" && d.request_id) || "";
  return e;
}
function req(url, init) {
  return fetch(url, init).then(function (r) {
    return r.text().then(function (t) {
      let d = null;
      if (t) { try { d = JSON.parse(t); } catch (e) { d = t; } }
      if (!r.ok) throw httpErr(d, r.status);
      return d;
    });
  });
}

export function mountAuditUI(root, opts) {
  if (!root) throw new Error('mountAuditUI: 缺少挂载容器');
  if (root.__au) return root.__au;              // 已挂载则复用，避免重复渲染
  opts = opts || {};
  const pdfUrl = opts.pdfUrl || function (name, page) {
    return API + '/pdf/' + enc(name) + '#page=' + page;
  };
  const state = {
    reports: [], name: '', running: false, job: null, result: null,
    review: {}, filterState: '', onlyNeed: false, eviAll: null, timer: null,
    /* 视图与批注视图的会话状态（2026-09-22）：
       annot 是服务端返回的批注包（含三档定位结果），page 是当前物理页。 */
    view: 'list', annot: null, page: 1, activeNote: '', allNotes: false
  };

  /* ------------------------------------------------------------ 骨架 */
  root.classList.add('au-shell');
  root.innerHTML = '';
  const bar = el('div', 'au-bar');
  const prog = el('div', 'au-progress', '<i></i>');
  const summary = el('div', 'au-summary');
  const tools = el('div', 'au-tools');
  const body = el('div', 'au-body');
  root.appendChild(bar); root.appendChild(prog); root.appendChild(summary);
  root.appendChild(tools); root.appendChild(body);

  bar.innerHTML =
    '<span class="au-label">报告</span>' +
    '<select class="au-pick" id="auPick"></select>' +
    '<button class="ghost" id="auUpload" title="上传自己的环评报告（PDF）">上传报告</button>' +
    '<input type="file" id="auFile" accept="application/pdf,.pdf" style="display:none">' +
    '<label class="au-check"><input type="checkbox" id="auLlm" checked> 启用模型抽取</label>' +
    '<button id="auRun">开始审核</button>' +
    '<span class="au-status" id="auStatus"></span>' +
    '<span class="au-views">' +
    '<button class="ghost au-view" data-view="list">清单</button>' +
    '<button class="ghost au-view" data-view="doc">原文批注</button>' +
    '</span>' +
    '<a class="au-new" href="/audit" target="_blank" rel="noopener">新窗口打开 ↗</a>';
  tools.innerHTML =
    '<label class="au-check"><input type="checkbox" id="auNeed"> 只看待复核（有问题/疑似/建议）</label>' +
    '<label class="au-check"><input type="checkbox" id="auEvi"> 展开全部证据</label>' +
    '<span class="au-grow"></span>' +
    '<button class="ghost" id="auSave" disabled>保存人工复核</button>' +
    '<button class="ghost" id="auCsv" disabled>导出审核表 CSV</button>' +
    '<button class="ghost" id="auJson" disabled>导出 JSON</button>' +
    /* 2026-09-22：给"人看的"交付件（CSV/JSON 是给机器核对的）。
       每件两个动作：预览（网页里直接看）/ 交付件（下载文件）。 */
    '<span class="au-deliv">批注版 PDF' +
    '<button class="ghost" id="auPvPdf" disabled>预览</button>' +
    '<button id="auExpPdf" disabled>下载</button></span>' +
    '<span class="au-deliv">审核意见书' +
    '<button class="ghost" id="auPvDocx" disabled>预览</button>' +
    '<button class="ghost" id="auExpDocx" disabled>下载</button></span>';
  /* 预览弹层另外挂在 root 上（不塞进工具栏：工具栏是 flex 行，弹层要脱离布局，
     而且万一将来给工具栏加了 overflow/transform，fixed 定位会被带跑偏）。 */
  root.insertAdjacentHTML('beforeend',
    '<div class="au-preview" id="auPreview">' +
    '  <div class="au-preview-box">' +
    '    <div class="au-preview-bar">' +
    '      <b id="auPreviewTitle"></b>' +
    '      <span class="au-preview-hint" id="auPreviewHint"></span>' +
    '      <span class="au-grow"></span>' +
    '      <a class="au-preview-link" id="auPreviewOpen" href="#" target="_blank" rel="noopener">新标签页打开 ↗</a>' +
    '      <button class="ghost" id="auPreviewClose">关闭</button>' +
    '    </div>' +
    '    <iframe class="au-preview-frame" id="auPreviewFrame" src="about:blank"></iframe>' +
    '  </div>' +
    '</div>');

  const $ = function (sel) { return root.querySelector(sel); };
  const pick = $('#auPick'), statusEl = $('#auStatus'), barI = prog.firstChild;
  const btnRun = $('#auRun'), btnSave = $('#auSave'), btnCsv = $('#auCsv'), btnJson = $('#auJson');
  /* 交付件按钮：只有跑完审核（有结果）才可用 */
  const btnExpPdf = $('#auExpPdf'), btnExpDocx = $('#auExpDocx');
  const btnPvPdf = $('#auPvPdf'), btnPvDocx = $('#auPvDocx');
  const DELIV = [btnCsv, btnJson, btnPvPdf, btnExpPdf, btnPvDocx, btnExpDocx];
  function setDeliv(on) { DELIV.forEach(function (b) { b.disabled = !on; }); }
  const btnUpload = $('#auUpload'), fileInput = $('#auFile');

  function setStatus(t) { statusEl.textContent = t || ''; }
  function setProgress(pct) { barI.style.width = (pct || 0) + '%'; }

  /* ------------------------------------------------------------ 视图切换
     两个视图共用同一份 state：切走再切回来不会丢人工复核的填写内容，
     也不会重新问一遍服务端（批注包缓存在 state.annot 里）。 */
  const docView = createDocView({
    API: API, req: req, enc: enc, esc: esc, state: state, setStatus: setStatus,
    exportDelivery: function (kind) { exportDelivery(kind); },
    previewDelivery: function (kind) { previewDelivery(kind); }
  });

  function setView(v) {
    state.view = (v === 'doc') ? 'doc' : 'list';
    Array.prototype.forEach.call(root.querySelectorAll('.au-view'), function (b) {
      b.classList.toggle('on', b.dataset.view === state.view);
    });
    if (state.result) render();
    else showEmpty();
  }
  Array.prototype.forEach.call(root.querySelectorAll('.au-view'), function (b) {
    b.onclick = function () { setView(b.dataset.view); };
  });

  /* ------------------------------------------------------------ 报告清单 */
  function loadReports() {
    return req(API + '/reports').then(function (r) {
      if (!r || !r.ok) { setStatus((r && r.error) || '读取清单失败'); return; }
      state.reports = r.reports || [];
      pick.innerHTML = state.reports.map(function (x) {
        return '<option value="' + esc(x.name) + '">' + esc(x.name) +
          '  (' + (x.size / 1048576).toFixed(1) + ' MB' +
          (x['已审核'] ? ' · 已审核' : '') + ')</option>';
      }).join('');
      if (opts.report) {
        for (let i = 0; i < pick.options.length; i++) {
          if (pick.options[i].value === opts.report) { pick.selectedIndex = i; break; }
        }
      }
      state.name = pick.value;
      if (!state.result) showEmpty();
      return loadReview().then(function () { return loadExistingResult(); });
    }).catch(function (e) {
      /* 改动前这里**没有 catch**，而两个调用方（挂载时 L373、宿主页 reload）
         都不接返回值：接口一失败 rejection 就无人接管，报告下拉框保持为空、
         页面停在"选一份报告，点开始审核"的引导态，用户完全不知道是后端挂了。 */
      setStatus('读取报告清单失败：' + ((e && e.message) || e));
      pick.innerHTML = '';
    });
  }

  /* ------------------------------------------------------------ 读回上次的结果
     刷新页面 / 换回来一份审过的报告时，把磁盘上的审核结果读回来渲染 ——
     否则用户只能重跑一遍（几十分钟）才能再看到"原文批注"。
     读不到就当没有：不报错、不弹窗（新报告本来就没有结果，是正常状态）。 */
  function loadExistingResult() {
    const want = state.name;
    return req(API + '/result/' + enc(want)).then(function (r) {
      if (!r || !r.ok || !r.has) return null;
      if (state.name !== want) return null;        // 期间用户又换报告了，丢弃
      state.result = r.result;
      docView.reload();                            // 结果换了，批注页码可能变
      render();
      setStatus('已读取上次的审核结果' + (r.time ? '（' + r.time + '）' : ''));
      return r;
    }).catch(function () { return null; });
  }

  /* ------------------------------------------------------------ 上传报告
   *
   * 2026-09-18 用户反馈：「环评报告审核这里没有上传自己的环评报告，
   * 我觉得这个功能需要有」。改动前只能审 /data/eia_reports 里已有的报告，
   * 得先由人手工把文件拷到服务器上，网页上没有任何入口。
   *
   * 用 XMLHttpRequest 而**不是 fetch**：报告动辄几十 MB，需要真实的
   * 上传进度条。fetch 没有上传进度事件（只有 request body 的 ReadableStream，
   * 拿不到已发送字节数），几十秒没有反馈用户会以为卡死了。
   */
  function pickFile() { fileInput.value = ''; fileInput.click(); }

  function uploadFile(file) {
    if (!file) return;
    /* 前端先挡一道，省得几十 MB 白传一趟再被后端拒。
       后端**一样要校验**（前端校验只是体验，不是安全边界）。 */
    const isPdf = /\.pdf$/i.test(file.name) ||
      file.type === 'application/pdf';
    if (!isPdf) { setStatus('只支持 PDF 格式的环评报告'); return; }
    const MAXMB = 200;
    if (file.size > MAXMB * 1048576) {
      setStatus('文件 ' + (file.size / 1048576).toFixed(1) + ' MB，超过 ' + MAXMB + ' MB 上限');
      return;
    }

    const fd = new FormData();
    fd.append('file', file, file.name);
    btnUpload.disabled = true;
    btnUpload.textContent = '上传中 0%';
    setStatus('正在上传《' + file.name + '》…');

    const xhr = new XMLHttpRequest();
    xhr.open('POST', API + '/upload');
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      btnUpload.textContent = '上传中 ' + pct + '%';
      setProgress(pct);
    };
    xhr.onload = function () {
      btnUpload.disabled = false;
      btnUpload.textContent = '上传报告';
      let d = null;
      try { d = JSON.parse(xhr.responseText); } catch (e) { d = xhr.responseText; }
      if (xhr.status < 200 || xhr.status >= 300) {
        setProgress(0);
        setStatus(errText(d, xhr.status));
        return;
      }
      setProgress(100);
      setStatus((d && d.message) || '上传完成');
      /* 传完立刻刷新清单并选中它 —— 用户下一步必然是"审这份"。
         内容与已有报告重复时后端返回的是**已有那份**的名字（列表按 sha1 去重，
         新名字根本不会出现在清单里），所以这里选中 name 而不是上传的文件名。 */
      const want = (d && d.name) || '';
      return loadReports().then(function () {
        if (!want) return;
        for (let i = 0; i < pick.options.length; i++) {
          if (pick.options[i].value === want) { pick.selectedIndex = i; break; }
        }
        state.name = pick.value;
        loadReview();
        setTimeout(function () { setProgress(0); }, 1200);
      });
    };
    xhr.onerror = function () {
      btnUpload.disabled = false;
      btnUpload.textContent = '上传报告';
      setProgress(0);
      setStatus('上传失败：网络中断，请重试');
    };
    xhr.onabort = function () {
      btnUpload.disabled = false;
      btnUpload.textContent = '上传报告';
      setProgress(0);
      setStatus('上传已取消');
    };
    xhr.send(fd);
  }

  btnUpload.addEventListener('click', pickFile);
  fileInput.addEventListener('change', function () { uploadFile(fileInput.files[0]); });

  function showEmpty() {
    summary.innerHTML = '';
    tools.style.display = 'none';
    body.classList.remove('au-body-doc');
    body.innerHTML = '<div class="au-empty"><b>环评报告审核智能体</b>' +
      '选一份报告，点「开始审核」。<br>每一条结论都会给出报告页码与原文摘录，' +
      '点页码可打开原文对照；结论分四态，判不出来的会明确写成「存在疑似问题」。' +
      '<br><br>想审自己的报告？点左上角<b>「上传报告」</b>选一个 PDF 即可，' +
      '上传后会自动选中它。</div>';
    btnSave.disabled = true; setDeliv(false);
  }

  /* ------------------------------------------------------------ 人工复核 */
  function loadReview() {
    state.review = {};
    if (!state.name) return Promise.resolve();
    /* 记住这次请求属于哪份报告：响应回来时若用户已经切走，就整份丢弃。
       改动前用的是"响应回来时"的 state.name 无条件覆盖 state.review，
       快速连切两份报告时两次响应乱序，会把**别人的**复核记录显示在当前报告上。 */
    const want = state.name;
    return req(API + '/review/' + enc(want))
      .then(function (r) {
        if (state.name !== want) return;
        state.review = (r && r.items) || {};
      })
      .catch(function (e) {
        if (state.name !== want) return;
        state.review = {};
        /* 改动前这是**空 catch**：接口挂了与"确实没保存过复核"在界面上完全一样，
           已复核项会被重新显示成"（未复核）"，用户以为自己的结论丢了。 */
        setStatus('读取人工复核失败：' + ((e && e.message) || e) + '（下列显示为未复核）');
      });
  }

  /* ------------------------------------------------------------ 跑审核 */
  function run() {
    if (!state.name || state.running) return;
    state.running = true; state.result = null;
    btnRun.disabled = true; btnSave.disabled = true; setDeliv(false);
    body.innerHTML = ''; summary.innerHTML = ''; tools.style.display = 'none';
    setStatus('已提交…'); setProgress(4);
    const want = state.name;              /* 记住这份任务属于哪份报告 */
    req(API + '/run?name=' + enc(want) + '&use_llm=' + ($('#auLlm').checked ? 'true' : 'false'),
      { method: 'POST' })
      .then(function (r) {
        if (!r || !r.ok) throw new Error((r && r.error) || '提交失败');
        /* job 缺失时以前会去请求 /job/undefined → 404 JSON → j.done 是 undefined
           → 落进下面那个静默无限轮询。这里直接拦下。 */
        if (!r.job) throw new Error('服务端没有返回任务号，无法跟踪进度');
        state.job = r.job; poll(want);
      })
      .catch(function (e) { fail((e && e.message) || e); });
  }

  /* 停止轮询并明确报出来。改动前 poll() 里**没有任何停止条件**：
     `.catch(function () { return {}; })` 把失败换成空对象，`if (!j.done) return;` 又是
     静默返回 —— 任务不存在（后端 404 + JSON {"detail":"任务不存在或已过期"}）时
     响应**能解析成功、连 catch 都不进**，j.done 是 undefined，于是每 900ms 空转一次；
     state.running 一直是 true、"开始审核"按钮一直禁用、进度条永远停在 4%，
     没有提示、没有超时、没有重试。审核是整套流程里最贵的操作，
     用户唯一的出路是刷新页面。 */
  function stop(msg) {
    clearInterval(state.timer);
    state.timer = null;
    fail(msg);
  }

  function poll(want) {
    clearInterval(state.timer);
    let fails = 0;
    const t0 = Date.now();
    const MAX_MS = 30 * 60 * 1000;
    state.timer = setInterval(function () {
      if (Date.now() - t0 > MAX_MS) { stop('审核超过 30 分钟仍未结束，已停止等待'); return; }
      req(API + '/job/' + state.job).then(function (j) {
        fails = 0;
        if (!j || typeof j !== 'object') { stop('服务端没有返回任务详情，已停止等待'); return; }
        if (j.stage) setStatus(j.stage + (j.secs ? '　' + j.secs + 's' : ''));
        setProgress(j.pct || 4);
        if (!j.done) return;
        clearInterval(state.timer); state.timer = null;
        state.running = false; btnRun.disabled = false;
        if (j.error) { fail(j.error); return; }
        /* 期间用户切了报告：这份结果不属于当前显示的报告，整份丢弃。
           改动前会直接把旧报告的 j.result 渲染到新报告名下 ——
           合规审核场景里"结论张冠李戴"比界面卡死危险得多。 */
        if (state.name !== want) return;
        state.result = j.result;
        /* 重新审了一遍 → 批注锚定必须重算（结论、证据、页码都可能变了） */
        docView.reload();
        loadReview().then(function () {
          render();
          /* 审核跑完自动切到「原文批注」（用户 2026-09-22：「审核完成之后可以在右侧
             默认打开吗，然后左侧点哪个问题就跳转到哪里」）。
             只在**本次跑完**时切，加载既有结果时不动 —— 否则用户回来看看旧结果，
             视图会被莫名其妙地换掉。失败分支不会走到这里（上面已 return）。 */
          if (state.name === want) setView('doc');
        });
      }).catch(function (e) {
        fails += 1;
        if ((e && e.status === 404) || fails >= 3) {
          stop((e && e.status === 404 ? '任务不存在或已过期：' : '连续取不到任务状态，已停止等待：')
            + ((e && e.message) || e));
        }
      });
    }, 900);
  }

  function fail(msg) {
    state.running = false; btnRun.disabled = false;
    setStatus('失败');
    body.innerHTML = '<div class="au-warnbox"><b>审核未完成</b><div style="margin-top:4px">' +
      esc(msg) + '</div></div>';
  }

  /* ------------------------------------------------------------ 渲染 */
  function evidenceOpen(it) {
    if (state.eviAll === true) return true;
    if (state.eviAll === false) return false;
    return !!NEED_REVIEW[it['AI审核']] || (it['需人工确认'] || []).length > 0;
  }

  function eviHTML(it) {
    const f = state.result.file;
    const ev = it['证据'] || [];
    if (!ev.length) return '';
    return ev.map(function (e) {
      const pg = e.page;
      const lbl = e.mark ? e.mark + '（P' + pg + '）' : 'P' + pg;
      const link = pg
        ? '<a class="au-pg" target="_blank" rel="noopener" href="' + esc(pdfUrl(f.name, pg)) + '">' + esc(lbl) + '</a>'
        : esc(lbl);
      return '<div class="au-evi">' + link +
        (e.source ? ' <span class="src">[' + esc(e.source) + ']</span>' : '') +
        '<span class="qt">' + esc(e.quote || '') + '</span></div>';
    }).join('');
  }

  function itemHTML(it) {
    const k = it['审核项'];
    const rv = state.review[k] || {};
    const human = rv['人工修改'] || '';
    const ev = it['证据'] || [];
    const open = evidenceOpen(it);
    const need = (it['需人工确认'] || []);
    let cls = 'au-item';
    if (it['AI审核'] === '存在问题') cls += ' top-problem';
    else if (it['AI审核'] === '存在疑似问题') cls += ' top-warn';
    else if (it['AI审核'] === '优化调整建议') cls += ' top-adj';
    if (state.onlyNeed && !NEED_REVIEW[it['AI审核']]) cls += ' hide';
    if (state.filterState && it['AI审核'] !== state.filterState) cls += ' hide';

    const opts = ['<option value="">（未复核）</option>'].concat(STATES.map(function (s) {
      return '<option value="' + s + '"' + (s === human ? ' selected' : '') + '>' + s + '</option>';
    })).join('');

    let evBlock = '';
    if (ev.length) {
      evBlock = '<div class="au-evwrap">' +
        '<span class="au-evtog" data-ev="' + esc(k) + '">' +
        (open ? ' 收起证据' : '▸ 展开 ' + ev.length + ' 条证据') + '</span>' +
        '<div class="au-evis" style="display:' + (open ? 'block' : 'none') + '">' + eviHTML(it) + '</div></div>';
    }
    return '<div class="' + cls + '" data-k="' + esc(k) + '">' +
      '<div><div class="au-head">' +
        '<span class="au-name">' + esc(k) + '</span>' +
        '<span class="au-tag" data-state="' + esc(it['AI审核']) + '">' + esc(it['AI审核']) + '</span>' +
        (it['环评文件'] ? '<span class="au-meta">' + esc(it['环评文件']) + '</span>' : '') +
        '<span class="au-conf">置信度 ' + esc(it['置信度'] || '—') + '</span>' +
      '</div>' +
      (it['参考依据'] ? '<div class="au-ref">依据：' + esc(it['参考依据']) + '</div>' : '') +
      '<div class="au-why">' + esc(it['理由'] || '') + '</div>' +
      need.map(function (c) { return '<div class="au-need">⚠ ' + esc(c) + '</div>'; }).join('') +
      evBlock + '</div>' +
      '<div class="au-ops">' +
        '<select data-human="' + esc(k) + '">' + opts + '</select>' +
        '<input type="text" data-note="' + esc(k) + '" placeholder="复核备注（选填）" value="' + esc(rv['备注'] || '') + '">' +
        (rv['时间'] ? '<span class="au-savedflag">已保存 ' + esc(String(rv['时间']).slice(5, 16)) + '</span>' : '') +
      '</div></div>';
  }

  // 「不适用」到底指什么 —— 2026-09-22 用户反馈（看到 9 项"不适用"不知道是不是漏审了）。
  // 实测 6 份报告 38 条"不适用"**全是同一个原因**：那 9 项"专项评价设置"依据的是
  // 《建设项目环境影响报告表编制技术指南（污染影响类）》表1，报告书不受它约束。
  // 把口径写在界面上，省得每次靠猜；交付件（Word/意见书）里同一句话也会出现。
  function naNote(f, st) {
    if (!st['不适用']) return '';
    const t = String(f['环评文件类型'] || '');
    const why = t.indexOf('报告书') >= 0
      ? '本报告是<b>报告书</b>，其中「专项评价设置」类 9 项是《建设项目环境影响报告表' +
        '编制技术指南（污染影响类）》表1 的判据，报告书不受该指南约束，故判「不适用」' +
        '（不是漏审、也不是没查到）。'
      : '这些项是按相应判据设置的，本报告不涉及该判据适用的情形，故判「不适用」' +
        '（不是漏审、也不是没查到）。';
    return '<div class="au-na-note"><b>「不适用」是什么意思：</b>' + why +
      '点上面「不适用」卡片可只看这一类。</div>';
  }

  function renderSummary(r) {
    const f = r.file, st = r['统计'] || {};
    const n = (r.items || []).length;
    setStatus('完成'); setProgress(100);
    summary.innerHTML =
      '<div class="au-title"><b>' + esc(f['项目名称'] || f.name) + '</b>' +
      '<span class="au-tag" data-state="不适用">' + esc(f['环评文件类型'] || '') + '</span>' +
      '<span class="au-meta">' + esc(f.name) + '　' + n + ' 项审核项　' + esc(f.pages) + ' 页</span></div>' +
      '<div class="au-cards">' + STATES.map(function (s) {
        const on = state.filterState === s ? ' on' : '';
        const tip = s === '不适用'
          ? ' title="判据对本报告不成立，不计入问题。点一下可只看这一类。"' : '';
        return '<button class="au-card' + on + '" data-state="' + s + '" data-filter="' + s + '"' +
          tip + '>' +
          '<span class="n">' + (st[s] || 0) + '</span><span class="t">' + s + '</span></button>';
      }).join('') + '</div>' + naNote(f, st);
  }

  function render() {
    const r = state.result;
    if (!r) { showEmpty(); return; }
    renderSummary(r);
    if (state.view === 'doc') {
      tools.style.display = 'none';
      body.classList.add('au-body-doc');
      btnSave.disabled = false; setDeliv(true);
      docView.mount(body);
      bind();
      return;
    }
    body.classList.remove('au-body-doc');
    tools.style.display = '';
    renderList(r);
    bind();
  }

  function renderList(r) {
    const seen = {}, groups = [];
    (r.items || []).forEach(function (it) {
      const g = it['类别'] || '其它';
      if (!seen[g]) { seen[g] = { title: g, items: [] }; groups.push(seen[g]); }
      seen[g].items.push(it);
    });
    groups.sort(function (a, b) {
      const ia = GROUPS.indexOf(a.title), ib = GROUPS.indexOf(b.title);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });

    const html = groups.map(function (g) {
      const dots = STATES.filter(function (s) {
        return g.items.some(function (i) { return i['AI审核'] === s; });
      }).map(function (s) {
        const c = g.items.filter(function (i) { return i['AI审核'] === s; }).length;
        const col = { '存在问题': 'var(--au-danger)', '存在疑似问题': 'var(--au-warning)',
          '优化调整建议': 'var(--au-primary)', '无问题': 'var(--au-success)', '不适用': 'var(--au-hint)' }[s];
        return '<span class="au-meta"><i class="au-dot" style="background:' + col + '"></i>' + esc(s) + ' ' + c + '</span>';
      }).join('');
      return '<section class="au-group" data-g="' + esc(g.title) + '">' +
        '<header><span class="chev">▾</span><b>' + esc(g.title) + '</b>' +
        '<span class="cnt">' + g.items.length + ' 项</span><span class="au-mini">' + dots + '</span></header>' +
        '<div class="au-list">' + g.items.map(itemHTML).join('') + '</div></section>';
    }).join('');

    let extra = '';
    if (r['冲突'] && r['冲突'].length) {
      extra = '<div class="au-warnbox"><b>抽取输入冲突（正则与模型结论相反，已按带原文核验的模型值取值并留痕）</b>' +
        r['冲突'].map(function (c) {
          return '<div style="margin-top:5px">' + esc(c['输入']) + '：正则 ' + esc(c['正则']) +
            '（P' + esc(c['正则页码']) + '） / 模型 ' + esc(c['模型']) + '（P' + esc(c['模型页码']) + '）</div>';
        }).join('') + '</div>';
    }
    extra += '<details class="au-fold"><summary>判据输入与抽取明细（点开核对）</summary><pre>' +
      esc(JSON.stringify({
        判据输入: r['判据输入'], 报告自述: r['报告自述'], 专项评价自述: r['专项评价自述'],
        抽取概况: r['抽取概况'],
        风险物质: (r['抽取明细'] || {})['风险物质'], 物料: (r['抽取明细'] || {})['物料']
      }, null, 1)) + '</pre></details>';

    body.innerHTML = html + extra;
    btnSave.disabled = false; setDeliv(true);
  }

  /* bind() 是**两个视图共用**的绑定：统计卡片的筛选、以及人工复核的
     select/input（清单视图与批注视图里都有 data-human / data-note，
     所以填写逻辑只写这一处）。视图各自的绑定在 audit_doc.js 内部。 */
  function bind() {
    body.querySelectorAll('.au-evtog').forEach(function (t) {
      t.onclick = function () {
        const box = t.parentNode.querySelector('.au-evis');
        const open = box.style.display !== 'none';
        box.style.display = open ? 'none' : 'block';
        t.textContent = open ? '▸ 展开证据' : '▾ 收起证据';
      };
    });
    body.querySelectorAll('.au-group > header').forEach(function (h) {
      h.onclick = function () { h.parentNode.classList.toggle('fold'); };
    });
    summary.querySelectorAll('[data-filter]').forEach(function (c) {
      c.onclick = function () {
        state.filterState = (state.filterState === c.dataset.filter) ? '' : c.dataset.filter;
        render();
      };
    });
    body.querySelectorAll('select[data-human], input[data-note]').forEach(function (n) {
      /* oninput 也绑上：批注视图切换页码时会重建批注卡，如果只在 change（失焦）时才写回
         state.review，**正在输入但还没失焦的那几个字会被一起丢掉**（不报错，用户重进才发现）。 */
      n.onchange = function () { markChanged(n); };
      n.oninput = function () { markChanged(n); };
    });
  }

  function markChanged(node) {
    const k = node.dataset.human || node.dataset.note;
    /* 以**当前编辑的这个节点所在的卡片**为准。
       不能再用 body.querySelector('select[data-human="…"]')：批注视图里
       同一个审核项会有多张卡（一条证据一张），那样永远读回第一张卡的值 ——
       用户改第二张、保存下去的是第一张的内容，而且界面回显还是他自己改的，
       看不出错。 */
    const card = node.closest('.au-note') || node.closest('.au-item') || body;
    const sel = node.dataset.human ? node : card.querySelector('select[data-human]');
    const note = node.dataset.note ? node : card.querySelector('input[data-note]');
    state.review[k] = { '人工修改': sel ? sel.value : '', '备注': note ? note.value : '' };
    /* 「全部批注」模式下同一审核项的几张卡会同屏，把兄弟卡的回显一起跟上，
       免得一屏之内两处显示的值不一样（用户只能猜哪个算数）。 */
    body.querySelectorAll('select[data-human], input[data-note]').forEach(function (m) {
      if (m === node) return;
      if (m.dataset.human === k && sel) m.value = sel.value;
      if (m.dataset.note === k && note) m.value = note.value;
    });
  }

  /* ------------------------------------------------------------ 保存 / 导出 */
  function save() {
    const items = {};
    Object.keys(state.review).forEach(function (k) {
      const v = state.review[k] || {};
      if (v['人工修改'] || v['备注']) items[k] = { '人工修改': v['人工修改'] || '', '备注': v['备注'] || '' };
    });
    if (!Object.keys(items).length) { setStatus('还没有填写复核结论'); return; }
    btnSave.disabled = true;
    req(API + '/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: state.name, items: items })
    }).then(function (r) {
      btnSave.disabled = false;
      if (!r || !r.ok) throw new Error((r && r.error) || '保存失败');
      setStatus('已保存 ' + r.saved + ' 项复核');
      return loadReview().then(render);
    }).catch(function (e) { btnSave.disabled = false; setStatus('失败：' + ((e && e.message) || e)); });
  }

  function exportAs(fmt) {
    req(API + '/export/' + enc(state.name) + '?fmt=' + fmt)
      .then(function (r) {
        if (!r || !r.ok) throw new Error((r && r.error) || '导出失败');
        const a = document.createElement('a');
        a.href = API + '/download/' + enc(r.file);
        a.download = r.file; a.click();
        setStatus('已导出 ' + r.file);
      }).catch(function (e) { setStatus('失败：' + ((e && e.message) || e)); });
  }

  /* 生成交付件（内部用）：返回 Promise，resolve 服务端返回体。 */
  function buildDelivery(kind) {
    const pdf = kind === 'pdf';
    /* 写成两个带字面量的分支，而不是 `API + (pdf ? A : B)`：
       前端契约测试是按"API 常量拼一个字符串字面量"扫接口的，写成三目就扫不到这两个接口了
       （扫不到 = 没人再保证它们和路由对得上）。 */
    const url = pdf ? API + '/export_pdf/' + enc(state.name)
      : API + '/export_docx/' + enc(state.name);
    setStatus(pdf ? '正在生成批注版 PDF…（正文批注＋汇总页，大报告要几十秒）'
      : '正在生成审核意见书…');
    return req(url).then(function (r) {
      if (r && r.need_parse) throw new Error('这份报告还没有解析缓存，请先在「原文批注」视图里打开一次');
      if (!r || !r.ok) throw new Error((r && (r.error || r.message)) || '生成失败');
      setStatus('已生成 ' + r.file + (r['汇总页'] ? '（含 ' + r['汇总页'] + ' 页审核意见汇总）' : ''));
      return r;
    });
  }

  function exportDelivery(kind) {
    buildDelivery(kind).then(function (r) {
      const a = document.createElement('a');
      a.href = API + '/download/' + enc(r.file);
      a.download = r.file; a.click();
      return null;
    }).catch(function (e) { setStatus('失败：' + ((e && e.message) || e)); });
  }

  /* 网页内预览（2026-09-22 用户问「这个没办法在网页中预览吗」）：
     · 批注版 PDF —— 浏览器自带阅读器内联显示（站点回原文 PDF 用的就是这条路）；
     · 审核意见书 —— docx 浏览器打不开，服务端另渲染一份"网页预览版"（内容同源）。
     先问一句交付件是不是最新的：是最新的就直接开（秒开）；过期或还没生成才重新生成。
     不这么做的话，每次点"预览"都要等 40 秒（大报告的批注版 PDF），用户会以为坏了。 */
  function previewDelivery(kind) {
    const pdf = kind === 'pdf';
    setStatus('正在检查交付件…');
    req(API + '/deliv/' + enc(state.name)).then(function (d) {
      const cur = d && d[kind];
      if (cur && !cur.stale) return null;          // 已是最新，直接打开
      return buildDelivery(kind);                  // 没有或过期：重新生成（会提示在等什么）
    }).then(function () {
      const url = pdf ? API + '/preview_pdf/' + enc(state.name)
        : API + '/preview_docx/' + enc(state.name);
      openPreview(pdf ? '批注版 PDF（网页内预览）' : '审核意见书（网页预览版）', url,
        pdf ? '批注可点开；若浏览器不显示 PDF，用右上角「新标签页打开」或直接下载。'
          : '这是网页预览版，与下载的 .docx 内容相同；可直接「打印 / 另存为 PDF」。');
      setStatus('预览已打开（' + (pdf ? '批注版 PDF' : '审核意见书') + '）');
      return null;
    }).catch(function (e) { setStatus('失败：' + ((e && e.message) || e)); });
  }

  /* ------------------------------------------------------------ 预览弹层 */
  function openPreview(title, url, hint) {
    const box = $('#auPreview');
    $('#auPreviewTitle').textContent = title;
    $('#auPreviewHint').textContent = hint || '';
    $('#auPreviewOpen').href = url;
    $('#auPreviewFrame').src = url;
    box.classList.add('on');
  }
  function closePreview() {
    $('#auPreviewFrame').src = 'about:blank';   // 停掉里面的加载/渲染
    $('#auPreview').classList.remove('on');
  }

  /* ------------------------------------------------------------ 事件 */
  pick.onchange = function () {
    /* 改动前这里只改 state.name，**没有 clearInterval(state.timer)、没有复位
       state.running、没有清 state.job**：正在跑的旧任务结束时会把**上一份报告的
       j.result** 渲染到新报告名下（点保存会被服务端 400 拦下，但界面在此之前
       已经把 A 的结论挂在 B 名下），而且 state.running 仍是 true，
       用户没法为新报告重新发起审核，只能干等旧任务跑完。 */
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.running = false; state.job = null; btnRun.disabled = false;
    state.name = pick.value; state.result = null; state.filterState = '';
    /* 换了报告，批注包与页缓存必须一起作废 —— 否则会把上一份报告的批注
       画在新报告的原文上（和 09-18 修掉的"结论张冠李戴"是同一类错误）。
       页码也归零：归零后批注视图会落在新报告的"第一条待复核问题"上。 */
    docView.reload();
    /* 换到一份**审过的**报告时把它的结果读回来 —— 与启动路径同一处理。
       漏了这一步的话（第一版就漏了，真机一测才发现）：切换到已审核的报告
       只会显示"选一份报告，点开始审核"的空状态，得重跑几十分钟才能看批注。 */
    showEmpty();
    loadReview().then(function () { return loadExistingResult(); });
  };
  btnRun.onclick = run;
  btnSave.onclick = save;
  btnCsv.onclick = function () { exportAs('csv'); };
  btnJson.onclick = function () { exportAs('json'); };
  btnPvPdf.onclick = function () { previewDelivery('pdf'); };
  btnExpPdf.onclick = function () { exportDelivery('pdf'); };
  btnPvDocx.onclick = function () { previewDelivery('docx'); };
  btnExpDocx.onclick = function () { exportDelivery('docx'); };
  $('#auPreviewClose').onclick = closePreview;
  /* 弹层背景点击关闭；Esc 也关（否则键盘用户只能去点那个小按钮） */
  $('#auPreview').onclick = function (ev) { if (ev.target === this) closePreview(); };
  root.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') closePreview();
  });
  $('#auNeed').onchange = function () { state.onlyNeed = this.checked; if (state.result) render(); };
  $('#auEvi').onchange = function () { state.eviAll = this.checked; if (state.result) render(); };

  const handle = {
    element: root,
    state: state,
    reload: function () { return loadReports(); },
    run: run,
    render: render,
    destroy: function () {
      clearInterval(state.timer);
      root.innerHTML = ''; root.classList.remove('au-shell');
      delete root.__au;
    }
  };
  root.__au = handle;
  showEmpty();
  loadReports();
  return handle;
}
