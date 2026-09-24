#!/usr/bin/env node
/**
 * 验证 2026-09-18 用户提的四项改造（前端部分）。
 *
 *   第 1 项：回答完成后，检索进度 / 图片识别内容 / 分析过程三块**默认折叠**
 *   第 2 项：抽屉不再渲染原始 JSON；没有 PDF 时退回显示文本版全文
 *   第 3 项：界面不出现技术错误，只出现友好文案；真实错误进 console
 *
 * 判据落在**渲染出来的 HTML** 和**实际调用的接口顺序**上，不靠读代码猜。
 *
 * ★ 每条正向断言都配了反向断言：
 *   · "折叠了"要同时证明"正文没被一起折叠掉"；
 *   · "友好文案没有技术词"要同时证明"真的换成了别的话"（不是返回空串）；
 *   · "没有 PDF 时不加载 iframe"要同时证明"有 PDF 时**会**加载"。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_四项验证');
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
    insertBefore(c) { el.children.unshift(c); return c; },
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

/* console.error 要拦下来 —— 第 3 项要求"真实错误进控制台"，
   所以我们既要允许它被调用，又要在测试输出里不刷屏。
   测试自己的输出走 stdout：走 stderr 会被 PowerShell 当成错误，误报退出码。 */
const consoleErrors = [];
const realConsoleError = console.error;
console.error = (...a) => { consoleErrors.push(a); };
const say = (...a) => process.stdout.write(a.join(' ') + '\n');

/* ------------------------------------------------------------ 断言小工具 */
const FAILS = [];
function check(cond, desc) {
  if (cond) say("  OK   " + desc);
  else { say("  FAIL " + desc); FAILS.push(desc); }
}
function section(t) { say(""); say("=== " + t + " ==="); }

/* --------------------------------------------------------------- 载入模块 */
const U = await import(pathToFileURL(path.join(DIR, 'js/util.js')).href);
const M = await import(pathToFileURL(path.join(DIR, 'js/message.js')).href);
const A = await import(pathToFileURL(path.join(DIR, 'js/ask.js')).href);

/* ================================================================ 第 1 项 */
section("第 1 项：完成后三个区块默认折叠");

const baseMsg = {
  role: 'assistant',
  content: '这是最终答案正文。',
  reasoning: '这里是分析过程。',
  vision: '图片识别出来的原文。',
  steps: [
    { stage: 'retrieve', message: '已完成资料检索和内容核对', state: 'done', detail: '5 条' },
    { stage: 'generate', message: '回答已生成', state: 'done' },
  ],
  sources: [{ index: 1, title: '某标准', source: 'a/b.md', text: '片段' }],
  route: 'rag',
  latency: 3.2,
};

const doneHtml = M.messageHtml({ ...baseMsg, streaming: false }, 0);
const liveHtml = M.messageHtml({ ...baseMsg, streaming: true }, 0);

// —— 正向：已完成 → 三个区块都不带 open ——
check(!/<details class="vision-box"[^>]*\bopen\b/.test(doneHtml),
      "已完成：图片识别内容默认折叠");
check(!/<details class="thinking"[^>]*\bopen\b/.test(doneHtml),
      "已完成：分析过程默认折叠");
check(/已完成资料检索和内容核对/.test(doneHtml),
      "已完成：检索进度已收成一行（'已完成资料检索和内容核对　查看处理过程'）");

// —— 反向：生成中 → 两个区块必须展开，否则用户看不到实时进度 ——
check(/<details class="vision-box"[^>]*\bopen\b/.test(liveHtml),
      "生成中：图片识别内容仍然展开（进度可见）");
check(/<details class="thinking"[^>]*\bopen\b/.test(liveHtml),
      "生成中：分析过程仍然展开");

// —— 反向：折叠 ≠ 把正文也藏了 ——
check(/这是最终答案正文。/.test(doneHtml), "折叠后**正文仍然显示**（没被一起收掉）");
check(/这里是分析过程。/.test(doneHtml), "分析过程的内容还在，只是收起来了（点开就能看）");
check(/图片识别出来的原文。/.test(doneHtml), "图片识别内容也还在");

// —— 反向：历史消息没有 streaming 字段 → 也必须折叠 ——
const legacyHtml = M.messageHtml({ ...baseMsg }, 0);
check(!/<details class="vision-box"[^>]*\bopen\b/.test(legacyHtml),
      "老消息（没有 streaming 字段）也按已完成处理 → 折叠");
check(!/<details class="thinking"[^>]*\bopen\b/.test(legacyHtml),
      "老消息的分析过程同样折叠");

/* ================================================================ 第 3 项 */
section("第 3 项：界面不显示技术错误");

// —— 网络类错误 → 用户要求的原话 ——
check(A.friendlyError('E_MODEL_UNAVAILABLE') === '当前网络繁忙，正在重新处理…',
      "模型不可用 → 「当前网络繁忙，正在重新处理…」");
check(A.friendlyError('E_HTTP_500') === '当前网络繁忙，正在重新处理…',
      "HTTP 500 → 同上");
check(A.friendlyError('E_INTERNAL') === '当前网络繁忙，正在重新处理…',
      "内部异常 → 同上");

// —— ★ 反向：业务错误**不能**说成网络繁忙 ——
// 说成网络繁忙会让用户一直重试一件永远不会成功的事。
const docMsg = A.friendlyError('E_DOC_NOT_FOUND');
check(docMsg !== '当前网络繁忙，正在重新处理…',
      "「原文找不到」不会被说成网络繁忙（否则用户白重试）");
check(docMsg.length > 4, "它仍然给了一句有意义的话：" + docMsg);
const visionMsg = A.friendlyError('E_VISION_FAILED');
check(visionMsg !== '当前网络繁忙，正在重新处理…', "「图片识别失败」也不会被说成网络繁忙");
check(/图片/.test(visionMsg), "而且提示了该怎么办：" + visionMsg);

// —— 反向：所有友好文案里不许出现技术词汇 ——
const TECH = ['E_', 'Error', 'error', 'Exception', 'Traceback', 'HTTP', 'null',
              'undefined', '[object', 'NaN', '502', '500', 'stack'];
const CODES = ['E_MODEL_UNAVAILABLE', 'E_TIMEOUT', 'E_INTERNAL', 'E_ENGINE_UNAVAILABLE',
               'E_RETRIEVE_FAILED', 'E_VISION_FAILED', 'E_IMAGE_TOO_LARGE', 'E_IMAGE_FORMAT',
               'E_QUERY_EMPTY', 'E_DOC_NOT_FOUND', 'E_VALIDATION', 'E_BAD_REQUEST',
               'E_TOO_MANY_REQUESTS', 'E_PHOTO_NEEDS_IMAGE', 'E_HTTP_502', 'E_HTTP_500',
               'E_HTTP_404', 'E_SOMETHING_NEW', undefined, '', null];
let dirty = [];
for (const c of CODES) {
  const s = A.friendlyError(c);
  const hit = TECH.filter((w) => s.includes(w));
  if (hit.length) dirty.push(`${c} → "${s}" 命中 ${hit}`);
  if (!s || s.length < 4) dirty.push(`${c} → 文案为空`);
}
check(dirty.length === 0,
      `全部 ${CODES.length} 个错误码的文案都不含技术词汇` +
      (dirty.length ? "：" + dirty.join('；') : ""));

// —— recordError：正文变友好、真实内容进 console ——
consoleErrors.length = 0;
const am = { content: '' };
const shown = A.recordError(am, 'E_MODEL_UNAVAILABLE', {
  message: '模型服务异常：ConnectError(Connection refused)',
  tech_detail: 'httpx.ConnectError: [Errno 111] Connection refused',
  request_id: 'a1b2c3d4',
});
check(shown === '当前网络繁忙，正在重新处理…', "recordError 返回友好文案");
check(am.content === '当前网络繁忙，正在重新处理…', "am.content 被写成友好文案（不是原始错误）");
check(am.route === 'error', "am.route 标记为 error");
check(am.errorCode === 'E_MODEL_UNAVAILABLE', "错误码保留在 am.errorCode（供折叠详情用）");
check(String(am.errorTech).includes('ConnectError'), "真实错误保留在 am.errorTech");
check(am.errorRequestId === 'a1b2c3d4', "request_id 保留下来，能和后端日志对上");
check(consoleErrors.length === 1, "console.error 被调用了 1 次（真实错误进了控制台，这是用户的要求）");
check(!String(am.content).includes('ConnectError'),
      "★ 界面上显示的正文里没有 ConnectError（技术细节没漏出去）");

/* ================================================================ 第 2 项 */
section("第 2 项：抽屉不再渲染原始 JSON");

// 造一条带引用的会话
U.state.chats = [{
  id: 'c1', title: '测试', messages: [{
    role: 'assistant', content: '答案', route: 'rag',
    sources: [{ index: 1, title: '江苏苏州市物资再生有限公司报废机动车拆解项目',
                source: '环评报告/江苏苏州市物资再生有限公司.md',
                standard_id: '', doc_type: '环境影响报告书', text: '命中片段内容' }],
  }],
}];
U.state.activeId = 'c1';
check(!!U.current() && U.current().messages.length === 1, "测试会话装载成功");

// 记录 fetch 调用顺序
let calls = [];
let docInfoReply = null, docTextReply = null;
globalThis.fetch = async (url) => {
  const u = String(url);
  calls.push(u);
  const body = u.startsWith('/doc/info') ? docInfoReply
             : u.startsWith('/doc/text') ? docTextReply : { ok: false };
  return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
};

function resetDrawer() {
  getEl('docDrawer').classList.remove('open');
  getEl('docFrame').removeAttribute('src');
  getEl('docText').textContent = '';
  getEl('docFallback').textContent = '';
  getEl('docFoot').innerHTML = '';
}

const tick = () => new Promise((r) => setTimeout(r, 20));

/* --- 场景 A：有 PDF → 加载 iframe --- */
resetDrawer(); calls = [];
docInfoReply = { ok: true, has_pdf: true, has_md: true, pdf_bytes: 123 };
M.openDoc(0, 1);
await tick(); await tick();
check(calls.some((u) => u.startsWith('/doc/info')), "A 先问 /doc/info（先探测再加载）");
check(getEl('docFrame').getAttribute('src') !== null,
      "A 有 PDF 时**确实**加载了 iframe（反向断言：不是一律不加载）");
check(getEl('docText').style.display === 'none', "A 有 PDF 时不显示文本视图");

/* --- 场景 B：只有 .md（环评报告那 592 条就是这种）→ 文本版全文 --- */
resetDrawer(); calls = [];
docInfoReply = { ok: true, has_pdf: false, has_md: true, md_bytes: 762000 };
docTextReply = { ok: true, text: '# 一、建设项目基本情况\n\n正文内容……', chars: 19573, truncated: true, has_pdf: false };
M.openDoc(0, 1);
await tick(); await tick(); await tick();
check(calls.some((u) => u.startsWith('/doc/text')), "B 没有 PDF 时去取文本版全文");
check(getEl('docText').textContent.includes('建设项目基本情况'),
      "B 文本视图里真的出现了全文内容");
check(getEl('docFrame').getAttribute('src') === null,
      "B **没有**加载 iframe（不会去请求一个不存在的 PDF）");
check(getEl('docText').style.display !== 'none', "B 文本视图可见");
check(getEl('docFallback').style.display === 'none', "B 友好提示不显示（有内容可读）");

/* --- 场景 C：既没有 PDF 也没有文本 → 只给人话 --- */
resetDrawer(); calls = [];
docInfoReply = { ok: true, has_pdf: false, has_md: false };
docTextReply = null;
M.openDoc(0, 1);
await tick(); await tick(); await tick();
const fb = getEl('docFallback').textContent;
check(getEl('docFallback').style.display !== 'none', "C 显示友好提示");
check(!/[{}]/.test(fb) && !fb.includes('E_DOC') && !fb.includes('ok":'),
      "★ C 提示里**没有 JSON / 错误码**（这正是用户看到的那个问题）：" + JSON.stringify(fb));
check(fb.length > 6, "C 提示是一句完整的话");
check(getEl('docFrame').getAttribute('src') === null, "C 不加载 iframe");

/* --- 场景 D：/doc/info 本身失败 → 也要给人话，不能露原始错误 --- */
resetDrawer(); calls = [];
docInfoReply = { ok: false, code: 'E_DOC_NOT_FOUND', message: '未找到原文 PDF：x.pdf' };
M.openDoc(0, 1);
await tick(); await tick(); await tick();
const fb2 = getEl('docFallback').textContent;
check(!fb2.includes('E_DOC_NOT_FOUND') && !fb2.includes('未找到原文'),
      "★ D 接口报错时界面也不显示原始错误文案：" + JSON.stringify(fb2));
check(fb2.length > 6, "D 仍然给了一句完整的话");

/* --- 场景 E：抽屉底部始终带着来源与命中片段（PDF 渲染失败时的救命信息） --- */
resetDrawer();
docInfoReply = { ok: true, has_pdf: false, has_md: false };
M.openDoc(0, 1);
await tick(); await tick();
const foot = getEl('docFoot').innerHTML;
check(foot.includes('环评报告/江苏苏州市物资再生有限公司.md'), "E 底部显示来源路径");
check(foot.includes('命中片段内容'), "E 底部显示命中片段");

/* ------------------------------------------------------------------ 汇总 */
say("");
if (FAILS.length) {
  say(`失败 ${FAILS.length} 项：`);
  for (const f of FAILS) say("  · " + f);
  process.exit(1);
}
say("全部通过。");
