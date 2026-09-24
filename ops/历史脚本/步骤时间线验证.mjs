#!/usr/bin/env node
/**
 * 步骤时间线验证：用真实的 SSE 事件流喂给真正的前端模块，看时间线渲染成什么样。
 *
 * 为什么这么测：这一步的价值全在「用户看得见」，而我没有浏览器。
 * 所以用 Node + DOM 桩把 ask() 真跑一遍，mock 掉 fetch 返回照片研判的真实事件序列，
 * 分两段喂 —— 中途检查「正在跑的那一步看得见」，喂完检查「收成一行摘要」。
 *
 * 设计约定（第一版测试就是在这里搞错的，记下来）：
 *   **每个 stage 一行**，不是每个事件一行。run 建行、done 更新这一行的文案与耗时：
 *     run  「生成专业研判」   ← 跑到一半时看到的就是它（带走动秒表 + 已生成字数）
 *     done 「研判内容已生成」2841 字 · 36.4s
 *   这样一行就是一个"步骤"，跑完变成结果，不会被拆成两行噪音。
 *
 * 另外：整段事件在同一个 tick 里灌进去时，ms 会是 0（不足 1 毫秒），
 * 所以判断"有没有记耗时"必须用 `ms === undefined`，不能用 `!ms` —— 0 是合法值。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_步骤测试');

fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, 'js'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'frontend/js'))) {
  if (f.endsWith('.js')) fs.copyFileSync(path.join(ROOT, 'frontend/js', f), path.join(DIR, 'js', f));
}

/* ---------------------------------------------------------------- DOM 桩 */
const ctxStub = new Proxy({}, { get: () => () => ctxStub });
const els = new Map();
function indexHtml(el, html) {
  el._byId = new Map(); el._byClass = new Map(); el._byAttr = new Map();
  const add = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  for (const m of html.matchAll(/\bid="([^"]+)"/g)) el._byId.set(m[1], makeEl('div', m[1]));
  for (const m of html.matchAll(/\bclass="([^"]*)"/g)) for (const c of m[1].split(/\s+/)) if (c) add(el._byClass, c, makeEl('div'));
  for (const m of html.matchAll(/\b(data-[a-z-]+)="?([^"\s>]*)"?/g)) add(el._byAttr, m[1], makeEl('div'));
}
function queryOne(el, sel) {
  const s = String(sel);
  if (s.startsWith('#')) return (el._byId && el._byId.get(s.slice(1))) || getEl(s.slice(1));
  if (s.startsWith('.')) { const l = el._byClass && el._byClass.get(s.slice(1)); return (l && l[0]) || makeEl('div'); }
  const am = s.match(/^([a-z]+)?\[(data-[a-z-]+)/);
  if (am && el._byAttr && el._byAttr.get(am[2])) return el._byAttr.get(am[2])[0];
  return makeEl('div');
}
function queryAll(el, sel) {
  const s = String(sel);
  if (s.startsWith('.')) { const l = el._byClass && el._byClass.get(s.slice(1)); return l && l.length ? l : []; }
  const am = s.match(/\[(data-[a-z-]+)/);
  if (am && el._byAttr && el._byAttr.get(am[1])) return el._byAttr.get(am[1]);
  return [];
}
function makeEl(tag = 'div', id = '') {
  const cls = new Set();
  let _html = '';
  const el = {
    tagName: String(tag).toUpperCase(), id, style: {}, dataset: {}, children: [],
    className: '', textContent: '', value: '', files: null, checked: false, disabled: false,
    scrollTop: 0, scrollHeight: 0, options: [], selectedIndex: 0, parentNode: null,
    _byId: new Map(), _byClass: new Map(), _byAttr: new Map(),
    classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c),
      toggle: (c, f) => (f === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : f ? cls.add(c) : cls.delete(c)),
      contains: (c) => cls.has(c) },
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    appendChild(c) { el.children.push(c); if (c) c.parentNode = el; return c; },
    insertBefore(c) { el.children.push(c); if (c) c.parentNode = el; return c; },
    removeChild() {}, remove() {}, replaceChildren() {},
    addEventListener() {}, removeEventListener() {},
    querySelector: (s) => queryOne(el, s), querySelectorAll: (s) => queryAll(el, s),
    closest() { return el; }, scrollIntoView() {}, focus() {}, blur() {}, click() {},
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0, right: 800, bottom: 600 }),
    getContext: () => ctxStub, toDataURL: () => 'data:image/png;base64,AAAA',
    animate: () => ({ finished: Promise.resolve(), cancel() {} }), play() {}, pause() {},
  };
  Object.defineProperty(el, 'innerHTML', {
    get: () => _html,
    set: (v) => { _html = String(v); indexHtml(el, _html); },
  });
  return el;
}
function getEl(id) { if (!els.has(id)) els.set(id, makeEl('div', id)); return els.get(id); }

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k), clear: () => store.clear(),
  get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null,
};
globalThis.document = {
  head: makeEl('head'),
  body: Object.assign(makeEl('body'), { classList: makeEl().classList }),
  documentElement: makeEl('html'),
  getElementById: getEl, querySelector: () => null, querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);

/* ------------------------------------------------- 照片研判的真实事件序列
   前 9 条是"还在跑"的阶段，后 7 条是收尾。分两段喂，才能观察到中途状态。 */
const PHASE1 = [
  ['status', { stage: 'vision', message: '读取图片', state: 'run' }],
  ['status', { stage: 'vision', message: '图片已识别', state: 'done', detail: '412 字 · 1.8s' }],
  ['vision', { text: '烟囱出口有明显白烟' }],
  ['status', { stage: 'retrieve', message: '检索判据与标准', state: 'run' }],
  ['status', { stage: 'retrieve', message: '已找到依据', state: 'done', detail: '12 条 · 2.1s' }],
  ['meta', { route: 'photo', sources: [] }],
  ['status', { stage: 'generate', message: '生成专业研判', state: 'run' }],
  ['status', { stage: 'generate', message: '生成专业研判', state: 'run', progress: 820 }],
  ['status', { stage: 'generate', message: '生成专业研判', state: 'run', progress: 2410 }],
];
const PHASE2 = [
  ['status', { stage: 'generate', message: '研判内容已生成', state: 'done', detail: '2841 字 · 36.4s' }],
  ['status', { stage: 'render', message: '渲染研判报告', state: 'run' }],
  ['status', { stage: 'render', message: '研判报告已生成', state: 'done', detail: '2841 字 · 合计 41.2s' }],
  ['status', { stage: 'verify', message: '核验引用依据', state: 'run' }],
  ['status', { stage: 'verify', message: '引用依据核验完成', state: 'done' }],
  ['chunk', '## 现场照片专业研判\n\n| 项 | 结论 |\n|---|---|\n| 判定 | 疑似 |'],
  ['done', { route: 'photo', sources: [], latency_s: 42.1 }],
];
const enc = (evs) => new TextEncoder().encode(evs.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(''));

/* 分两段喂：第一段读完挂住，等测试检查完中途状态再放第二段 */
let releaseSecond;
const secondReady = new Promise((r) => { releaseSecond = r; });
let reads = 0;
globalThis.fetch = () =>
  Promise.resolve({
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          reads++;
          if (reads === 1) return { done: false, value: enc(PHASE1) };
          if (reads === 2) { await secondReady; return { done: false, value: enc(PHASE2) }; }
          return { done: true, value: undefined };
        },
      }),
    },
    text: () => Promise.resolve(''),
  });

/* ---------------------------------------------------------------- 跑 */
let pass = 0, fail = 0;
const problems = [];
function ck(label, ok, extra = '') {
  if (ok) { pass++; console.log(`  √ ${label}${extra ? '　' + extra : ''}`); }
  else { fail++; problems.push(label); console.log(`  ✗ ${label}${extra ? '　' + extra : ''}`); }
}
const js = (f) => 'file://' + path.join(DIR, 'js', f).replace(/\\/g, '/');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { ask } = await import(js('ask.js'));
await import(js('main.js'));
getEl('q').value = '这是现场照片';
getEl('photoMode').checked = true;

const askP = ask();
await sleep(60);                       // 让第一段流被处理完

console.log('='.repeat(88));
console.log('① 中途（照片研判还在跑）：必须看得见"正在跑哪一步"');
console.log('='.repeat(88));
let html = getEl('messages').innerHTML;
ck('时间线已展开（不是收起的 details）',
  html.includes('class="trace"') && !html.includes('<details class="trace"'));
ck('有正在跑的步骤', html.includes('trace-row running'));
ck('正在跑的那步带秒表', /trace-row running[\s\S]{0,200}trace-time">[\d.]+s</.test(html));
ck('正在跑的是「生成专业研判」', /trace-row running[^>]*>[\s\S]{0,80}生成专业研判/.test(html));
ck('带已生成字数（让用户知道在动）', html.includes('2410 字'));
ck('已完成的步骤显示为 ✓', (html.match(/trace-mark">✓</g) || []).length === 2,
  (html.match(/trace-mark">✓</g) || []).length + ' 个');
ck('已完成步骤带耗时', html.includes('1.8s') && html.includes('2.1s'));
ck('此刻还没有正文（确实没东西可流式）', !html.includes('md-table'));

console.log();
console.log('='.repeat(88));
console.log('② 喂完剩余事件后：收成一行摘要，每步都在');
console.log('='.repeat(88));
releaseSecond();
await askP;
await sleep(20);
html = getEl('messages').innerHTML;
/* 2026-09-18 第二批：收起后的文案按用户要求改了。
 *   旧：「处理过程 · N 步 · Xs」
 *   新：「已完成资料检索和内容核对　6.7s　查看处理过程 ›」
 * 断言跟着改。这里刻意**不**再断言"步数"—— 新文案里没有步数是有意的：
 * 收起来那一行该回答"刚才做完了什么"，而不是"有几步"。
 * 每步的耗时仍然在展开后的明细里，下面照旧断言 5 处 trace-time。 */
ck('收成 <details>（不再占正文位置）', html.includes('<details class="trace trace-done">'));
ck('摘要文案是「已完成资料检索和内容核对」', html.includes('已完成资料检索和内容核对'));
ck('摘要右侧是「查看处理过程 ›」', /class="trace-toggle">查看处理过程<i class="trace-chev">›<\/i>/.test(html));
ck('摘要保留总耗时', /class="trace-secs">[\d.]+s</.test(html),
  (html.match(/class="trace-secs">[\d.]+s</) || [''])[0]);
ck('默认收起（summary 上没有 open）',
  !/<details class="trace trace-done"[^>]*\sopen/.test(html));
ck('旧文案「处理过程 · N 步」已不再出现', !/处理过程 · \d+ 步/.test(html));
for (const label of ['图片已识别', '已找到依据', '研判内容已生成', '研判报告已生成', '引用依据核验完成']) {
  ck(`时间线含「${label}」`, html.includes(label));
}
ck('每步都记了耗时', (html.match(/trace-time">[\d.]+s</g) || []).length === 5,
  (html.match(/trace-time">[\d.]+s</g) || []).length + ' 处');
ck('没有残留 running（否则一直转圈）', !html.includes('trace-row running'));
ck('图片识别内容照常显示', html.includes('vision-box'));
ck('正文照常渲染（含表格）', html.includes('md-table'));
ck('完成后的步骤全部是 ✓', (html.match(/trace-mark">✓</g) || []).length === 5,
  (html.match(/trace-mark">✓</g) || []).length + ' 个');

console.log();
console.log('='.repeat(88));
console.log('③ 步骤数据随消息保存（刷新/切会话后还能看）');
console.log('='.repeat(88));
const { state } = await import(js('util.js'));
const am = state.chats.flatMap((x) => x.messages).find((m) => m.steps);
ck('步骤存进了消息对象', !!am && am.steps.length === 5, am ? am.steps.length + ' 步' : '无');
if (am) {
  ck('没有卡在 running 的步骤', am.steps.every((s) => s.state === 'done'),
    am.steps.filter((s) => s.state !== 'done').map((s) => s.message).join(',') || '无');
  // 0 是合法耗时（整段流在同一毫秒内灌完），所以必须比 undefined 而不是比真假
  ck('每步都记了耗时（0 也算）', am.steps.every((s) => s.ms !== undefined),
    am.steps.filter((s) => s.ms === undefined).map((s) => s.message).join(',') || '无');
  ck('步骤按 stage 去重（一个 stage 一行）',
    new Set(am.steps.map((s) => s.stage)).size === am.steps.length,
    am.steps.map((s) => s.stage).join(' → '));
}

console.log();
console.log('='.repeat(88));
console.log(`结论：通过 ${pass} / 失败 ${fail}`);
if (fail) { console.log('失败项：'); for (const p of problems) console.log('  × ' + p); }
console.log('='.repeat(88));
process.exit(fail ? 1 : 0);
