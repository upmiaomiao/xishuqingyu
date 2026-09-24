/* 原文批注视图 · 前端契约测试（在服务器上用 node 跑）
 *
 * 这个测试**不渲染页面**（服务器上没有无头浏览器），它查的是最容易出错、
 * 又最难靠肉眼发现的三类问题：
 *   ① JS 里 querySelector('#x') 的 id，在同一个文件生成的 HTML 里是不是真的存在
 *      —— 拼错一个 id，界面上就是一块永远空白，还不报错；
 *   ② JS 调的接口路径，后端是否真有这条路由；
 *   ③ JS 读的响应字段名，服务端返回里是否真有这个键
 *      —— 这类错的表现是"页面在、数据空"，比报错更难查。
 */
const fs = require('fs');
const http = require('http');

/* 服务器上的 node 比较老（没有全局 fetch），用 http 模块自己写一个 getJSON */
function getJSON(path) {
  return new Promise((resolve, reject) => {
    http.get(BASE + path, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { buf += d; });
      res.on('end', () => {
        try { resolve(JSON.parse(buf)); } catch (e) { reject(new Error('非 JSON：' + buf.slice(0, 120))); }
      });
    }).on('error', reject);
  });
}

const S = '/home/test/xishu_qingyu_serve/xishu_pipeline';
const BASE = 'http://127.0.0.1:8011';
/* 剥掉注释再扫：否则注释里写的示例（比如"按 API + '字面量' 扫接口"这句话本身）
   会被正则当成"JS 调了一个叫 字面量 的接口"，报出并不存在的失败。 */
function stripComments(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"\\])\/\/[^\n]*/g, '$1 ');
}
const files = {
  audit_doc: fs.readFileSync(S + '/static/audit_doc.js', 'utf8'),
  audit_ui: fs.readFileSync(S + '/static/audit_ui.js', 'utf8'),
  routes: fs.readFileSync(S + '/audit_routes.py', 'utf8'),
};
const code = { audit_doc: stripComments(files.audit_doc), audit_ui: stripComments(files.audit_ui) };
const fails = [];
const ok = [];

/* ---------------------------------------------------------- ① DOM id */
for (const [name, src] of Object.entries(code)) {
  const declared = new Set([...src.matchAll(/id="([A-Za-z0-9_-]+)"/g)].map((m) => m[1]));
  const used = new Set([
    ...[...src.matchAll(/querySelector\(\s*'#([A-Za-z0-9_-]+)'\s*\)/g)].map((m) => m[1]),
    ...[...src.matchAll(/getElementById\(\s*'([A-Za-z0-9_-]+)'\s*\)/g)].map((m) => m[1]),
    // audit_ui.js 用的是 const $ = sel => root.querySelector(sel) 这个辅助函数
    ...[...src.matchAll(/\$\(\s*'#([A-Za-z0-9_-]+)'\s*\)/g)].map((m) => m[1]),
  ]);
  const missing = [...used].filter((id) => !declared.has(id));
  if (missing.length) fails.push(`${name}: 引用了不存在的 id → ${missing.join(', ')}`);
  else ok.push(`${name}: ${used.size} 个 id 引用全部有对应元素（声明 ${declared.size} 个）`);
}

/* ---------------------------------------------------------- ② 接口路径 */
/* 路由装饰器里写的是 /api/xxx，router 的 prefix 是 /audit，拼起来才是完整路径 */
const routes = new Set([...files.routes.matchAll(/@router\.(?:get|post)\("([^"]+)"/g)]
  .map((m) => '/audit' + m[1]));
/* API 常量本身是 '/audit/api'，所以拼出来的就是完整路径 */
const apiCalls = new Set(
  [...(code.audit_ui + code.audit_doc).matchAll(/API \+ '([^']+)'/g)]
    .map((m) => '/audit/api' + m[1].replace(/\?.*$/, '')));
for (const call of apiCalls) {
  const hit = [...routes].some((r) => {
    const rp = r.split('/'), cp = call.split('/');
    if (rp.length !== cp.length) return false;
    return rp.every((seg, i) => /^\{.+\}$/.test(seg) || seg === cp[i]);
  });
  if (!hit) fails.push(`JS 调的接口没有对应路由：${call}`);
  else ok.push(`接口 ${call} → 路由存在`);
}

/* ---------------------------------------------------------- ③ 字段名 */
const mustKeys = {
  // 批注包（/annot）
  annot: ['ok', 'anchors', 'pages', 'toc', '定位统计', 'empty_pages', 'file'],
  // 单条批注
  anchor: ['item', '审核项', '类别', '结论', '置信度', '参考依据', '理由', '需人工确认',
    'page', 'printed', 'quote', 'level', 'span', 'table', 'why'],
  // 单页负载（/page）
  page: ['n', 'printed', 'empty', 'text', 'tables', 'total'],
};
// JS 源码里实际读到的键（引号形式）
function quotedKeys(src, varName) {
  const re = new RegExp(varName + "\\['([^']+)'\\]", 'g');
  return [...new Set([...src.matchAll(re)].map((m) => m[1]))];
}

(async () => {
  const rep = await getJSON('/audit/api/reports');
  const name = (rep.reports || []).map((r) => r.name).find((n) => n.includes('临沂')) || rep.reports[0].name;
  const annot = await getJSON('/audit/api/annot/' + encodeURIComponent(name) + '?parse=0');
  if (!annot.ok) { fails.push('/annot 没返回 ok，无法校验字段'); }
  else {
    const a = annot.anchors[0];
    for (const k of mustKeys.annot) {
      if (!(k in annot)) fails.push(`/annot 缺顶层键 ${k}`);
    }
    for (const k of mustKeys.anchor) {
      if (!(k in a)) fails.push(`批注缺字段 ${k}`);
    }
    // JS 里用引号读的键，必须真的存在
    for (const k of quotedKeys(code.audit_doc, 'a')) {
      if (!(k in a)) fails.push(`audit_doc.js 读的批注字段 ${k} 服务端没有`);
    }
    /* audit_ui.js 的 itemHTML 读的是**审核结果条目**（键名是 结论→AI审核、证据），
       不是批注对象 —— 两者字段名不同是设计如此，所以要对原始结果文件校验。 */
    const rawPath = '/data/eia_audit/_审核结果/' + name.replace(/\.[^.]+$/, '') + '.json';
    if (!fs.existsSync(rawPath)) {
      fails.push('找不到原始审核结果：' + rawPath);
    } else {
      const raw = JSON.parse(fs.readFileSync(rawPath, 'utf8'));
      const it0 = (raw.items || [])[0] || {};
      for (const k of quotedKeys(code.audit_ui, 'it')) {
        if (!(k in it0)) fails.push(`audit_ui.js 读的条目字段 ${k} 审核结果里没有`);
      }
      // 两份数据必须能按「审核项」对上：批注是审核结果的展开
      const byItem = new Map((raw.items || []).map((x) => [x['审核项'], x]));
      for (const an of annot.anchors) {
        const src = byItem.get(an['审核项']);
        if (!src) { fails.push(`批注「${an['审核项']}」在审核结果里找不到对应审核项`); continue; }
        if (src['AI审核'] !== an['结论']) {
          fails.push(`批注「${an['审核项']}」结论与审核结果不一致：${an['结论']} vs ${src['AI审核']}`);
        }
      }
      ok.push(`批注 ↔ 审核结果：${annot.anchors.length} 条全部能按审核项对上，结论一致`);
    }
    const pgPage = annot.anchors.find((x) => x.page && x.span);
    const pg = await getJSON('/audit/api/page/' + encodeURIComponent(name) + '?n=' + pgPage.page);
    for (const k of mustKeys.page) {
      if (!(k in pg)) fails.push(`/page 缺字段 ${k}`);
    }
    for (const k of quotedKeys(code.audit_doc, 'p')) {
      if (!(k in pg)) fails.push(`audit_doc.js 读的页字段 ${k} 服务端没有`);
    }
    ok.push(`字段契约：批注 ${Object.keys(a).length} 键 / 页面 ${Object.keys(pg).length} 键 全部对上`);
  }

  console.log('通过项：');
  ok.forEach((s) => console.log('  ✓ ' + s));
  if (fails.length) {
    console.log('\n❌ 失败 ' + fails.length + ' 条：');
    fails.forEach((s) => console.log('  ✗ ' + s));
    process.exit(1);
  }
  console.log('\n✅ 前端契约全部通过');
})();
