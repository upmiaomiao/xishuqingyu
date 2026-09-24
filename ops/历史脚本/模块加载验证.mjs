#!/usr/bin/env node
/**
 * 阶段 2b/3 的最后一层验证：用 Node 真实**执行**这些 ES 模块（带最小 DOM 桩）。
 *
 * 为什么必须做：HTTP 检查只能证明文件取得到、MIME 对。但「模块能不能被 JS 引擎加载」
 * 是另一回事 —— 语法错误、导出名写错、顶层代码抛异常，HTTP 全是 200 却在浏览器里白屏。
 * 这里把模块真的 import 一遍，并断言导出齐全、window 契约挂上了。
 *
 * 顺带：main.js 顶层会调 load() -> newConversation() -> save() -> render()，
 * 所以 import main.js 会**真的跑通一遍渲染链路**（历史列表 + 消息区 HTML 都会生成）。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_模块加载测试');

fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, 'js'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'frontend/js'))) {
  if (f.endsWith('.js')) {
    fs.copyFileSync(path.join(ROOT, 'frontend/js', f), path.join(DIR, 'js', f));
  }
}
fs.copyFileSync(path.join(ROOT, 'xishu_pipeline/static/gen_ui.js'), path.join(DIR, 'gen_ui.js'));
fs.copyFileSync(path.join(ROOT, 'xishu_pipeline/static/audit_ui.js'), path.join(DIR, 'audit_ui.js'));

// ---------------------------------------------------------------- DOM 桩
const ctxStub = new Proxy({}, { get: () => () => ctxStub });
const els = new Map();

// 极小的 innerHTML 索引器：浏览器会把 innerHTML 解析成真实节点，
// 而模块挂载后会立刻 root.querySelector('#auNeed') 这类查询。
// 桩若直接返回 null，模块就抛 "Cannot set properties of null"，
// 那是**桩的问题不是代码的问题** —— 但也不能就这么放过，否则挂载测试等于没测。
// 这里扫一遍 id / class / data-* 并建索引，让查询能命中。
function indexHtml(el, html) {
  el._byId = new Map();
  el._byClass = new Map();
  el._byAttr = new Map();
  const add = (map, k, v) => {
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(v);
  };
  for (const m of html.matchAll(/\bid="([^"]+)"/g)) {
    el._byId.set(m[1], makeEl('div', m[1]));
  }
  for (const m of html.matchAll(/\bclass="([^"]*)"/g)) {
    for (const c of m[1].split(/\s+/)) if (c) add(el._byClass, c, makeEl('div'));
  }
  for (const m of html.matchAll(/\b(data-[a-z-]+)="?([^"\s>]*)"?/g)) {
    add(el._byAttr, m[1], makeEl('div'));
  }
}

function queryOne(el, sel) {
  const s = String(sel);
  if (s.startsWith('#')) {
    const id = s.slice(1);
    if (el._byId && el._byId.has(id)) return el._byId.get(id);
    return getEl(id);          // 兜底：造一个，避免模块因 null 崩掉
  }
  if (s.startsWith('.')) {
    const c = s.slice(1);
    const list = el._byClass && el._byClass.get(c);
    if (list && list.length) return list[0];
    return makeEl('div');
  }
  const am = s.match(/^([a-z]+)?\[(data-[a-z-]+)/);
  if (am) {
    const list = el._byAttr && el._byAttr.get(am[2]);
    if (list && list.length) return list[0];
  }
  return makeEl('div');
}

function queryAll(el, sel) {
  const s = String(sel);
  if (s.startsWith('.')) {
    const c = s.slice(1);
    const list = el._byClass && el._byClass.get(c);
    return list && list.length ? list : [makeEl('div')];
  }
  const am = s.match(/\[(data-[a-z-]+)/);
  if (am) {
    const list = el._byAttr && el._byAttr.get(am[1]);
    return list && list.length ? list : [makeEl('div')];
  }
  return [];
}

function makeEl(tag = 'div', id = '') {
  const cls = new Set();
  let _html = '';
  const el = {
    tagName: String(tag).toUpperCase(),
    id,
    style: {},
    dataset: {},
    children: [],
    className: '',
    textContent: '',
    value: '',
    files: null,
    checked: false,
    disabled: false,
    scrollTop: 0,
    scrollHeight: 0,
    options: [],
    selectedIndex: 0,
    parentNode: null,
    _byId: new Map(),
    _byClass: new Map(),
    _byAttr: new Map(),
    classList: {
      add: (c) => cls.add(c),
      remove: (c) => cls.delete(c),
      toggle: (c, f) => (f === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : f ? cls.add(c) : cls.delete(c)),
      contains: (c) => cls.has(c),
    },
    setAttribute() {},
    getAttribute() {
      return null;
    },
    removeAttribute() {},
    appendChild(c) {
      el.children.push(c);
      if (c) c.parentNode = el;
      return c;
    },
    insertBefore(c) {
      el.children.push(c);
      if (c) c.parentNode = el;
      return c;
    },
    removeChild() {},
    remove() {},
    replaceChildren() {},
    addEventListener() {},
    removeEventListener() {},
    querySelector: (sel) => queryOne(el, sel),
    querySelectorAll: (sel) => queryAll(el, sel),
    closest() {
      return el;
    },
    scrollIntoView() {},
    focus() {},
    blur() {},
    click() {},
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0, right: 800, bottom: 600 }),
    getContext: () => ctxStub,
    toDataURL: () => 'data:image/png;base64,AAAA',
    animate: () => ({ finished: Promise.resolve(), cancel() {} }),
    play() {},
    pause() {},
  };
  Object.defineProperty(el, 'innerHTML', {
    get: () => _html,
    set: (v) => {
      _html = String(v);
      indexHtml(el, _html);
    },
  });
  return el;
}

function getEl(id) {
  if (!els.has(id)) els.set(id, makeEl('div', id));
  return els.get(id);
}

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
  get length() {
    return store.size;
  },
  key: (i) => [...store.keys()][i] ?? null,
};

globalThis.document = {
  head: makeEl('head'),
  body: Object.assign(makeEl('body'), { classList: makeEl().classList }),
  documentElement: makeEl('html'),
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (t) => makeEl(t),
  createTextNode: (t) => ({ textContent: t }),
  addEventListener() {},
  removeEventListener() {},
  readyState: 'complete',
  cookie: '',
  title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};

globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
// Node 24 的 navigator 是只读 getter，不能覆盖，直接用自带的
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
globalThis.fetch = () => Promise.reject(new Error('桩：不发起真实请求'));
globalThis.TextDecoder = TextDecoder;
globalThis.URL = URL;

// ---------------------------------------------------------------- 开始验证
let pass = 0;
let fail = 0;
const problems = [];
function ck(label, ok, extra = '') {
  if (ok) {
    pass++;
    console.log(`  √ ${label}${extra ? '　' + extra : ''}`);
  } else {
    fail++;
    problems.push(label);
    console.log(`  ✗ ${label}${extra ? '　' + extra : ''}`);
  }
}

(async () => {
  console.log('='.repeat(90));
  console.log('① 前端 8 个 ES 模块：逐个真实加载');
  console.log('='.repeat(90));
  const mods = {};
  for (const f of ['util.js', 'message.js', 'image.js', 'kg.js', 'views.js', 'store.js', 'ask.js', 'main.js']) {
    try {
      mods[f] = await import('file://' + path.join(DIR, 'js', f).replace(/\\/g, '/'));
      ck(`import js/${f}`, true, `${Object.keys(mods[f]).length} 个导出`);
    } catch (e) {
      ck(`import js/${f}`, false, e.message);
    }
  }

  console.log();
  console.log('='.repeat(90));
  console.log('② window 契约（HTML 的 onclick 只能调到全局函数）');
  console.log('='.repeat(90));
  const need = ['newConversation', 'selectChat', 'deleteChat', 'toggleSidebar',
    'openKnowledgeGraph', 'closeKnowledgeGraph', 'openAudit', 'openGen',
    'searchKnowledgeGraph', 'ask', 'useExample', 'showCitation', 'openImage',
    'onPickImage', 'clearPendingImage'];
  for (const n of need) {
    ck(`window.${n} 是函数`, typeof globalThis[n] === 'function');
  }
  ck('window.openAudit 是包装后的版本（先 closeGen）',
    typeof globalThis.openAudit === 'function' && globalThis.openAudit !== mods['views.js'].openAudit);

  console.log();
  console.log('='.repeat(90));
  console.log('③ main.js 顶层真的跑通了渲染链路（load -> newConversation -> save -> render）');
  console.log('='.repeat(90));
  const histHtml = getEl('history').innerHTML;
  ck('历史列表已渲染出内容', histHtml.length > 0, `${histHtml.length} 字符`);
  ck('历史列表含一个会话行', histHtml.includes('history-row'));
  ck('localStorage 已写入会话', (store.get('xishu_qingyu_chats_v2') || '').includes('新对话'));
  ck('消息区已渲染（空会话显示欢迎页）', getEl('messages').innerHTML.includes('welcome'));
  ck('chatTitle 被设置为会话标题', getEl('chatTitle').textContent === '新对话');

  console.log();
  console.log('='.repeat(90));
  console.log('④ 两个子界面模块：导出与 window 解耦');
  console.log('='.repeat(90));
  const gen = await import('file://' + path.join(DIR, 'gen_ui.js').replace(/\\/g, '/'));
  ck('gen_ui.js 导出 mountGenUI', typeof gen.mountGenUI === 'function');
  ck('gen_ui.js 导出 setEmbedded', typeof gen.setEmbedded === 'function');
  ck('gen_ui.js 不再挂 window.mountGenUI', globalThis.mountGenUI === undefined);
  const au = await import('file://' + path.join(DIR, 'audit_ui.js').replace(/\\/g, '/'));
  ck('audit_ui.js 导出 mountAuditUI', typeof au.mountAuditUI === 'function');
  ck('audit_ui.js 不再挂 window.mountAuditUI', globalThis.mountAuditUI === undefined);

  console.log();
  console.log('='.repeat(90));
  console.log('⑤ 真的调一次 mountGenUI / mountAuditUI（挂载到桩容器）');
  console.log('='.repeat(90));
  const genBox = makeEl('div', 'genBody');
  try {
    const h = gen.mountGenUI(genBox);
    ck('mountGenUI 返回句柄', h !== undefined && h !== null);
    ck('挂载后容器里有内容', genBox.innerHTML.length > 1000 || genBox.children.length > 0,
      `innerHTML ${genBox.innerHTML.length} 字符 / 子节点 ${genBox.children.length} 个`);
    ck('挂载是幂等的（重复挂载同一容器不重建）', gen.mountGenUI(genBox) === h);
  } catch (e) {
    ck('mountGenUI 执行', false, e.message);
  }
  const auBox = makeEl('div', 'auditRoot');
  try {
    const h = au.mountAuditUI(auBox);
    ck('mountAuditUI 返回句柄', h !== undefined && h !== null);
    // 注意：audit_ui.js 是用 appendChild 建 DOM 的，不是设 innerHTML，
    // 所以这里要查 children 而不是 innerHTML（我第一版就查错了地方）。
    ck('审核容器里挂了子节点', auBox.children.length > 0,
      `子节点 ${auBox.children.length} 个 / innerHTML ${auBox.innerHTML.length} 字符`);
    ck('句柄带 reload / run / render / destroy', h && typeof h.reload === 'function' &&
      typeof h.run === 'function' && typeof h.render === 'function' && typeof h.destroy === 'function');
    ck('重复挂载返回同一个实例（不丢审核结果）', au.mountAuditUI(auBox) === h);
  } catch (e) {
    ck('mountAuditUI 执行', false, e.message);
  }

  console.log();
  console.log('='.repeat(90));
  console.log(`结论：通过 ${pass} / 失败 ${fail}`);
  if (fail) {
    console.log('失败项：');
    for (const p of problems) console.log('  × ' + p);
  }
  console.log('='.repeat(90));
  process.exit(fail ? 1 : 0);
})();
