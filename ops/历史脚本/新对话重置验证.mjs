#!/usr/bin/env node
/**
 * 「新对话」重置验证。
 *
 * 用户报的问题：底部状态栏停在 `完成 · 6.672s`，点「新对话」不会清掉。
 * 查下来是同一类问题的三处：chatTitle / routePill / state 都是"视图 chrome"，
 * 被 openKnowledgeGraph / openAudit / openGen 改过之后**没有任何地方恢复**。
 * 另外 `6.672s` 是服务端 round(...,3) 直接显示的，三位小数又长又假精确。
 *
 * 这个测试把真实模块跑起来，走完整流程：
 *   提问完成 → 三处 chrome 变成"已答完" → 点新对话 → 必须全部回到空闲态
 * 外加一个竞态：等待期间点新对话，旧请求回来时**不能**把新对话的状态栏写脏。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_重置测试');
fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, 'js'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'frontend/js'))) {
  if (f.endsWith('.js')) fs.copyFileSync(path.join(ROOT, 'frontend/js', f), path.join(DIR, 'js', f));
}

/* ---------------------------------------------------------------- DOM 桩 */
const ctxStub = new Proxy({}, { get: () => () => ctxStub });
const els = new Map();
function makeEl(tag = 'div', id = '') {
  const cls = new Set();
  const el = {
    tagName: String(tag).toUpperCase(), id, style: {}, dataset: {}, children: [],
    className: '', textContent: '', value: '', checked: false, disabled: false, hidden: false,
    scrollTop: 0, scrollHeight: 0, _handlers: {},
    classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c),
      toggle: (c, f) => (f ? cls.add(c) : cls.delete(c)), contains: (c) => cls.has(c) },
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    appendChild(c) { el.children.push(c); if (c) c.parentNode = el; return c; },
    insertBefore(c) { el.children.push(c); return c; },
    removeChild() {}, remove() {}, replaceChildren() {},
    addEventListener(t, fn) { (el._handlers[t] = el._handlers[t] || []).push(fn); },
    removeEventListener() {},
    fire(t, ev) { (el._handlers[t] || []).forEach((fn) => fn(ev || {})); },
    querySelector: (s) => find(el, s) || makeEl('div'),
    querySelectorAll: (s) => findAll(el, s),
    closest() { return el; }, scrollIntoView() {}, focus() {}, blur() {}, click() { el.fire('click'); },
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0 }),
    getContext: () => ctxStub, toDataURL: () => 'data:image/png;base64,AAAA',
    animate: () => ({ finished: Promise.resolve(), cancel() {} }),
  };
  let _own = '';
  Object.defineProperty(el, 'innerHTML', {
    get: () => _own + el.children.map((c) => c.innerHTML).join(''),
    set: (v) => { _own = String(v); el.children = []; indexHtml(el, _own); },
  });
  return el;
}
function indexHtml(el, html) {
  el._byId = new Map(); el._byClass = new Map();
  const add = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  for (const m of html.matchAll(/\bid="([^"]+)"/g)) {
    const e = makeEl('div', m[1]);
    el._byId.set(m[1], e);
    if (!els.has(m[1])) els.set(m[1], e);
  }
  for (const m of html.matchAll(/\bclass="([^"]*)"/g))
    for (const c of m[1].split(/\s+/)) if (c) add(el._byClass, c, makeEl('div'));
}
function find(el, sel) {
  const s = String(sel);
  if (s.startsWith('#')) return (el._byId && el._byId.get(s.slice(1))) || (els.has(s.slice(1)) ? els.get(s.slice(1)) : null);
  if (s.startsWith('.')) {
    const l = el._byClass && el._byClass.get(s.slice(1));
    if (l && l.length) return l[0];
    for (const c of el.children || []) { const r = find(c, sel); if (r) return r; }
    return null;
  }
  return null;
}
function findAll(el, sel) {
  const s = String(sel);
  if (!s.startsWith('.')) return [];
  const out = [...((el._byClass && el._byClass.get(s.slice(1))) || [])];
  for (const c of el.children || []) out.push(...findAll(c, sel));
  return out;
}
function getEl(id) { if (!els.has(id)) els.set(id, makeEl('div', id)); return els.get(id); }

// 预置 index.html 里那几个 chrome 元素的初始文案（空闲态就是这个）
getEl('chatTitle').textContent = '新对话';
getEl('routePill').textContent = 'Thinking 已开启';
getEl('state').textContent = 'Enter 发送，Shift+Enter 换行';

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k),
  clear: () => store.clear(), get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null,
};
// 真实页面里 .composer-wrap 是存在的（index.html 里的容器），桩必须也能"找到"它，
// 否则 closeKnowledgeGraph 里那句 querySelector('.composer-wrap').style 直接抛异常。
// 按选择器字符串缓存一个稳定的桩元素 —— 这样多次取到的是同一个对象，能查状态。
const bySelector = new Map();
function selectorEl(sel) {
  const k = String(sel);
  if (!bySelector.has(k)) bySelector.set(k, makeEl('div'));
  return bySelector.get(k);
}
globalThis.document = {
  head: makeEl('head'), body: makeEl('body'), documentElement: makeEl('html'),
  getElementById: getEl, querySelector: (s) => selectorEl(s), querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.alert = () => {};
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);

/* ------------------------------------------------------------ 假 SSE 流 */
let gate = null;
const SSE = [
  ['status', { stage: 'intent', message: '识别意图…', state: 'run' }],
  ['meta', { route: 'rag', sources: [] }],
  ['chunk', '危险废物转移联单自接受之日起十日内交付。'],
  ['done', { route: 'rag', sources: [], latency_s: 6.672 }],
];
const SSE_TEXT = SSE.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('');
globalThis.fetch = () => {
  const bytes = new TextEncoder().encode(SSE_TEXT);
  let sent = false;
  return Promise.resolve({
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (gate) { await gate; gate = null; }
          if (sent) return { done: true, value: undefined };
          sent = true;
          return { done: false, value: bytes };
        },
      }),
    },
    text: () => Promise.resolve(''),
  });
};

/* ------------------------------------------------------------------ 跑 */
let pass = 0, fail = 0;
const problems = [];
function ck(label, ok, extra = '') {
  if (ok) { pass++; console.log(`  √ ${label}${extra ? '　' + extra : ''}`); }
  else { fail++; problems.push(label); console.log(`  ✗ ${label}${extra ? '　' + extra : ''}`); }
}
const js = (f) => 'file://' + path.join(DIR, 'js', f).replace(/\\/g, '/');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { fmtSecs } = await import(js('util.js'));
const { ask } = await import(js('ask.js'));
const { newConversation, selectChat } = await import(js('store.js'));
const views = await import(js('views.js'));
const { state } = await import(js('util.js'));
await import(js('main.js'));

console.log('='.repeat(88));
console.log('① 耗时格式：三位小数 → 一位');
console.log('='.repeat(88));
ck('6.672 → 6.7s', fmtSecs(6.672) === '6.7s', fmtSecs(6.672));
ck('18.079 → 18.1s', fmtSecs(18.079) === '18.1s', fmtSecs(18.079));
ck('0.16 → 0.2s', fmtSecs(0.16) === '0.2s', fmtSecs(0.16));
ck('12.31 → 12.3s', fmtSecs(12.31) === '12.3s', fmtSecs(12.31));
ck('没有耗时则不给单位', fmtSecs(0) === '' && fmtSecs(null) === '' && fmtSecs(undefined) === '');

console.log();
console.log('='.repeat(88));
console.log('② 答完之后：三处 chrome 变成"已答完"');
console.log('='.repeat(88));
getEl('q').value = '危险废物转移联单的确认期限是多久？';
await ask();
await sleep(30);
ck('状态栏显示完成 + 一位小数耗时', getEl('state').textContent === '完成 · 6.7s',
  getEl('state').textContent);
ck('右上角显示路由', getEl('routePill').textContent === 'RAG · Thinking',
  getEl('routePill').textContent);
ck('消息里的耗时也是一位小数',
  /RAG 检索 · 6\.7s/.test(getEl('messages').innerHTML),
  (getEl('messages').innerHTML.match(/RAG 检索 · [\d.]+s/) || ['无'])[0]);

console.log();
console.log('='.repeat(88));
console.log('③ 点「新对话」：三处必须全部回到空闲态（这就是用户报的问题）');
console.log('='.repeat(88));
newConversation();
await sleep(20);
ck('状态栏回到空闲提示（不再停在「完成 · 6.7s」）',
  getEl('state').textContent === 'Enter 发送，Shift+Enter 换行', getEl('state').textContent);
ck('右上角回到 Thinking 已开启', getEl('routePill').textContent === 'Thinking 已开启',
  getEl('routePill').textContent);
ck('顶栏标题回到「新对话」', getEl('chatTitle').textContent === '新对话',
  getEl('chatTitle').textContent);
ck('新会话确实是空的', state.chats[0].messages.length === 0);
ck('历史里还留着上一轮（只是切走了，没删）',
  state.chats.some((c) => c.messages.some((m) => m.latency)));

console.log();
console.log('='.repeat(88));
console.log('④ 从别的视图回问答：同样要恢复（原先标题会一直挂着视图名）');
console.log('='.repeat(88));
views.openKnowledgeGraph();
await sleep(20);
ck('进图谱后标题变成图谱', getEl('chatTitle').textContent === '生态环境知识图谱',
  getEl('chatTitle').textContent);
views.closeKnowledgeGraph();
await sleep(20);
ck('回问答后标题恢复', getEl('chatTitle').textContent === '新对话', getEl('chatTitle').textContent);
ck('回问答后右上角恢复', getEl('routePill').textContent === 'Thinking 已开启',
  getEl('routePill').textContent);

console.log();
console.log('='.repeat(88));
console.log('⑤ 竞态：等待期间点「新对话」，旧请求回来不能把新对话写脏');
console.log('='.repeat(88));
getEl('q').value = '第二个问题，用来制造竞态';
gate = new Promise((r) => setTimeout(r, 150));   // 让流卡住 150ms
const asking = ask();
await sleep(20);
newConversation();                                // 流还没读完就切走
await asking;
await sleep(30);
ck('新对话的状态栏没有被旧请求覆盖',
  getEl('state').textContent === 'Enter 发送、Shift+Enter 换行'.replace('、', '，'),
  getEl('state').textContent);
ck('新对话的右上角没有被旧请求覆盖', getEl('routePill').textContent === 'Thinking 已开启',
  getEl('routePill').textContent);
ck('答完的那条消息进了它自己的会话（没丢）',
  state.chats.some((c) => c.messages.some((m) => /第二个问题/.test(m.content || ''))),
  state.chats.map((c) => c.messages.length).join('/'));

console.log();
console.log('='.repeat(88));
console.log(`结论：通过 ${pass} / 失败 ${fail}`);
if (fail) { console.log('失败项：'); for (const p of problems) console.log('  × ' + p); }
console.log('='.repeat(88));
process.exit(fail ? 1 : 0);
