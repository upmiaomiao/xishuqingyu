/* 排查 v3：把界面实际 DOM 倒出来看 */
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

  console.log('root 子元素:', JSON.stringify(await ev(
    "var r=document.querySelector('#auditRoot');return Array.prototype.map.call(r.children,function(x){return x.tagName+'.'+x.className})")));
  console.log('顶层结构  :', String(await ev("return document.querySelector('#auditRoot').innerHTML.slice(0,500)")));
  console.log('body 区   :', String(await ev("var d=document.querySelector('.au-body');return d?d.innerHTML.slice(0,600):'(无 .au-body)'")));
  console.log('空状态框  :', await ev("return document.querySelectorAll('.au-empty').length"));
  console.log('结果接口  :', JSON.stringify(await ev(
    "var n=document.querySelector('#auPick').value;" +
    "return fetch('/audit/api/result/'+encodeURIComponent(n)).then(function(r){return r.json()}).then(function(j){" +
    "return {ok:j.ok,has:j.has,top:j.has?Object.keys(j.result||{}):[],items:j.has?((j.result||{}).items||[]).length:0," +
    "tongji:j.has?((j.result||{})['统计']||null):null}})")));
  c.close();
})().catch((e) => { console.error('❌ ' + e.message); process.exit(1); });
