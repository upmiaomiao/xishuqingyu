/* 悉数清宇 · 示例题库面板：questions.js
 *
 * 需求原话：「这两个问题是需要展示在网站中的……按照现在的分组把他们放到界面上，
 * 比如在用户输入窗口那里放一个小的抽屉，里面可以分类看到这些问题，
 * 然后点击某一条问题发送给模型进行回答」。
 *
 * 三个取舍，都是为了不把首页做重：
 *   ① 不新造组件体系 —— 面板就地长在输入框上方（不是浮层），沿用作曲器与示例按钮那套
 *      视觉语言（--line / --selected / --primary 同一批变量）。展开时聊天区自然变矮，
 *      正文不会被盖住，也不会跟已有的 markdown 渲染、滚动手势打架。
 *   ② 条目只显示题干摘要（最长的一道题 1168 字），点「全文」就地展开；
 *      **点条目本身 = 直接发送**（调 ask()，与欢迎页示例按钮同一套行为，不另做一套发送逻辑）。
 *   ③ 题目数据放 /static/data/question-bank.json（在 routes.py 白名单里登记），
 *      改题目不用动代码；懒加载 —— 不点开就不发请求，首页首屏不多一次往返。
 *
 * 数据来源与加工口径（谁改题库请先看这段）：
 *   原始 PDF 两份（焚烧 32 题 / 固废 41 题）→ 抽取文本 → 去重、剥掉"来源、效果证据、工艺域"
 *   等**内部评测信息**、两道英文题译为中文 → 71 条。去重记录与解析脚本在本机工作区
 *   `_题集勘察/`，仓库里只放成品 JSON，不放带内部信息的中间产物。
 */

import { ask } from './ask.js';         // 发送走首页既有那一套，不另写一份

const BANK_URL = '/static/data/question-bank.json';
const SUMMARY_LEN = 52;                 // 摘要字数：一屏能扫读，又不至于看不出问的什么

let bank = null;                        // 已加载的题库（{tabs:[{name,groups:[{name,items}]}]}）
let loading = null;                     // 加载中的 Promise：连点两次不会发两个请求
let activeTab = 0;

const el = (id) => document.getElementById(id);

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function summary(text) {
  const t = String(text).replace(/\s+/g, ' ').trim();
  return t.length > SUMMARY_LEN ? t.slice(0, SUMMARY_LEN) + '…' : t;
}

function countItems(tab) {
  return tab.groups.reduce((n, g) => n + g.items.length, 0);
}

function isOpen() {
  const p = el('qbPanel');
  return !!p && !p.hidden;
}

/* ---------------------------------------------------------------- 加载 */

function ensureBank() {
  if (bank) return Promise.resolve(bank);
  if (!loading) {
    loading = fetch(BANK_URL, { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then((d) => {
        if (!d || !Array.isArray(d.tabs) || !d.tabs.length) throw new Error('题库数据不完整');
        bank = d;
        return bank;
      })
      .catch((e) => {
        loading = null;                  // 失败要允许重试，不能把失败也缓存住
        throw e;
      });
  }
  return loading;
}

/* ---------------------------------------------------------------- 渲染 */

function renderBank() {
  const tab = bank.tabs[activeTab];
  el('qbTabs').innerHTML = bank.tabs.map((t, i) =>
    '<button class="qb-tab' + (i === activeTab ? ' on' : '') + '" data-tab="' + i + '">' +
    esc(t.name) + '<span class="qb-n"> ' + countItems(t) + '</span></button>').join('');

  el('qbBody').innerHTML = tab.groups.map((g, gi) =>
    '<div class="qb-group">' + esc(g.name) +
    '<span class="qb-n"> · ' + g.items.length + ' 条</span></div>' +
    g.items.map((q, ii) =>
      '<div class="qb-item">' +
      '<div class="qb-row" data-g="' + gi + '" data-i="' + ii + '" title="点击直接发送给模型">' +
      '<div class="qb-text">' + esc(summary(q)) + '</div>' +
      '<button class="qb-more" data-more="1">全文</button>' +
      '</div>' +
      '<div class="qb-full" hidden>' + esc(q) + '</div>' +
      '</div>').join('')).join('');
  el('qbBody').scrollTop = 0;
}

/* ---------------------------------------------------------------- 交互 */

function sendQuestion(gi, ii) {
  const g = bank && bank.tabs[activeTab].groups[gi];
  const text = g && g.items[ii];
  if (!text) return;
  const input = el('q');
  input.value = text;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 180) + 'px';
  closeQuestionBank();
  ask();
}

function onPanelClick(ev) {
  const tab = ev.target.closest('[data-tab]');
  if (tab) {
    activeTab = Number(tab.getAttribute('data-tab'));
    renderBank();
    return;
  }
  // 「全文」必须排在条目之前判断 —— 它就在条目里面，否则点全文会被当成"发送"
  const more = ev.target.closest('[data-more]');
  if (more) {
    const full = more.closest('.qb-item').querySelector('.qb-full');
    full.hidden = !full.hidden;
    more.textContent = full.hidden ? '全文' : '收起';
    return;
  }
  const row = ev.target.closest('.qb-row');
  if (row) sendQuestion(Number(row.getAttribute('data-g')), Number(row.getAttribute('data-i')));
}

export function closeQuestionBank() {
  const panel = el('qbPanel');
  if (!panel) return;
  panel.hidden = true;
  el('qbToggle').setAttribute('aria-expanded', 'false');
}

export function openQuestionBank() {
  const panel = el('qbPanel');
  if (!panel) return;
  panel.hidden = false;
  el('qbToggle').setAttribute('aria-expanded', 'true');
  if (bank) {
    renderBank();
    return;
  }
  el('qbBody').innerHTML = '<div class="qb-load">正在读取题库…</div>';
  ensureBank().then(() => {
    el('qbN').textContent = String(bank.tabs.reduce((n, t) => n + countItems(t), 0));
    renderBank();
  }).catch((e) => {
    // 题库读不出来不该影响提问本身 —— 面板里说清楚就行，不弹窗、不阻断
    el('qbBody').innerHTML = '<div class="qb-err">题库暂时读不出来（' +
      esc((e && e.message) || e) + '）。可以直接在下面输入问题。</div>';
  });
}

export function toggleQuestionBank() {
  if (isOpen()) closeQuestionBank();
  else openQuestionBank();
}

/* 入口按钮与面板的事件委托。挂一次即可 —— 面板内容每次整块重渲染。
 * 不为每一条题目在 HTML 里写 onclick：那样 71 条题库会变成 71 个全局函数调用点。 */
export function initQuestionBank() {
  const toggle = el('qbToggle');
  if (!toggle) return;
  toggle.addEventListener('click', toggleQuestionBank);
  el('qbClose').addEventListener('click', closeQuestionBank);
  el('qbPanel').addEventListener('click', onPanelClick);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen()) closeQuestionBank();
  });
}
