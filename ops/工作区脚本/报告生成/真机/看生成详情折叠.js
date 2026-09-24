/* 真机验收：C4「生成详情」折叠（默认收起、引导不被收走、进度条不被收走）+ C6 判定卡初始态
 *
 * 为什么非得真跑：折叠是**浏览器自己的 details 行为** —— 静态扫代码只能证明
 * <details> 写进去了，证明不了"默认是收起的"（多写一个 open 就全变了）、
 * 也证明不了"使用步骤还在外面看得见"（它原来就在 ge-log 里面）。
 * C6 只验初始态（折叠/未出现）："判定在生成过程中就可见"已由服务端探针
 * 验判定摘要时机.py 用真实任务验过（1.0s 可见、当时 status=running、总用时 7.0s），
 * 那件事在浏览器里验要真跑一次生成，代价大而信息量相同。
 *
 * 用法（先起 Chrome：--remote-debugging-port=9222 --headless=new <站点>）：
 *   node 看生成详情折叠.js <截图目录>
 */
const fs = require('fs');
const path = require('path');
const CDP = 'http://127.0.0.1:9222';
const OUT = process.argv[2] || '.';
const SITE = 'http://10.201.31.10:8011/gen';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function conn(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    let id = 0; const waiters = {};
    ws.onopen = () => res({
      send(m, p) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
        return new Promise((ok, no) => { waiters[mid] = { ok, no }; });
      },
      close() { ws.close(); },
    });
    ws.onerror = () => rej(new Error('ws 出错'));
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && waiters[m.id]) {
        const w = waiters[m.id]; delete waiters[m.id];
        if (m.error) w.no(new Error(m.error.message)); else w.ok(m.result);
      }
    };
  });
}

(async () => {
  const list = await (await fetch(CDP + '/json/list')).json();
  const pg = list.filter((t) => t.type === 'page')[0];
  const c = await conn(pg.webSocketDebuggerUrl);
  let passes = 0, fails = 0;
  const ck = (ok, msg) => { if (ok) { passes++; console.log('  ✓ ' + msg); } else { fails++; console.log('  × ' + msg); } };
  await c.send('Page.enable');
  await c.send('Runtime.enable');
  const ev = async (expr) => {
    const r = await c.send('Runtime.evaluate', {
      expression: '(function(){' + expr + '})()', awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception || {}).description || '页面里报错');
    return r.result.value;
  };
  const shot = async (name) => {
    const r = await c.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.data, 'base64'));
    console.log('   截图 ' + path.join(OUT, name));
  };

  await c.send('Page.navigate', { url: SITE });
  let ready = false;
  for (let i = 0; i < 60; i++) {
    ready = await ev("return !!document.getElementById('ge-logbox')");
    if (ready) break;
    await sleep(500);
  }
  if (!ready) throw new Error('编制页没挂载出 #ge-logbox');

  // ---- C4：折叠块本身 ----
  const d = await ev(
    "var b=document.getElementById('ge-logbox');" +
    "var s=b.querySelector('summary');" +
    "return {tag:b.tagName, open:b.open, attr:b.hasAttribute('open')," +
    " sum:(s?s.textContent:'').trim()," +
    " guideVis:(function(){var g=document.querySelector('.ge-guide');" +
    "   if(!g) return null; var r=g.getBoundingClientRect();" +
    "   return r.height>0 && getComputedStyle(g).display!=='none';})()," +
    " guideInBox:!!b.querySelector('.ge-guide')," +
    " logN:(document.getElementById('ge-logn')||{}).textContent," +
    " progInBox:!!b.querySelector('#ge-prog')," +
    " logEmpty:document.getElementById('ge-log').children.length}");
  console.log('   ' + JSON.stringify(d));
  ck(d.tag === 'DETAILS', '日志容器是 <details>（tag=' + d.tag + '）');
  ck(d.open === false && d.attr === false, '默认收起（open=' + d.open + '，无 open 属性=' + d.attr + '）');
  ck(d.sum.indexOf('生成详情') >= 0, '标题写「生成详情」：' + d.sum);
  ck(d.sum.indexOf('暂无日志') >= 0, '标题带条数位（初始：暂无日志）');
  ck(d.guideVis === true, '「使用步骤」折叠后仍可见（没被收走）');
  ck(d.guideInBox === false, '「使用步骤」已移出折叠块（在 ge-logbox 之外）');
  ck(d.progInBox === false, '进度条不在折叠块里（当前状态常驻可见）');
  await shot('01_生成详情_默认收起.png');

  // ---- C4：点开/收起 ----
  const toggled = await ev(
    "var b=document.getElementById('ge-logbox');" +
    "b.querySelector('summary').click(); var o1=b.open;" +
    "b.querySelector('summary').click(); var o2=b.open;" +
    "return {o1:o1, o2:o2}");
  ck(toggled.o1 === true, '点一下能展开（open=true）');
  ck(toggled.o2 === false, '再点一下能收起');
  await ev("document.getElementById('ge-logbox').open=true;return true");
  await sleep(300);
  await shot('02_展开后.png');
  await ev("document.getElementById('ge-logbox').open=false;return true");

  // ---- C6：判定卡初始态 ----
  const dec = await ev(
    "var card=document.getElementById('ge-dec-card');" +
    "return {exists:!!card, hidden:card?card.hidden:null," +
    " box:!!document.getElementById('ge-dec')," +
    " fn:(typeof window.renderDec)}");
  ck(dec.exists === true, '判定摘要卡片存在（还没跑生成时隐藏）');
  ck(dec.hidden === true, '初始隐藏（hidden=' + dec.hidden + '）');
  ck(dec.box === true, '有只读容器 #ge-dec');

  // ---- 新建报告：折叠与判定卡都要复位（否则上一份的痕迹留着） ----
  await ev(
    "document.getElementById('ge-logbox').open=true;" +
    "document.getElementById('ge-log').innerHTML='<div class=\"ge-line\">上一份日志</div>';" +
    "document.getElementById('ge-logn').textContent='共 9 条';" +
    "var card=document.getElementById('ge-dec-card');card.hidden=false;" +
    "document.getElementById('ge-dec').innerHTML='<div>上一份判定</div>';" +
    "return true");
  await ev("document.getElementById('ge-new').click();return true");
  await sleep(1200);
  const after = await ev(
    "var b=document.getElementById('ge-logbox');" +
    "return {open:b.open, logN:(document.getElementById('ge-logn')||{}).textContent," +
    " logHTML:document.getElementById('ge-log').innerHTML," +
    " decHidden:document.getElementById('ge-dec-card').hidden," +
    " decHTML:document.getElementById('ge-dec').innerHTML}");
  console.log('   新建后：' + JSON.stringify(after));
  ck(after.open === false, '新建报告后折叠块复位为收起');
  ck(after.logN === '暂无日志', '日志条数复位（' + after.logN + '）');
  ck(after.logHTML === '', '日志内容清空');
  ck(after.decHidden === true, '判定卡重新隐藏');
  ck(after.decHTML === '', '判定内容清空');
  await shot('03_新建后_已复位.png');

  console.log('\n通过 ' + passes + ' / 失败 ' + fails);
  c.close();
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
