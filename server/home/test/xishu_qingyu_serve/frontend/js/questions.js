/* 悉数清宇 · 示例题库浮层：questions.js
 *
 * 需求原话：「这两个问题是需要展示在网站中的……按照现在的分组把他们放到界面上，
 * 比如在用户输入窗口那里放一个小的抽屉，里面可以分类看到这些问题，
 * 然后点击某一条问题发送给模型进行回答」。
 * 后续按用户反馈调整了两处：① 入口从输入框上方挪到**新对话这一屏的中间**（三个示例问题下面）；
 *   ② 打开后**点别处/按 Esc 自动收起**。
 *
 * 四个取舍，都是为了不把首页做重：
 *   ① 不新造组件体系 —— 浮层是白卡片 + 既有变量（--line / --selected / --primary），
 *      和欢迎页、抽屉同一套视觉语言；正文不会被永久盖住（点一下就收）。
 *   ② 条目只显示题干摘要（最长的一道题 978 字），点「全文」就地展开；
 *      **点条目本身 = 直接发送**（调 ask()，与欢迎页示例按钮同一套行为，不另做一套发送逻辑）。
 *   ③ 题目数据放 /static/data/question-bank.json（在 routes.py 白名单里登记），改题目不用动代码。
 *   ④ 题库在**页面初始化时预取**：欢迎页那三个问题就是从这里轮换出来的，首屏要用；
 *      代价是首页多一次约 60 KB 的请求（原来是点开才取）。
 *
 * 数据来源与加工口径（谁改题库请先看这段）：
 *   原始 PDF 两份（焚烧 32 题 / 固废 41 题）→ 抽取文本 → 去重、剥掉"来源、效果证据、工艺域"
 *   等**内部评测信息**、两道英文题译为中文 → 71 条。解析与去重脚本在本机工作区 `_题集勘察/`。
 *   ⚠️ 这份 JSON 是**客户评测题原文，只放线上、不进公开仓库**（见 README「不入库的东西」）。
 */

import { ask } from './ask.js';                     // 发送走首页既有那一套，不另写一份
import { renderMessages } from './message.js';      // 题库到位后要就地刷新欢迎页那三个问题
import { registerWelcomeBank } from './util.js';

const BANK_URL = '/static/data/question-bank.json';
const SUMMARY_LEN = 52;                 // 摘要字数：一屏能扫读，又不至于看不出问的什么
const WELCOME_PICKS = 3;                // 欢迎页轮换几条（与原来写死的三个一致）

let bank = null;                        // 已加载的题库（{tabs:[{name,groups:[{name,items}]}]}）
let loading = null;                     // 加载中的 Promise：连点两次不会发两个请求
let activeTab = 0;
let panel = null;                       // 浮层外壳（懒建，建成后挂到 body 上）
let tabsEl = null;
let subEl = null;
let bodyEl = null;
let activeGroup = 0;                    // 当前所在的二级分组（导航条高亮用）

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

/* ---------------------------------------------------------------- 浮层外壳 */

/* 为什么建成浮层、而且挂在 body 上：
 *   欢迎页整块是 message.js 每次 renderMessages() 重建的 innerHTML。面板要是长在欢迎页里，
 *   流式回答、切会话、发一条消息都会把它连带销毁；挂到 body 上就跟聊天区的重渲染彻底解耦，
 *   也才谈得上"点别处收起"这种浮层行为。 */
function ensurePanel() {
  if (panel) return panel;
  panel = document.createElement('section');
  panel.className = 'qb-panel';
  panel.id = 'qbPanel';
  panel.hidden = true;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', '示例题库');
  panel.innerHTML =
    '<div class="qb-head"><div class="qb-tabs"></div>' +
    '<button class="qb-x" type="button" title="收起（Esc）" aria-label="收起题库">×</button>' +
    '</div><div class="qb-sub"></div>' +
    '<div class="qb-body"><div class="qb-load">正在读取题库…</div></div>';
  tabsEl = panel.querySelector('.qb-tabs');
  subEl = panel.querySelector('.qb-sub');
  bodyEl = panel.querySelector('.qb-body');
  panel.querySelector('.qb-x').addEventListener('click', closeQuestionBank);
  /* 二级导航跟随滚动高亮（scrollspy）：滚到哪一组，上面的芯片就亮哪个。
     阈值 8px 是留一点余量 —— 标题吸顶后 rect.top 会有不到 1px 的误差。 */
  bodyEl.addEventListener('scroll', () => {
    if (!bank) return;
    const heads = bodyEl.querySelectorAll('[data-group]');
    if (!heads.length) return;
    const base = bodyEl.getBoundingClientRect().top;
    let cur = 0;
    heads.forEach((h, i) => {
      if (h.getBoundingClientRect().top - base <= 8) cur = i;
    });
    /* 最后一组往往顶不到最上面（下面没内容了），光看阈值会一直亮着倒数第二组 ——
       滚到底就直接认最后一组。（scrollHeight > clientHeight 是给垫片测试留的路：
       垫片里两者都是 0，那样会误判成"已经在底部"。） */
    if (bodyEl.scrollHeight > bodyEl.clientHeight &&
        bodyEl.scrollTop + bodyEl.clientHeight >= bodyEl.scrollHeight - 8) {
      cur = heads.length - 1;
    }
    setActiveGroup(cur);
  });
  document.body.appendChild(panel);
  return panel;
}

function isOpen() {
  return !!panel && !panel.hidden;
}

/* ---------------------------------------------------------------- 加载 */

/* 欢迎页要拿它轮换示例问题，所以只挑"小问题"当池子：固废那两组的题最长 35 字、平均 24 字，
 * 正好摆在首屏；其余分组是长案例，不合适。 */
function simplePool(data) {
  const tab = data.tabs.find((t) => t.name === '固废') || data.tabs[0];
  return tab.groups
    .filter((g) => /简单|日常/.test(g.name))
    .reduce((acc, g) => acc.concat(g.items), []);
}

function totalItems(data) {
  return data.tabs.reduce((n, t) => n + countItems(t), 0);
}

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
        registerWelcomeBank(simplePool(d), totalItems(d));   // 交给 util 转给欢迎页
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

/* 二级导航条：一级页签底下的分组芯片。原先分组只是列表里的一行小字标题，
 * 往下滚就划走了，也没法跳组（用户提的「二级目录没有导航栏」）。
 * 芯片点一下就滚到那一组；滚动时按 scrollspy 高亮当前所在的那一组。 */
function renderSub(tab) {
  subEl.innerHTML = tab.groups.map((g, gi) =>
    '<button class="qb-subitem' + (gi === activeGroup ? ' on' : '') + '" data-goto="' + gi +
    '" type="button">' + esc(g.name) + '<span class="qb-n"> ' + g.items.length + '</span></button>')
    .join('');
}

/* 换组才重画芯片条：滚动事件很密，但组号很少变，别每个事件都重画一遍 */
function setActiveGroup(gi) {
  if (gi === activeGroup || !bank) return;
  activeGroup = gi;
  renderSub(bank.tabs[activeTab]);
}

function gotoGroup(gi) {
  const head = bodyEl.querySelector('[data-group="' + gi + '"]');
  setActiveGroup(gi);
  if (!head || !head.getBoundingClientRect) return;
  /* 用两份 rect 的差来算，不碰 offsetTop —— offsetTop 是相对"最近的定位祖先"的，
     浮层是 fixed，层级一变就会算错；rect 的差在任何布局下都对。 */
  bodyEl.scrollTop += head.getBoundingClientRect().top - bodyEl.getBoundingClientRect().top;
}

function renderBank() {
  const tab = bank.tabs[activeTab];
  tabsEl.innerHTML = bank.tabs.map((t, i) =>
    '<button class="qb-tab' + (i === activeTab ? ' on' : '') + '" data-tab="' + i + '">' +
    esc(t.name) + '<span class="qb-n"> ' + countItems(t) + '</span></button>').join('');

  activeGroup = 0;
  renderSub(tab);
  bodyEl.innerHTML = tab.groups.map((g, gi) =>
    '<div class="qb-group" data-group="' + gi + '">' + esc(g.name) +
    '<span class="qb-n"> · ' + g.items.length + ' 条</span></div>' +
    g.items.map((q, ii) =>
      '<div class="qb-item">' +
      '<div class="qb-row" data-g="' + gi + '" data-i="' + ii + '" title="点击直接发送给模型">' +
      '<div class="qb-text">' + esc(summary(q)) + '</div>' +
      '<button class="qb-more" data-more="1">全文</button>' +
      '</div>' +
      '<div class="qb-full" hidden>' + esc(q) + '</div>' +
      '</div>').join('')).join('');
  bodyEl.scrollTop = 0;
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
  // 二级导航芯片：跳到那一组（不发送、不展开）
  const go = ev.target.closest('[data-goto]');
  if (go) {
    gotoGroup(Number(go.getAttribute('data-goto')));
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
  if (!panel || panel.hidden) return;
  panel.hidden = true;
  const tg = el('qbToggle');
  if (tg) tg.setAttribute('aria-expanded', 'false');
}

export function openQuestionBank() {
  ensurePanel();
  panel.hidden = false;
  const tg = el('qbToggle');
  if (tg) tg.setAttribute('aria-expanded', 'true');
  if (bank) {
    renderBank();
    return;
  }
  bodyEl.innerHTML = '<div class="qb-load">正在读取题库…</div>';
  ensureBank().then(() => renderBank()).catch((e) => {
    // 题库读不出来不该影响提问本身 —— 浮层里说清楚就行，不弹窗、不阻断
    bodyEl.innerHTML = '<div class="qb-err">题库暂时读不出来（' +
      esc((e && e.message) || e) + '）。可以直接在下面输入问题。</div>';
  });
}

export function toggleQuestionBank() {
  if (isOpen()) closeQuestionBank();
  else openQuestionBank();
}

/* 交互全挂在 document 一层，不往按钮上挂：
 *   ① 入口按钮在欢迎页里，而欢迎页每次渲染都是新 DOM —— 挂上去会随渲染失效；
 *   ② "点浮层外面收起"本来就得在 document 上看点击。 */
function onDocClick(ev) {
  const t = ev.target;
  if (t && t.closest && t.closest('#qbToggle')) {
    toggleQuestionBank();
    return;
  }
  if (!isOpen()) return;
  if (t && t.closest && t.closest('#qbPanel')) {
    onPanelClick(ev);
    return;
  }
  closeQuestionBank();                   // 点了别处 → 自动收起
}

function onDocKey(ev) {
  if (!isOpen()) return;
  if (ev.key === 'Escape') {
    closeQuestionBank();
    return;
  }
  /* 在输入框里直接回车发送时也收起：否则浮层会一直盖着刚发出去的那轮对话。
     （点欢迎页示例、点题库条目这两条路径本来就会走到 onDocClick，不用管。） */
  if (ev.key === 'Enter' && !ev.shiftKey && ev.target && ev.target.id === 'q') {
    closeQuestionBank();
  }
}

export function initQuestionBank() {
  ensurePanel();
  document.addEventListener('click', onDocClick);
  document.addEventListener('keydown', onDocKey);
  /* 预取题库，好让欢迎页那三个问题从写死换成轮换的。
     读到之前欢迎页显示兜底的三条，读到之后如果还停在欢迎页就就地换掉。 */
  ensureBank().then(() => {
    if (document.querySelector('.welcome .examples')) renderMessages();
  }).catch(() => {});                    // 读不到就用兜底问题，不打扰用户
}
