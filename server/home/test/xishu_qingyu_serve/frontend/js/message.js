/* 悉数清宇 · 问答主页脚本模块：message.js
 *
 * 消息与引用渲染、侧栏开关、原文预览抽屉、正文实体标记。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 *
 * 注：第 7 项之后本文件**会**发一个请求（POST /kg/entities，拿正文里的图谱实体）。
 *   这是唯一一处，且失败静默 —— 见 linkifyAnswers()。
 */

import { esc, current, fmtSecs, welcomeBank, pickWelcomeExamples, rotateWelcomeExamples } from './util.js';
import { openKgEntity } from './kg.js';

/* ============================================================
 *  message.js
 * ============================================================ */


/* 欢迎页那三个示例问题：从题库里的"简单"题轮换取（每开一个新会话换一组，同一会话内稳定）。
 * 题库还没到位（首屏那一下、或读失败）就用下面这三个写死的兜底 —— 首屏不能是空的。 */
const FALLBACK_EXAMPLES = [
  '危险废物转移联单的确认期限是多久？',
  '垃圾焚烧厂的烟囱冒白烟，有毒吗？',
  '楼下饭店油烟味太大，该找谁投诉？',
];

function welcome(c) {
  const picked = pickWelcomeExamples(3, c && c.id);
  const examples = (picked.length ? picked : FALLBACK_EXAMPLES)
    .map((q) => `<button class="example" onclick="useExample(this)">${esc(q)}</button>`)
    .join('');
  /* 题库入口放在这三个问题下面（原先我放在输入框旁边，用户要求挪到这里）：
     停在新对话这一屏时视线本来就在中间。点开是浮层，点别处/按 Esc 自动收起。 */
  const total = welcomeBank.total;
  return `<div class="welcome"><div class="welcome-mark">清</div><h1>有什么可以帮忙的？</h1><p>我是中节能研发的悉数清宇大模型，可回答生态环境法规、标准规范与监管执法问题，也能解答垃圾处理、环保投诉等日常问题。</p><div class="examples">${examples}</div><button class="qb-entry" id="qbToggle" aria-expanded="false" aria-haspopup="dialog">查看全部示例问题${total ? `<span class="qb-n"> ${total} 条</span>` : ''}</button></div>`;
}

/* 停在新对话这一屏不动时，每 10 秒换一组示例问题（用户要求「默认 10 秒换一次问题」）。
 * 只改按钮上的文字，不整块重渲染消息区 —— 重渲染是 innerHTML 全量替换，会把
 * 用户正在看的其它东西一起抖一下（滚动位置也会跳）。 */
const WELCOME_ROTATE_MS = 10000;
let welcomeTimer = 0;
let welcomePaused = false;

function stopWelcomeRotation() {
  if (welcomeTimer) {
    clearInterval(welcomeTimer);
    welcomeTimer = 0;
  }
  welcomePaused = false;
}

function startWelcomeRotation(box) {
  stopWelcomeRotation();
  /* 鼠标停在示例区上就暂停（用户 2026-09-24 确认要这个）：否则他正看着某道题、手已经移过去
     准备点，正好到点被换掉，就会点到**另一道题**上 —— 每条都是点一下直接发送，没有二次确认。
     暂停用"跳过这一拍"而不是停表重来：移开后接着当前这一轮的剩余时间走，节奏不会乱。
     监听挂在 .examples 容器上（mouseenter/mouseleave 不冒泡），在三个按钮之间移动不会反复触发。 */
  const area = box.querySelector('.examples');
  if (area && area.addEventListener) {
    area.addEventListener('mouseenter', () => { welcomePaused = true; });
    area.addEventListener('mouseleave', () => { welcomePaused = false; });
  }
  welcomeTimer = setInterval(() => {
    if (welcomePaused) return;             // 鼠标还在问题上面，这一拍不动
    const btns = box.querySelectorAll('.welcome .example');
    if (!btns.length) {                   // 已经不在欢迎页了（或节点被换掉）→ 自己停掉，不留空转的定时器
      stopWelcomeRotation();
      return;
    }
    const next = rotateWelcomeExamples(btns.length);
    btns.forEach((b, i) => {
      if (next[i] != null) b.textContent = next[i];
    });
  }, WELCOME_ROTATE_MS);
}
function formatAnswer(text, mi) {
  let s = esc(text).replace(
    /\[(\d+)\]/g,
    (_, n) => `<button class="cite" onclick="showCitation(${mi},${n})">[${n}]</button>`,
  );
  s = s.replace(/\n/g, '<br>');
  /* markdown 表格 → <table>（专业研判报告用） */ const lines = s.split('<br>'),
    out = [];
  let i = 0;
  while (i < lines.length) {
    if (/^\s*\|.*\|\s*$/.test(lines[i])) {
      const block = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        block.push(lines[i]);
        i++;
      }
      const rows = block
        .filter((l) => !/^\s*\|[\s:\-|]+\|\s*$/.test(l))
        .map((l) =>
          l
            .replace(/^\s*\|/, '')
            .replace(/\|\s*$/, '')
            .split('|')
            .map((c) => c.trim()),
        );
      if (rows.length > 1) {
        const head = rows.shift();
        out.push(
          '<div class="md-table-wrap"><table class="md-table"><thead><tr>' +
            head.map((h) => `<th>${h}</th>`).join('') +
            '</tr></thead><tbody>' +
            rows
              .map(
                (r) =>
                  '<tr>' +
                  r
                    .map(
                      (c) =>
                        `<td class="${c === '满足' ? 'st-ok' : c === '不满足' ? 'st-bad' : c === '无法判断' ? 'st-na' : ''}">${c || '&nbsp;'}</td>`,
                    )
                    .join('') +
                  '</tr>',
              )
              .join('') +
            '</tbody></table></div>',
        );
      } else {
        out.push(block.join('<br>'));
      }
    } else {
      out.push(lines[i]);
      i++;
    }
  }
  return out.join('<br>');
}
/* 引用卡片：元数据徽章 + 「查看原文」。
 *
 * 第 6 项改动：原先是一个 target="_blank" 的链接，点了**跳到新标签页**，
 * 用户就离开了当前对话（回来后滚动位置、展开状态全没了）。
 * 现在改成按钮，在当前页右侧弹出抽屉；抽屉右上角仍保留"在新标签打开"，
 * 想用独立界面的人也有路可走。
 * 传参用 (消息下标, 引用序号) 而不是把 source 字符串拼进 onclick ——
 * 路径里有引号、反斜杠、中文时，字符串拼接转义极容易出错，
 * 让函数自己去 state 里查最稳。
 *
 * 2026-09-19 改动：按钮文案改成**先探测再说话**。
 * 背景：592 条环评报告引用只有全文 .md、没有 PDF（它们的片段占索引 82.7%），
 * 而按钮一直写「📄 查看原文 PDF」，用户点下去以为能看 PDF，实际是 404。
 * 后来虽然加了文本版兜底，抽屉里那条"在新标签打开"仍然指向不存在的 PDF。
 * 现在用 /doc/info_batch 一次问清每条引用的家底，三种情况三种说法：
 *   有 PDF   → 「📄 查看原文 PDF」
 *   只有文本 → 「📄 查看原文（文本版）」
 *   都没有   → 不渲染按钮（画一个点了必然失败的按钮才是真的骗人）
 * 探测结果按 source 缓存：同一份文件被引 5 次也只探一次。 */
const docInfo = new Map();          // source -> {has_pdf, has_md}

/* 批量探测引用来源，填满缓存。返回是否有新结果（调用方据此决定要不要重渲染）。 */
export async function probeDocInfo(sources) {
  const want = [];
  for (const x of sources || []) {
    const src = x && x.source;
    if (src && /\.md$/i.test(src) && !docInfo.has(src) && !want.includes(src)) want.push(src);
  }
  if (!want.length) return false;
  const qs = want.slice(0, 20).map((s) => `source=${encodeURIComponent(s)}`).join('&');
  try {
    const r = await fetch(`/doc/info_batch?${qs}`);
    if (!r.ok) return false;
    const d = await r.json();
    const items = (d && d.items) || {};
    for (const s of want) docInfo.set(s, items[s] || { has_pdf: false, has_md: false });
    return true;
  } catch (e) {
    return false;                   // 探测失败就不缓存，下次再试
  }
}

function srcCard(x, mi) {
  const meta = [
    ['标准号', x.standard_id],
    ['类型', x.doc_type],
    ['状态', x.status],
    ['发布', x.issuer],
    ['地区', x.region],
  ].filter((p) => p[1]);
  const src = x.source || '';
  const info = docInfo.get(src);
  let btn = '';
  if (/\.md$/i.test(src)) {
    if (!info) btn = '📄 查看原文';                                   // 尚未探测：中性说法
    else if (info.has_pdf) btn = '📄 查看原文 PDF';
    else if (info.has_md) btn = '📄 查看原文（文本版）';
    else btn = '';                                                    // 都没有：不画按钮
  }
  return (
    `<div class="source-card" id="src-${mi}-${x.index}">` +
    `<div class="source-title">[${x.index}] ${esc(x.title)}</div>` +
    (meta.length
      ? `<div class="source-meta">${meta.map((p) => `<span class="${/废止|失效|作废/.test(String(p[1])) ? 'st-warn' : ''}">${esc(p[0])}：${esc(p[1])}</span>`).join('')}</div>`
      : '') +
    (btn ? `<button class="pdf-link" onclick="openDoc(${mi},${x.index})">${btn}</button>` : '') +
    `<div class="source-path">${esc(src)}</div>` +
    `<div class="source-text">${esc(x.text || '')}</div></div>`
  );
}

/* ------------------------------------------------------------
 * 原文预览抽屉（第 6 项）
 *
 * 三种入口都指向同一个抽屉：引用卡片上的「查看原文」、正文里的引用角标
 * （showCitation 之后由用户自己点）、以及外部直接调用。
 * 抽屉是 .app 的 flex 子元素，展开时 .main 自动变窄，聊天留在原地。
 * ------------------------------------------------------------ */
let docEscBound = false;

export function openDoc(mi, idx) {
  const c = current();
  const msg = c && c.messages[mi];
  const x = msg && (msg.sources || []).find((s) => s.index === idx);
  if (!x || !x.source) return;

  const drawer = document.getElementById('docDrawer');
  const frame = document.getElementById('docFrame');
  const textBox = document.getElementById('docText');
  const fallback = document.getElementById('docFallback');
  const title = document.getElementById('docTitle');
  const newTab = document.getElementById('docOpenNew');
  const foot = document.getElementById('docFoot');
  const url = /\.md$/i.test(x.source) ? `/doc?source=${encodeURIComponent(x.source)}` : '';

  title.textContent = x.title || '原文';
  /* 「在新标签打开」只有在**确实有 PDF** 时才给。
     改造前这里只判断"来源是 .md"，于是环评报告那 592 条引用都有这条链接，
     点开新标签页就是一个 JSON 格式的 404 —— 用户就是这么发现死链的。
     缓存里已经有探测结果就立刻决定，没有就先藏起来，等下面 /doc/info 回来再定。 */
  const known = docInfo.get(x.source);
  newTab.href = url || '#';
  newTab.style.display = url && known && known.has_pdf ? '' : 'none';   // 未知时先藏

  /* 元数据与命中片段放在抽屉底部。
     为什么要有：PDF 在 iframe 里偶尔渲染失败（浏览器设置、响应头不对），
     那时用户至少还能看到"这条引用是什么、命中了哪一段"，而不是一片空白。 */
  const meta = [
    ['标准号', x.standard_id],
    ['类型', x.doc_type],
    ['状态', x.status],
    ['发布', x.issuer],
    ['地区', x.region],
    ['来源', x.source],
  ].filter((p) => p[1]);
  foot.innerHTML =
    (meta.length
      ? `<div class="doc-meta">${meta.map((p) => `<span>${esc(p[0])}：${esc(p[1])}</span>`).join('')}</div>`
      : '') +
    (x.text ? `<div class="doc-snippet"><b>命中片段</b>${esc(x.text)}</div>` : '');

  /* 三种显示模式互斥，切换时必须把另外两个清干净 ——
     否则会出现"文本视图下面还压着一个 iframe"这种叠影。 */
  const show = (which, note) => {
    frame.style.display = which === 'pdf' ? '' : 'none';
    textBox.style.display = which === 'text' ? '' : 'none';
    fallback.style.display = which === 'note' ? '' : 'none';
    if (which !== 'pdf') frame.removeAttribute('src');
    if (which !== 'text') textBox.textContent = '';
    if (which === 'note') fallback.textContent = note;
  };

  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');

  if (!docEscBound) {
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDoc();
    });
    docEscBound = true;
  }

  /* ★ 先问清楚"这条引用能怎么打开"，再决定加载什么（2026-09-18 用户反馈）。
   *
   * 原先是直接把 /doc 塞进 iframe。资料不存在时服务端返回 404 + JSON，
   * **iframe 会把那串 JSON 当文本原样渲染出来** —— 用户看到一大坨
   * {"ok":false,"code":"E_DOC_NOT_FOUND",...}，而"正在加载原文 PDF…"还挂在上面。
   * iframe 的 onerror 抓不到这种"HTTP 200 内容却是错误"的情况，
   * 所以只能先探测、后加载。
   *
   * 实测背景：环评报告那 592 条引用**只有全文 .md、没有 PDF**
   * （/data/fagui_pdf/环评报告/ 下 0 个 PDF）。所以"没有 PDF"是常态而非异常，
   * 必须给它一条体面的退路 —— 显示文本版全文，用户照样读得到原文。 */
  if (!url) {
    show('note', '这条引用没有可打开的原文文件（来源不是索引里的 .md 路径）。');
    return;
  }

  show('note', '正在打开原文…');
  fetch(`/doc/info?source=${encodeURIComponent(x.source)}`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
    .then((info) => {
      if (!drawer.classList.contains('open')) return;      // 用户已经关掉了
      if (!info || !info.ok) {
        show('note', '暂时打不开这份原文，请稍后再试。');
        return;
      }
      if (info.has_pdf) {
        show('pdf');
        frame.src = url;
        newTab.style.display = '';        // 确认有 PDF，才放出「在新标签打开」
        return;
      }
      newTab.style.display = 'none';      // 没有 PDF：那条链接点开就是 404，撤掉
      if (info.has_md) {
        // 没有 PDF，但有全文文本 —— 退而显示文本版，并说清楚为什么
        return fetch(`/doc/text?source=${encodeURIComponent(x.source)}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
          .then((d) => {
            if (!drawer.classList.contains('open')) return;
            if (!d || !d.ok || !d.text) {
              show('note', '暂时打不开这份原文，请稍后再试。');
              return;
            }
            show('text');
            textBox.textContent = d.text;                  // textContent，不做 HTML 注入
            textBox.scrollTop = 0;
            if (d.truncated) {
              const tip = document.createElement('div');
              tip.className = 'doc-trunc';
              tip.textContent = `全文共 ${d.chars.toLocaleString()} 字，此处显示前 ${d.text.length.toLocaleString()} 字。`;
              foot.insertBefore(tip, foot.firstChild);
            }
          });
      }
      // 既没有 PDF 也没有文本：给一句人话，不显示任何原始错误
      show('note', '这份资料暂时没有可打开的原文。下面的命中片段是本次回答引用的内容。');
    });
}
export function closeDoc() {
  const drawer = document.getElementById('docDrawer');
  if (!drawer || !drawer.classList.contains('open')) return;
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  /* 关掉时清空 src：否则 iframe 里的 PDF 继续占着内存和连接。
     延迟到过渡结束再清，避免动画过程中白屏闪一下。 */
  const frame = document.getElementById('docFrame');
  setTimeout(() => {
    if (!drawer.classList.contains('open') && frame) frame.removeAttribute('src');
  }, 260);
}
/* 处理过程时间线。
 *
 * 为什么要有：照片研判这类通路要「读图 → 检索 → 整段 JSON 生成 → 代码渲染」，
 * 中途确实没有正文可以逐字流式。原先只有角落里一句「生成专业研判…」，
 * 几十秒不动会被当成卡死。这里把后端 status 事件攒成的步骤画出来：
 *   · 正在跑 → 展开，带走动秒表与已生成字数
 *   · 跑完了 → 自动收成一行「处理过程 · N 步 · Xs」，不占正文位置
 */
function traceHtml(m) {
  const steps = m.steps || [];
  if (!steps.length) return '';
  const running = steps.some((s) => s.state === 'running');
  const total = steps.reduce((a, s) => a + (s.ms || 0), 0);
  const rows = steps
    .map((s) => {
      const done = s.state === 'done';
      const secs = done
        ? (s.ms || 0) / 1000
        : (Date.now() - (s.t0 || Date.now())) / 1000;
      const note = done ? s.detail || '' : s.progress ? s.progress + ' 字' : '';
      return (
        `<div class="trace-row ${done ? 'done' : 'running'}">` +
        `<span class="trace-mark">${done ? '✓' : '◐'}</span>` +
        `<span class="trace-label">${esc(s.message)}</span>` +
        (note ? `<span class="trace-note">${esc(note)}</span>` : '') +
        `<span class="trace-time">${secs.toFixed(1)}s</span></div>`
      );
    })
    .join('');
  if (running) {
    return `<div class="trace"><div class="trace-head">处理过程</div>${rows}</div>`;
  }
  /* 跑完了自动收成一行。
   *
   * 文案是按用户要求定的：「已完成资料检索和内容核对　查看处理过程 ›」。
   * 原先收起来写的是「处理过程 · N 步 · Xs」—— 那行字只说明"有几步"，
   * 不说明"做完的是什么"，用户还是得点开才知道发生了什么。
   * 现在的左半句直接回答"刚才在干嘛"，右半句才是"点这里看细节"。
   *
   * 用 <details> 而不是自己写展开逻辑：键盘可达、Ctrl+F 能搜到内容，
   * 而且不带 open 属性就是默认折叠 —— 正好是"完成后自动折叠"。
   * 展开后如果 renderMessages() 重建了 innerHTML，它会被重新折叠；
   * 这是既有行为（见 ask.js 里 tick 的注释），此处不额外处理。 */
  return (
    `<details class="trace trace-done"><summary>` +
    `<span class="trace-sum">已完成资料检索和内容核对</span>` +
    `<span class="trace-secs">${(total / 1000).toFixed(1)}s</span>` +
    `<span class="trace-toggle">查看处理过程<i class="trace-chev">›</i></span>` +
    `</summary>${rows}</details>`
  );
}
/* 导出仅为可测：它是 (消息, 序号) → HTML 字符串的纯函数，
   测试据此直接断言"已完成的消息里三个区块是不是都折叠了"。
   注意这不扩大对外的 API —— 页面能调到的只有 main.js 的 WINDOW_API。 */
export function messageHtml(m, i) {
  /* 用户消息只保留头像里的"你"，不再另起一行 `.who`。
     原先 `<div class="avatar user-avatar">你</div>` 和 `<div class="who">你</div>`
     把同一个字显示了两遍，还白占 28px 行高（.who 的 margin 5px 0 8px + 20px 行高）。
     头像留着是为了和助手消息的「清」保持同一套两栏栅格，视觉上对齐。 */
  if (m.role === 'user')
    return `<article class="message user-msg"><div class="message-inner"><div class="avatar user-avatar">你</div><div>${m.image ? `<img class="msg-img" src="${m.image}" alt="上传的图片" onclick="openImage(this.src)">` : ''}<div class="content">${esc(m.content || '（图片）')}</div></div></div></article>`;
  /* 图片识别内容与分析过程：**生成中展开、完成后折叠**（2026-09-18 用户要求）。
   *
   * 用户的原话：「除了最后的答案，都默认折叠就好了……在回答完成之后默认折叠」。
   * 原先这两个 <details> 写死了 open，于是一条回答下面挂着三块内容
   * （检索进度 / 图片识别原文 / 分析过程），正文反而被挤到下面去。
   *
   * 为什么用 m.streaming 而不是"是不是最后一条消息"来判断：
   * 用户完全可能在等待期间点「新对话」或切到别的会话，那时最后一条消息
   * 就不是"正在生成"的那条了。streaming 标记由 ask.js 在请求开始/结束时写，
   * 跟消息本身绑定，切来切去也不会错。
   *
   * 历史消息没有 streaming 字段（undefined）→ 当作已完成 → 折叠，正是想要的。 */
  const live = m.streaming === true;
  const vision = m.vision
    ? `<details class="vision-box"${live ? ' open' : ''}><summary>图片识别内容（模型读到的原文，请核对）</summary><div class="vision-body">${esc(m.vision)}</div></details>`
    : '';
  const thinking = m.reasoning
    ? `<details class="thinking"${live ? ' open' : ''}><summary>分析过程</summary><div class="thinking-body">${esc(m.reasoning)}</div></details>`
    : '';
  const sources = (m.sources || []).length
    ? `<details class="sources"><summary>查看 ${m.sources.length} 条引用资料</summary>${m.sources.map((x) => srcCard(x, i)).join('')}</details>`
    : '';
  /* 出错时的技术细节：默认折叠，界面上一个字都看不到。
     用户要求「界面不显示错误」—— 所以正文只出现友好文案（ask.js 的 friendlyError）；
     但排查时点开就有错误码和请求编号，不用再让用户去截控制台。
     与后端日志里的 request_id 是同一个串，能直接对上。 */
  const errDetail =
    m.route === 'error' && (m.errorCode || m.errorRequestId || m.errorTech)
      ? `<details class="err-detail"><summary>详情</summary><div class="err-body">` +
        (m.errorCode ? `<div>错误码：${esc(m.errorCode)}</div>` : '') +
        (m.errorRequestId ? `<div>请求编号：${esc(m.errorRequestId)}</div>` : '') +
        (m.errorTech ? `<div class="err-tech">${esc(m.errorTech)}</div>` : '') +
        `</div></details>`
      : '';
  /* 降级提示：模型生成失败、改成了"检索资料直出"或"稍后重试"。
     必须让用户知道这份回答不是正常生成的 —— 否则他会以为
     "资料直出"就是系统本来的回答风格。 */
  const degradedNote = m.degraded
    ? `<div class="degraded-note">本次回答由备用方式生成（模型服务临时不可用），内容仅供参考。</div>`
    : '';
  const route =
    m.route === 'direct_chat' ? '直接对话' : m.route === 'general' ? '科普问答' : 'RAG 检索';
  const secs = fmtSecs(m.latency);
  return `<article class="message assistant-msg" data-mi="${i}"><div class="message-inner"><div class="avatar ai-avatar">清</div><div><div class="who">悉数清宇</div>${traceHtml(m)}${vision}${thinking}<div class="content">${formatAnswer(m.content, i)}</div>${degradedNote}${errDetail}<div class="meta">${route}${secs ? ' · ' + secs : ''}${m.cached ? ' · 缓存' : ''}</div>${sources}</div></div></article>`;
}
export function renderMessages() {
  const c = current(),
    box = document.getElementById('messages');
  if (c.messages.length) {
    box.innerHTML = c.messages.map(messageHtml).join('');
    stopWelcomeRotation();        // 已经在聊了，没必要再让欢迎页的定时器空转
  } else {
    box.innerHTML = welcome(c);
    startWelcomeRotation(box);
  }
  document.getElementById('chatTitle').textContent = c.title;
  box.scrollTop = box.scrollHeight;
  linkifyAnswers(c, box);
}

/* ------------------------------------------------------------
 * 正文实体可点击（第 7 项第一条）
 *
 * 做法：拿回答正文去问后端"这里面有哪些图谱实体"，然后在**文本节点**上做替换。
 *
 * 为什么必须走文本节点而不是字符串替换：
 *   formatAnswer() 已经把正文渲染成 HTML（表格、加粗、引用角标、代码块）。
 *   在 HTML 字符串上做 replace，实体名一旦出现在 class 名、属性值或 URL 里，
 *   就会把标签改坏 —— 比如实体名恰好是 "md-table" 的一部分。
 *   遍历文本节点则天然避开了标签内部，安全得多。
 *
 * 为什么静默失败：这只是锦上添花。接口挂了、图谱没加载，
 *   正文照样该正常显示 —— 绝不能因为加不上下划线就弹报错或者卡住。
 * ------------------------------------------------------------ */

const ENTITY_SKIP_TAGS = new Set(['CODE', 'PRE', 'BUTTON', 'A', 'SUP', 'SCRIPT', 'STYLE']);
let entityScanKey = '';
let entityScanTimer = 0;
let lastEntities = [];

function linkifyAnswers(chat, box) {
  if (!document.createTreeWalker || !box.querySelectorAll) return;
  const items = [];
  box.querySelectorAll('article.assistant-msg').forEach((art) => {
    const mi = Number(art.dataset && art.dataset.mi);
    const m = chat.messages[mi];
    const body = art.querySelector('.content');
    if (m && body && m.content) items.push({ body, text: String(m.content) });
  });
  if (!items.length) return;

  const key = items.map((x) => x.text).join('\u0000');
  if (key === entityScanKey) {
    applyEntities(items, lastEntities);
    return;
  }
  entityScanKey = key;
  clearTimeout(entityScanTimer);
  /* 延后 250ms：流式输出过程中 renderMessages 可能被连续调用，
     不防抖就会对同一个后端接口连打十几次。 */
  entityScanTimer = setTimeout(async () => {
    const entities = await fetchEntities(key);
    lastEntities = entities;
    if (entityScanKey !== key) return;   // 期间正文又变了，这批结果作废
    applyEntities(items, entities);
  }, 250);
}

async function fetchEntities(text) {
  try {
    const r = await fetch('/kg/entities', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 20000) }),
    });
    if (!r.ok) return [];
    const d = await r.json().catch(() => null);
    return (d && Array.isArray(d.entities)) ? d.entities : [];
  } catch {
    return [];
  }
}

function applyEntities(items, entities) {
  if (!entities || !entities.length) return;
  // 后端已按名字长度从长到短排好，这里保持顺序，替换时才不会把长名字切碎
  const list = entities.slice().sort((a, b) => b.name.length - a.name.length);
  items.forEach((it) => markEntities(it.body, list));
}

function inSkipped(node, root) {
  let p = node.parentNode;
  while (p && p !== root) {
    if (p.tagName && ENTITY_SKIP_TAGS.has(String(p.tagName).toUpperCase())) return true;
    p = p.parentNode;
  }
  return false;
}

function markEntities(root, list) {
  const nodes = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (n.nodeValue && n.nodeValue.trim().length >= 2 && !inSkipped(n, root)) nodes.push(n);
  }
  nodes.forEach((node) => {
    const text = node.nodeValue;
    const hits = [];
    list.forEach((e) => {
      let from = 0,
        at;
      while ((at = text.indexOf(e.name, from)) !== -1) {
        hits.push({ start: at, end: at + e.name.length, e });
        from = at + e.name.length;
      }
    });
    if (!hits.length) return;
    /* 去重叠：两个实体名互相包含时（"固体废物" 与 "固体废物污染环境防治法"），
       只保留先出现的那个，否则会切出嵌套的按钮。 */
    hits.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
    const keep = [];
    let cursor = 0;
    hits.forEach((h) => {
      if (h.start >= cursor) {
        keep.push(h);
        cursor = h.end;
      }
    });
    if (!keep.length) return;

    const frag = document.createDocumentFragment();
    let pos = 0;
    keep.forEach((h) => {
      if (h.start > pos) frag.appendChild(document.createTextNode(text.slice(pos, h.start)));
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'kg-entity';
      btn.textContent = text.slice(h.start, h.end);
      btn.title = `在知识图谱中查看「${h.e.name}」`;
      /* 用 addEventListener 而不是 onclick="openKgEntity('名字')"：
         实体名里可能有引号，拼进属性会把 JS 字符串截断；
         而这里本来就是 DOM 遍历，用监听器反而更直接。 */
      btn.addEventListener('click', () => openKgEntity(h.e.name));
      frag.appendChild(btn);
      pos = h.end;
    });
    if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
    if (node.parentNode) node.parentNode.replaceChild(frag, node);
  });
}
export function showCitation(mi, n) {
  const el = document.getElementById(`src-${mi}-${n}`);
  if (!el) return;
  const details = el.closest('details');
  details.open = true;
  el.classList.add('focus');
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => el.classList.remove('focus'), 1800);
}
export function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}
export function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

/* ------------------------------------------------------------
 * 侧栏收起 / 展开（桌面端）
 *
 * 和上面的 toggleSidebar() 是两件事，别混：
 *   · toggleSidebar()  —— **移动端**抽屉。<900px 时 .sidebar 用 transform 滑进滑出，
 *                        宽屏下完全没用（那时 .mobile-menu 是 display:none）。
 *   · 本组函数        —— **桌面端**把侧栏压扁到 0 宽，让正文占满。
 * 两者互不干扰：窄屏收起靠抽屉，宽屏收起靠 .side-collapsed。
 *
 * 状态存 localStorage：用户收起侧栏通常是为了专注读一段长回答，
 * 刷新后不该又自己弹回来。读不到（隐私模式）就用默认的展开态，不影响使用。
 * ------------------------------------------------------------ */
const SIDE_KEY = 'xishu.side.collapsed';

function setSidebarCollapsed(collapsed) {
  const app = document.querySelector('.app');
  if (app) app.classList.toggle('side-collapsed', collapsed);
  const btn = document.getElementById('sideToggle');
  if (btn) {
    btn.textContent = collapsed ? '»' : '«';
    btn.title = collapsed ? '展开侧栏' : '收起侧栏（专注阅读）';
    btn.setAttribute('aria-expanded', String(!collapsed));
  }
}
export function applySidebarCollapse() {
  let collapsed = false;
  try {
    collapsed = localStorage.getItem(SIDE_KEY) === '1';
  } catch {
    /* 读不到就用默认展开态 */
  }
  setSidebarCollapsed(collapsed);
}
export function toggleSidebarCollapse() {
  const app = document.querySelector('.app');
  const next = !(app && app.classList.contains('side-collapsed'));
  setSidebarCollapsed(next);
  try {
    localStorage.setItem(SIDE_KEY, next ? '1' : '0');
  } catch {
    /* 存不下就算了，本次切换已经生效 */
  }
}
