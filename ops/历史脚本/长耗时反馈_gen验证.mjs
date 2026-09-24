#!/usr/bin/env node
/**
 * 报告编制 · 长耗时反馈验证。
 *
 * 背景：摸底实测 `POST /gen/api/chat/start` 要 12.31 秒才返回，而这段时间里
 * 页面只有"发送"按钮变灰 —— 完全无反馈，比照片研判还糟。这次补了两处：
 *   A. 等待气泡：同步接口拿不到服务端信号，只能客户端自己报"在干什么 + 走动秒表"
 *   B. 进度条：任务里加了 stage/pct/secs，与「报告审核」链路拉齐标准
 *
 * 这个测试把 gen_ui.js 真加载起来、真触发点击、真喂假的 fetch 响应，
 * 检查上面两处是否按预期出现（我没有浏览器，这是能验证到的最深层）。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_gen测试');
fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(DIR, { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
fs.copyFileSync(path.join(ROOT, 'xishu_pipeline/static/gen_ui.js'), path.join(DIR, 'gen_ui.js'));

/* ---------------------------------------------------------------- DOM 桩
   与其它验证脚本同一套，但多一件事：**记下 addEventListener 的回调**，
   这样测试能真的"点"按钮，而不是绕过 UI 直接调内部函数。 */
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
    // 真实浏览器里 appendChild 加进去的内容**会**出现在 innerHTML 里。
    // 第一版桩没做这件事，于是 4 个断言全假失败（代码其实是对的）。
    // 第二版把子节点 HTML 拼进 _own 缓存，结果又错一次：子节点**后来**改了 innerHTML
    // （等待气泡变成结果就是这种），父节点读到的还是拼接时的旧串。
    // 所以现在改成：_own 只存自己的，getter **实时**序列化子节点。
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
    els.set(m[1], e);                       // 全局登记，$() 才找得到
  }
  for (const m of html.matchAll(/\bclass="([^"]*)"/g))
    for (const c of m[1].split(/\s+/)) if (c) add(el._byClass, c, makeEl('div'));
}
/* 找不到时返回 null（内部用），这样递归能继续往下找 —— 第一版直接返回一个空 div，
   导致递归第一层就"找到"了，永远找不到真正在子节点里的那个元素。 */
function find(el, sel) {
  const s = String(sel);
  if (s.startsWith('#')) {
    return (el._byId && el._byId.get(s.slice(1))) || (els.has(s.slice(1)) ? els.get(s.slice(1)) : null);
  }
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

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k),
  clear: () => store.clear(), get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null,
};
globalThis.document = {
  head: makeEl('head'), body: makeEl('body'), documentElement: makeEl('html'),
  getElementById: getEl, querySelector: () => null, querySelectorAll: () => [],
  createElement: (t) => makeEl(t), createTextNode: (t) => ({ textContent: t }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/gen' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.alert = () => {};
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);

/* ------------------------------------------------------------ 假 fetch */
let releaseStart, releaseJob;
const startGate = new Promise((r) => { releaseStart = r; });
const jobGate = new Promise((r) => { releaseJob = r; });
const calls = [];

globalThis.fetch = (url, opt) => {
  calls.push(String(url));
  const u = String(url);
  /* 假响应必须同时提供 json() 和 text()。
     2026-09-18 错误码改造后，gen_ui.js 的 post()/get() 改成**先 r.text() 拿原文、
     再尝试 JSON.parse**（为了防住"后端 500 回纯文本时 r.json() 抛 SyntaxError"），
     这里只给了 json()，于是测试直接崩在 `r.text is not a function`。
     这是**测试桩过期**，不是被测代码的问题。 */
  const body = (d) => ({
    ok: true, status: 200,
    json: () => Promise.resolve(d),
    text: () => Promise.resolve(JSON.stringify(d)),
  });
  const json = (d) => Promise.resolve(body(d));
  if (u.includes('/chat/start')) {
    // 挂住不返回，模拟那 12 秒；测试检查完等待气泡再放行
    return startGate.then(() => json({
      ok: true, session: 'S1', 采纳数: 5, 丢弃数: 1, 已知: [], 依据: {}, 丢弃: [],
      问题: [{ key: 'k1', 中文名: '总投资', 类型: 'float', 问题: '总投资多少？' }],
      还剩: 5, 缺项总数: 6, 剩余项: [], 对话: [], 描述: '',
    }));
  }
  if (u.includes('/chat/generate')) return json({ ok: true, job: 'J1' });
  if (u.includes('/job/J1')) {
    return jobGate.then(() => json({
      ok: true,
      job: { id: 'J1', status: 'running', stage: '③生成', pct: 35, secs: 4.2, step: 3, steps: 4,
             log: [{ step: '①校验', text: '校验通过', level: 'ok' },
                   { step: '③生成', text: '调用模型写叙述', level: 'info' }] },
    }));
  }
  if (u.includes('/outputs')) return json({ ok: true, files: [] });
  if (u.includes('/health')) return json({ ok: true, 字段数: 39, docx: 'ok' });
  return json({ ok: true });
};

/* ------------------------------------------------------------------ 跑 */
let pass = 0, fail = 0;
const problems = [];
function ck(label, ok, extra = '') {
  if (ok) { pass++; console.log(`  √ ${label}${extra ? '　' + extra : ''}`); }
  else { fail++; problems.push(label); console.log(`  ✗ ${label}${extra ? '　' + extra : ''}`); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const mod = await import('file://' + path.join(DIR, 'gen_ui.js').replace(/\\/g, '/'));
const host = makeEl('div');
mod.mountGenUI(host);
mod.setEmbedded(true);
await sleep(30);

console.log('='.repeat(88));
console.log('① 模板：进度条的四个 id 都在，且代码里真的用到了');
console.log('='.repeat(88));
const jsSrc = fs.readFileSync(path.join(DIR, 'gen_ui.js'), 'utf8');
for (const id of ['ge-prog', 'ge-prog-stage', 'ge-prog-secs', 'ge-prog-fill']) {
  const inTpl = jsSrc.includes(`id="${id}"`);
  const used = jsSrc.includes(`$("${id}")`);
  ck(`${id}：模板里定义 + 代码里使用`, inTpl && used, inTpl ? (used ? '' : '代码没用') : '模板没有');
}
ck('进度条初始是隐藏的', jsSrc.includes('id="ge-prog" class="ge-prog" hidden'));

console.log();
console.log('='.repeat(88));
console.log('② 提交项目描述（12 秒的同步接口）：必须出现走动秒表');
console.log('='.repeat(88));
getEl('ge-say').value = '临沂市兰山区某公司新建年产 3000 吨塑料制品生产线项目，总投资 500 万元。';
getEl('ge-send').fire('click');
await sleep(400);                      // 请求还挂着，正是"那 12 秒"
const stream = getEl('ge-stream');
const bubbles = stream.children;
ck('出现了等待气泡', bubbles.some((b) => String(b.className).includes('ge-wait')));
const wait = bubbles.find((b) => String(b.className).includes('ge-wait'));
ck('等待气泡说了在干什么', wait && /正在读你写的项目情况/.test(wait.innerHTML));
ck('等待气泡里有秒表', wait && /ge-secs/.test(wait.innerHTML));
// 秒表靠 setInterval 改 textContent —— 读 innerHTML 是读不到的（那是静态串），
// 必须读那个元素本身的 textContent，否则永远看到初始的 0.0。
const secsEl = wait && wait.querySelector('.ge-secs');
ck('秒表在走（>0）', secsEl && parseFloat(secsEl.textContent) > 0,
  secsEl ? secsEl.textContent + 's' : '找不到秒表元素');
ck('发送按钮已禁用（防重复提交）', getEl('ge-send').disabled === true);
ck('用户那句话排在等待气泡前面（顺序不能反）',
  bubbles.findIndex((b) => String(b.className).includes('ge-me')) <
  bubbles.findIndex((b) => String(b.className).includes('ge-wait')));

console.log();
console.log('='.repeat(88));
console.log('③ 接口返回后：等待气泡换成真实结果');
console.log('='.repeat(88));
releaseStart();
await sleep(120);
const waitAfter = stream.children.find((b) => String(b.className).includes('ge-wait'));
ck('等待气泡已消失', !waitAfter);
ck('换成了真实结果（含采纳数）', /读到 5 项信息/.test(stream.innerHTML));
ck('秒表已停（没有残留的 ge-secs）', !/ge-secs/.test(stream.innerHTML));
ck('发送按钮恢复', getEl('ge-send').disabled === false);

console.log();
console.log('='.repeat(88));
console.log('④ 生成报告：进度条显示 stage / 百分比 / 已用秒数');
console.log('='.repeat(88));
getEl('ge-gen').fire('click');
await sleep(60);
ck('发出了 /chat/generate', calls.some((c) => c.includes('/chat/generate')));
releaseJob();
await sleep(1800);                     // 等一轮轮询（间隔 1500ms）
const prog = getEl('ge-prog');
ck('进度条已显示', prog.hidden === false);
ck('显示当前阶段 + 第几步', getEl('ge-prog-stage').textContent === '③生成（第 3/4 步）',
  getEl('ge-prog-stage').textContent);
ck('显示已用秒数', /^[\d.]+s$/.test(getEl('ge-prog-secs').textContent),
  getEl('ge-prog-secs').textContent);
// 百分比是"走完了几步"不是"还剩多久"：③生成 是最大的一块活，此刻必须还在低位，
// 第一版给的 65% 会让用户以为快好了，那是错的。
ck('长阶段进行中时百分比仍在低位（不谎报接近完成）',
  parseFloat(getEl('ge-prog-fill').style.width) <= 40,
  getEl('ge-prog-fill').style.width);
ck('日志行照常出现', /校验通过/.test(getEl('ge-log').innerHTML));

console.log();
console.log('='.repeat(88));
console.log('⑤ 补充描述那条路：也调同一个 12 秒接口，同样要有秒表 + catch');
console.log('='.repeat(88));
const src = fs.readFileSync(path.join(DIR, 'gen_ui.js'), 'utf8');
ck('补充描述分支有等待气泡', /我（补充）[\s\S]{0,400}waitBubble/.test(src));
ck('补充描述分支有 catch（原先没有，报错时界面毫无反应）',
  /我（补充）[\s\S]{0,900}\.catch\(/.test(src));

console.log();
console.log('='.repeat(88));
console.log(`结论：通过 ${pass} / 失败 ${fail}`);
if (fail) { console.log('失败项：'); for (const p of problems) console.log('  × ' + p); }
console.log('='.repeat(88));
process.exit(fail ? 1 : 0);
