/* 环评审核界面 · 真浏览器验收（2026-09-22）
 *
 * 为什么写这个：服务器上没有无头浏览器，本地也没装 puppeteer/playwright/jsdom，
 * 而这一轮改的全是**界面行为**（左栏问题清单、点一行跳转、跑完自动切视图）——
 * 静态扫代码只能证明"字符串写对了"，证明不了"点下去真的跳"。
 *
 * 做法：本机有 Chrome/Edge，用 --remote-debugging-port 起一个无头实例，
 * 本脚本只用 Node 自带的 fetch + WebSocket 走 CDP 协议（**不 spawn 子进程**：
 * 沙箱下 node 用管道捕获子进程输出会 EPERM，而且也用不着）。
 * 于是可以真的：打开页面 → 选报告 → 切批注视图 → 点第 N 行问题 →
 * 读回 DOM 里发生了什么 → 截图。
 *
 * 用法：node 看审核界面.js <输出目录> [报告名关键字]
 */
const fs = require('fs');
const path = require('path');

const OUT = process.argv[2] || '.';
const KEY = process.argv[3] || '临沂';
const SITE = 'http://10.201.31.10:8011/audit';
const CDP = 'http://127.0.0.1:9222';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(CDP + '/json/list')).json();
      const pg = list.filter((t) => t.type === 'page')[0];
      if (pg && pg.webSocketDebuggerUrl) return pg;
    } catch (e) { /* 还没起来 */ }
    await sleep(500);
  }
  throw new Error('连不上 Chrome 调试端口 9222');
}

function conn(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    let id = 0;
    const waiters = {};
    ws.onopen = () => res({
      send(method, params) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method, params: params || {} }));
        return new Promise((ok, no) => { waiters[mid] = { ok, no }; });
      },
      close() { ws.close(); },
    });
    ws.onerror = (e) => rej(new Error('WebSocket 出错'));
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && waiters[m.id]) {
        const w = waiters[m.id]; delete waiters[m.id];
        if (m.error) w.no(new Error(m.error.message)); else w.ok(m.result);
      }
    };
  });
}

(async () => {
  const t = await target();
  const c = await conn(t.webSocketDebuggerUrl);
  let fails = 0, passes = 0;
  const ck = (ok, msg) => { if (ok) { passes++; console.log('  ✓ ' + msg); } else { fails++; console.log('  × ' + msg); } };

  await c.send('Page.enable');
  await c.send('Runtime.enable');
  /* 页面里的未捕获错误要记下来 —— 界面改动最容易出"点了没反应"，
     那种毛病状态码看不出来，只能看控制台。 */
  await c.send('Page.addScriptToEvaluateOnNewDocument', {
    source: 'window.__auErr=[];window.addEventListener("error",function(e){window.__auErr.push(String(e.message))});' +
      'window.addEventListener("unhandledrejection",function(e){window.__auErr.push("reject:"+String(e.reason))});',
  });

  async function ev(expr) {
    const r = await c.send('Runtime.evaluate', {
      expression: '(function(){' + expr + '})()',
      awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(expr.slice(0, 60) + ' → ' + (r.exceptionDetails.exception || {}).description);
    return r.result.value;
  }
  async function until(expr, ms, what) {
    const t0 = Date.now();
    while (Date.now() - t0 < (ms || 30000)) {
      if (await ev('return !!(' + expr + ')')) return true;
      await sleep(300);
    }
    throw new Error('等不到：' + what);
  }
  async function shot(name) {
    const r = await c.send('Page.captureScreenshot', { format: 'png' });
    const f = path.join(OUT, name);
    fs.writeFileSync(f, Buffer.from(r.data, 'base64'));
    console.log('   截图 ' + f);
  }

  console.log('打开 ' + SITE);
  await c.send('Page.navigate', { url: SITE });
  await until("document.querySelector('#auPick') && document.querySelector('#auPick').options.length", 30000, '报告下拉框');

  const reports = await ev("var o=document.querySelector('#auPick');return Array.prototype.map.call(o.options,function(x){return x.textContent})");
  console.log('  报告 ' + reports.length + ' 份；已审核标记：' +
    reports.filter((s) => s.indexOf('已审核') >= 0).length + ' 份');
  ck(reports.some((s) => s.indexOf('已审核') >= 0), '下拉框标出了"已审核"的报告（新接口 /api/reports 的 已审核 字段）');

  console.log('选报告：' + KEY);
  const picked = await ev(
    "var o=document.querySelector('#auPick');var i=-1;" +
    "for(var k=0;k<o.options.length;k++){if(o.options[k].value.indexOf('" + KEY + "')>=0){i=k;break}}" +
    "if(i<0)return null;o.selectedIndex=i;" +
    "o.dispatchEvent(new Event('change',{bubbles:true}));return o.value");
  if (!picked) throw new Error('没找到含「' + KEY + '」的报告');

  // 换报告后会把上次的结果读回来（新接口 /api/result）
  await until("document.querySelector('#auStatus').textContent.indexOf('已读取上次的审核结果')>=0" +
    " || document.querySelectorAll('.au-card').length", 60000, '读回上次结果');
  const restored = await ev("return document.querySelector('#auStatus').textContent");
  ck(restored.indexOf('已读取上次的审核结果') >= 0, '刷新/换报告能读回上次结果：' + restored);

  // 切到原文批注视图
  await ev("Array.prototype.forEach.call(document.querySelectorAll('.au-view'),function(b){if(b.dataset.view==='doc')b.click()})");
  await until("document.querySelectorAll('#auSideItems .au-item').length", 60000, '左栏问题清单');
  await until("document.querySelector('#auPageNo').value", 60000, '正文页');

  const rows = await ev(
    "return Array.prototype.map.call(document.querySelectorAll('#auSideItems .au-item'),function(d){" +
    "return {name:d.dataset.item,cls:d.className,pg:d.querySelector('.au-item-pg').textContent}})");
  console.log('  左栏问题清单 ' + rows.length + ' 行；前 5 行：');
  rows.slice(0, 5).forEach((r) => console.log('    ' + r.pg + '  ' + r.name + '   [' + r.cls.replace('au-item ', '') + ']'));
  ck(rows.length > 5, '左栏渲染出问题清单（' + rows.length + ' 行）');
  ck(rows[0].cls.indexOf('sev-danger') >= 0, '第一行是最严重的结论（' + rows[0].cls.replace('au-item ', '') + '）');
  ck(rows.every((r) => r.name && r.pg), '每行都有审核项名与页码');

  const tabItems = await ev("var b=document.querySelector('.au-side-tab[data-side=\"items\"]');return b?b.className:''");
  ck(tabItems.indexOf('on') >= 0, '默认停在「问题清单」页签');
  await shot('01_批注视图_问题清单.png');

  // 点第 3 行 → 应当跳到那一页并选中
  const before = await ev("return {p:document.querySelector('#auPageNo').value,meta:document.querySelector('#auPageMeta').textContent}");
  const targetRow = rows[2];
  const jump = await ev(
    "var d=document.querySelectorAll('#auSideItems .au-item')[2];d.click();" +
    "return {pg:d.querySelector('.au-item-pg').textContent,name:d.dataset.item}");
  await sleep(2500);
  const after = await ev(
    "var on=document.querySelector('#auSideItems .au-item.on');" +
    "var card=document.querySelector('.au-note.on');" +
    "return {p:document.querySelector('#auPageNo').value," +
    "meta:document.querySelector('#auPageMeta').textContent," +
    "onItem:on?on.dataset.item:null," +
    "onCard:card?card.querySelector('b').textContent:null," +
    "hl:(document.querySelector('.au-hl.on')||{}).textContent||null," +
    "noteCount:document.querySelectorAll('.au-note').length}");
  console.log('  点第 3 行「' + jump.name + '」(' + jump.pg + ')：' + before.p + ' → ' + after.p + '　' + after.meta);
  const wantPage = String(parseInt((jump.pg || '').replace(/[^0-9]/g, ''), 10));
  const nowPage = String(parseInt((after.p || '').split('/')[0].trim(), 10));
  ck(nowPage === wantPage, '正文跳到该问题的页码（' + before.p + ' → ' + after.p + '，期望 P' + wantPage + '）');
  ck(after.onItem === jump.name, '左栏那一行被选中（' + after.onItem + '）');
  ck(!!after.onCard, '右侧批注卡同步选中（' + after.onCard + '）');
  ck(after.noteCount > 0, '右侧渲染出本页批注卡 ' + after.noteCount + ' 张');
  await shot('02_点问题后跳转.png');

  // 正文里点高亮 → 左栏应当跟着变（三向同步）
  const hl = await ev(
    "var m=document.querySelector('.au-hl');if(!m)return null;m.click();" +
    "var on=document.querySelector('#auSideItems .au-item.on');" +
    "return {onItem:on?on.dataset.item:null,card:(document.querySelector('.au-note.on b')||{}).textContent||null}");
  if (hl) {
    ck(!!hl.onItem, '正文里点高亮 → 左栏问题行跟着选中（' + hl.onItem + '）');
    ck(!!hl.card, '正文里点高亮 → 右侧批注卡跟着选中（' + hl.card + '）');
  } else {
    console.log('  · 本页正文没有高亮可点（该页可能是扫描页），跳过反向同步检查');
  }

  // 章节页签还在
  await ev("document.querySelector('.au-side-tab[data-side=\"toc\"]').click()");
  const toc = await ev("return {n:document.querySelectorAll('#auToc .au-toc-item').length," +
    "vis:document.querySelector('#auToc').style.display," +
    "itemsVis:document.querySelector('#auSideItems').style.display}");
  ck(toc.n > 10 && toc.vis !== 'none' && toc.itemsVis === 'none',
    '「章节」页签可用（' + toc.n + ' 条目录，切换时两个面板互斥显示）');
  await ev("document.querySelector('.au-side-tab[data-side=\"items\"]').click()");

  // 预览弹层（上一轮做的）在这台机器上真的能开
  await ev("document.querySelector('#auDocPvDocx').click()");
  await until("document.querySelector('#auPreview').className.indexOf('on')>=0", 60000, '预览弹层');
  await sleep(2000);
  const pv = await ev("return {on:document.querySelector('#auPreview').className," +
    "src:document.querySelector('#auPreviewFrame').getAttribute('src')," +
    "title:document.querySelector('#auPreviewTitle').textContent}");
  ck(pv.on.indexOf('on') >= 0 && pv.src.indexOf('/preview_docx/') >= 0,
    '意见书预览弹层打开：' + pv.title);
  await shot('03_意见书预览.png');
  await ev("document.querySelector('#auPreviewClose').click()");

  // 控制台有没有报错
  const jsErr = await ev("return window.__auErr ? window.__auErr.length : 0");
  ck(jsErr === 0, '页面没有未捕获的 JS 错误');

  console.log('\n通过 ' + passes + ' / 失败 ' + fails);
  c.close();
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
