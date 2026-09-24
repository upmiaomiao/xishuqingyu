#!/usr/bin/env node
/**
 * 验证两个 bug 的修复（2026-09-18）。
 *
 *   bug 1：第一轮发图后，第二轮输入纯文字，回答仍然在讲图片
 *   bug 2：回答完成后"生成中"的转圈图标不停
 *
 * 判据落在**实际发出去的请求体**和**渲染出来的 HTML** 上，不靠读代码猜。
 *
 * ★ 必须有反向断言：光证明"图片那轮不进历史"是不够的 —— 还要证明
 *   **正常的多轮对话历史没被一起砍掉**。否则把 buildHistory 写成 return []
 *   也能让前两条通过，但那等于废掉了多轮对话。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_修复验证');
fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, 'js'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'frontend/js'))) {
  if (f.endsWith('.js')) fs.copyFileSync(path.join(ROOT, 'frontend/js', f), path.join(DIR, 'js', f));
}

/* ---------------------------------------------------------------- DOM 桩 */
function makeCtx() {
  const c = new Proxy({}, { get: (t, k) => (k === 'measureText' ? () => ({ width: 30 }) : () => c), set: () => true });
  return c;
}
const els = new Map();
function makeEl(tag = 'div', id = '') {
  const cls = new Set();
  const el = {
    tagName: String(tag).toUpperCase(), id, style: {}, dataset: {}, children: [],
    className: '', textContent: '', value: '', checked: false, disabled: false, hidden: false,
    files: [], width: 0, height: 0, scrollTop: 0, scrollHeight: 0, clientWidth: 800, clientHeight: 500,
    _handlers: {}, _attrs: {},
    classList: {
      add: (c) => cls.add(c), remove: (c) => cls.delete(c),
      toggle: (c, f) => (f === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : (f ? cls.add(c) : cls.delete(c))),
      contains: (c) => cls.has(c), _all: () => [...cls],
    },
    setAttribute(k, v) { el._attrs[k] = String(v); },
    getAttribute(k) { return k in el._attrs ? el._attrs[k] : null; },
    removeAttribute(k) { delete el._attrs[k]; },
    appendChild(c) { el.children.push(c); if (c) c.parentNode = el; return c; },
    insertBefore(c) { el.children.push(c); return c; },
    removeChild() {}, remove() {}, replaceChildren() {},
    replaceChild(n) { el.children.push(n); },
    addEventListener(t, fn) { (el._handlers[t] = el._handlers[t] || []).push(fn); },
    removeEventListener() {},
    fire(t, ev) { (el._handlers[t] || []).forEach((fn) => fn(ev || {})); },
    querySelector: (s) => find(el, s), querySelectorAll: (s) => findAll(el, s),
    closest() { return el; }, scrollIntoView() {}, focus() {}, blur() {}, click() {},
    setPointerCapture() {}, releasePointerCapture() {}, hasPointerCapture: () => false,
    getBoundingClientRect: () => ({ width: 800, height: 500, left: 0, top: 0, right: 800, bottom: 500 }),
    getContext: () => makeCtx(), toDataURL: () => 'data:image/jpeg;base64,THUMB',
    animate: () => ({ finished: Promise.resolve(), cancel() {} }),
  };
  let _own = '';
  Object.defineProperty(el, 'innerHTML', {
    get: () => _own,
    set: (v) => { _own = String(v); el.children = []; indexHtml(el, _own); },
  });
  for (const p of ['src', 'href']) {
    Object.defineProperty(el, p, { get: () => el._attrs[p] || '', set: (v) => { el._attrs[p] = String(v); }, configurable: true });
  }
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

getEl('chatTitle').textContent = '新对话';
getEl('photoMode').checked = true;
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k),
  clear: () => store.clear(), get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null,
};
const bySelector = new Map();
function selectorEl(sel) { const k = String(sel); if (!bySelector.has(k)) bySelector.set(k, makeEl('div')); return bySelector.get(k); }
globalThis.document = {
  head: makeEl('head'), body: makeEl('body'), documentElement: makeEl('html'),
  getElementById: getEl, querySelector: (s) => selectorEl(s), querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  createDocumentFragment: () => makeEl('fragment'),
  createTreeWalker: () => ({ nextNode: () => false, currentNode: null }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.devicePixelRatio = 1;
globalThis.NodeFilter = { SHOW_TEXT: 4 };
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
globalThis.Image = class { set src(v) { setTimeout(() => this.onload && this.onload(), 0); } get src() { return ''; } width = 800; height = 600; };
globalThis.FileReader = class {
  readAsDataURL() { setTimeout(() => { this.result = 'data:image/jpeg;base64,FULL'; this.onload && this.onload(); }, 0); }
};

/* ------------------------------------------------- 假 SSE 流 */
const BODIES = [];
function sse(events) {
  const enc = new TextEncoder();
  const text = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('');
  let sent = false;
  return {
    ok: true, status: 200, body: {
      getReader: () => ({
        read: async () => {
          if (sent) return { done: true, value: undefined };
          sent = true;
          return { done: false, value: enc.encode(text) };
        },
      }),
    },
  };
}
let nextStream = () => sse([]);
globalThis.fetch = async (url, opt) => {
  BODIES.push({ url: String(url), body: opt && opt.body ? JSON.parse(opt.body) : null });
  if (String(url).includes('/kg/entities')) {
    const d = { entities: [] };
    return { ok: true, status: 200, text: async () => JSON.stringify(d), json: async () => d };
  }
  return nextStream();
};

let pass = 0, fail = 0;
const ok = (name, cond, note = '') => {
  if (cond) { pass++; console.log('  √ ' + name + (note ? '　' + note : '')); }
  else { fail++; console.log('  × ' + name + (note ? '　' + note : '')); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const last = () => BODIES[BODIES.length - 1].body;

const { state } = await import(pathToFileURL(path.join(DIR, 'js/util.js')).href);
state.chats = [{ id: 'c1', title: '新对话', created: 1, updated: 1, messages: [] }];
state.activeId = 'c1';

const img = await import(pathToFileURL(path.join(DIR, 'js/image.js')).href);
const askMod = await import(pathToFileURL(path.join(DIR, 'js/ask.js')).href);

const PHOTO_REPORT = '【一、图片类型】\n其他现场\n\n【二、图中可见事实】\n1. 照片显示一个室内空间……';
// 后端普通问答路径的真实形态：发了 generate run 之后**直接** done，没有 generate done
const PLAIN_DONE_MISSING = () => sse([
  ['status', { stage: 'intent', message: '识别意图…', state: 'run' }],
  ['status', { stage: 'generate', message: '生成中…', state: 'run' }],
  ['chunk', '您好，请问有什么可以帮您？'],
  ['done', { route: 'general', sources: [], latency_s: 1.2 }],
]);

/* ============================================================ 第一轮：带图 */
console.log('\n【第一轮】上传图片并提问');
{
  getEl('fileInput').files = [{ type: 'image/jpeg', size: 1024, name: '现场.jpg' }];
  await img.onPickImage(getEl('fileInput'));
  await sleep(20);
  ok('图片已就绪', !!img.pendingImage, img.pendingImage ? img.pendingImage.name : 'null');

  nextStream = () => sse([
    ['status', { stage: 'vision', message: '读取图片', state: 'run' }],
    ['status', { stage: 'vision', message: '图片已识别', state: 'done', detail: '120 字' }],
    ['vision', { text: '照片里是一处危废暂存间' }],
    ['status', { stage: 'generate', message: '生成专业研判', state: 'run' }],
    ['status', { stage: 'generate', message: '研判内容已生成', state: 'done' }],
    ['chunk', PHOTO_REPORT],
    ['done', { route: 'photo', sources: [], latency_s: 6.7 }],
  ]);
  getEl('q').value = '';
  await askMod.ask();
  await sleep(30);

  const b = last();
  ok('第一轮请求带了图片', typeof b.image === 'string' && b.image.startsWith('data:image/'));
  ok('第一轮 report=photo', b.report === 'photo', String(b.report));
  ok('第一轮结束后 pendingImage 已清空', img.pendingImage === null, String(img.pendingImage));
  /* ★ 这条是"当前轮带图就不发历史"的断言 */
  ok('第一轮（带图）不发历史，图片分析自成一体', Array.isArray(b.history) && b.history.length === 0,
    'history 条数 = ' + (b.history || []).length);
}

/* ==================================================== 第二轮：纯文字 111 */
console.log('\n【第二轮】输入 111（纯文字）—— 核心断言');
{
  nextStream = PLAIN_DONE_MISSING;
  getEl('q').value = '111';
  await askMod.ask();
  await sleep(30);
  const b = last();
  const dump = JSON.stringify(b.history);
  console.log('      第二轮 history：' + (dump.length > 200 ? dump.slice(0, 200) + '…' : dump));

  ok('bug1：第二轮请求不带图片', b.image === null, String(b.image));
  ok('bug1：第二轮 report 不是 photo', b.report !== 'photo', String(b.report));
  ok('bug1：历史里不含图片数据（data:image）', !dump.includes('data:image'));
  ok('bug1：历史里不含上一轮的照片研判报告', !dump.includes('图片类型') && !dump.includes('图中可见事实'),
    dump.includes('图片类型') ? '报告还在历史里！' : '已剔除');
}

/* ============ 反向断言：正常的多轮对话历史不能被一起砍掉 ============ */
console.log('\n【反向断言】不带图片的多轮对话，历史必须照常发送');
{
  const c1 = state.chats.find((x) => x.id === 'c1');
  c1.messages.push({ role: 'user', content: '危废贮存有什么要求？' });
  c1.messages.push({ role: 'assistant', content: '要分区贮存、设置识别标志、做防渗。' });
  nextStream = PLAIN_DONE_MISSING;
  getEl('q').value = '那防渗具体怎么做？';
  await askMod.ask();
  await sleep(30);
  const b = last();
  const dump = JSON.stringify(b.history);
  ok('正常多轮：历史照常发送（没被一刀砍空）', Array.isArray(b.history) && b.history.length > 0,
    'history 条数 = ' + (b.history || []).length);
  ok('正常多轮：历史里含上一轮的用户提问', dump.includes('危废贮存有什么要求'));
  ok('正常多轮：历史里含上一轮的助手回答', dump.includes('要分区贮存'));
  ok('正常多轮：本轮问题仍在 query 里', b.query === '那防渗具体怎么做？', String(b.query));
  ok('正常多轮：assistant/user 角色交替正确',
    b.history.every((m, i) => m.role === (i % 2 === 0 ? 'user' : 'assistant')),
    b.history.map((m) => m.role).join(','));
}

/* ========================================================== bug 2：转圈 */
console.log('\n【bug 2】回答完成后，步骤时间线不能还有 running');
{
  const msgs = state.chats.find((x) => x.id === 'c1').messages;
  let stillRunning = [];
  for (const m of msgs) {
    if (m.role !== 'assistant') continue;
    for (const s of m.steps || []) if (s.state === 'running') stillRunning.push(s.stage || '?');
  }
  console.log('      所有助手消息的步骤状态：');
  for (const m of msgs) {
    if (m.role !== 'assistant' || !(m.steps || []).length) continue;
    console.log('        route=' + (m.route || '?') + '  '
      + m.steps.map((s) => (s.stage || '?') + '=' + s.state).join('  '));
  }
  ok('bug2：没有任何残留 running 的步骤', stillRunning.length === 0,
    stillRunning.length ? stillRunning.join(',') + ' 还在 running' : '全部已收尾');

  const html = getEl('messages').innerHTML;
  ok('bug2：渲染的 HTML 里没有 trace-row running（否则 CSS 无限转）',
    !html.includes('trace-row running'),
    html.includes('trace-row running') ? '还有在转的行！' : '干净');
  ok('bug2：后端漏发 done 的那步被标成了详细说明',
    jsonHasDetail(msgs, '已完成'), '');
}
function jsonHasDetail(msgs, detail) {
  for (const m of msgs) for (const s of m.steps || []) if (s.state === 'done' && s.detail === detail) return true;
  return false;
}

/* ================= 反向断言：后端补齐 done 之后，不再依赖兜底 ================= */
console.log('\n【反向断言】后端发全 done 时，兜底不该篡改正常的 detail');
{
  state.chats.push({ id: 'c2', title: 'x', created: 2, updated: 2, messages: [] });
  state.activeId = 'c2';
  nextStream = () => sse([
    ['status', { stage: 'intent', message: '识别意图…', state: 'run' }],
    ['status', { stage: 'intent', message: '意图已识别', state: 'done', detail: '科普问答' }],
    ['status', { stage: 'generate', message: '生成中…', state: 'run' }],
    ['status', { stage: 'generate', message: '回答已生成', state: 'done' }],
    ['chunk', '好的。'],
    ['done', { route: 'general', sources: [], latency_s: 1.0 }],
  ]);
  getEl('q').value = '你好';
  await askMod.ask();
  await sleep(30);
  const m = state.chats.find((x) => x.id === 'c2').messages.filter((x) => x.role === 'assistant').pop();
  ok('已收尾的步骤 detail 保持后端给的内容（"科普问答"）',
    (m.steps || []).some((s) => s.stage === 'intent' && s.detail === '科普问答'),
    (m.steps || []).map((s) => s.stage + ':' + s.detail).join(' | '));
  ok('兜底没有把已完成的步骤改成"已完成"',
    !(m.steps || []).every((s) => s.detail === '已完成'));
}

console.log('\n' + '='.repeat(80));
console.log('结论：通过 ' + pass + ' / 失败 ' + fail);
console.log('='.repeat(80));
process.exit(fail ? 1 : 0);
