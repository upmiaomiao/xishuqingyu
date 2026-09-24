/* 悉数清宇 · 问答主页脚本模块：views.js
 *
 * 视图切换（问答 / 图谱 / 审核 / 编制）与两个子模块的**按需加载**。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 */

import { closeSidebar, renderMessages } from './message.js';
import { loadKgSuggestions, loadKnowledgeGraphStats, searchKnowledgeGraph } from './kg.js';

/* ============================================================
 *  views.js
 * ============================================================ */


export function openKnowledgeGraph() {
  closeAudit();
  document.getElementById('messages').style.display = 'none';
  document.querySelector('.composer-wrap').style.display = 'none';
  document.getElementById('kgView').classList.add('open');
  document.getElementById('chatTitle').textContent = '生态环境知识图谱';
  document.getElementById('routePill').textContent = '图谱检索';
  closeSidebar();
  loadKnowledgeGraphStats();
  /* 先给推荐关键词：用户原话「我也不知道有哪些字段，你让我自己搜索好像不太现实」。
     不 await —— 推荐词是锦上添花，图谱本身不该等它。 */
  loadKgSuggestions();
  searchKnowledgeGraph();
}
/* 顶栏与状态栏的**空闲态**文案，取自 index.html 里的初始值。 */
const IDLE_TITLE = '新对话';
const IDLE_PILL = 'Thinking 已开启';
export const IDLE_STATE = 'Enter 发送，Shift+Enter 换行';

/* 回到问答视图时，把"视图 chrome"恢复成空闲态。
 *
 * 为什么需要：chatTitle / routePill / state 这三处会被 openKnowledgeGraph、
 * openAudit、openGen 改掉（"生态环境知识图谱"、"报告编制"、"图谱检索"…），
 * 但**原先没有任何地方恢复**。于是点「新对话」之后：
 *   · 顶栏标题还写着上一个视图的名字；
 *   · 右上角还挂着「报告编制」；
 *   · 底部状态栏还停在上一次的「完成 · 6.672s」，看起来像新对话已经答完了。
 */
export function resetChatChrome() {
  const t = document.getElementById('chatTitle');
  if (t) t.textContent = IDLE_TITLE;
  const p = document.getElementById('routePill');
  if (p) p.textContent = IDLE_PILL;
  const s = document.getElementById('state');
  if (s) s.textContent = IDLE_STATE;
}

export function closeKnowledgeGraph() {
  document.getElementById('kgView').classList.remove('open');
  closeAudit();
  document.getElementById('messages').style.display = '';
  document.querySelector('.composer-wrap').style.display = '';
  resetChatChrome();
  renderMessages();
}
export function openAudit() {
  closeKnowledgeGraph();
  document.getElementById('messages').style.display = 'none';
  document.querySelector('.composer-wrap').style.display = 'none';
  document.getElementById('auditView').classList.add('open');
  document.getElementById('chatTitle').textContent = '环评报告审核';
  document.getElementById('routePill').textContent = '报告审核';
  closeSidebar();
  ensureAuditUI(function (m) {
    m.mountAuditUI(document.getElementById('auditBody'));
  });
}
function closeAudit() {
  const v = document.getElementById('auditView');
  if (v) {
    v.classList.remove('open');
  }
}
/* ---------------- 报告编制视图（与报告审核同一套挂载方式） ---------------- */
export function openGen() {
  closeKnowledgeGraph();
  closeAudit();
  document.getElementById('messages').style.display = 'none';
  document.querySelector('.composer-wrap').style.display = 'none';
  document.getElementById('genView').classList.add('open');
  document.getElementById('chatTitle').textContent = '报告编制';
  document.getElementById('routePill').textContent = '报告编制';
  closeSidebar();
  ensureGenUI(function (m) {
    m.mountGenUI(document.getElementById('genBody'));
    m.setEmbedded(true);
  });
}
export function closeGen() {
  const v = document.getElementById('genView');
  if (v) {
    v.classList.remove('open');
  }
}

/* ============================================================
 *  两个子界面的**按需加载**
 *
 *  阶段 3 之前是往 <head> 里插一个 <script src>，靠 window.mountGenUI 通信。
 *  那两个文件现在是 ES 模块，传统 <script> 读到 export 就会语法报错、整页白屏，
 *  所以改成动态 import()。
 *
 *  好处：浏览器原生缓存模块，来回切视图不会重复请求；也不用再往 window 上挂东西。
 *  注意：CSS 仍是独立的 <link> —— 在模块里 import CSS 需要打包器，这套站点没有。
 * ============================================================ */
let genMod = null,
  genLoading = null;
let auditMod = null,
  auditLoading = null;

function loadCssOnce(id, href) {
  if (document.getElementById(id)) return;
  const l = document.createElement('link');
  l.id = id;
  l.rel = 'stylesheet';
  l.href = href;
  document.head.appendChild(l);
}

function ensureGenUI(cb) {
  loadCssOnce('geCss', '/gen/static/gen_ui.css');
  if (genMod) {
    cb(genMod);
    return;
  }
  genLoading = genLoading || import('/gen/static/gen_ui.js');
  genLoading
    .then(function (m) {
      genMod = m;
      cb(m);
    })
    .catch(function (e) {
      console.error('报告编制界面加载失败', e);
    });
}

/* 审核界面模块按需加载：没用过就不下载（不拖慢问答页首屏）。
   模块自身幂等（重复挂载返回同一个实例），所以来回切换不会重建界面、不丢审核结果。 */
function ensureAuditUI(cb) {
  loadCssOnce('auCss', '/audit/static/audit_ui.css');
  if (auditMod) {
    cb(auditMod);
    return;
  }
  auditLoading = auditLoading || import('/audit/static/audit_ui.js');
  auditLoading
    .then(function (m) {
      auditMod = m;
      cb(m);
    })
    .catch(function (e) {
      console.error('审核界面加载失败', e);
    });
}
