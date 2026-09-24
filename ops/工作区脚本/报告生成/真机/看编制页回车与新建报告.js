/* 真机验收：编制页「回车发送 / 输入法选词不发 / 新建报告不留上一份痕迹」
 *
 * 为什么非得真跑：这三条都是**浏览器事件层**的行为 —— 静态扫代码只能证明
 * "字符串写进去了"，证明不了"按下去真的走那条分支"。用户 2026-09-22 的原话是
 * 「每次都要用鼠标点发送不方便」（希望回车）与「新建报告后会保留上一份的内容」。
 *
 * 怎么做到"只验行为、不打模型"：把 window.fetch 换成记录器并让它直接失败。
 *   · 记录器 = 能看到"到底有没有发起 /chat/start"（＝发送行为发生了）；
 *   · 直接失败 = 不会真去调模型、不会建会话、不会写任何数据。
 *
 * 用法（先起 Chrome：--remote-debugging-port=9222 --headless=new <站点>）：
 *   node 看编制页回车与新建报告.js <截图目录>
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
    if (r.exceptionDetails) {
      throw new Error((r.exceptionDetails.exception || {}).description || '页面里报错');
    }
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
    ready = await ev("var o=document.getElementById('ge-say');return !!(o&&document.getElementById('ge-send'))");
    if (ready) break;
    await sleep(500);
  }
  if (!ready) throw new Error('编制页没挂载出来（#ge-say / #ge-send 不存在）');
  console.log('  编制页已挂载');

  // 把发送通道换成"只记录、不真发"
  await ev(
    "window.__sent=[];" +
    "window.fetch=function(u){window.__sent.push(String(u));" +
    "return Promise.reject(new Error('测试拦截：不真发'))};" +
    "return true");

  const sendKey = (opts) => ev(
    "var t=document.getElementById('ge-say');" +
    "var e=new KeyboardEvent('keydown',Object.assign({key:'Enter',bubbles:true,cancelable:true}," +
    JSON.stringify(opts) + "));" +
    "window.__sent=[];" +
    "var ok=t.dispatchEvent(e);" +
    "return {sent:window.__sent.slice(),prevented:!ok,val:t.value}");

  const LONG = '我们公司要在临沂市兰山区建一台20吨/小时的生物质锅炉给生产线供蒸汽';

  // ---- 1. 中文输入法选词的回车：不能发 ----
  await ev("document.getElementById('ge-say').value='" + LONG + "';return true");
  let r = await sendKey({ isComposing: true });
  ck(r.sent.length === 0, '输入法选词中按回车（isComposing）不发送');
  r = await sendKey({ keyCode: 229 });
  ck(r.sent.length === 0, '输入法只给 keyCode=229 时也不发送');

  // ---- 2. Shift+回车：留给换行，不能发 ----
  r = await sendKey({ shiftKey: true });
  ck(r.sent.length === 0, 'Shift+回车不发送（留给换行）');

  // ---- 3. 纯回车：必须发送 ----
  r = await sendKey({});
  ck(r.sent.length > 0 && r.sent.some((u) => u.indexOf('/chat/start') >= 0),
    '纯回车发送（发起 /chat/start）：' + JSON.stringify(r.sent));
  ck(r.prevented === true, '发送时阻止了默认换行（否则文本里会多一行）');
  await sleep(800);
  await shot('01_编制页回车发送.png');

  // ---- 4. 新建报告：上一份的痕迹必须全部复位 ----
  await ev(
    "document.getElementById('ge-count').textContent='12 项';" +
    "document.getElementById('ge-drop').innerHTML='<div class=\"ge-drop-row\">上一份的未采信内容</div>';" +
    "var p=document.getElementById('ge-prog');p.hidden=false;" +
    "document.getElementById('ge-prog-stage').textContent='已完成 100%';" +
    "document.getElementById('ge-prog-secs').textContent='88.8s';" +
    "document.getElementById('ge-prog-fill').style.width='100%';" +
    "document.getElementById('ge-fresh').checked=true;" +
    "return true");
  const before = await ev(
    "return {c:document.getElementById('ge-count').textContent," +
    "d:document.getElementById('ge-drop').innerHTML.length," +
    "p:document.getElementById('ge-prog').hidden," +
    "f:document.getElementById('ge-fresh').checked}");
  console.log('   造出的"上一份残留"：' + JSON.stringify(before));
  await shot('02_新建前_残留痕迹.png');

  await ev("document.getElementById('ge-new').click();return true");
  await sleep(1200);
  const after = await ev(
    "return {c:document.getElementById('ge-count').textContent," +
    "d:document.getElementById('ge-drop').innerHTML," +
    "p:document.getElementById('ge-prog').hidden," +
    "st:document.getElementById('ge-prog-stage').textContent," +
    "fill:document.getElementById('ge-prog-fill').style.width," +
    "f:document.getElementById('ge-fresh').checked," +
    "known:(document.getElementById('ge-known').textContent||'').slice(0,20)," +
    "say:document.getElementById('ge-say').value}");
  console.log('   新建后：' + JSON.stringify(after));
  ck(after.c === '0 项', '事实计数胶囊复位（' + after.c + '）');
  ck(after.d === '', '未采信内容清空（长度 ' + after.d.length + '）');
  ck(after.p === true, '进度条收起（hidden=' + after.p + '）');
  ck(after.st === '准备中', '进度条阶段文字复位（' + after.st + '）');
  ck(after.f === false, '「重新生成」复选框复位（checked=' + after.f + '）');
  ck(after.say === '', '输入框清空');
  await shot('03_新建后_已复位.png');

  console.log('\n通过 ' + passes + ' / 失败 ' + fails);
  c.close();
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
