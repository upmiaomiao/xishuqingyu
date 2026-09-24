/* 报告编制 · 可挂载模块
 *
 * 与「报告审核」同一套做法：ES 模块，导出 mountGenUI(容器) 与 setEmbedded(on)，由宿主页面决定挂到哪儿。
 * 同一份代码既能**嵌进问答页**（点侧栏按钮切视图，不跳转），也能独立页 /gen 用。
 *
 * 版式：**左边输入、右边过程与成稿**，右上角「历史报告」按钮看以前生成的稿子。
 *   ┌ 顶栏：标题 …… [历史报告] [就绪状态] ┐
 *   │ 左：说 / 问 / 答 / 已确认事实 │ 右：生成过程 + 结果 + 成稿预览 + 下载 │
 *   └ 脚注 ┘
 *
 * 约定：
 *   · 挂载是**幂等**的（容器上打 data-ge-mounted，重复调用不会挂两份）；
 *   · 样式全部限定在 .ge-shell 内、类名 ge- 前缀，不污染宿主页面；
 *   · 独立页靠 body.ge-standalone 自动挂载；宿主页 `import` 后自己调 mountGenUI。
 *   · 嵌入时隐藏"返回问答/报告审核"这类跳转链接（宿主已有导航）与重复的大标题。
 *
 * 2026-09-18 重构（阶段 3）：由 IIFE 传统脚本改为 ES 模块，
 *   var 全部改为 const/let（AST 逐节点验证等价），
 *   挂载入口由 window.* 改为 export。
 */
const API = "/gen/api";
const $ = function (id) { return document.getElementById(id); };
let SID = null, polling = null, JOB = null, ROOT = null;
let OUT_FILES = [];          // 历史报告当前列表（按钮按下标取，文件名不进 HTML 属性）
let LOGN = 0;                // 「生成详情」里累计的日志条数（折叠着也要能看到有几条）
// 初始版式的快照（"新建报告"要把页面还原成刚打开的样子）
let INIT = null;

const TEMPLATE = [
  '<div class="ge-bar">',
  '  <div class="ge-title"><b>报告编制</b>',
  '    <span class="ge-sub">左侧描述项目，右侧查看判定过程与成稿</span></div>',
  '  <div class="ge-tools">',
  '    <a class="ge-link ge-crosslink" href="/" title="回到法规问答">← 返回问答</a>',
  '    <a class="ge-link ge-crosslink" href="/audit" title="报告审核">报告审核</a>',
  '    <button id="ge-new" class="ge-btn ge-btn-ghost" title="清空当前对话与右侧结果，重新开始一份">新建报告</button>',
  '    <button id="ge-history" class="ge-btn ge-btn-ghost">历史报告 ',
  '      <span id="ge-hcount" class="ge-pill">0</span></button>',
  '    <span id="ge-health" class="ge-health">检查中…</span>',
  '  </div>',
  '</div>',
  '<main class="ge-main">',
  '  <section class="ge-left">',
  '    <div class="ge-chat">',
  '      <div class="ge-chat-body">',
  '        <div id="ge-stream" class="ge-stream">',
  '          <div class="ge-sys">',
  '            <p class="ge-sys-h">用一段话描述项目，无需逐项填表</p>',
  '            <p>请说明项目名称与所属行业、建设地点、生产规模、总投资，以及废气、废水、噪声等产污环节和周边环境敏感目标。',
  '               信息可以不全 —— <strong>未提及的会逐项询问；仍未提供的，报告中标注「需人工补充」，不作推测。</strong></p>',
  '            <button id="ge-demo" class="ge-btn ge-btn-ghost">换一个示例</button>',
  '            <span id="ge-demo-n" class="ge-hint">共 5 个虚构示例，每次点击换一条</span>',
  '          </div>',
  '        </div>',
  '        <div id="ge-ask" class="ge-ask"></div>',
  '        <div id="ge-mine" class="ge-mine"></div>',
  '      </div>',
  '      <div class="ge-compose">',
  '        <textarea id="ge-say" class="ge-input ge-say" rows="3"',
  '          placeholder="例如：我们公司要在××市××区建一台 20 吨/小时的生物质锅炉给生产线供蒸汽，属于技术改造……（回车发送，Shift+回车换行）"></textarea>',
  '        <div class="ge-compose-bar">',
  '          <button id="ge-send" class="ge-btn ge-btn-main">发送</button>',
  '          <label class="ge-check"><input type="checkbox" id="ge-model" checked> 正文由模型撰写</label>',
  '          <label class="ge-check" title="跳过缓存、换一版措辞；代价是这一版不保证与上次字节一致">',
  '            <input type="checkbox" id="ge-fresh"> 重新生成（换一版措辞）</label>',
  '          <button id="ge-gen" class="ge-btn ge-btn-ghost" disabled>直接生成报告</button>',
  '        </div>',
  '      </div>',
  '    </div>',
  '  </section>',
  '  <section class="ge-right">',
  '    <div class="ge-card ge-card-flat">',
  '      <div class="ge-card-h">我了解到的事实 <span id="ge-count" class="ge-pill">0 项</span></div>',
  '      <div id="ge-known" class="ge-known"><div class="ge-empty">暂无信息，请在左侧描述项目。</div></div>',
  '      <div id="ge-drop" class="ge-drop"></div>',
  '    </div>',
  '    <div class="ge-card ge-card-flat" id="ge-dec-card" hidden>',
  '      <div class="ge-card-h">判定摘要 <span class="ge-hint">生成前先定档：纯代码判定，依据可回溯</span></div>',
  '      <div id="ge-dec" class="ge-dec"></div>',
  '      <div class="ge-dec-rule">报告按此判定撰写；判定为「未定」的项一律在成稿里标【需人工补充】，不会替您猜。</div>',
  '    </div>',
  '    <div class="ge-card ge-card-flat">',
  '      <div class="ge-card-h">生成过程 <span class="ge-hint">校验 → 判定 → 生成 → 自审</span></div>',
  // 进度条：与「报告审核」同一套观感。原先只有日志行，用户得自己数行猜进度。
  // 百分比是**固定档位**（走完第几步），不按时间估算 —— 各阶段耗时差太远，
  // 估出来的数字会一直骗人；档位至少诚实。
  '      <div id="ge-prog" class="ge-prog" hidden>',
  '        <div class="ge-prog-row">',
  '          <span id="ge-prog-stage" class="ge-prog-stage">准备中</span>',
  '          <span id="ge-prog-secs" class="ge-prog-secs">0.0s</span>',
  '        </div>',
  '        <div class="ge-prog-track"><div id="ge-prog-fill" class="ge-prog-fill"></div></div>',
  '      </div>',
  // C4（用户反馈「生成日志太长、希望折叠成"生成详情"、默认收起」）：
  //   ① **使用步骤**是首次使用的引导，不能跟着折叠 —— 挪出日志容器，常驻可见；
  //   ② 技术日志包进 <details>（不带 open = 默认收起），标题上带条数；
  //   ③ 出错的日志行会**自动展开**（失败了还得手动点开才知道为什么，那才是真的难用）。
  //   刻意**不折叠**进度条与结论：那两个是"当前状态"，折叠了等于藏信息。
  '      <div class="ge-guide">',
  '        <div class="ge-guide-t">使用步骤</div>',
  '        <ol class="ge-guide-l">',
  '          <li>在左侧描述项目情况，或点「换一个示例」参考写法。</li>',
  '          <li>回答左侧列出的问题；确实不了解的可选择跳过，报告中会标注「需人工补充」。</li>',
  '          <li>点「直接生成报告」，判定过程显示在此处，成稿可预览、可下载。</li>',
  '        </ol>',
  '      </div>',
  '      <details id="ge-logbox" class="ge-logbox">',
  '        <summary class="ge-logsum">生成详情 <span id="ge-logn" class="ge-hint">暂无日志</span></summary>',
  '        <div id="ge-log" class="ge-log"></div>',
  '      </details>',
  '      <div id="ge-result" class="ge-result"></div>',
  '    </div>',
  '    <div class="ge-card ge-card-flat" id="ge-preview-card" hidden>',
  '      <div class="ge-card-h">报告成稿',
  '        <span class="ge-hint">预览即交付件本身（由同一份 .docx 渲染）</span></div>',
  '      <div class="ge-prev-tools">',
  '        <a id="ge-dl" class="ge-dl" href="#" hidden>下载 Word</a>',
  '        <button id="ge-open" class="ge-btn ge-btn-ghost" hidden>在新窗口打开预览</button>',
  '      </div>',
  '      <iframe id="ge-prev" class="ge-prev" title="报告预览"></iframe>',
  '    </div>',
  '  </section>',
  '</main>',
  '<div id="ge-modal" class="ge-modal" hidden>',
  '  <div class="ge-modal-box">',
  '    <div class="ge-modal-h"><b>历史报告</b>',
  '      <button id="ge-mclose" class="ge-btn ge-btn-ghost">关闭</button></div>',
  '    <div id="ge-outputs" class="ge-outputs"><div class="ge-empty">加载中…</div></div>',
  '    <div class="ge-modal-f">草稿存放在服务器 <code>/data/eia_report_gen/_生成结果/</code>。',
  '      「归档」移出列表但保留文件，可找回；「删除」为永久删除，需二次确认。</div>',
  '  </div>',
  '</div>'
].join("\n");

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
/* ------------------------------------------------------------------ 错误解析
   改动前这两个函数各有一个毛病，合起来让"报错"变成"界面什么都不发生"：
     · post() 是**先 r.json() 再判 r.ok** —— 后端 500 回的是纯文本
       "Internal Server Error"，r.json() 当场抛 SyntaxError，
       `d.detail` 那一行根本执行不到，用户读到的是
       `Unexpected token 'I', "Internal S"... is not valid JSON`；
     · get() **连 r.ok 都不判** —— 404/500 的响应体被当成正常数据往下传，
       调用方 `if (!d.ok) return;` 静默返回，轮询就永远空转下去。
   现在统一：先拿原文 → 尝试解析 → 不是 JSON 就保留原文 → 最后才按 r.ok 判。
   后端已统一回 {ok:false, code, message, detail, request_id}，优先取 message；
   但仍要防住"响应体不是 JSON"（代理塞 HTML、网关 502、旧版后端）。
   `code` 保留在 Error 上，调用方需要按错误类型分支时用 e.code。 */
function errText(d, status) {
  if (d && typeof d === "object") {
    if (typeof d.message === "string" && d.message) return d.message;
    if (typeof d.detail === "string" && d.detail) return d.detail;
    if (Array.isArray(d.detail)) return "请求参数有误";      /* 旧版 422 的数组形状 */
    return "HTTP " + status;
  }
  if (typeof d === "string" && d.trim() && d.length <= 200) return d.trim();
  return "HTTP " + status;
}
function readBody(r) {
  return r.text().then(function (t) {
    if (!t) return null;
    try { return JSON.parse(t); } catch (e) { return t; }
  });
}
function httpErr(d, status) {
  const e = new Error(errText(d, status));
  e.code = (d && typeof d === "object" && d.code) || ("E_HTTP_" + status);
  e.status = status;
  e.requestId = (d && typeof d === "object" && d.request_id) || "";
  return e;
}
function post(path, body) {
  return fetch(API + path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).then(function (r) {
    return readBody(r).then(function (d) {
      if (!r.ok) throw httpErr(d, r.status);
      return d;
    });
  });
}
function get(path) {
  return fetch(API + path).then(function (r) {
    return readBody(r).then(function (d) {
      if (!r.ok) throw httpErr(d, r.status);
      return d;
    });
  });
}

function bubble(kind, head, text) {
  const box = $("ge-stream");
  const d = document.createElement("div");
  d.className = "ge-msg ge-" + kind;
  d.innerHTML = (head ? '<div class="ge-msg-h">' + esc(head) + "</div>" : "") + esc(text);
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

/* 等待气泡：接口是同步的，请求返回前拿不到任何中间信号，只能由客户端自己报。
 *
 * 为什么必须有：`POST /gen/api/chat/start` 实测 **12.31 秒**才返回 ——
 * 它要调一次模型把整段描述抽成字段。这 12 秒里原先只有"发送"按钮变灰，
 * 页面其他地方一动不动，看起来就是卡死。
 *
 * 模型调用是非流式的（gen/intake.py 的 _model_json 走 audit.llm.call_model），
 * 中途确实没有真实进度可报 —— 所以**不编造百分比**，只给：
 *   · 一句"在干什么"（说明为什么慢，比空转圈有用）
 *   · 一个**走动秒表**（证明进程还活着，这是关键）
 * 返回后把气泡换成真实结果。
 */
function waitBubble(what) {
  const d = bubble("ai ge-wait", "系统", what);
  const row = document.createElement("div");
  row.className = "ge-wait-row";
  row.innerHTML = '<span class="ge-spin">◐</span>' +
    '<span class="ge-wait-t">已用 <b class="ge-secs">0.0</b> 秒</span>';
  d.appendChild(row);
  const t0 = Date.now();
  const timer = setInterval(function () {
    const el = d.querySelector(".ge-secs");
    if (el) el.textContent = ((Date.now() - t0) / 1000).toFixed(1);
  }, 100);
  return {
    done: function (head, text) {
      clearInterval(timer);
      d.className = "ge-msg ge-ai";
      d.innerHTML = (head ? '<div class="ge-msg-h">' + esc(head) + "</div>" : "") + esc(text);
    },
    fail: function (text) {
      clearInterval(timer);
      d.className = "ge-msg ge-note";
      d.innerHTML = '<div class="ge-msg-h">出错了</div>' + esc(text);
    },
  };
}

function health() {
  get("/health").then(function (d) {
    const el = $("ge-health");
    if (!el) return;
    if (!d.ok) { el.textContent = "引擎异常：" + (d.error || ""); el.className = "ge-health ge-bad"; return; }
    el.textContent = "就绪 · 字段 " + d.字段数 + " · Word " + (d.docx || "?");
    el.className = "ge-health";
  }).catch(function (e) {
    const el = $("ge-health");
    if (el) { el.textContent = "连不上：" + e; el.className = "ge-health ge-bad"; }
  });
}

// ---------------- 左栏：已确认事实 / 问题 ----------------

function renderKnown(v) {
  $("ge-count").textContent = (v.已知 || []).length + " 项";
  const box = $("ge-known");
  if (!(v.已知 || []).length) { box.innerHTML = '<div class="ge-empty">暂无信息。</div>'; }
  else {
    box.innerHTML = v.已知.map(function (r) {
      return '<div class="ge-k-row"><span class="ge-k-key">' + esc(r.字段) + "</span>" +
             '<span class="ge-k-val">' + esc(r.值) + "</span></div>";
    }).join("");
  }
  const dropped = (v.丢弃 || []).filter(function (d) { return d && d.原因; });
  const db = $("ge-drop");
  if (!dropped.length) { db.innerHTML = ""; return; }
  /* 2026-09-22 用户反馈 C1：「提问未采信内容时，回答后没有更新或者下一步／每个问题
   * 后面直接给操作按钮："去补充信息"」。
   * 所以每条未采信都配一个按钮：点了就把**对应问题**（按字段名匹配）滚到眼前并聚焦输入框，
   * 实在找不到对应问题时退回主输入框，并把"上次为什么没被采信"提示出来 ——
   * 让用户知道下一步该补什么，而不是只看到一句"未采信"。 */
  db.innerHTML = '<div class="ge-drop-h">未采信内容（缺少依据的不写入报告）</div>' +
    dropped.slice(-6).map(function (d) {
      return '<div class="ge-drop-row"><b>' + esc(d.字段) + "</b>：" + esc(d.原因) +
        '<button class="ge-btn ge-btn-mini ge-drop-go" data-field="' + esc(d.字段) +
        '">去补充信息</button></div>';
    }).join("");
  Array.prototype.forEach.call(db.querySelectorAll(".ge-drop-go"), function (b) {
    /* 未采信条目里给的是**字段中文名**，不是 key（key 是 schema 字段名，如
     * 专项用事实_地下水）。所以必须当"中文名"传第二个参数去匹配问题卡；
     * 第一版误当 key 传，结果永远匹配不上、默默退回主输入框 —— 真机测试第 [5] 条抓到的。 */
    b.addEventListener("click", function () { goSupplement("", b.getAttribute("data-field")); });
  });
}

/* ---------------- C1/C2：补充内容的"落点" ----------------
 *
 * 用户反馈两条是同一个病根：
 *   C2「采信问题保持在底部，导致发送的补充内容会出现在上方会忽略」
 *     —— 回答问题时，答案被塞进**上方**的聊天流（bubble("me", …)），
 *        而问题列表在**下方**；两者隔着一屏，答案看起来就"飘走了"。
 *   C1「每个问题后面直接给操作按钮：去补充信息」
 *     —— 未被采信时，用户不知道该去哪儿补。
 *
 * 修法（都在前端，不动判定链路）：
 *   ① 每次回答都记进 MINE，并在**问题列表正下方**渲染"我补充过的内容"，
 *      带「已采信／未采信」徽标和原因 —— 补充内容从此留在原地，不再只往上飘；
 *   ② 每个问题卡、每条未采信、每条补充记录都配「去补充信息」按钮，
 *      点击=滚动到该问题并聚焦输入框（找不到就退回主输入框并给出提示）；
 *   ③ 聊天流里的"我"气泡带上它回答的是哪个问题，避免对不上号。
 */
const MINE = [];
const ANSWERED = {};

function shortQ(s, n) {
  s = String(s || "");
  return s.length > (n || 22) ? s.slice(0, n || 22) + "…" : s;
}

function renderMine() {
  const box = $("ge-mine");
  if (!box) return;
  if (!MINE.length) { box.innerHTML = ""; return; }
  box.innerHTML = '<div class="ge-mine-h">我补充过的内容（最近 ' +
    Math.min(MINE.length, 5) + " 条）</div>" +
    MINE.slice(-5).reverse().map(function (m, i) {
      const ok = m.采纳;
      return '<div class="ge-mine-row' + (i === 0 ? " ge-mine-new" : "") + '" data-key="' +
        esc(m.key || "") + '">' +
        '<span class="ge-tag ' + (ok ? "ge-tag-ok" : "ge-tag-bad") + '">' +
        (ok ? "已采信" : "未采信") + "</span>" +
        '<span class="ge-mine-q">' + esc(shortQ(m.问题)) + "</span>" +
        '<span class="ge-mine-a">' + esc(shortQ(m.答, 30)) + "</span>" +
        (ok ? "" : '<span class="ge-mine-why">' + esc(shortQ(m.说明, 26)) + "</span>") +
        '<button class="ge-btn ge-btn-mini ge-mine-go">去补充信息</button></div>';
    }).join("");
  Array.prototype.forEach.call(box.querySelectorAll(".ge-mine-go"), function (b) {
    b.addEventListener("click", function () {
      const row = b.parentNode;
      goSupplement(row.getAttribute("data-key"), row.querySelector(".ge-mine-q").textContent);
    });
  });
}

/** 把用户送到"该补充的地方"：优先对应问题卡的输入框，其次主输入框。 */
function goSupplement(key, name) {
  const cards = document.querySelectorAll("#ge-ask .ge-q");
  for (let i = 0; i < cards.length; i++) {
    const c = cards[i];
    if ((key && c.getAttribute("data-key") === key) ||
        (name && c.getAttribute("data-name") === name)) {
      const inp = c.querySelector("input");
      if (c.scrollIntoView) c.scrollIntoView({ behavior: "smooth", block: "center" });
      c.classList.add("ge-q-flash");
      setTimeout(function () { c.classList.remove("ge-q-flash"); }, 1600);
      if (inp) { inp.focus(); inp.select && inp.select(); }
      return true;
    }
  }
  const say = $("ge-say");
  if (say) {
    if (say.scrollIntoView) say.scrollIntoView({ behavior: "smooth", block: "center" });
    say.classList.add("ge-q-flash");
    setTimeout(function () { say.classList.remove("ge-q-flash"); }, 1600);
    say.focus();
  }
  return false;
}

function renderQuestions(v) {
  const box = $("ge-ask");
  box.innerHTML = "";
  const qs = v.问题 || [];
  if (!qs.length) {
    if (SID) {
      box.innerHTML = '<div class="ge-q"><div class="ge-q-t">该问的都问过了。</div>' +
        '<div class="ge-q-w">还有 ' + (v.还剩 || 0) + " 项可以选择性补充；" +
        '现在就可以生成报告，没提供的会逐项标注。</div></div>';
    }
    $("ge-gen").disabled = !SID;
    return;
  }
  qs.forEach(function (q, i) {
    const d = document.createElement("div");
    d.className = "ge-q";
    d.setAttribute("data-key", q.key || "");
    d.setAttribute("data-name", q.中文名 || "");
    const prev = ANSWERED[q.key];
    d.innerHTML =
      '<div class="ge-q-t">' + (i + 1) + ". " + esc(q.问题) + "</div>" +
      '<div class="ge-q-w">为什么问：' + esc(q.为什么问 || "报告表需要") + "</div>" +
      (prev ? '<div class="ge-q-state ' + (prev.采纳 ? "ok" : "bad") + '">' +
        (prev.采纳 ? "已采信：" : "上次未被采信：") +
        esc(shortQ(prev.说明, 60)) + "</div>" : "") +
      '<div class="ge-q-row">' +
        '<input class="ge-input" type="text" placeholder="直接回答；不知道就点右边「不知道」">' +
        '<button class="ge-btn ge-ans">回答</button>' +
        '<button class="ge-btn ge-btn-ghost ge-skip">不知道</button>' +
        '<button class="ge-btn ge-btn-ghost ge-go">去补充信息</button>' +
      "</div>";
    const input = d.querySelector("input"), ans = d.querySelector(".ge-ans"),
        skip = d.querySelector(".ge-skip"), go = d.querySelector(".ge-go");
    /* 2026-09-22 排查 C1「回答后没有更新」时挖出来的**真 bug**：
     * 这里原本写成 `const input = …, ans = …, skip = …, busy = false;`，
     * 而下面 `busy = true;` 要给 const 赋值 —— JS 必抛
     *   TypeError: Assignment to constant variable
     * 且抛出点在 click/回车处理器里，**请求根本发不出去、页面毫无反应**：
     * 这正是用户看到的"回答后没有更新"。改成 let 才能真正发出去。
     * 症状与修法的真机证据见 看补充信息按钮.js 的前后两次运行。 */
    let busy = false;
    if (prev && prev.答) input.value = prev.答;
    go.addEventListener("click", function () {
      if (d.scrollIntoView) d.scrollIntoView({ behavior: "smooth", block: "center" });
      d.classList.add("ge-q-flash");
      setTimeout(function () { d.classList.remove("ge-q-flash"); }, 1600);
      input.focus();
    });

    function done(msg) {
      d.querySelector(".ge-q-row").innerHTML = '<span class="ge-q-done">' + esc(msg) + "</span>";
    }
    function send(kind) {
      if (busy) return;
      busy = true; ans.disabled = skip.disabled = true;
      const path = kind === "answer" ? "/chat/answer" : "/chat/skip";
      post(path, { session: SID, key: q.key, 中文名: q.中文名, 类型: q.类型,
                   事实名: q.事实名, 问题: q.问题, text: input.value })
        .then(function (r) {
          if (kind === "answer") {
            ANSWERED[q.key] = { 答: input.value, 采纳: !!r.采纳, 说明: r.本次 || "" };
            MINE.push({ key: q.key, 问题: q.问题, 答: input.value,
                        采纳: !!r.采纳, 说明: r.本次 || "" });
            // 气泡带上"回答的是哪个问题"：否则答案飘在聊天流里，和下方问题对不上号（C2）
            bubble("me", "我（回答：" + shortQ(q.问题) + "）", input.value);
          }
          bubble("ai", "系统", r.本次 || "已记录");
          done(r.本次 || "已记录");
          renderKnown(r);
          renderMine();
          setTimeout(function () { renderQuestions(r); }, 30);
          // 更新要出现在用户刚刚操作的地方（底部），而不是只在上面留个气泡
          const box = $("ge-mine");
          if (box && box.scrollIntoView) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
        })
        .catch(function (e) {
          done("失败：" + e.message); busy = false;
          ans.disabled = skip.disabled = false;
        });
    }
    ans.addEventListener("click", function () { send("answer"); });
    skip.addEventListener("click", function () { input.value = "不知道"; send("skip"); });
    // 2026-09-22 用户反馈：「用鼠标点发送太麻烦，希望能直接回车」。
    // 两个细节必须一起做，否则中文输入法会发半截话：
    //   ① ev.isComposing / keyCode 229 —— 拼音候选框上按回车是"选词"，不是"发送"；
    //   ② shiftKey —— Shift+回车留给换行（与问答页一致）。
    input.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" || ev.shiftKey) return;
      if (ev.isComposing || ev.keyCode === 229) return;
      ev.preventDefault();
      send("answer");
    });
    box.appendChild(d);
  });
  $("ge-gen").disabled = false;
}

// ---------------- 动作 ----------------

function startChat(text) {
  $("ge-send").disabled = true;
  bubble("me", "我", text);
  // 这一步要调模型把描述抽成字段，实测 12s 上下，期间没有任何服务端信号可收
  const w = waitBubble("正在读你写的项目情况：抽取可核验的事实、核对原文依据。" +
    "这一步要调一次模型，通常十几秒；下面的秒表在走就说明没卡住。");
  post("/chat/start", { text: text }).then(function (r) {
    SID = r.session;
    w.done("系统", "我从这段话里读到 " + r.采纳数 + " 项信息" +
      (r.丢弃数 ? "，另有 " + r.丢弃数 + " 处没依据的内容我没有采信（左下角列出）。" : "。") +
      "接下来问你 " + (r.问题 || []).length + " 个问题。");
    renderKnown(r);
    renderQuestions(r);
    $("ge-send").disabled = false;
    $("ge-say").value = "";
    $("ge-gen").disabled = false;
  }).catch(function (e) {
    w.fail(e.message);
    $("ge-send").disabled = false;
  });
}

function runJob() {
  $("ge-preview-card").hidden = true;
  $("ge-log").innerHTML = "";
  LOGN = 0;
  if ($("ge-logn")) $("ge-logn").textContent = "暂无日志";
  // 上一轮的判定摘要不能挂在新任务上：先收起来，等这一轮的②判定回来再显示
  if ($("ge-dec-card")) $("ge-dec-card").hidden = true;
  if ($("ge-dec")) $("ge-dec").innerHTML = "";
  $("ge-result").innerHTML = "";
  // 进度条先藏起来，免得上一轮的 100% 还挂在那儿（新任务还没开始就显示"已完成"）
  if ($("ge-prog")) $("ge-prog").hidden = true;
  const fresh = !!($("ge-fresh") && $("ge-fresh").checked);
  post("/chat/generate", { session: SID, model: $("ge-model").checked, fresh: fresh })
    .then(function (r) {
      JOB = r.job;
      log("提交", "生成任务 " + r.job + "（模型撰写：" + ($("ge-model").checked ? "开" : "关") +
        (fresh ? "，重新生成：忽略缓存" : "") + "）");
      poll();
    }).catch(function (e) { log("失败", e.message, "error"); });
}

function log(step, text, level) {
  const box = $("ge-log");
  const div = document.createElement("div");
  div.className = "ge-line" + (level ? " ge-" + level : "");
  div.innerHTML = '<span class="ge-step">[' + esc(step) + ']</span> <span class="ge-txt">' +
    esc(text) + "</span>";
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  LOGN += 1;
  const n = $("ge-logn");
  if (n) n.textContent = "共 " + LOGN + " 条";
  // 出错必须让人看见：日志折叠着的时候，失败原因等于被藏起来了
  if (level === "error" && $("ge-logbox")) $("ge-logbox").open = true;
}

/* 进度条：阶段 + 第几步 + 已用秒数，与「报告审核」观感一致。
 *
 * 百分比只表示**走完了几步**，不表示"还剩多久"—— ①校验/②判定 是纯代码毫秒级就过，
 * ③生成 要调模型、占九成时间，所以按时间估的数字必然骗人。
 * 真正诚实的信号是那个走动的秒表。 */
function setProgress(stage, pct, secs, step, steps) {
  const box = $("ge-prog");
  if (!box) return;
  box.hidden = false;
  const no = step && steps ? "（第 " + step + "/" + steps + " 步）" : "";
  $("ge-prog-stage").textContent = (stage || "生成中") + no;
  $("ge-prog-secs").textContent = (secs || 0).toFixed(1) + "s";
  $("ge-prog-fill").style.width = Math.max(2, Math.min(100, pct || 4)) + "%";
}

/* 停止轮询并明确告诉用户为什么。
   改动前 poll() 里**根本没有停止条件**：请求失败时 rejection 无人接管，
   `if (!d.ok) return;` 又是静默返回，于是 setInterval 每 1.5 秒空转一次，
   进度条和秒表冻结在最后一格、日志不再增长 —— 用户只会以为"还在生成"。 */
function stopPolling(msg) {
  clearInterval(polling);
  polling = null;
  if (msg) log("失败", msg, "error");
  if ($("ge-prog")) $("ge-prog").hidden = true;
}

function poll() {
  clearInterval(polling);
  let seen = 0;
  let fails = 0;
  const t0 = Date.now();
  const MAX_MS = 30 * 60 * 1000;      /* 30 分钟还没结束就当异常，不再无限空转 */
  polling = setInterval(function () {
    if (Date.now() - t0 > MAX_MS) {
      stopPolling("生成任务超过 30 分钟仍未结束，已停止等待。产物可到「历史报告」里查看。");
      return;
    }
    get("/job/" + JOB).then(function (d) {
      fails = 0;
      const j = d && d.job;
      if (!j) {
        /* 200 但缺 job 字段：改动前这里 `j.log` 会抛 TypeError，
           而那是在 setInterval 回调里、没有 catch，于是每一轮都抛一次、永不停止。 */
        stopPolling("服务端没有返回任务详情，已停止等待");
        return;
      }
      (j.log || []).slice(seen).forEach(function (l) { log(l.step, l.text, l.level); });
      seen = (j.log || []).length;
      setProgress(j.stage, j.pct, j.secs, j.step, j.steps);
      if (j.判定) renderDec(j.判定);          /* C6：判定一到就显示，不等生成完 */
      if (j.status === "done" || j.status === "rejected" || j.status === "failed") {
        clearInterval(polling);
        polling = null;
        if (j.status === "failed") log("失败", j.error || "未知错误", "error");
        setProgress(j.status === "done" ? "已完成" : "已结束", 100, j.secs, null, null);
        renderResult(j);
        if (j.status === "done") showPreview(j);
        loadOutputs();
      }
    }).catch(function (e) {
      /* 任务真的没了（404）就别再等了；网络抖动忍三次再说 */
      fails += 1;
      if ((e && e.status === 404) || fails >= 3) {
        stopPolling((e && e.status === 404 ? "任务不存在或已过期：" : "连续取不到任务状态，已停止等待：")
          + ((e && e.message) || e));
      }
    });
  }, 1500);
}

// C6（用户反馈「生成过程看不到当前判定」）：只读的「判定摘要」卡片。
// 服务端在②判定一做完就把 判定 塞进任务（不等 done），这里每轮轮询刷新。
// 刻意做成**只读**：判定结果由判据库+代码给出，界面不给改的入口，
// 要改就去补事实（事实补齐后重跑，判定自然跟着变）。
function renderDec(d) {
  const card = $("ge-dec-card"), box = $("ge-dec");
  if (!card || !box || !d) return;
  const c = d.名录 || {}, sp = (d.专项评价 || {}).要素 || [];
  const secs = d.章节 || [];
  const filled = secs.reduce(function (n, s) { return n + (s.已填字段 || 0); }, 0);
  const total = secs.reduce(function (n, s) { return n + (s.字段数 || 0); }, 0);
  const setSpecial = sp.filter(function (r) { return r.set_special === true; });
  const undecided = sp.filter(function (r) { return r.status === "unknown"; });
  const manual = d.需人工确认 || [];
  const h = [];
  h.push('<div class="ge-dec-row"><b>名录档级</b><span class="ge-pill' +
    (c.tier ? "" : " ge-warn") + '">' + esc(c.tier || "未定") + "</span>" +
    (c.decided === false && c.倾向档位 ? '<span class="ge-hint">倾向 ' + esc(c.倾向档位) +
      "，事实不足</span>" : "") + "</div>");
  if (c.名录序号 || c.名录条目) {
    h.push('<div class="ge-dec-row"><b>命中条目</b><span>序号 ' + esc(c.名录序号 || "-") + " " +
      esc(c.名录条目 || "") + "</span></div>");
  }
  h.push('<div class="ge-dec-row"><b>专项评价</b><span>' +
    (setSpecial.length ? "应设 " + esc(setSpecial.map(function (r) { return r.element; }).join("、"))
      : "无需设置") + "</span>" +
    (undecided.length ? '<span class="ge-hint">未定 ' +
      esc(undecided.map(function (r) { return r.element; }).join("、")) + "</span>" : "") + "</div>");
  h.push('<div class="ge-dec-row"><b>章节清单</b><span>' + secs.length + " 节，已填字段 " +
    filled + "/" + total + "</span></div>");
  h.push('<div class="ge-dec-row"><b>标准候选</b><span>' + (d.标准候选 || []).length +
    ' 个</span><span class="ge-hint">语料共现，须人工核定</span></div>');
  if (manual.length) {
    h.push('<div class="ge-dec-row ge-warn"><b>需人工补充</b><span>' +
      esc(manual.slice(0, 6).join("；")) + (manual.length > 6 ? " 等 " + manual.length + " 项" : "") +
      "</span></div>");
  }
  box.innerHTML = h.join("");
  card.hidden = false;
}

function renderResult(j) {
  const box = $("ge-result"), h = [];
  if (j.status === "rejected") {
    box.innerHTML = '<span class="ge-pill">校验未通过，未生成</span>' +
      "<p>缺什么已在上面逐条列出。补全后重试。</p>";
    return;
  }
  if (j.status !== "done") return;
  const d = j.判定 || {}, c = d.名录 || {}, a = j.自审 || {};
  h.push('<div class="ge-kv">');
  h.push('<span class="ge-pill">' + esc(c.tier || "档级未定") + "</span>");
  h.push("<span>名录序号 " + esc(c.名录序号) + " " + esc(c.名录条目 || "") + "</span>");
  h.push("<span>标准候选 " + ((d.标准候选 || []).length) + " 个（须人工核定）</span>");
  h.push('<span class="ge-pill' + ((a.分布 || {})["存在问题"] ? " ge-err" : "") + '">自审 ' +
    esc(a.适用项数 || 0) + " 项：" + esc(JSON.stringify(a.分布 || {})) + "</span>");
  h.push("</div>");
  if ((a.需注意 || []).length) {
    h.push("<table class='ge-table'><tr><th>自审结论</th><th>审核项</th><th>说明</th></tr>");
    a.需注意.forEach(function (it) {
      h.push("<tr><td>" + esc(it.状态) + "</td><td>" + esc(it.审核项) + "</td><td>" +
        esc((it.理由 || "").slice(0, 150)) + "</td></tr>");
    });
    h.push("</table>");
  }
  box.innerHTML = h.join("");
}

function showPreview(j) {
  $("ge-preview-card").hidden = false;
  $("ge-prev").src = API + "/preview/" + j.id;
  const dl = $("ge-dl");
  dl.hidden = false;
  dl.href = API + "/download/" + j.id;
  dl.textContent = "下载 Word（" + Math.round((j.size || 0) / 1024) + " KB）";
  const op = $("ge-open");
  op.hidden = false;
  op.onclick = function () { window.open(API + "/preview/" + j.id, "_blank"); };
  bubble("ai", "系统", "报告草稿已生成（" + Math.round((j.size || 0) / 1024) +
    " KB），可在右栏预览并下载 Word。");
  const card = $("ge-preview-card");
  if (card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------- 右上角：以前的生成报告 ----------------

function loadOutputs() {
  return get("/outputs").then(function (d) {
    const box = $("ge-outputs"), n = (d.ok && (d.files || []).length) || 0;
    if ($("ge-hcount")) $("ge-hcount").textContent = n;
    if (!box) return;
    // 记住这一份列表：按钮只带下标，文件名不写进 HTML ——
    // 文件名可能含引号，拼进 data-* 属性会被截断（也就成了注入面）
    OUT_FILES = (d.ok && d.files) || [];
    if (!n) { box.innerHTML = '<div class="ge-empty">还没有生成过报告。</div>'; return; }
    box.innerHTML = OUT_FILES.map(function (f, i) {
      const q = encodeURIComponent(f.name);
      return '<div class="ge-out-row">' +
        '<span class="ge-out-name">' + esc(f.name) + "</span>" +
        '<span class="ge-out-meta">' + Math.round(f.size / 1024) + " KB · " + esc(f.mtime) + "</span>" +
        '<a class="ge-link" href="' + API + "/preview_file/" + q + '" target="_blank">预览</a>' +
        '<a class="ge-link" href="' + API + "/output/" + q + '">下载</a>' +
        '<button type="button" class="ge-out-act" data-i="' + i + '" data-act="archive"' +
        ' title="移出列表，文件保留在服务器上，可找回">归档</button>' +
        '<button type="button" class="ge-out-act ge-out-act-danger" data-i="' + i + '" data-act="delete"' +
        ' title="永久删除，不可恢复">删除</button>' +
        "</div>";
    }).join("");
  });
}

/** 归档：移出列表但保留文件（符合「归档不删除」纪律，可找回）。 */
function archiveOutput(name) {
  if (!window.confirm("归档这份草稿？\n\n" + name +
      "\n\n归档后不再出现在列表里，文件仍保留在服务器上，可以找回。")) return;
  post("/archive", { name: name }).then(loadOutputs).catch(function (e) {
    alert("归档失败：" + e.message);
  });
}

/** 彻底删除：不可恢复，所以问两次。 */
function deleteOutput(name) {
  if (!window.confirm("永久删除这份草稿？\n\n" + name +
      "\n\n删除后无法恢复，也不会进归档目录。")) return;
  if (!window.confirm("请再确认一次：确定永久删除「" + name + "」？")) return;
  post("/delete", { name: name }).then(loadOutputs).catch(function (e) {
    alert("删除失败：" + e.message);
  });
}

function openHistory() { $("ge-modal").hidden = false; loadOutputs(); }
function closeHistory() { $("ge-modal").hidden = true; }

/** 新建报告：清空这次对话与右侧结果，回到刚打开的样子。
 *
 * 已经生成的 Word **不删**（归档不删），所以文案里说明"仍能在历史报告里找到"。
 * 有正在跑的生成任务或有已确认事实时先确认一次，免得误点丢掉一轮问答。
 */
function newReport() {
  const dirty = !!JOB || !!(SID && $("ge-known") && $("ge-known").children.length);
  if (dirty && !window.confirm(
      "新建报告会清空当前这次对话和右侧结果。\n" +
      "已经生成的 Word 文件不会被删除，仍能在「历史报告」里预览/下载。\n\n继续？")) return;
  if (SID) post("/chat/reset", { session: SID }).catch(function () { /* 清不掉也不拦着新建 */ });
  if (polling) { clearInterval(polling); polling = null; }
  SID = null; JOB = null;
  if (INIT) {
    Object.keys(INIT).forEach(function (k) { const n = $(k); if (n) n.innerHTML = INIT[k]; });
  }
  // 2026-09-22 用户反馈（"新建报告后上一份的内容还在"）：
  // INIT 只是 5 个区域的 **innerHTML 快照**，下面这几处是**性质不同的可变状态**，
  // 一个都没在快照清单里，所以之前新建后原样留着上一份的痕迹：
  //   ge-count  计数胶囊 —— 它是 ge-known 的**兄弟节点**，写的是 textContent 不是 innerHTML，
  //             于是出现"正文已回到『暂无信息』、右上角还挂着『12 项』"这种自相矛盾的界面；
  //   ge-drop   未采信内容（写 innerHTML，但没进快照清单）；
  //   ge-prog   进度条 —— 写的是 hidden 属性与两个子节点，上一轮的「已完成 100%」会一直挂着；
  //   ge-fresh  「重新生成」复选框 —— 不复位会让下一份**默默沿用**换措辞模式。
  // 不能靠"把它们也塞进 INIT"解决：那几个值不是 innerHTML，机制不同，得逐项复位。
  if ($("ge-count")) $("ge-count").textContent = "0 项";
  if ($("ge-drop")) $("ge-drop").innerHTML = "";
  if ($("ge-prog")) {
    $("ge-prog").hidden = true;
    if ($("ge-prog-stage")) $("ge-prog-stage").textContent = "准备中";
    if ($("ge-prog-secs")) $("ge-prog-secs").textContent = "0.0s";
    if ($("ge-prog-fill")) $("ge-prog-fill").style.width = "2%";
  }
  if ($("ge-fresh")) $("ge-fresh").checked = false;
  // C1/C2 的收尾：我补充过的内容与"已回答"记忆也得清，否则新报告会挂着上一份的补充记录
  MINE.length = 0;
  Object.keys(ANSWERED).forEach(function (k) { delete ANSWERED[k]; });
  if ($("ge-mine")) $("ge-mine").innerHTML = "";
  // C4/C6 的收尾：日志条数、折叠状态、判定摘要卡 —— 都不是 innerHTML，得逐项复位
  LOGN = 0;
  if ($("ge-logn")) $("ge-logn").textContent = "暂无日志";
  if ($("ge-logbox")) $("ge-logbox").open = false;
  if ($("ge-dec-card")) $("ge-dec-card").hidden = true;
  if ($("ge-dec")) $("ge-dec").innerHTML = "";
  $("ge-preview-card").hidden = true;
  $("ge-say").value = "";
  $("ge-gen").disabled = true;
  $("ge-send").disabled = false;
  if ($("ge-demo-n")) $("ge-demo-n").textContent = "每次点都换一个（共 5 个虚构示例）";
  closeHistory();
  $("ge-say").focus();
}

function bind() {
  const box = $("ge-say");
  // 不再挂载时补一条"先说说你的项目"的系统气泡 —— 说明卡已经说了同一件事，
  // 两个盒子说一句话是左栏显挤的主因之一。
  const sendSay = function () {
    const t = box.value.trim();
    if (t.length < 8) { alert("请再多描述一些项目情况"); return; }
    if (SID) {   // 已有会话：当作"补充描述"，服务端只填补空缺、不覆盖已确认值
      bubble("me", "我（补充）", t);
      // 与首次提交走同一个接口，同样要等十几秒，所以同样给秒表
      const w2 = waitBubble("正在读这段补充说明：只填补空缺，已确认的字段不会被覆盖。" +
        "这一步同样要调一次模型。");
      post("/chat/start", { text: t, session: SID }).then(function (r) {
        w2.done("系统", "本次补充采信 " + r.采纳数 + " 项；" + r.丢弃数 +
          " 处因缺少依据未采信，已确认字段未被覆盖。");
        renderKnown(r); renderQuestions(r); box.value = "";
      }).catch(function (e) {
        // 原先这里没有 catch：接口报错时界面一点反应都没有，用户只会以为没点上
        w2.fail(e.message);
      });
      return;
    }
    startChat(t);
  };
  $("ge-send").addEventListener("click", sendSay);
  // 2026-09-22 用户反馈：「每次都要用鼠标点发送，不方便」。
  // 与问答页保持同一套习惯：回车发送、Shift+回车换行。
  // 两个细节必须一起做，否则中文输入法按回车会**把半截拼音当问题发出去**：
  //   ① ev.isComposing / keyCode 229 —— 拼音候选框上按回车是"选词"，不是"发送"；
  //   ② shiftKey —— 留给换行，不抢。
  box.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" || ev.shiftKey) return;
    if (ev.isComposing || ev.keyCode === 229) return;
    ev.preventDefault();
    sendSay();
  });
  $("ge-demo").addEventListener("click", function () {
    // 每次点都换一条（把上一次给的文本传回去，服务端会跳过它，不会连着重复）
    const last = $("ge-say").value.trim();
    const url = "/chat/demo" + (last ? "?exclude=" + encodeURIComponent(last) : "");
    get(url).then(function (d) {
      $("ge-say").value = d.示例;
      $("ge-say").focus();
      if ($("ge-demo-n")) $("ge-demo-n").textContent = "已换到第 " + d.序号 + " / " + d.总数 + " 个示例";
      bubble("ai", "系统", "已切换至第 " + d.序号 + "/" + d.总数 + " 个示例（不同行业与敏感目标）。" +
        "点「发送」查看事实抽取与追问；点「直接生成报告」将得到另一份草稿。");
    });
  });
  $("ge-gen").addEventListener("click", function () { if (SID) runJob(); });
  $("ge-new").addEventListener("click", newReport);
  $("ge-history").addEventListener("click", openHistory);
  $("ge-mclose").addEventListener("click", closeHistory);
  // 归档 / 删除：事件委托。列表会整体重绘，逐个按钮绑监听会漏。
  $("ge-outputs").addEventListener("click", function (ev) {
    const btn = ev.target.closest ? ev.target.closest("button[data-act]") : null;
    if (!btn) return;
    const f = OUT_FILES[Number(btn.getAttribute("data-i"))];
    if (!f) return;
    if (btn.getAttribute("data-act") === "archive") archiveOutput(f.name);
    else deleteOutput(f.name);
  });
  $("ge-modal").addEventListener("click", function (ev) {
    if (ev.target === $("ge-modal")) closeHistory();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !$("ge-modal").hidden) closeHistory();
  });
  health();
  loadOutputs();
}

/** 挂载到容器。宿主页（问答页）与独立页都调它。幂等。
 *
 * **必须把 .ge-shell 包上**：全部 --ge-* 变量都声明在 .ge-shell 上，
 * 少了这层，所有 var(--ge-*) 会静默失效 —— 版式还在（.ge-main/.ge-card 是纯类选择器），
 * 但背景、边框、按钮配色全没了（实测踩过：发送按钮白字透明底直接看不见）。
 */
export function mountGenUI(el) {
  if (!el) return false;
  if (el.getAttribute("data-ge-mounted") === "1") return true;
  el.setAttribute("data-ge-mounted", "1");
  el.innerHTML = '<div class="ge-shell">' + TEMPLATE + "</div>";
  ROOT = el.querySelector(".ge-shell");
  // 记下刚挂载时的四个可变区域 —— 「新建报告」靠它还原，不用在 JS 里再抄一遍说明卡
  INIT = {};
  ["ge-stream", "ge-ask", "ge-log", "ge-known", "ge-result", "ge-mine"].forEach(function (k) {
    const n = $(k);
    INIT[k] = n ? n.innerHTML : "";
  });
  bind();
  return true;
}

/** 嵌入模式：隐藏跳转链接与重复标题（宿主已有导航与标题）。 */
export function setEmbedded(on) {
  if (!ROOT) return;
  ROOT.classList.toggle("ge-embedded", !!on);
}

document.addEventListener("DOMContentLoaded", function () {
  if (document.body && document.body.classList.contains("ge-standalone")) {
    mountGenUI($("genBody"));
  }
});
