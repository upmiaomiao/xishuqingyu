#!/usr/bin/env node
/**
 * 批次 A 验证：第 1/2/3 项。
 *
 *   第 1 项  用户消息里头像「你」和用户名「你」重复 → 只留一个
 *   第 2 项  回答中展开显示检索进度；完成后自动折叠为
 *            「已完成资料检索和内容核对　查看处理过程 ›」，手动可展开
 *   第 3 项  左侧功能区增加收起按钮
 *
 * 用真实模块跑（不是正则匹配源码）—— 这三项都是渲染/交互行为，
 * 只查字符串出现过没有，测不出"折叠了没有""状态存没存下来"。
 */
import fs from 'node:fs';
import path from 'node:path';
// Windows 上 import() 不收 'D:\...' 这种绝对路径，必须是 file:// URL。
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_批次A测试');
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
    scrollTop: 0, scrollHeight: 0, _handlers: {}, _attrs: {},
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

getEl('chatTitle').textContent = '新对话';
getEl('routePill').textContent = 'Thinking 已开启';
getEl('state').textContent = 'Enter 发送，Shift+Enter 换行';

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k),
  clear: () => store.clear(), get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null,
};
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

/* ------------------------------------------------------------ 断言 */
let pass = 0, fail = 0;
const ok = (name, cond, note = '') => {
  if (cond) { pass++; console.log('  √ ' + name + (note ? '　' + note : '')); }
  else { fail++; console.log('  × ' + name + (note ? '　' + note : '')); }
};

const { state } = await import(pathToFileURL(path.join(DIR, 'js/util.js')).href);
const { renderMessages, toggleSidebarCollapse, applySidebarCollapse } =
  await import(pathToFileURL(path.join(DIR, 'js/message.js')).href);

/* ================================================================ 第 1 项 */
console.log('\n【第 1 项】用户消息不再重复显示「你」');
{
  state.chats = [{
    id: 'c1', title: '测试', created: 1, updated: 1,
    messages: [
      { role: 'user', content: '危险废物的确认期限是多久？' },
      { role: 'assistant', content: '十日内。', route: 'rag', latency: 6.672, sources: [] },
    ],
  }];
  state.activeId = 'c1';
  const box = getEl('messages');
  renderMessages();
  const html = box.innerHTML;

  const userPart = html.slice(html.indexOf('user-msg'), html.indexOf('assistant-msg'));
  ok('用户消息里「你」只出现一次', (userPart.match(/你/g) || []).length === 1,
    '出现 ' + (userPart.match(/你/g) || []).length + ' 次');
  ok('用户消息不含 .who 用户名行', !/class="who"/.test(userPart));
  ok('用户头像仍在（与助手消息保持两栏对齐）', /class="avatar user-avatar"/.test(userPart));
  ok('正文完整保留', userPart.includes('危险废物的确认期限是多久？'));

  const asstPart = html.slice(html.indexOf('assistant-msg'));
  ok('助手消息仍显示「悉数清宇」（没被误删）', /class="who">悉数清宇/.test(asstPart));
}

/* ================================================================ 第 2 项 */
console.log('\n【第 2 项】检索进度：过程中展开，完成后自动折叠');
{
  const withSteps = (steps) => {
    state.chats = [{
      id: 'c2', title: '测试', created: 1, updated: 1,
      messages: [{ role: 'assistant', content: '答案正文', route: 'rag', latency: 6.7, sources: [], steps }],
    }];
    state.activeId = 'c2';
    renderMessages();
    return getEl('messages').innerHTML;
  };

  const running = withSteps([
    { stage: 'retrieve', message: '检索法规资料…', state: 'done', ms: 2100 },
    { stage: 'vision', message: '识别现场照片…', state: 'running', t0: Date.now() - 1500, progress: 320 },
  ]);
  ok('生成过程中：展开显示（不是 details，没有折叠）', /<div class="trace">/.test(running) && !/<details/.test(running));
  ok('生成过程中：有「处理过程」标题', /class="trace-head">处理过程</.test(running));
  ok('生成过程中：逐步显示检索进度', running.includes('检索法规资料') && running.includes('识别现场照片'));
  ok('生成过程中：显示已生成字数', running.includes('320 字'));

  const done = withSteps([
    { stage: 'retrieve', message: '检索法规资料…', state: 'done', ms: 2100, detail: '命中 8 条' },
    { stage: 'verify', message: '核对条文…', state: 'done', ms: 4600, detail: '全部可溯源' },
  ]);
  ok('完成后：折叠为 <details>（默认收起）',
    /<details class="trace trace-done">/.test(done) && !/<details class="trace trace-done" open/.test(done));
  ok('完成后：文案是「已完成资料检索和内容核对」', done.includes('已完成资料检索和内容核对'));
  ok('完成后：右侧是「查看处理过程 ›」',
    /class="trace-toggle">查看处理过程<i class="trace-chev">›<\/i>/.test(done));
  ok('完成后：旧文案「处理过程 · N 步」已不再出现', !/处理过程 · \d+ 步/.test(done));
  ok('完成后：总耗时仍在（6.7s）', /class="trace-secs">6\.7s</.test(done));
  ok('完成后：展开仍能看到每一步细节', done.includes('命中 8 条') && done.includes('全部可溯源'));

  const none = withSteps([]);
  ok('没有步骤时不渲染时间线', !none.includes('class="trace"'));
}

/* ================================================================ 第 3 项 */
console.log('\n【第 3 项】侧栏收起按钮');
{
  // 用 selectorEl() 而不是 bySelector.get()：DOM 桩是**按需创建**的，
  // 直接 get() 在第一次查询之前会拿到 undefined。（这里踩过一次。）
  const app = selectorEl('.app');
  const btn = getEl('sideToggle');

  store.delete('xishu.side.collapsed');
  applySidebarCollapse();
  ok('默认（没存过）是展开态', !app.classList.contains('side-collapsed'));
  ok('默认按钮是「«」（点了会收起）', btn.textContent === '«', '文案 ' + btn.textContent);
  ok('默认 aria-expanded=true', btn.getAttribute('aria-expanded') === 'true');

  toggleSidebarCollapse();
  ok('点一下：侧栏收起', app.classList.contains('side-collapsed'));
  ok('点一下：按钮变成「»」', btn.textContent === '»', '文案 ' + btn.textContent);
  ok('点一下：标题变成「展开侧栏」', btn.title === '展开侧栏', btn.title);
  ok('点一下：aria-expanded=false', btn.getAttribute('aria-expanded') === 'false');
  ok('点一下：写进 localStorage', store.get('xishu.side.collapsed') === '1',
    String(store.get('xishu.side.collapsed')));

  toggleSidebarCollapse();
  ok('再点一下：展开回来', !app.classList.contains('side-collapsed'));
  ok('再点一下：按钮变回「«」', btn.textContent === '«');
  ok('再点一下：localStorage 记成 0', store.get('xishu.side.collapsed') === '0');

  // 持久化：模拟刷新页面（重设 DOM 状态，再 apply）
  store.set('xishu.side.collapsed', '1');
  app.classList.remove('side-collapsed');
  applySidebarCollapse();
  ok('刷新后记住收起状态', app.classList.contains('side-collapsed'));
  ok('刷新后按钮图标跟着对', btn.textContent === '»');

  // localStorage 抛异常（隐私模式）不能把整个页面带崩
  const realGet = globalThis.localStorage.getItem;
  globalThis.localStorage.getItem = () => { throw new Error('SecurityError'); };
  let threw = false;
  try { applySidebarCollapse(); } catch { threw = true; }
  ok('localStorage 读不到时不抛异常（隐私模式）', !threw);
  globalThis.localStorage.getItem = realGet;
}

console.log('\n' + '='.repeat(80));
console.log('结论：通过 ' + pass + ' / 失败 ' + fail);
console.log('='.repeat(80));
process.exit(fail ? 1 : 0);
