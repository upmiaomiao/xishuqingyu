#!/usr/bin/env node
/**
 * 批次 C 验证：第 6 项（预览资料不离开当前对话）。
 *
 * 要求：
 *   · 在同一界面向右弹开（不是跳新标签页）
 *   · 也能单独打开一个界面（抽屉右上角保留"在新标签打开"）
 *   · 关闭后主聊天界面回弹
 *
 * 关键断言是"**没有**跳到新标签页"—— 这是本次改动的核心，
 * 只断言"有抽屉"是不够的：旧代码也有链接，也能打开原文，只是会离开对话。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_批次C测试');
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
    closest() { return el; }, scrollIntoView() {}, focus() {}, blur() {}, click() {},
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 20, top: 40, bottom: 76, right: 800 }),
    getContext: () => ctxStub, toDataURL: () => 'data:image/png;base64,AAAA',
    animate: () => ({ finished: Promise.resolve(), cancel() {} }),
  };
  let _own = '';
  Object.defineProperty(el, 'innerHTML', {
    get: () => _own + el.children.map((c) => c.innerHTML).join(''),
    set: (v) => { _own = String(v); el.children = []; indexHtml(el, _own); },
  });
  /* 真实 DOM 里 el.src = x 会**反映**到 src 属性上，removeAttribute('src') 也会让
     el.src 变成空串。桩必须照做 —— 否则 `frame.src = url` 之后
     getAttribute('src') 拿到 null，测试会误报"没设置"。第一版就踩了这个。 */
  for (const prop of ['src', 'href']) {
    Object.defineProperty(el, prop, {
      get: () => el._attrs[prop] || '',
      set: (v) => { el._attrs[prop] = String(v); },
      configurable: true,
    });
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
// document 上注册的 keydown 要能触发，才能测 Esc 关闭
const docHandlers = {};
globalThis.document = {
  head: makeEl('head'), body: makeEl('body'), documentElement: makeEl('html'),
  getElementById: getEl, querySelector: (s) => selectorEl(s), querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  addEventListener(t, fn) { (docHandlers[t] = docHandlers[t] || []).push(fn); },
  removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);

let pass = 0, fail = 0;
const ok = (name, cond, note = '') => {
  if (cond) { pass++; console.log('  √ ' + name + (note ? '　' + note : '')); }
  else { fail++; console.log('  × ' + name + (note ? '　' + note : '')); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { state } = await import(pathToFileURL(path.join(DIR, 'js/util.js')).href);
const { renderMessages, openDoc, closeDoc } = await import(pathToFileURL(path.join(DIR, 'js/message.js')).href);

const SRC = {
  index: 1,
  title: '危险废物贮存污染控制标准',
  standard_id: 'GB 18597-2023',
  doc_type: '国家标准',
  status: '现行',
  issuer: '生态环境部',
  region: '全国',
  source: '固废/危险废物贮存污染控制标准.md',
  text: '贮存设施应设置符合要求的标识标志。',
};
function seed(sources = [SRC]) {
  state.chats = [{
    id: 'c1', title: '测试', created: 1, updated: 1,
    messages: [
      { role: 'user', content: '问' },
      { role: 'assistant', content: '答[1]', route: 'rag', latency: 1, sources },
    ],
  }];
  state.activeId = 'c1';
  renderMessages();
}

/* ================================================================ */
console.log('\n【第 6 项】引用卡片：不再跳新标签页');
{
  seed();
  const html = getEl('messages').innerHTML;
  ok('「查看原文」是 <button>（不是 <a target=_blank>）',
    /<button class="pdf-link" onclick="openDoc\(1,1\)">/.test(html),
    (html.match(/<[a-z]+ class="pdf-link"[^>]*>/) || [''])[0]);
  ok('正文里已没有 target="_blank" 的原文链接', !/pdf-link[^>]*target="_blank"/.test(html));
  ok('按钮文案不再写「PDF」（后面除了 PDF 还可能是别的）', html.includes('📄 查看原文'));
}

console.log('\n【第 6 项】在当前页向右弹开');
{
  seed();
  const drawer = getEl('docDrawer');
  const frame = getEl('docFrame');
  const title = getEl('docTitle');
  const newTab = getEl('docOpenNew');
  const foot = getEl('docFoot');
  const fallback = getEl('docFallback');

  ok('初始是收起的', !drawer.classList.contains('open'));

  openDoc(1, 1);
  ok('抽屉打开', drawer.classList.contains('open'));
  ok('aria-hidden 变 false（无障碍）', drawer.getAttribute('aria-hidden') === 'false');
  ok('标题显示资料名', title.textContent === SRC.title, title.textContent);
  ok('iframe 指向 /doc?source=…', String(frame.getAttribute('src') || '').startsWith('/doc?source='),
    String(frame.getAttribute('src')));
  ok('中文路径做了 URL 编码',
    /%E5%8D%B1%E9%99%A9%E5%BA%9F%E7%89%A9/.test(String(frame.getAttribute('src'))),
    String(frame.getAttribute('src')));
  ok('iframe 可见', frame.style.display !== 'none');
  ok('抽屉底部有元数据', foot.innerHTML.includes('GB 18597-2023') && foot.innerHTML.includes('现行'));
  ok('抽屉底部有命中片段（PDF 渲染失败时仍有信息）', foot.innerHTML.includes('贮存设施应设置'));

  ok('仍保留「在新标签打开」这条路', String(newTab.href).startsWith('/doc?source='),
    String(newTab.href));
}

console.log('\n【第 6 项】关闭后主聊天界面回弹');
{
  const drawer = getEl('docDrawer');
  const frame = getEl('docFrame');
  closeDoc();
  ok('抽屉关闭', !drawer.classList.contains('open'));
  ok('aria-hidden 变 true', drawer.getAttribute('aria-hidden') === 'true');
  await sleep(300);
  ok('关闭后清掉 iframe src（释放 PDF 占用）', !frame.getAttribute('src'),
    String(frame.getAttribute('src')));

  // Esc 关闭
  seed();
  openDoc(1, 1);
  ok('重新打开', drawer.classList.contains('open'));
  (docHandlers.keydown || []).forEach((fn) => fn({ key: 'Escape' }));
  ok('按 Esc 能关闭', !drawer.classList.contains('open'));
}

console.log('\n【第 6 项】边界情况');
{
  // 来源不是 .md：没有 PDF 可开，但不能白屏
  seed([{ index: 2, title: '某地方文件', source: 'a.txt', text: '片段' }]);
  const drawer = getEl('docDrawer');
  const frame = getEl('docFrame');
  const fallback = getEl('docFallback');
  const newTab = getEl('docOpenNew');
  openDoc(1, 2);
  ok('非 .md 来源：抽屉仍打开', drawer.classList.contains('open'));
  ok('非 .md 来源：不加载 iframe', frame.style.display === 'none');
  ok('非 .md 来源：给出说明而不是空白', fallback.textContent.includes('没有可打开的原文'),
    fallback.textContent);
  ok('非 .md 来源：隐藏「在新标签打开」', newTab.style.display === 'none');
  ok('非 .md 来源：仍能看到命中片段', getEl('docFoot').innerHTML.includes('片段'));
  closeDoc();

  // 不存在的引用序号：不能抛异常
  seed();
  let threw = false;
  try { openDoc(99, 99); } catch { threw = true; }
  ok('引用序号不存在时不抛异常', !threw);
  ok('引用序号不存在时不误开抽屉', !drawer.classList.contains('open'));

  // 没有 sources 的消息
  state.chats[0].messages[1].sources = [];
  threw = false;
  try { openDoc(1, 1); } catch { threw = true; }
  ok('消息没有 sources 时不抛异常', !threw);
}

console.log('\n' + '='.repeat(80));
console.log('结论：通过 ' + pass + ' / 失败 ' + fail);
console.log('='.repeat(80));
process.exit(fail ? 1 : 0);
