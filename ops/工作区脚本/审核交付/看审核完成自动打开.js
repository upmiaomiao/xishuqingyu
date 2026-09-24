/* 真机验收：跑完一次审核，页面是否**自动**切到「原文批注」并停在问题上
 *
 * 为什么非得真跑：这段逻辑挂在任务轮询的完成分支上，静态扫代码只能看到
 * "字符串写对了"，证明不了"跑完真的切过去"。用户 2026-09-22 的原话是
 * 「审核完成之后可以在右侧默认打开吗」—— 这条不验就没有交付。
 *
 * **用副本跑**：直接在正式报告上重跑会覆盖它已落盘的审核结果，
 * 现有交付件也会变成"过期"，而且关了模型抽取重跑出来的结论跟原来那份不一样。
 * 所以先在 /data/eia_reports 里放一份临时副本，跑完把副本与它的结果删掉。
 *
 * 用法：node 看审核完成自动打开.js <截图目录> <副本报告名关键字>
 */
const fs = require('fs');
const path = require('path');
const CDP = 'http://127.0.0.1:9222';
const OUT = process.argv[2] || '.';
const KEY = process.argv[3] || '验收副本';
const SITE = 'http://10.201.31.10:8011/audit';
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
  let fails = 0, passes = 0;
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
    const f = path.join(OUT, name);
    fs.writeFileSync(f, Buffer.from(r.data, 'base64'));
    console.log('   截图 ' + f);
  };

  await c.send('Page.navigate', { url: SITE });
  for (let i = 0; i < 60; i++) {
    if (await ev("var o=document.querySelector('#auPick');return o&&o.options.length>0")) break;
    await sleep(500);
  }

  const picked = await ev(
    "var o=document.querySelector('#auPick');var i=-1;" +
    "for(var k=0;k<o.options.length;k++){if(o.options[k].value.indexOf('" + KEY + "')>=0){i=k;break}}" +
    "if(i<0)return null;o.selectedIndex=i;o.dispatchEvent(new Event('change',{bubbles:true}));return o.value");
  if (!picked) throw new Error('下拉框里没有含「' + KEY + '」的报告');
  console.log('跑审核：' + picked);
  await sleep(1500);
  ck(await ev("return document.querySelector('.au-view[data-view=\"doc\"]').className.indexOf('on')<0"),
    '跑之前停在清单视图（不是批注视图）');
  await ev("document.querySelector('#auLlm').checked=false");   // 关模型抽取，只为验证界面行为
  await ev("document.querySelector('#auRun').click()");

  // 等任务真的结束
  const t0 = Date.now();
  let stage = '';
  for (;;) {
    if (Date.now() - t0 > 25 * 60 * 1000) throw new Error('审核超过 25 分钟未结束，放弃等待');
    const st = await ev(
      "return {s:document.querySelector('#auStatus').textContent," +
      "run:document.querySelector('#auRun').disabled," +
      "doc:!!document.querySelector('.au-doc')," +
      "docOn:(document.querySelector('.au-view[data-view=\"doc\"]')||{}).className||''}");
    if (st.s !== stage) { stage = st.s; console.log('   [' + Math.round((Date.now() - t0) / 1000) + 's] ' + stage); }
    if (/失败|未完成|停止等待/.test(st.s)) { await shot('90_审核失败.png'); throw new Error('审核失败：' + st.s); }
    if (st.doc) break;                       // 自动切过去了
    await sleep(2000);
  }
  console.log('   审核用时 ' + Math.round((Date.now() - t0) / 1000) + 's');

  // 自动切过来之后，界面应当是"可用的批注视图"而不是空壳
  let rows = 0;
  for (let i = 0; i < 60; i++) {
    rows = await ev("return document.querySelectorAll('#auSideItems .au-item').length");
    if (rows) break;
    await sleep(1000);
  }
  const final = await ev(
    "var on=document.querySelector('.au-view[data-view=\"doc\"]');" +
    "return {docOn:on.className.indexOf('on')>=0," +
    "rows:document.querySelectorAll('#auSideItems .au-item').length," +
    "pg:document.querySelector('#auPageNo').value," +
    "meta:document.querySelector('#auPageMeta').textContent," +
    "notes:document.querySelectorAll('.au-note').length," +
    "cards:document.querySelectorAll('.au-card').length," +
    "stat:document.querySelector('#auAnnotStat').textContent," +
    "status:document.querySelector('#auStatus').textContent}");
  console.log('   落点：第 ' + final.pg + ' 页　' + final.meta + '　左栏 ' + final.rows + ' 行　右栏 ' + final.notes + ' 张卡');
  ck(final.docOn, '审核跑完**自动**切到「原文批注」视图');
  ck(final.rows > 5, '左栏问题清单已就绪（' + final.rows + ' 行）');
  ck(final.notes > 0, '右侧批注卡已渲染（' + final.notes + ' 张）');
  ck(/^\d+/.test(final.pg) && parseInt(final.pg, 10) > 0, '正文已经落在具体页上：' + final.pg);
  ck(final.cards > 0, '结论统计卡片也在（' + final.cards + ' 张）');
  await shot('04_跑完自动打开批注视图.png');

  // 点第一条问题，确认跳转仍然可用
  const jump = await ev(
    "var d=document.querySelectorAll('#auSideItems .au-item')[0];if(!d)return null;" +
    "d.click();return {name:d.dataset.item,pg:d.querySelector('.au-item-pg').textContent}");
  await sleep(2500);
  const after = await ev(
    "var on=document.querySelector('#auSideItems .au-item.on');" +
    "return {p:document.querySelector('#auPageNo').value,item:on?on.dataset.item:null," +
    "card:(document.querySelector('.au-note.on b')||{}).textContent||null}");
  const want = String(parseInt((jump.pg || '').replace(/[^0-9]/g, ''), 10));
  const now = String(parseInt((after.p || '').split('/')[0].trim(), 10));
  console.log('   点第一条「' + jump.name + '」(' + jump.pg + ') → ' + after.p);
  ck(now === want, '跑完后的新结果里，点问题照样跳到对应页（' + jump.pg + '）');
  ck(after.item === jump.name && !!after.card, '左栏行与右栏卡同步选中（' + after.card + '）');
  await shot('05_跑完后点问题跳转.png');

  console.log('\n通过 ' + passes + ' / 失败 ' + fails);
  c.close();
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
