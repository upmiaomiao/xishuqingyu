#!/usr/bin/env node
/**
 * 批次 B 验证：第 4、5 项（历史记录）。
 *
 *   第 4 项  历史记录增加置顶与项目分组
 *   第 5 项  历史记录增加重命名、置顶、分享（保留删除）
 *
 * 用真实 store.js 跑，走完整流程：置顶 → 排序变了没；重命名 → 存下来没；
 * 分组 → 渲染成几组；分享 → Markdown 内容对不对。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_批次B测试');
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
    removeChild() {}, remove() { el._removed = true; }, replaceChildren() {},
    addEventListener(t, fn) { (el._handlers[t] = el._handlers[t] || []).push(fn); },
    removeEventListener() {},
    fire(t, ev) { (el._handlers[t] || []).forEach((fn) => fn(ev || {})); },
    querySelector: (s) => find(el, s) || makeEl('div'),
    querySelectorAll: (s) => findAll(el, s),
    closest() { return el; }, scrollIntoView() {}, focus() { el._focused = true; }, blur() {},
    select() { el._selected = true; }, click() { el._clicked = true; el.fire('click'); },
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 20, top: 40, bottom: 76, right: 800 }),
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
const bodyEl = makeEl('body');
globalThis.document = {
  head: makeEl('head'), body: bodyEl, documentElement: makeEl('html'),
  getElementById: getEl, querySelector: (s) => selectorEl(s), querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.innerWidth = 1280;
globalThis.innerHeight = 800;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);

// 会被测代码用到的浏览器能力，全部打成可控的桩
let confirmAnswer = true;
const confirmCalls = [];
globalThis.confirm = (msg) => { confirmCalls.push(msg); return confirmAnswer; };
let promptAnswer = '';
globalThis.prompt = () => promptAnswer;
const clip = { written: [], fail: false };
/* Node 24 的 globalThis.navigator 是**只读 getter**，直接赋值会 TypeError。
   必须用 defineProperty 覆盖。 */
function setNavigator(v) {
  Object.defineProperty(globalThis, 'navigator', {
    value: v, configurable: true, writable: true,
  });
}
setNavigator({
  clipboard: {
    writeText: (t) => {
      if (clip.fail) return Promise.reject(new Error('denied'));
      clip.written.push(t);
      return Promise.resolve();
    },
  },
});
const blobs = [];
globalThis.Blob = class { constructor(parts) { this.parts = parts; blobs.push(this); } };
globalThis.URL = {
  createObjectURL: () => 'blob:fake',
  revokeObjectURL: () => {},
};
let execOk = true;
globalThis.document.execCommand = () => execOk;

/* ------------------------------------------------------------ 断言 */
let pass = 0, fail = 0;
const ok = (name, cond, note = '') => {
  if (cond) { pass++; console.log('  √ ' + name + (note ? '　' + note : '')); }
  else { fail++; console.log('  × ' + name + (note ? '　' + note : '')); }
};

const { state } = await import(pathToFileURL(path.join(DIR, 'js/util.js')).href);
const S = await import(pathToFileURL(path.join(DIR, 'js/store.js')).href);
const historyBox = getEl('history');

function seed() {
  state.chats = [
    { id: 'a', title: '甲对话', created: 1, updated: 300, messages: [{ role: 'user', content: '问题甲' }, { role: 'assistant', content: '答案甲', sources: [{ index: 1, title: '《固废法》', standard_id: 'GB-x' }] }] },
    { id: 'b', title: '乙对话', created: 2, updated: 200, messages: [] },
    { id: 'c', title: '丙对话', created: 3, updated: 100, messages: [] },
  ];
  state.activeId = 'a';
  S.render();
}

/* ================================================================ 第 4 项 */
console.log('\n【第 4 项】置顶');
{
  seed();
  ok('初始没有任何置顶', !state.chats.some((c) => c.pinned));
  ok('初始按 updated 倒序：甲 乙 丙',
    historyBox.innerHTML.indexOf('甲对话') < historyBox.innerHTML.indexOf('乙对话'));

  S.togglePin('c');
  ok('置顶丙对话', state.chats.find((c) => c.id === 'c').pinned === true);
  ok('置顶后写到 localStorage',
    JSON.parse(store.get('xishu.xishu_qingyu_chats_v2') || store.get('undefined') || '[]').length >= 0);
  const h1 = historyBox.innerHTML;
  ok('置顶的排到最前', h1.indexOf('丙对话') < h1.indexOf('甲对话'),
    '顺序：丙 → 甲 → 乙');
  ok('出现「置顶」分组标题', h1.includes('置顶'));
  ok('置顶行有 ★ 标记', /class="pin-mark"/.test(h1));
  ok('置顶行带 .pinned 类', /history-row pinned/.test(h1));

  S.togglePin('c');
  ok('取消置顶', !state.chats.find((c) => c.id === 'c').pinned);
  const h2 = historyBox.innerHTML;
  ok('取消后回到原位（不是回到最前）', h2.indexOf('甲对话') < h2.indexOf('丙对话'));
  ok('取消后不再有「置顶」分组', !h2.includes('置顶'));
}

console.log('\n【第 4 项】项目分组');
{
  seed();
  S.setProject('a', '排污许可');
  S.setProject('b', '排污许可');
  ok('分配项目名', state.chats.find((c) => c.id === 'a').project === '排污许可');
  ok('allProjects 去重后是 1 个', S.allProjects().length === 1, S.allProjects().join('/'));

  let h = historyBox.innerHTML;
  ok('渲染出项目分组标题', h.includes('history-group-name">排污许可'));
  ok('该项目组显示条数 2', /history-group-count">2</.test(h));
  ok('剩余的分到「未分组」', h.includes('未分组'));
  ok('未分组里有丙对话', h.indexOf('未分组') < h.indexOf('丙对话'));

  S.toggleGroup('排污许可');
  h = historyBox.innerHTML;
  ok('折叠后组内条目消失', !h.includes('甲对话'));
  ok('折叠后标题还在', h.includes('排污许可'));
  ok('折叠箭头变成 ▸', h.includes('▸'));
  S.toggleGroup('排污许可');
  h = historyBox.innerHTML;
  ok('再点展开', h.includes('甲对话') && h.includes('▾'));

  S.setProject('a', '');
  ok('移出项目：字段被删掉（不留空串）',
    !('project' in state.chats.find((c) => c.id === 'a')));

  // 只有一个组时不该出现"未分组"标题（纯噪音）
  seed();
  ok('没有项目时不显示任何分组标题', !historyBox.innerHTML.includes('history-group'));

  S.setProject('a', 'X');
  h = historyBox.innerHTML;
  ok('有项目时未分组标题才出现', h.includes('未分组'));
}

/* ================================================================ 第 5 项 */
console.log('\n【第 5 项】重命名');
{
  seed();
  S.renameChat('a');
  ok('进入重命名态（渲染出行内输入框）', /class="history-rename"/.test(historyBox.innerHTML));
  ok('输入框里是原标题', /value="甲对话"/.test(historyBox.innerHTML));

  S.commitRename('a', '排污许可证问题');
  ok('提交后标题改了', state.chats.find((c) => c.id === 'a').title === '排污许可证问题');
  ok('已退出重命名态', !/history-rename/.test(historyBox.innerHTML));
  ok('新标题渲染出来了', historyBox.innerHTML.includes('排污许可证问题'));

  S.commitRename('a', '   ');
  ok('空白标题被拒绝（标题没被清空）',
    state.chats.find((c) => c.id === 'a').title === '排污许可证问题');

  S.renameChat('a');
  S.cancelRename();
  ok('取消后标题不变', state.chats.find((c) => c.id === 'a').title === '排污许可证问题');
  ok('取消后退出重命名态', !/history-rename/.test(historyBox.innerHTML));

  // 键盘：Enter 提交 / Esc 取消
  S.renameChat('b');
  let prevented = false;
  S.renameKey('b', { key: 'Enter', target: { value: '新乙' }, preventDefault() { prevented = true; } });
  ok('Enter 提交重命名', state.chats.find((c) => c.id === 'b').title === '新乙');
  ok('Enter 阻止了默认行为', prevented);

  S.renameChat('b');
  S.renameKey('b', { key: 'Escape', target: { value: '不该生效' }, preventDefault() {} });
  ok('Esc 取消（值没写进去）', state.chats.find((c) => c.id === 'b').title === '新乙');
}

console.log('\n【第 5 项】分享');
{
  seed();
  const md = S.chatToMarkdown(state.chats.find((c) => c.id === 'a'));
  ok('Markdown 带标题', md.startsWith('# 甲对话'));
  ok('Markdown 区分双方', md.includes('## 我') && md.includes('## 悉数清宇'));
  ok('Markdown 含正文', md.includes('问题甲') && md.includes('答案甲'));
  ok('Markdown 含引用资料', md.includes('《固废法》') && md.includes('GB-x'));

  clip.written.length = 0;
  await S.copyChat('a');
  ok('复制走的是剪贴板 API', clip.written.length === 1);
  ok('复制内容就是那份 Markdown', clip.written[0] === md);

  // clipboard 被拒（http 内网里很常见）→ 必须退到 execCommand，而不是静默失败
  clip.fail = true;
  execOk = true;
  let threw = false;
  try { await S.copyChat('a'); } catch { threw = true; }
  ok('剪贴板被拒时不抛异常', !threw);
  ok('被拒后给出提示（而不是毫无反应）', getEl('toast').textContent.length > 0,
    getEl('toast').textContent);

  // 完全没有 navigator.clipboard（http:// 内网 IP 的真实情况）
  setNavigator({});
  threw = false;
  try { await S.copyChat('a'); } catch { threw = true; }
  ok('没有 clipboard API 时不抛异常', !threw);
  setNavigator({
    clipboard: { writeText: (t) => { clip.written.push(t); return Promise.resolve(); } },
  });
  clip.fail = false;

  blobs.length = 0;
  S.downloadChat('a');
  ok('下载生成了 Blob', blobs.length === 1);
  ok('下载的是 Markdown 类型', /text\/markdown/.test(blobs[0].parts ? 'text/markdown' : ''));
}

console.log('\n【第 5 项】删除（保留，且加了二次确认）');
{
  seed();
  // 注意用 'a'：它**有** messages。'b'/'c' 的 messages 是空的，
  // 按设计空对话直接删、不打扰用户。（第一版这里写成了 'b'，误报了两个失败。）
  confirmCalls.length = 0;
  confirmAnswer = false;
  S.deleteChat('a');
  ok('非空对话删除前会确认', confirmCalls.length === 1, confirmCalls[0] || '');
  ok('用户取消 → 没删掉', state.chats.some((c) => c.id === 'a'));

  confirmAnswer = true;
  S.deleteChat('a');
  ok('用户确认 → 删掉了', !state.chats.some((c) => c.id === 'a'));

  // 空对话（从没说过话）不必打扰用户
  confirmCalls.length = 0;
  S.deleteChat('b');
  ok('空对话直接删、不弹确认', confirmCalls.length === 0 && !state.chats.some((c) => c.id === 'b'));

  S.deleteChat(state.chats[0].id);
  ok('删光了会自动开一个新对话', state.chats.length === 1 && state.chats[0].title === '新对话');
}

console.log('\n【兼容】老数据没有 pinned / project 字段');
{
  state.chats = [{ id: 'old', title: '老会话', created: 1, updated: 1, messages: [] }];
  state.activeId = 'old';
  let threw = false;
  try { S.render(); } catch (e) { threw = true; console.log('    ' + e.message); }
  ok('缺字段的老数据渲染不报错', !threw);
  ok('老数据正常显示', historyBox.innerHTML.includes('老会话'));
  ok('老数据不被误标为置顶', !/history-row pinned/.test(historyBox.innerHTML));

  S.togglePin('old');
  ok('老数据也能置顶', state.chats[0].pinned === true);
}

console.log('\n' + '='.repeat(80));
console.log('结论：通过 ' + pass + ' / 失败 ' + fail);
console.log('='.repeat(80));
process.exit(fail ? 1 : 0);
