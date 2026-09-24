/* 真机验收：审核页「不适用」口径说明真的出现在界面上，且统计卡没被改坏
 *
 * 为什么非得真跑：改的是 renderSummary 的返回字符串，静态扫代码只能证明"拼进去了"，
 * 证明不了"渲染出来没有、有没有把统计卡挤掉"。而且要拿**真实结果**验：
 * 报告书的 9 条"不适用"才是这句话的适用场景。
 *
 * 关键：审核页会自动读回磁盘上已有的结果（loadExistingResult），
 * 所以这里**不重跑审核**、不覆盖任何结论、不调模型。
 *
 * 用法（先起 Chrome：--remote-debugging-port=9222 --headless=new <站点>）：
 *   node 看不适用口径.js <截图目录> [报告名关键字]
 */
const fs = require('fs');
const path = require('path');
const CDP = 'http://127.0.0.1:9222';
const OUT = process.argv[2] || '.';
const KEY = process.argv[3] || '中节能（临沂）';
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
  let n = 0;
  for (let i = 0; i < 60; i++) {
    n = await ev("var o=document.querySelector('#auPick');return o?o.options.length:0");
    if (n > 0) break;
    await sleep(500);
  }
  ck(n > 0, '报告清单已加载（' + n + ' 份）');

  const picked = await ev(
    "var o=document.querySelector('#auPick');var i=-1;" +
    "for(var k=0;k<o.options.length;k++){if(o.options[k].value.indexOf('" + KEY + "')>=0){i=k;break}}" +
    "if(i<0)return null;o.selectedIndex=i;o.dispatchEvent(new Event('change',{bubbles:true}));return o.value");
  if (!picked) throw new Error('清单里没有含「' + KEY + '」的报告');
  console.log('   选中：' + picked);

  // 等已有结果读回来并渲染
  let note = null;
  for (let i = 0; i < 60; i++) {
    note = await ev("var d=document.querySelector('.au-na-note');" +
      "return d?{t:d.textContent,html:d.innerHTML.length}:null");
    if (note) break;
    await sleep(500);
  }

  const st = await ev(
    "var cards=document.querySelectorAll('.au-card');var out={cards:cards.length,byState:{}};" +
    "for(var i=0;i<cards.length;i++){var k=cards[i].getAttribute('data-state');" +
    "out.byState[k]=cards[i].querySelector('.n').textContent}" +
    "var na=document.querySelector('.au-card[data-state=\"不适用\"]');" +
    "out.tip=na?na.getAttribute('title'):null;" +
    "out.type=(document.querySelector('.au-tag')||{}).textContent||null;" +
    "out.items=document.querySelectorAll('#auList .au-item, .au-group').length;" +
    "out.title=(document.querySelector('.au-title b')||{}).textContent||null;" +
    "return out");
  console.log('   统计：' + JSON.stringify(st.byState) + '　卡片数 ' + st.cards + '　文件类型 ' + st.type);

  ck(!!note, '界面上出现了「不适用」口径说明条');
  if (note) {
    ck(note.t.indexOf('不适用') >= 0 && note.t.indexOf('不是漏审') >= 0,
      '说明里写清了"不是漏审/没查到"');
    ck(note.t.indexOf('报告表编制技术指南') >= 0 && note.t.indexOf('报告书不受该指南约束') >= 0,
      '报告书场景给出了具体依据（《报告表编制技术指南》表1）');
  }
  ck(st.cards === 5, '五张结论统计卡都在（' + st.cards + '）');
  ck(String(st.byState['不适用'] || '').trim() === '9',
    '「不适用」计数仍是 9（' + st.byState['不适用'] + '）');
  ck(!!st.tip && st.tip.indexOf('不计入问题') >= 0, '统计卡上有悬停提示：' + st.tip);
  ck(st.items > 0, '问题清单/分组仍在渲染（' + st.items + '）');
  ck(!!st.title, '报告标题仍在（' + String(st.title).slice(0, 24) + '）');
  await shot('04_审核页不适用口径.png');

  console.log('\n通过 ' + passes + ' / 失败 ' + fails);
  c.close();
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
