/* 排查 v2：直接在页面里抓住异常堆栈 */
const CDP = 'http://127.0.0.1:9222';
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
  await c.send('Runtime.enable');
  const ev = async (expr) => {
    const r = await c.send('Runtime.evaluate', {
      expression: '(function(){' + expr + '})()', awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) {
      const e = r.exceptionDetails;
      return { __err: (e.exception && (e.exception.description || e.exception.value)) || e.text };
    }
    return r.result.value;
  };

  console.log('hook 装了没:', await ev("return typeof window.__auErr"));
  console.log('汇总卡片  :', await ev("return document.querySelectorAll('.au-card').length"));
  console.log('summary   :', String(await ev("var d=document.querySelector('#auSummary')||document.querySelector('.au-summary');return d?d.textContent.slice(0,120):'(找不到汇总容器)'")));
  console.log('body 容器 :', await ev("var d=document.querySelector('.au-body')||document.querySelector('#auBody');return d?d.className:'(找不到)'"));
  console.log('--- 手动再点一次「原文批注」，抓异常 ---');
  console.log(JSON.stringify(await ev(
    "var b=document.querySelector('.au-view[data-view=\"doc\"]');" +
    "try{b.click()}catch(e){return {抓到了:String(e&&e.message),stack:String(e&&e.stack).slice(0,600)}}" +
    "return {点完了:true,doc:!!document.querySelector('.au-doc'),body:(document.querySelector('.au-body')||{}).className}" )));
  c.close();
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
