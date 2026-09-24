/* 悉数清宇 · 问答主页脚本模块：kg.js
 *
 * 知识图谱：canvas 力导向布局、平移缩放、节点选中、匹配列表、逐层展开。
 * 自成一体，只依赖 util.js。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 *
 * 2026-09-18 第三轮回改（用户第 7 项）：中文化、匹配列表、双层展开、视图操作、
 *   连线着色与避让、详情栏补全。
 */

import { esc } from './util.js';

/* ============================================================
 *  kg.js
 * ============================================================ */

/* ------------------------------------------------------------------ 中文映射
 *
 * 这三张表**不是猜的**。2026-09-18 用「摸清图谱结构.py」实测线上图谱得到：
 *   14 种 label、14 个属性键、23 种关系名（关系名连出现次数一起统计）。
 * 表里只收实际出现过的键；遇到表外的值就原样显示 —— 图谱以后加了新类型，
 * 界面会显示英文原名，而不是变成空白或 undefined。
 * -------------------------------------------------------------------------- */
const LABEL_ZH = {
  Law: '法律',
  Regulation: '行政法规',
  Standard: '标准',
  Article: '条款',
  Pollutant: '污染物',
  PollutionSource: '污染源',
  Industry: '行业',
  TreatmentTech: '治理技术',
  Violation: '违法行为',
  Penalty: '行政处罚',
  Case: '案例',
  Organization: '机构',
  Region: '区域',
  Document: '文档',
};
const PROP_ZH = {
  name_zh: '名称',
  name: '名称',
  full_name: '全称',
  level: '层级',
  validity_status: '时效性',
  region: '适用地区',
  std_id: '标准号',
  article_no: '条款号',
  parent_doc: '所属文件',
  text_preview: '条款原文',
  category: '类别',
  type: '处罚类型',
  case_type: '案件类型',
  case_time: '案件时间',
};
const REL_ZH = {
  APPLIES_TO_REGION: '适用于地区',
  ISSUED_BY: '发布机构',
  SUPERSEDES: '替代',
  CONTAINS_ARTICLE: '包含条款',
  ARTICLE_REGULATES: '规制对象',
  ARTICLE_DEFINES_VIOLATION: '界定违法行为',
  ARTICLE_DEFINES_PENALTY: '规定处罚',
  ARTICLE_DEFINES_OBLIGATION: '规定义务',
  SOURCE_EMITS_POLLUTANT: '排放污染物',
  CASE_INVOLVES_POLLUTANT: '涉及污染物',
  CASE_INVOLVES_REGION: '涉及地区',
  CASE_INVOLVES_VIOLATION: '涉及违法行为',
  CASE_INVOLVES_ORGANIZATION: '涉及机构',
  CASE_INVOLVES_ORG: '涉及机构',
  CASE_INVOLVES_POLLUTION_SOURCE: '涉及污染源',
  CASE_INVOLVES_INDUSTRY: '涉及行业',
  CASE_VIOLATES: '违反条款',
  CASE_REGULATED_BY: '受监管于',
  INDUSTRY_USES_TECH: '采用治理技术',
  TECH_TREATS_POLLUTANT: '治理污染物',
  ORGANIZATION_REGULATES: '监管对象',
  ORGANIZATION_DRAFTS_LIST: '起草名录',
  ORGANIZATION_HANDLES_CASE: '办理案件',
};
/* 颜色同时用于图例、节点和**连线**。原先所有连线都是同一个浅灰 #D9E1E7，
   在浅色底上几乎看不见，而且无法区分关系种类。按起点节点的类型着色，
   一眼就能看出"这条线是从法律拉出去的还是从机构拉出去的"。 */
const KG_COLORS = {
  Law: '#0173C0',
  Regulation: '#2E7BD6',
  Standard: '#25B2B9',
  Article: '#1E9E6A',
  Pollutant: '#D89400',
  PollutionSource: '#E07B2B',
  Industry: '#2FA36B',
  TreatmentTech: '#1C97A0',
  Violation: '#D93F3F',
  Penalty: '#C94F4F',
  Case: '#6B7280',
  Organization: '#2478D6',
  Region: '#4A4F5C',
  Document: '#94A0AD',
};
/* 关系太多时优先显示的"实质关系"。
   APPLIES_TO_REGION ×19473 和 ISSUED_BY ×15770 占了全部关系的八成 ——
   每个法律都连到「全国」、每个文件都连到「发布机构」，
   结果图上全是这两类线，把真正有信息量的"条款界定违法"之类淹掉了。 */
const REL_MAJOR = new Set([
  'CONTAINS_ARTICLE', 'ARTICLE_REGULATES', 'ARTICLE_DEFINES_VIOLATION',
  'ARTICLE_DEFINES_PENALTY', 'ARTICLE_DEFINES_OBLIGATION', 'SOURCE_EMITS_POLLUTANT',
  'CASE_VIOLATES', 'CASE_INVOLVES_POLLUTANT', 'CASE_INVOLVES_VIOLATION',
  'CASE_INVOLVES_POLLUTION_SOURCE', 'CASE_INVOLVES_INDUSTRY', 'CASE_INVOLVES_ORGANIZATION',
  'CASE_INVOLVES_ORG', 'CASE_INVOLVES_REGION', 'CASE_REGULATED_BY',
  'INDUSTRY_USES_TECH', 'TECH_TREATS_POLLUTANT', 'ORGANIZATION_REGULATES',
  'ORGANIZATION_DRAFTS_LIST', 'ORGANIZATION_HANDLES_CASE', 'SUPERSEDES',
]);

const zhLabel = (x) => LABEL_ZH[x] || x || '';
const zhProp = (x) => PROP_ZH[x] || x || '';
const zhRel = (x) => REL_ZH[x] || x || '';

let kgGraph = { nodes: [], links: [] },
  kgPositions = [],
  kgEdges = [],
  kgSelected = null,
  kgCanvasState = { w: 0, h: 0, ratio: 1 },
  kgView = { x: 0, y: 0, scale: 1 },
  kgGesture = null;
let kgMatches = [];            // 搜索命中的实体，先列出来让用户选
let kgDepth = 1;               // 当前展开层数
let kgDirectMode = false;      // 只看直接关系
let kgFocusId = '';            // 当前聚焦的节点 id
let kgHover = null;            // 鼠标悬停到哪个节点

/* ------------------------------------------------------------------ 错误解析
   改动前本文件两处都是**先 await r.json() 再判 r.ok**，而后端未捕获异常回的是
   纯文本 "Internal Server Error"：r.json() 当场抛 SyntaxError，`d.detail` 那一行
   永远执行不到，L74 把 JSON 解析器报错原文贴到图谱空白区，用户读到的是
   `Unexpected token 'I', "Internal S"... is not valid JSON`。
   另外 FastAPI 422 的 detail 是**数组**，`new Error(数组)` 显示 [object Object]。
   现在统一：先取原文 → 尝试解析 → 不是 JSON 就保留原文 → 再按 r.ok 判。 */
async function readBody(r) {
  const t = await r.text();
  if (!t) return null;
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}
function errText(d, status) {
  if (d && typeof d === 'object') {
    if (typeof d.message === 'string' && d.message) return d.message;
    if (typeof d.detail === 'string' && d.detail) return d.detail;
    if (Array.isArray(d.detail)) return '请求参数有误';
    return `HTTP ${status}`;
  }
  if (typeof d === 'string' && d.trim() && d.length <= 200) return d.trim();
  return `HTTP ${status}`;
}
function kgEl(id) {
  return document.getElementById(id);
}

export async function loadKnowledgeGraphStats() {
  try {
    const r = await fetch('/kg/stats'),
      d = await readBody(r);
    if (!r.ok) throw new Error(errText(d, r.status));
    /* 后端用 available 明确告知图谱有没有加载上。改动前这个标志**从未被检查**：
       图谱文件缺失时界面显示"0 个节点 · 0 条关系"，与"真的空图"无法区分。 */
    if (!d || !d.available) {
      kgEl('kgStats').textContent = '图谱未加载';
      kgEl('kgLegend').innerHTML = '';
      return;
    }
    kgEl('kgStats').textContent =
      `${Number(d.nodes || 0).toLocaleString()} 个节点 · ${Number(d.links || 0).toLocaleString()} 条关系`;
    /* labels 缺失不该把已经拿到的节点数一起丢掉 —— 改动前这里抛错会被下面的 catch
       把统计覆盖成"图谱暂不可用"，**部分成功被当成整体失败**，用户丢掉已有的数据。 */
    const labels = d.labels && typeof d.labels === 'object' ? d.labels : {};
    /* 图例：**按节点数从多到少排，并且全部显示**。
       改动前是 `Object.entries(labels).slice(0, 10)` —— 截取顺序就是 JSON 里的
       插入顺序，而实测线上恰好是 Document, Organization, Violation, …, Law, …, Case。
       结果「法律」「行政法规」「标准」「案例」这四种**专业问答里最该看到的类型**
       排在第 11～14 位，被切掉了，图例上只剩文档、机构、违法这些。
       14 种类型在 flex-wrap 下占两行，没必要截。 */
    kgEl('kgLegend').innerHTML = Object.entries(labels)
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
      .map(
        ([k, v]) =>
          `<span><i class="kg-dot" style="background:${KG_COLORS[k] || '#89938f'}"></i>${esc(zhLabel(k))} ${v}</span>`,
      )
      .join('');
  } catch (e) {
    kgEl('kgStats').textContent = `图谱暂不可用：${(e && e.message) || e}`;
  }
}

/* ------------------------------------------------------------------ 推荐关键词
 *
 * 2026-09-18 用户反馈：「知识图谱，我也不知道有哪些字段，你让我自己搜索好像
 * 不太现实，可以放几个推荐的关键词」。
 *
 * 改动前进入图谱页看到的是一句"输入关键词探索知识图谱"——把发现成本全推给用户。
 * 而图谱里有 2000 多个实体、14 种类型，没人猜得出来。
 *
 * 这里一次给出两样东西：
 *   · 「推荐关键词」—— 跨类型挑连接数最高的十几个，点了直接搜；
 *   · 「按类型浏览」—— 每种类型的中文名 + 数量 + 几个例子。
 *     这一块同时回答了"有哪些字段"：用户扫一眼就知道这里能查法律、标准、
 *     条款、污染物、行业、案例……
 *
 * 推荐词全部是**服务端返回的真实节点名**，不是前端编的 ——
 * 点了一个搜不到结果，比不给推荐更让人困惑。
 */
let kgSuggestData = null;

function hideKgSuggest() {
  const box = kgEl('kgSuggest');
  if (box) box.hidden = true;
}

function chipHtml(name) {
  /* 用 data-kg-chip 而不是 onclick 内联：实体名里有引号、书名号、括号，
     拼进 onclick="..." 里会被截断（这正是 esc 存在的理由之一）。
     事件用委托统一处理。
     类名用 kg-sg-chip 而不是 kg-chip —— 后者已经被详情栏的节点按钮占用了。

     过长的名字（实测最长 46 字，如「中华人民共和国国家生态环境标准
     HJ 1322—2023 非道路移动机械排放远程监控技术规范」）会把整排撑爆，
     所以按钮上截断显示，title 里给全名，点了搜索用的也仍然是全名。 */
  const short = name.length > 16 ? name.slice(0, 15) + '…' : name;
  const tip = name.length > 16 ? name : '';
  return `<button class="kg-sg-chip" data-kg-chip="${esc(name)}" title="${esc(tip || ('搜索「' + name + '」'))}">${esc(short)}</button>`;
}

function renderKgSuggest(d) {
  const box = kgEl('kgSuggest');
  if (!box) return;
  const types = (d && d.types) || [];
  if (!types.length) { box.innerHTML = '<div class="kg-sg-load">图谱里还没有可推荐的实体。</div>'; return; }

  /* 跨类型**轮转**取，而不是把所有例子合起来按连接数排序。
     纯按度数排的实测结果：前 14 个里 4 个是 Organization（生态环境部及其别名）、
     4 个是标准、2 个区域（"全国"度数 2519，一个词就压过所有），
     污染物、法律、行业、案例**一个都进不来**。
     用户要的是"这里都有些什么"，被最大的几类占满就完全答不到这个问题。 */
  const top = [];
  const depth = 4;
  for (let r = 0; r < depth && top.length < 14; r++) {
    for (const t of types) {
      const e = (t.examples || [])[r];
      if (!e) continue;
      top.push(e);
      if (top.length >= 14) break;
    }
  }

  /* 类型默认只列前 6 种（按实体数排序），其余折起来 ——
     14 行一次性铺开会把"我该点什么"这个重点淹掉。 */
  const SHOW = 6;
  const rowHtml = (t) =>
    '<div class="kg-sg-row"><span class="kg-sg-label"><b>' +
    esc(zhLabel(t.label)) + '</b><br>' + t.count + ' 个</span>' +
    '<div class="kg-sg-chips">' +
    ((t.examples || []).length
      ? t.examples.map((e) => chipHtml(e.name)).join('')
      : '<span class="kg-sg-none">这一类的名字不适合当关键词，可在上方直接搜索</span>') +
    '</div></div>';

  box.innerHTML =
    '<div class="kg-sg-head">图谱里有 <b>' + (d.total_nodes || 0) + '</b> 个实体、<b>' +
    (d.total_links || 0) + '</b> 条关系，分 <b>' + (d.type_count || types.length) +
    '</b> 种类型。不知道搜什么？点下面的词试试。</div>' +
    '<div class="kg-sg-title">推荐关键词<small>每类挑一个，覆盖全部 ' + types.length +
    ' 种类型</small></div>' +
    '<div class="kg-sg-chips">' + top.map((e) => chipHtml(e.name)).join('') + '</div>' +
    '<div class="kg-sg-title">按类型浏览<small>共 ' + types.length + ' 种</small></div>' +
    types.slice(0, SHOW).map(rowHtml).join('') +
    '<div id="kgSgRest" hidden>' + types.slice(SHOW).map(rowHtml).join('') + '</div>' +
    (types.length > SHOW
      ? '<button class="kg-sg-more" id="kgSgMore">显示全部 ' + types.length + ' 种类型 ▾</button>'
      : '');
  box.hidden = false;

  const more = box.querySelector('#kgSgMore'), rest = box.querySelector('#kgSgRest');
  if (more && rest) {
    more.addEventListener('click', function () {
      const open = rest.hidden;
      rest.hidden = !open;
      more.textContent = open ? '收起 ▴' : '显示全部 ' + types.length + ' 种类型 ▾';
    });
  }
}

/** 拉取并渲染推荐关键词。已加载过就直接复用，除非 force。 */
export async function loadKgSuggestions(force) {
  const box = kgEl('kgSuggest');
  if (!box) return;
  if (kgSuggestData && !force) { renderKgSuggest(kgSuggestData); return; }
  try {
    const r = await fetch('/kg/suggest?per_label=4');
    const d = await readBody(r);
    if (!r.ok) throw new Error(errText(d, r.status));
    if (!d || !Array.isArray(d.types)) throw new Error('推荐词数据不完整');
    kgSuggestData = d;
    renderKgSuggest(d);
  } catch (e) {
    /* 推荐词拿不到不该挡住图谱本身：搜索框仍然可用，
       所以这里只在面板里说明情况，不弹错、不改变页面其他部分。 */
    box.innerHTML = '<div class="kg-sg-err">推荐关键词暂时读不出来（' +
      esc((e && e.message) || e) + '）。<br>你仍然可以直接在上方搜索框输入关键词。</div>';
    box.hidden = false;
  }
}

/* 点推荐词 = 把词填进搜索框再搜，让用户看到"我搜的就是这个词"，
   而不是凭空出来一张图（也方便他改了再搜）。 */
function onKgSuggestClick(e) {
  const btn = e.target && e.target.closest ? e.target.closest('[data-kg-chip]') : null;
  if (!btn) return;
  const input = kgEl('kgQuery');
  if (!input) return;
  input.value = btn.getAttribute('data-kg-chip') || '';
  searchKnowledgeGraph();
}

/** 挂上推荐词面板的事件委托。由 main.js 在启动时调用一次。 */
export function initKgSuggest() {
  const box = kgEl('kgSuggest');
  if (box) box.addEventListener('click', onKgSuggestClick);
}

/* ------------------------------------------------------------------ 搜索
 *
 * 第 7 项要求"搜索后先提供匹配结果列表，再由用户选择某个对象查看关系图"。
 * 改动前是"搜什么就直接画什么"：搜「固体废物」出来一团 70 个节点的图，
 * 用户不知道哪个才是自己要找的，也没法换一个。
 * 现在分两步：先列命中的实体（带类型和连接数），点了再画它的邻域。 */
export async function searchKnowledgeGraph() {
  const input = kgEl('kgQuery'),
    query = input.value.trim();
  if (!query) return;
  hideKgSuggest();               // 开始检索，推荐面板让位给结果
  const empty = kgEl('kgEmpty');
  empty.textContent = '正在检索…';
  empty.style.display = 'grid';
  kgEl('kgDetail').innerHTML = '<h3>知识图谱</h3><span class="kg-type">正在检索</span>';
  try {
    const r = await fetch(`/kg/search?query=${encodeURIComponent(query)}&depth=0&limit=70`),
      d = await readBody(r);
    if (!r.ok) throw new Error(errText(d, r.status));
    if (!d || !Array.isArray(d.nodes)) throw new Error('图谱返回的数据不完整');

    /* depth=0 时后端只返回命中节点本身（matched=1），正好当候选列表用。
       matched 为 0 说明一个都没命中，此时后端会退回"度数最高的 12 个"，
       那些**不是**匹配结果，必须区分开，否则用户会以为「随便搜什么都搜得到」。 */
    kgMatches = d.nodes.filter((n) => n.matched);
    if (!kgMatches.length) {
      kgMatches = [];
      renderMatchList(query, d.matched);
      empty.textContent = `没有找到与「${query}」相关的实体`;
      return;
    }
    kgMatches.sort((a, b) => (b.props && b.props.level ? 1 : 0) - (a.props && a.props.level ? 1 : 0));
    renderMatchList(query, d.matched);
    // 只有一个命中就直接画，省一次点击
    if (kgMatches.length === 1) await focusNode(kgMatches[0].id, 1);
    else empty.textContent = '请从右侧列表中选择一个实体';
  } catch (e) {
    /* 加"查询失败："前缀：改动前直接把 e.message 当界面文案，
       用户会读到 TypeError/SyntaxError 的原文，不知道那是出错还是提示。 */
    empty.textContent = `查询失败：${(e && e.message) || e}`;
    kgMatches = [];
    renderMatchList(query, 0);
  }
}

function renderMatchList(query, total) {
  const box = kgEl('kgMatches');
  if (!box) return;
  const head = total > kgMatches.length
    ? `匹配 ${total} 个，显示前 ${kgMatches.length} 个`
    : `匹配 ${kgMatches.length} 个实体`;
  box.innerHTML = kgMatches.length
    ? `<div class="kg-match-head">${esc(head)}</div>` +
      kgMatches
        .map(
          (n) =>
            `<button class="kg-match" onclick="pickKgMatch('${esc(n.id)}')">` +
            `<i class="kg-dot" style="background:${KG_COLORS[n.label] || '#89938f'}"></i>` +
            `<span class="kg-match-name">${esc(n.name)}</span>` +
            `<span class="kg-match-type">${esc(zhLabel(n.label))}</span></button>`,
        )
        .join('')
    : `<div class="kg-match-head">没有匹配「${esc(query)}」的实体</div>`;
  box.style.display = '';
}

/* 用户在匹配列表里选了一个实体 → 画它的邻域并居中 */
export async function pickKgMatch(id) {
  const n = kgMatches.find((x) => x.id === id);
  await focusNode(id, kgDepth, n ? n.name : '');
}

/* ------------------------------------------------------------------ 取邻域
 *
 * focusNode 是图谱的主入口：不管从搜索列表点、从正文实体点，还是双击展开，
 * 最终都是"以某个实体为中心取它的邻域"。
 * 用**实体名**作为查询词再交给后端 —— 后端本来就有"精确匹配 200 分"的排序，
 * 比前端自己拼子图可靠（也复用了同一套匹配规则）。 */
export async function focusNode(id, depth, name) {
  hideKgSuggest();               // 已经在看图了，推荐面板该让位
  const empty = kgEl('kgEmpty');
  empty.textContent = '正在构建子图…';
  empty.style.display = 'grid';
  kgFocusId = id;
  kgDepth = Math.max(1, Math.min(2, depth || 1));
  kgDirectMode = false;
  try {
    let q = name;
    if (!q) {
      const hit = kgMatches.find((x) => x.id === id);
      q = hit ? hit.name : String(id).split('_').slice(1, -1).join('_');
    }
    const r = await fetch(
      `/kg/search?query=${encodeURIComponent(q)}&depth=${kgDepth}&limit=70`,
    );
    const d = await readBody(r);
    if (!r.ok) throw new Error(errText(d, r.status));
    if (!d || !Array.isArray(d.nodes)) throw new Error('图谱返回的数据不完整');
    kgGraph = d;
    kgSelected = kgGraph.nodes.find((n) => n.id === id) || kgSelected;
    layoutKnowledgeGraph();
    const inGraph = kgGraph.nodes.some((n) => n.id === id);
    empty.style.display = kgGraph.nodes.length ? 'none' : 'grid';
    if (!inGraph) {
      /* 后端按名字匹配，理论上会命中；万一没有（同名/改名），
         至少要告诉用户"它不在当前子图里"，而不是画一张和选中项无关的图。 */
      kgEl('kgStats').textContent = '该实体不在返回的子图里，已显示相关结果';
    } else {
      kgEl('kgStats').textContent =
        `当前 ${kgGraph.nodes.length} 个节点 · ${(kgGraph.links || []).length} 条关系` +
        `（展开 ${kgDepth} 层）`;
    }
    if (kgSelected) renderDetail(kgSelected);
  } catch (e) {
    empty.textContent = `查询失败：${(e && e.message) || e}`;
  }
}

/* ------------------------------------------------------------------ 视图操作 */
export function kgDirectOnly() {
  if (!kgSelected) return;
  kgDirectMode = true;
  const keep = new Set([kgSelected.id]);
  kgEdges.forEach((e) => {
    const an = kgPositions[e.a] && kgPositions[e.a].node.id,
      bn = kgPositions[e.b] && kgPositions[e.b].node.id;
    if (an === kgSelected.id) keep.add(bn);
    if (bn === kgSelected.id) keep.add(an);
  });
  kgGraph = {
    nodes: kgGraph.nodes.filter((n) => keep.has(n.id)),
    links: kgGraph.links.filter((l) => keep.has(l.source) && keep.has(l.target)),
  };
  layoutKnowledgeGraph();
  kgEl('kgStats').textContent =
    `只看「${kgSelected.name}」的直接关系：${kgGraph.nodes.length - 1} 个邻居`;
}
export function kgExpandLayer() {
  const id = kgSelected ? kgSelected.id : kgFocusId;
  if (!id) return;
  focusNode(id, Math.min(2, kgDepth + 1), kgSelected ? kgSelected.name : '');
}
export function kgResetView() {
  kgDirectMode = false;
  kgView = { x: 0, y: 0, scale: 1 };
  if (kgFocusId && kgMatches.length) focusNode(kgFocusId, 1);
  else layoutKnowledgeGraph();
}

/* ------------------------------------------------------------------ 布局 */
function layoutKnowledgeGraph() {
  const canvas = kgEl('kgCanvas'),
    wrap = kgEl('kgCanvasWrap'),
    w = Math.max(wrap.clientWidth, 500),
    h = Math.max(wrap.clientHeight, 420),
    ratio = window.devicePixelRatio || 1;
  canvas.width = w * ratio;
  canvas.height = h * ratio;
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  kgCanvasState = { w, h, ratio };
  kgView = { x: 0, y: 0, scale: 1 };
  const nodes = kgGraph.nodes,
    index = new Map(nodes.map((n, i) => [n.id, i]));
  kgPositions = nodes.map((node) => ({ x: w / 2, y: h / 2, vx: 0, vy: 0, node, degree: 0 }));
  kgEdges = kgGraph.links
    .map((e) => ({ a: index.get(e.source), b: index.get(e.target), type: e.type }))
    .filter((e) => e.a !== undefined && e.b !== undefined);
  kgEdges.forEach((e) => {
    kgPositions[e.a].degree++;
    kgPositions[e.b].degree++;
  });
  const order = kgPositions
      .map((_, i) => i)
      .sort((a, b) => kgPositions[b].degree - kgPositions[a].degree),
    golden = Math.PI * (3 - Math.sqrt(5)),
    spread = Math.min(w, h) * 0.35;
  order.forEach((idx, rank) => {
    const radius = spread * Math.sqrt((rank + 0.5) / Math.max(order.length, 1)),
      angle = rank * golden;
    kgPositions[idx].x = w / 2 + Math.cos(angle) * radius;
    kgPositions[idx].y = h / 2 + Math.sin(angle) * radius;
  });
  const margin = 36;
  /* 斥力：节点越多要越大，否则 70 个节点会挤成一坨、标签全叠在一起。
     第 7 项提到"连线穿过其他节点、遮挡节点名称"—— 根因之一就是节点挨得太近。 */
  const density = Math.max(1, kgPositions.length / 26);
  for (let step = 0; step < 150; step++) {
    for (let i = 0; i < kgPositions.length; i++)
      for (let j = i + 1; j < kgPositions.length; j++) {
        const a = kgPositions[i],
          b = kgPositions[j];
        let dx = a.x - b.x,
          dy = a.y - b.y,
          d = Math.hypot(dx, dy);
        if (d < 0.1) {
          dx = ((i * 17 + j * 13) % 7) - 3;
          dy = ((i * 11 + j * 19) % 7) - 3;
          d = Math.max(Math.hypot(dx, dy), 1);
        }
        const minDistance = (30 + (a.node.matched || b.node.matched ? 8 : 0)) * density * 0.55,
          force =
            Math.min(1.4, (950 * density) / (d * d)) +
            (d < minDistance ? (minDistance - d) * 0.09 : 0),
          fx = (dx / d) * force,
          fy = (dy / d) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    kgEdges.forEach((e) => {
      const a = kgPositions[e.a],
        b = kgPositions[e.b],
        dx = b.x - a.x,
        dy = b.y - a.y,
        d = Math.max(Math.hypot(dx, dy), 1),
        /* 弹簧自然长度也随密度变长，否则边把节点又拉回一起 */
        rest = 92 * Math.min(density, 2.2),
        force = (d - rest) * 0.0045;
      a.vx += (dx / d) * force;
      a.vy += (dy / d) * force;
      b.vx -= (dx / d) * force;
      b.vy -= (dy / d) * force;
    });
    kgPositions.forEach((p) => {
      p.vx += (w / 2 - p.x) * 0.0012;
      p.vy += (h / 2 - p.y) * 0.0012;
      if (p.x < margin) p.vx += (margin - p.x) * 0.035;
      if (p.x > w - margin) p.vx -= (p.x - (w - margin)) * 0.035;
      if (p.y < margin) p.vy += (margin - p.y) * 0.035;
      if (p.y > h - margin) p.vy -= (p.y - (h - margin)) * 0.035;
      p.vx *= 0.78;
      p.vy *= 0.78;
      const speed = Math.hypot(p.vx, p.vy),
        limit = 7;
      if (speed > limit) {
        p.vx = (p.vx / speed) * limit;
        p.vy = (p.vy / speed) * limit;
      }
      p.x += p.vx;
      p.y += p.vy;
    });
  }
  /* 收尾的硬性分离：保证任意两个节点的圆心距 ≥ 2r + 文字宽度余量。
     这一步是"连线遮挡节点名"的直接对策 —— 名字画在节点右侧，
     相邻节点太近时名字必然压到别的节点上。 */
  const minSep = 34 * Math.min(density, 2.4);
  for (let step = 0; step < 40; step++)
    for (let i = 0; i < kgPositions.length; i++)
      for (let j = i + 1; j < kgPositions.length; j++) {
        const a = kgPositions[i],
          b = kgPositions[j];
        let dx = b.x - a.x,
          dy = b.y - a.y,
          d = Math.hypot(dx, dy);
        if (d < 0.1) {
          dx = 1;
          dy = 0;
          d = 1;
        }
        if (d < minSep) {
          const move = (minSep - d) / 2 + 0.15,
            ux = dx / d,
            uy = dy / d;
          a.x -= ux * move;
          a.y -= uy * move;
          b.x += ux * move;
          b.y += uy * move;
        }
      }
  if (kgPositions.length) {
    const minX = Math.min(...kgPositions.map((p) => p.x)),
      maxX = Math.max(...kgPositions.map((p) => p.x)),
      minY = Math.min(...kgPositions.map((p) => p.y)),
      maxY = Math.max(...kgPositions.map((p) => p.y)),
      spanX = Math.max(maxX - minX, 1),
      spanY = Math.max(maxY - minY, 1),
      fit = Math.min(1, (w - margin * 2) / spanX, (h - margin * 2) / spanY),
      cx = (minX + maxX) / 2,
      cy = (minY + maxY) / 2;
    kgPositions.forEach((p) => {
      p.x = w / 2 + (p.x - cx) * fit;
      p.y = h / 2 + (p.y - cy) * fit;
    });
  }
  drawKnowledgeGraph();
}

function nodeRadius(p) {
  return p.node.matched ? 10 : Math.min(8, 4.5 + p.degree * 0.22);
}

/* ------------------------------------------------------------------ 绘制
 *
 * 第 7 项提到两个具体毛病："连线颜色偏浅"和"连线穿过其他节点、遮挡节点名称"。
 * 三个对策：
 *   1. 按关系着色 + 提高对比度（原来全是 #D9E1E7 一种浅灰）；
 *   2. 连线画成**向一侧弯的弧**并提前在节点边缘收住 —— 直线会从中间穿过
 *      别的节点；弧线绕开，且起止点收在圆周上，不会压到节点圆面；
 *   3. 节点文字加白色描边（先 strokeText 再 fillText），
 *      这样即使底下压着一条线，字也能看清。
 * 另外把"实质关系"画深、"背景关系"（适用于地区/发布机构）画淡，
 * 避免 19473 条 APPLIES_TO_REGION 把图变成一片灰。 */
function drawKnowledgeGraph() {
  const { w, h, ratio } = kgCanvasState,
    ctx = kgEl('kgCanvas').getContext('2d');
  if (!w || !h) return;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.save();
  ctx.translate(kgView.x, kgView.y);
  ctx.scale(kgView.scale, kgView.scale);

  const selId = kgSelected ? kgSelected.id : '';
  const neighbors = new Set();
  if (selId)
    kgEdges.forEach((e) => {
      const an = kgPositions[e.a].node.id, bn = kgPositions[e.b].node.id;
      if (an === selId) neighbors.add(bn);
      if (bn === selId) neighbors.add(an);
    });

  const arrow = (x1, y1, x2, y2) => Math.atan2(y2 - y1, x2 - x1);

  kgEdges.forEach((e) => {
    const a = kgPositions[e.a], b = kgPositions[e.b];
    const an = a.node.id, bn = b.node.id;
    const touchesSel = selId && (an === selId || bn === selId);
    const major = REL_MAJOR.has(e.type);
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const ra = nodeRadius(a), rb = nodeRadius(b);
    // 起止点收在圆周外一点，线不会压到节点圆面
    const ux = dx / d, uy = dy / d;
    const sx = a.x + ux * (ra + 1), sy = a.y + uy * (ra + 1);
    const ex = b.x - ux * (rb + 3), ey = b.y - uy * (rb + 3);

    // 弧线：按两端节点类型算一个固定的垂直偏移，同类型的边弯曲方向一致
    const bend = Math.min(d * 0.16, 26) * (((e.a * 7 + e.b * 13) % 2) ? 1 : -1);
    const mx = (sx + ex) / 2 - uy * bend, my = (sy + ey) / 2 + ux * bend;

    let color, alpha, width;
    if (touchesSel) {
      color = KG_COLORS[a.node.label] || '#6B7280';
      alpha = 0.95;
      width = 1.8;
    } else if (major) {
      color = '#8792A2';
      alpha = kgDirectMode ? 0.5 : 0.42;
      width = 0.9;
    } else {
      color = '#C3CBD6';
      alpha = selId ? 0.16 : 0.35;   // 选中某节点时，无关的背景线让得更淡
      width = 0.6;
    }
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width / kgView.scale;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.quadraticCurveTo(mx, my, ex, ey);
    ctx.stroke();

    // 箭头只画在重要的边上，否则 70 个节点全是箭头会糊成一片
    if (touchesSel || (major && kgPositions.length <= 34)) {
      const ang = arrow(mx, my, ex, ey), size = touchesSel ? 6 : 4.5;
      ctx.beginPath();
      ctx.moveTo(ex, ey);
      ctx.lineTo(ex - size * Math.cos(ang - 0.42), ey - size * Math.sin(ang - 0.42));
      ctx.lineTo(ex - size * Math.cos(ang + 0.42), ey - size * Math.sin(ang + 0.42));
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    }
  });
  ctx.globalAlpha = 1;

  kgPositions.forEach((p) => {
    const selected = selId && selId === p.node.id,
      hovered = kgHover && kgHover.node.id === p.node.id,
      r = nodeRadius(p);
    ctx.beginPath();
    ctx.arc(p.x, p.y, selected ? r + 3 : hovered ? r + 2 : r, 0, Math.PI * 2);
    ctx.fillStyle = KG_COLORS[p.node.label] || '#89938f';
    ctx.fill();
    if (selected || hovered || p.node.matched) {
      ctx.lineWidth = (selected ? 2.2 : 1.6) / kgView.scale;
      ctx.strokeStyle = selected ? '#014E86' : '#0173C0';
      ctx.stroke();
    }
  });

  /* 标签单独一遍、画在所有节点之上：
     否则后画的节点圆面会盖住先画节点的文字。
     条件是"命中的 / 度数高的 / 图中节点不多的 / 选中的 / 悬停的"。 */
  const showAll = kgPositions.length < 28;
  kgPositions.forEach((p) => {
    const selected = selId && selId === p.node.id;
    if (!(p.node.matched || selected || p.node.id === kgFocusId || p.degree > 4 || showAll || (kgHover && kgHover.node.id === p.node.id)))
      return;
    const r = nodeRadius(p);
    ctx.font = `${selected ? 12 : 11}px "Microsoft YaHei",Arial,sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const label = p.node.name.length > 16 ? p.node.name.slice(0, 15) + '…' : p.node.name;
    const lx = p.x + r + 4, ly = p.y;
    // 白色描边：字底下的连线被"擦"掉，名字因此可读
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(255,255,255,0.92)';
    ctx.strokeText(label, lx, ly);
    ctx.fillStyle = selected ? '#014E86' : '#2B3040';
    ctx.fillText(label, lx, ly);
  });
  ctx.restore();
}

/* ------------------------------------------------------------------ 详情栏
 *
 * 第 7 项要求显示：节点名称、节点类型、关联法规、来源文件、相关条款、关系路径。
 * 这些全部能从**当前子图**推出来，不需要再发请求：
 *   · 关联法规 = 邻居里 label 属于 法律/行政法规/标准 的
 *   · 来源文件 = 邻居里的文档，外加 Article 自带的 parent_doc
 *   · 相关条款 = 邻居里的条款（带条款号与原文摘录）
 *   · 关系路径 = 本节点出发的每一条边，写成「—关系→ 对方」
 */
const LAW_LIKE = new Set(['Law', 'Regulation', 'Standard']);
function neighborsOf(id) {
  const out = [];
  kgEdges.forEach((e) => {
    const an = kgPositions[e.a] && kgPositions[e.a].node,
      bn = kgPositions[e.b] && kgPositions[e.b].node;
    if (!an || !bn) return;
    if (an.id === id) out.push({ node: bn, rel: e.type, dir: 'out' });
    else if (bn.id === id) out.push({ node: an, rel: e.type, dir: 'in' });
  });
  // 同一对节点之间可能有多条关系，去重时保留第一条，避免详情栏刷屏
  const seen = new Set();
  return out.filter((x) => {
    const k = x.node.id + '|' + x.rel;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
function section(title, inner) {
  return inner ? `<div class="kg-sec"><div class="kg-sec-head">${title}</div>${inner}</div>` : '';
}
function nodeChip(n) {
  return (
    `<button class="kg-chip" onclick="pickKgMatch('${esc(n.id)}')" title="在图中定位">` +
    `<i class="kg-dot" style="background:${KG_COLORS[n.label] || '#89938f'}"></i>` +
    `${esc(n.name)}<span class="kg-chip-type">${esc(zhLabel(n.label))}</span></button>`
  );
}
function renderDetail(n) {
  const nb = neighborsOf(n.id);
  const laws = nb.filter((x) => LAW_LIKE.has(x.node.label));
  const articles = nb.filter((x) => x.node.label === 'Article');
  /* 来源文件：① Article 的 parent_doc 属性直接给了出处；
     ② 邻居里的文档节点。两者都列，去重。 */
  const docs = nb.filter((x) => x.node.label === 'Document').map((x) => x.node);
  const parentDoc = (n.props || {}).parent_doc || '';
  const docNames = [...new Set([parentDoc, ...docs.map((d) => d.name)].filter(Boolean))];

  // 属性：按中文名排序，name_zh/name 已经是标题了就不再重复列
  const skip = new Set(['name_zh', 'name']);
  const props = Object.entries(n.props || {})
    .filter(([k, v]) => v && !skip.has(k))
    .map(
      ([k, v]) =>
        `<div class="kg-prop"><b>${esc(zhProp(k))}</b><span>${esc(String(v))}</span></div>`,
    )
    .join('');

  const relRows = nb
    .map((x) => {
      const arrowTxt = x.dir === 'out' ? '→' : '←';
      return (
        `<div class="kg-rel"><span class="kg-rel-name">${esc(zhRel(x.rel))}</span>` +
        `<span class="kg-rel-arrow">${arrowTxt}</span>` +
        `<button class="kg-rel-target" onclick="pickKgMatch('${esc(x.node.id)}')">${esc(x.node.name)}</button>` +
        `<span class="kg-rel-type">${esc(zhLabel(x.node.label))}</span></div>`
      );
    })
    .join('');

  kgEl('kgDetail').innerHTML =
    `<h3>${esc(n.name)}</h3>` +
    `<span class="kg-type" style="background:${KG_COLORS[n.label] || '#89938f'}22;border-color:${KG_COLORS[n.label] || '#89938f'}66;color:${KG_COLORS[n.label] || '#565962'}">${esc(zhLabel(n.label))}</span>` +
    `<div class="kg-actions">` +
    `<button onclick="kgDirectOnly()">只看直接关系</button>` +
    `<button onclick="kgExpandLayer()">展开下一层</button>` +
    `<button onclick="kgResetView()">重置视图</button>` +
    `</div>` +
    section('属性', props) +
    section('关联法规（' + laws.length + '）', laws.map((x) => nodeChip(x.node)).join('')) +
    section('来源文件（' + docNames.length + '）',
      docNames.map((d) => `<div class="kg-prop"><b>文件</b><span>${esc(d)}</span></div>`).join('')) +
    section('相关条款（' + articles.length + '）',
      articles
        .map((x) => {
          const p = x.node.props || {};
          return (
            `<div class="kg-article"><button class="kg-rel-target" onclick="pickKgMatch('${esc(x.node.id)}')">` +
            `${esc(p.article_no || x.node.name)}</button>` +
            (p.text_preview ? `<div class="kg-article-text">${esc(String(p.text_preview).slice(0, 200))}</div>` : '') +
            `</div>`
          );
        })
        .join('')) +
    section('关系路径（' + nb.length + '）', relRows);
}

function selectKnowledgeGraphNode(node) {
  kgSelected = node;
  kgFocusId = node.id;
  renderDetail(node);
  drawKnowledgeGraph();
  kgEl('kgDetail').scrollTop = 0;
}

/* ------------------------------------------------------------------ 交互 */
function kgScreenPoint(e) {
  const rect = e.currentTarget.getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}
function kgWorldPoint(point) {
  return { x: (point.x - kgView.x) / kgView.scale, y: (point.y - kgView.y) / kgView.scale };
}
function kgHitNode(point) {
  const world = kgWorldPoint(point);
  let best = null,
    dist = 18 / kgView.scale;
  kgPositions.forEach((p) => {
    const d = Math.hypot(p.x - world.x, p.y - world.y);
    if (d < dist) {
      best = p;
      dist = d;
    }
  });
  return best;
}
export function kgZoom(factor) {
  const cx = kgCanvasState.w / 2, cy = kgCanvasState.h / 2;
  const world = kgWorldPoint({ x: cx, y: cy });
  const next = Math.max(0.35, Math.min(3, kgView.scale * factor));
  kgView.x = cx - world.x * next;
  kgView.y = cy - world.y * next;
  kgView.scale = next;
  drawKnowledgeGraph();
}

const kgCanvas = document.getElementById('kgCanvas');
kgCanvas.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  const screen = kgScreenPoint(e),
    node = kgHitNode(screen);
  kgGesture = { pointerId: e.pointerId, node, start: screen, last: screen, moved: false };
  kgCanvas.setPointerCapture(e.pointerId);
  kgCanvas.classList.add('dragging');
  e.preventDefault();
});
kgCanvas.addEventListener('pointermove', (e) => {
  if (!kgGesture || kgGesture.pointerId !== e.pointerId) {
    // 没在拖拽时跟踪悬停，让用户知道哪个点可以点
    const hit = kgHitNode(kgScreenPoint(e));
    if (hit !== kgHover) {
      kgHover = hit;
      kgCanvas.style.cursor = hit ? 'pointer' : '';
      drawKnowledgeGraph();
    }
    return;
  }
  const screen = kgScreenPoint(e),
    dx = screen.x - kgGesture.last.x,
    dy = screen.y - kgGesture.last.y;
  if (Math.hypot(screen.x - kgGesture.start.x, screen.y - kgGesture.start.y) > 3)
    kgGesture.moved = true;
  if (kgGesture.node) {
    kgGesture.node.x += dx / kgView.scale;
    kgGesture.node.y += dy / kgView.scale;
  } else {
    kgView.x += dx;
    kgView.y += dy;
  }
  kgGesture.last = screen;
  drawKnowledgeGraph();
  e.preventDefault();
});
function finishKgGesture(e) {
  if (!kgGesture || kgGesture.pointerId !== e.pointerId) return;
  const gesture = kgGesture;
  kgGesture = null;
  kgCanvas.classList.remove('dragging');
  if (kgCanvas.hasPointerCapture(e.pointerId)) kgCanvas.releasePointerCapture(e.pointerId);
  if (!gesture.moved && gesture.node) selectKnowledgeGraphNode(gesture.node.node);
}
kgCanvas.addEventListener('pointerup', finishKgGesture);
kgCanvas.addEventListener('pointercancel', finishKgGesture);
/* 双击：进详情 + 展开下一层（第 7 项明确要求）。
   双击会在 pointerup 之后再触发一次单击选中，所以这里只是"选中 + 展开"，
   不额外做别的事，避免两次行为打架。 */
kgCanvas.addEventListener('dblclick', (e) => {
  const hit = kgHitNode(kgScreenPoint(e));
  if (!hit) return;
  selectKnowledgeGraphNode(hit.node);
  focusNode(hit.node.id, Math.min(2, kgDepth + 1), hit.node.name);
  e.preventDefault();
});
kgCanvas.addEventListener(
  'wheel',
  (e) => {
    const point = kgScreenPoint(e),
      world = kgWorldPoint(point),
      next = Math.max(0.35, Math.min(3, kgView.scale * Math.exp(-e.deltaY * 0.001)));
    kgView.x = point.x - world.x * next;
    kgView.y = point.y - world.y * next;
    kgView.scale = next;
    drawKnowledgeGraph();
    e.preventDefault();
  },
  { passive: false },
);
kgEl('kgQuery').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') searchKnowledgeGraph();
});
window.addEventListener('resize', () => {
  if (kgEl('kgView').classList.contains('open') && kgGraph.nodes.length)
    layoutKnowledgeGraph();
});

/* ------------------------------------------------------------------ 正文实体跳转
 *
 * 第 7 项第一条：回答里出现的法规、机构、污染物等名称要可点击，点了跳到图谱。
 * 从问答页调过来时，图谱视图可能还没初始化，所以这里负责"打开图谱 +
 * 用这个实体名搜一次"。
 * 交互上用**匹配列表**而不是直接画图：同名/近名的实体可能有好几个
 * （比如「固体废物」既可能是污染物也可能是文件名），让用户选一个更准。 */
export async function openKgEntity(name) {
  const q = kgEl('kgQuery');
  if (q) q.value = name || '';
  await searchKnowledgeGraph();
  if (kgMatches.length === 1) await pickKgMatch(kgMatches[0].id);
}
