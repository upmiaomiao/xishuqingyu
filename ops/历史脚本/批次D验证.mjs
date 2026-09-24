#!/usr/bin/env node
/**
 * 批次 D 验证：第 7 项知识图谱的前端部分。
 *
 *   ② 图例 / 详情字段中文化
 *   ③④ 详情栏内容（名称、类型、关联法规、来源文件、相关条款、关系路径）
 *   ⑤ 搜索先出匹配结果列表，再选对象看图
 *   ⑥ 只看直接关系 / 展开下一层 / 重置视图
 *
 * 最有价值的两条断言是"**英文不许漏出来**"：
 *   LABEL_ZH / PROP_ZH / REL_ZH 三张表只要漏一个键，界面就会显示 Law、name_zh、
 *   APPLIES_TO_REGION 这类原文 —— 而这种遗漏不会报错，只能靠断言兜住。
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = 'D:/项目/中节能/0911训练/_中间产物/重构工作区';
const DIR = path.join(ROOT, '_批次D测试');
fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, 'js'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'package.json'), JSON.stringify({ type: 'module' }), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'frontend/js'))) {
  if (f.endsWith('.js')) fs.copyFileSync(path.join(ROOT, 'frontend/js', f), path.join(DIR, 'js', f));
}

/* ---------------------------------------------------------------- DOM 桩 */
function makeCtx() {
  const calls = [];
  const ctx = new Proxy({}, {
    get(_t, k) {
      if (k === 'setTransform' || k === 'clearRect' || k === 'save' || k === 'restore') return () => {};
      if (k === 'measureText') return () => ({ width: 40 });
      if (k === 'canvas') return { width: 800, height: 600 };
      if (typeof k === 'string' && /^(fillStyle|strokeStyle|lineWidth|globalAlpha|font|textAlign|textBaseline)$/.test(k)) return '';
      return (...a) => { calls.push([k, a]); };
    },
    set: () => true,
  });
  ctx.__calls = calls;
  return ctx;
}
const THE_CTX = makeCtx();
const els = new Map();
function makeEl(tag = 'div', id = '') {
  const cls = new Set();
  const el = {
    tagName: String(tag).toUpperCase(), id, style: {}, dataset: {}, children: [],
    className: '', textContent: '', value: '', checked: false, disabled: false, hidden: false,
    width: 0, height: 0, scrollTop: 0, scrollHeight: 0, clientWidth: 860, clientHeight: 520,
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
    removeChild() {}, remove() {}, replaceChildren(c) { el.children = c ? [c] : []; },
    replaceChild(n) { el.children.push(n); },
    addEventListener(t, fn) { (el._handlers[t] = el._handlers[t] || []).push(fn); },
    removeEventListener() {},
    fire(t, ev) { (el._handlers[t] || []).forEach((fn) => fn(ev || {})); },
    setPointerCapture() {}, releasePointerCapture() {}, hasPointerCapture: () => false,
    querySelector: (s) => find(el, s) || makeEl('div'),
    querySelectorAll: (s) => findAll(el, s),
    closest() { return el; }, scrollIntoView() {}, focus() {}, blur() {}, click() {},
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 20, top: 40, bottom: 76, right: 820 }),
    getContext: () => THE_CTX, toDataURL: () => 'data:image/png;base64,AAAA',
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

const kgView = getEl('kgView');
kgView.classList.add('open');
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
  createDocumentFragment: () => makeEl('fragment'),
  createTreeWalker: () => ({ nextNode: () => false, currentNode: null }),
  addEventListener() {}, removeEventListener() {}, readyState: 'complete', cookie: '', title: '',
  location: { search: '', href: 'http://127.0.0.1:8011/' },
};
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.devicePixelRatio = 2;
globalThis.NodeFilter = { SHOW_TEXT: 4 };
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.location = document.location;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);

/* ------------------------------------------------------- fetch 桩：假图谱 */
const LABELS = { Document: 697, Organization: 305, Violation: 243, PollutionSource: 147,
  Pollutant: 116, Article: 114, Region: 108, Industry: 78, TreatmentTech: 75,
  Penalty: 66, Law: 49, Case: 43, Standard: 29, Regulation: 27 };
const LAW = { id: 'Law_固废法_1', name: '中华人民共和国固体废物污染环境防治法', label: 'Law',
  props: { full_name: '中华人民共和国固体废物污染环境防治法', validity_status: '现行', region: '全国', level: '国家' }, matched: true };
const REGION = { id: 'Region_全国_2', name: '全国', label: 'Region', props: { name_zh: '全国', level: '国家' }, matched: false };
const ORG = { id: 'Org_生态环境部_3', name: '生态环境部', label: 'Organization', props: { name_zh: '生态环境部', level: '国家' }, matched: false };
const ART = { id: 'Article_第一百二十条_4', name: 'Article_…_第一百二十条', label: 'Article',
  props: { article_no: '第一百二十条', parent_doc: '中华人民共和国固体废物污染环境防治法', text_preview: '违反本法规定，有下列行为之一…' }, matched: false };
const DOC = { id: 'Doc_固废法_5', name: '固体废物污染环境防治法', label: 'Document', props: { name: '固体废物污染环境防治法' }, matched: false };
// 一个标准邻居：法条往往同时引用标准，"关联法规"这一段要靠它才有内容
const STD = { id: 'Std_18597_6', name: '危险废物贮存污染控制标准', label: 'Standard',
  props: { full_name: '危险废物贮存污染控制标准', std_id: 'GB 18597-2023', validity_status: '现行' }, matched: false };
const NODES = [LAW, REGION, ORG, ART, DOC, STD];
const LINKS = [
  { source: LAW.id, target: REGION.id, type: 'APPLIES_TO_REGION' },
  { source: LAW.id, target: ORG.id, type: 'ISSUED_BY' },
  { source: LAW.id, target: ART.id, type: 'CONTAINS_ARTICLE' },
  { source: LAW.id, target: DOC.id, type: 'CONTAINS_ARTICLE' },
  { source: LAW.id, target: STD.id, type: 'SUPERSEDES' },
];
const fetchCalls = [];
globalThis.fetch = async (url, opt) => {
  fetchCalls.push(String(url));
  const body = (d) => ({ ok: true, status: 200, text: async () => JSON.stringify(d), json: async () => d });
  if (String(url).includes('/kg/stats')) return body({ available: true, nodes: 2097, links: 7771, labels: LABELS });
  // depth=0 是"只要命中节点本身"当候选列表用，这里给两个**都标记为命中**的节点。
  // （第一版把 REGION 的 matched 留成 false，于是只算 1 个命中、触发了自动画图，
  //   误报了两条失败。桩的数据必须自洽。）
  if (String(url).includes('depth=0')) return body({ query: 'x', nodes: [LAW, { ...REGION, matched: true }], links: [], matched: 2 });
  return body({ query: 'x', nodes: NODES, links: LINKS, matched: 1 });
};

let pass = 0, fail = 0;
const ok = (name, cond, note = '') => {
  if (cond) { pass++; console.log('  √ ' + name + (note ? '　' + note : '')); }
  else { fail++; console.log('  × ' + name + (note ? '　' + note : '')); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const kg = await import(pathToFileURL(path.join(DIR, 'js/kg.js')).href);

/* ================================================================ ② 中文化 */
console.log('\n【第 7 项②】图例中文化');
{
  await kg.loadKnowledgeGraphStats();
  const legend = getEl('kgLegend').innerHTML;
  ok('节点数 / 关系数正常显示', getEl('kgStats').textContent.includes('2,097'),
    getEl('kgStats').textContent);
  const english = Object.keys(LABELS).filter((k) => new RegExp(`>${k}\\b`).test(legend));
  ok('图例里没有英文类型名', english.length === 0, english.join(',') || '干净');
  // 14 种类型必须**全部**出现在图例里。改动前是 slice(0,10)，
  // 而插入顺序恰好把 法律/行政法规/标准/案例 排在第 11～14 位，全被切掉了。
  ok('图例包含全部 14 种类型',
    (legend.match(/kg-dot/g) || []).length === Object.keys(LABELS).length,
    (legend.match(/kg-dot/g) || []).length + ' / ' + Object.keys(LABELS).length + ' 项');
  ok('图例里有「法律」（不能因为排序被截掉）', legend.includes('法律'));
  ok('图例按节点数从多到少排（Document 697 在最前）',
    legend.indexOf('文档') < legend.indexOf('法律'));
}

/* ================================================================ ⑤ 匹配列表 */
console.log('\n【第 7 项⑤】搜索先出匹配结果列表');
{
  getEl('kgQuery').value = '固体废物';
  await kg.searchKnowledgeGraph();
  const box = getEl('kgMatches');
  ok('搜索结果列出来了', box.innerHTML.includes('中华人民共和国固体废物污染环境防治法'));
  ok('列表项带中文类型', box.innerHTML.includes('法律'));
  ok('列表项可点击（onclick=pickKgMatch）', /onclick="pickKgMatch\('/.test(box.innerHTML));
  ok('给出匹配数量提示', /匹配 \d+ 个/.test(box.innerHTML),
    (box.innerHTML.match(/匹配[^<]*/) || [''])[0]);
  // 命中 2 个时不该自作主张画图，等用户选
  ok('命中多个时不自动画图（等用户选）', getEl('kgStats').textContent.indexOf('当前') === -1,
    getEl('kgStats').textContent);
  ok('命中多个时提示去右侧选择', getEl('kgEmpty').textContent.includes('请从右侧列表中选择'),
    getEl('kgEmpty').textContent);
}

console.log('\n【第 7 项⑤】只命中一个实体时直接画图（省一次点击）');
{
  const saved = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const body = (d) => ({ ok: true, status: 200, text: async () => JSON.stringify(d), json: async () => d });
    if (String(url).includes('depth=0')) return body({ query: 'x', nodes: [LAW, REGION], links: [], matched: 1 });
    return body({ query: 'x', nodes: NODES, links: LINKS, matched: 1 });
  };
  // REGION.matched 是 false，所以只有 LAW 算命中
  getEl('kgQuery').value = '固废法';
  await kg.searchKnowledgeGraph();
  ok('唯一命中 → 自动画图', getEl('kgStats').textContent.indexOf('当前') === 0,
    getEl('kgStats').textContent);
  globalThis.fetch = saved;
}

/* ================================================== ③④ 详情栏 */
console.log('\n【第 7 项③④】选中实体后画图 + 详情栏内容');
{
  await kg.pickKgMatch(LAW.id);
  const detail = getEl('kgDetail').innerHTML;
  ok('节点名称', detail.includes('中华人民共和国固体废物污染环境防治法'));
  ok('节点类型（中文）', detail.includes('法律') && !/>Law</.test(detail));

  ok('有关联法规分段', detail.includes('关联法规'));
  ok('有关联法规内容（生态环境部 / 全国）',
    detail.includes('生态环境部') || detail.includes('全国'));
  ok('有来源文件分段', detail.includes('来源文件'));
  ok('来源文件取自 Article 的 parent_doc', detail.includes('固体废物污染环境防治法'));
  ok('有相关条款分段', detail.includes('相关条款'));
  ok('相关条款带条款号', detail.includes('第一百二十条'));
  ok('相关条款带原文摘录', detail.includes('违反本法规定'));
  ok('有关系路径分段', detail.includes('关系路径'));

  // 中文化：详情里不该漏出英文字段名或英文关系名
  const leaks = ['name_zh', 'full_name', 'validity_status', 'article_no', 'parent_doc',
    'text_preview', 'APPLIES_TO_REGION', 'ISSUED_BY', 'CONTAINS_ARTICLE']
    .filter((k) => detail.includes(k));
  ok('详情栏没有漏出英文字段名/关系名', leaks.length === 0, leaks.join(',') || '干净');
  ok('关系名显示为中文（发布机构/适用于地区/包含条款）',
    detail.includes('发布机构') || detail.includes('包含条款'));

  // 视图操作按钮
  ok('有「只看直接关系」', detail.includes('只看直接关系'));
  ok('有「展开下一层」', detail.includes('展开下一层'));
  ok('有「重置视图」', detail.includes('重置视图'));
  ok('统计数据标明当前展开层数', /展开 \d 层/.test(getEl('kgStats').textContent),
    getEl('kgStats').textContent);
}

/* ================================================================ ⑥ 视图操作 */
console.log('\n【第 7 项⑥】只看直接关系 / 展开下一层 / 重置视图');
{
  fetchCalls.length = 0;
  kg.kgDirectOnly();
  ok('只看直接关系：统计显示邻居数', /直接关系/.test(getEl('kgStats').textContent),
    getEl('kgStats').textContent);
  ok('只看直接关系：不发新请求（本地过滤）', fetchCalls.length === 0, fetchCalls.join(' '));

  fetchCalls.length = 0;
  kg.kgExpandLayer();
  await sleep(30);
  ok('展开下一层：重新请求后端', fetchCalls.some((u) => u.includes('depth=2')),
    fetchCalls.join(' '));
  ok('展开下一层：层数封顶在 2（后端 depth 上限就是 2）',
    !fetchCalls.some((u) => /depth=[3-9]/.test(u)), fetchCalls.join(' '));

  fetchCalls.length = 0;
  kg.kgResetView();
  await sleep(30);
  ok('重置视图：回到 1 层', fetchCalls.some((u) => u.includes('depth=1')),
    fetchCalls.join(' '));
}

/* ================================================================ 边界 */
console.log('\n【第 7 项】边界情况');
{
  // 后端挂了 / 返回非 JSON
  const savedFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 500, text: async () => 'Internal Server Error', json: async () => { throw new Error('x'); } });
  let threw = false;
  try { await kg.loadKnowledgeGraphStats(); } catch { threw = true; }
  ok('图谱统计接口 500 时不抛异常', !threw);
  ok('给出可读的失败提示（不是 JSON 解析器报错原文）',
    getEl('kgStats').textContent.includes('图谱暂不可用') &&
    !/Unexpected token|SyntaxError/.test(getEl('kgStats').textContent),
    getEl('kgStats').textContent.slice(0, 60));

  threw = false;
  getEl('kgQuery').value = '危险废物';
  try { await kg.searchKnowledgeGraph(); } catch { threw = true; }
  ok('搜索接口 500 时不抛异常', !threw);
  ok('搜索失败给出「查询失败：」前缀',
    getEl('kgEmpty').textContent.startsWith('查询失败：'),
    getEl('kgEmpty').textContent.slice(0, 50));

  globalThis.fetch = savedFetch;

  // 图谱未加载
  globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ available: false }), json: async () => ({ available: false }) });
  await kg.loadKnowledgeGraphStats();
  ok('图谱未加载时明确说「图谱未加载」（不是"0 个节点"）',
    getEl('kgStats').textContent === '图谱未加载', getEl('kgStats').textContent);
  globalThis.fetch = savedFetch;

  // 一个都没命中
  globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ query: 'zzz', nodes: [{ id: 'x', name: 'n', label: 'Document', props: {}, matched: false }], links: [], matched: 0 }), json: async () => ({}) });
  getEl('kgQuery').value = 'zzz';
  await kg.searchKnowledgeGraph();
  ok('没有命中时明说没找到（不拿"度数最高"的结果冒充）',
    getEl('kgEmpty').textContent.includes('没有找到'), getEl('kgEmpty').textContent);
  ok('没有命中时匹配列表为空', !/pickKgMatch/.test(getEl('kgMatches').innerHTML));
  globalThis.fetch = savedFetch;

  // 清空搜索词不该发请求
  fetchCalls.length = 0;
  getEl('kgQuery').value = '   ';
  await kg.searchKnowledgeGraph();
  ok('空搜索词不发请求', fetchCalls.length === 0, fetchCalls.join(' '));
}

console.log('\n' + '='.repeat(80));
console.log('结论：通过 ' + pass + ' / 失败 ' + fail);
console.log('='.repeat(80));
process.exit(fail ? 1 : 0);
