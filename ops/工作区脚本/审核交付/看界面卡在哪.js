/* 一次性排查：批注视图切过去之后到底停在哪一步 */
const CDP = 'http://127.0.0.1:9222';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function conn(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    let id = 0; const waiters = {};
    ws.onopen = () => res({
      send(method, params) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method, params: params || {} }));
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
  await c.send('Runtime.enable');
  const ev = async (expr) => {
    const r = await c.send('Runtime.evaluate', {
      expression: '(function(){' + expr + '})()', awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) return { __err: (r.exceptionDetails.exception || {}).description };
    return r.result.value;
  };

  console.log('URL      :', await ev("return location.href"));
  console.log('视图按钮 :', await ev("return Array.prototype.map.call(document.querySelectorAll('.au-view'),function(b){return b.dataset.view+':'+b.className}).join(' | ')"));
  console.log('状态栏   :', await ev("return document.querySelector('#auStatus').textContent"));
  console.log('有 .au-doc:', await ev("return !!document.querySelector('.au-doc')"));
  console.log('左栏 html:', String(await ev("var d=document.querySelector('#auSideItems');return d?d.innerHTML.slice(0,300):'(无 #auSideItems)'")));
  console.log('正文区   :', String(await ev("var d=document.querySelector('#auPage');return d?d.textContent.slice(0,200):'(无 #auPage)'")));
  console.log('右栏     :', String(await ev("var d=document.querySelector('#auNotes');return d?d.textContent.slice(0,120):'(无 #auNotes)'")));
  console.log('页号框   :', await ev("var d=document.querySelector('#auPageNo');return d?d.value:'(无)'"));
  console.log('JS 错误  :', JSON.stringify(await ev("return (window.__auErr||[]).slice(0,5)")));
  console.log('批注接口 :', JSON.stringify(await ev(
    "return fetch('/audit/api/annot/'+encodeURIComponent(document.querySelector('#auPick').value)+'?parse=0')" +
    ".then(function(r){return r.json()}).then(function(j){return {ok:j.ok,anchors:(j.anchors||[]).length,toc:(j.toc||[]).length,pages:j.pages,keys:Object.keys(j).slice(0,12),msg:j.message}})")));
  c.close();
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
