/* 真机验收：编制页 C1「去补充信息」按钮 + C2「补充内容不再飘到上面被忽略」
 *
 * 兼作一个**真 bug 的回归测试**（2026-09-22 排查 C1 时挖出来的）：
 *   `const input = …, skip = …, busy = false;` 而 `send()` 里写 `busy = true;`
 *   → JS 必抛 TypeError: Assignment to constant variable，抛出点在 click/回车处理器里，
 *     **请求根本发不出去、页面没有任何反应** —— 用户看到的"回答后没有更新"就是这个。
 *   所以本脚本第 ② 条断言（"点了回答必须真的发出 /chat/answer"）在修复前**必然失败**，
 *   修复后必过。用它做前后对照，比读代码更有说服力。
 *
 * 怎么做到"既真跑又不烧模型"：
 *   · 先用页面自己的流程真发一次 /chat/start（约 12s，调一次模型）拿到问题卡；
 *   · 然后**换掉 window.fetch**，让 /chat/answer 返回一份我指定的应答（含"未采信"），
 *     于是后续交互全部是确定性的，不碰服务端数据。
 *
 * 用法（先起 Chrome：--remote-debugging-port=9222 --headless=new <站点>）：
 *   node 看补充信息按钮.js <截图目录>
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
    let id = 0; const waiters = {}; const events = []; const dialogs = [];
    const api = {
      events,
      dialogs,
      send(m, p) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method: m, params: p || {} }));
        /* 必须带超时：页面正在导航时发出 Runtime.evaluate，CDP 可能**根本不回包**，
         * 上一版脚本就是在这儿永久挂住的（表现为整条命令 600s 被超时杀掉，
         * 而且因为输出被管道缓冲，连跑到哪一步都看不到）。 */
        return new Promise((ok, no) => {
          const t = setTimeout(() => {
            delete waiters[mid];
            no(new Error('CDP 超时：' + m));
          }, 30000);
          waiters[mid] = {
            ok: (v) => { clearTimeout(t); ok(v); },
            no: (e) => { clearTimeout(t); no(e); },
          };
        });
      },
      close() { ws.close(); },
    };
    ws.onopen = () => res(api);
    ws.onerror = () => rej(new Error('ws 出错'));
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && waiters[m.id]) {
        const w = waiters[m.id]; delete waiters[m.id];
        if (m.error) w.no(new Error(m.error.message)); else w.ok(m.result);
      } else if (m.method === 'Runtime.exceptionThrown') {
        const d = m.params.exceptionDetails || {};
        events.push((d.exception && d.exception.description) || d.text || '未知异常');
      } else if (m.method === 'Page.javascriptDialogOpening') {
        /* 模态对话框（alert/confirm）会**阻塞渲染进程**：不处理的话，后续所有
         * Runtime.evaluate 都不再回包，看起来就像"CDP 卡死"。这里一律确认并记下来。 */
        dialogs.push(m.params.message || '');
        api.send('Page.handleJavaScriptDialog', { accept: true }).catch(() => {});
      }
    };
  });
}

(async () => {
  /* 为什么不用"列表里的第一个页面"：只要上一轮跑挂过（例如空文本点发送弹出模态框，
   * 模态框会**阻塞渲染进程**），那个页面就会永久不回 CDP 包 ——
   * 表现为 Page.enable 直接超时，脚本连页面都摸不到。
   * 所以这里先把残留的站点页关掉，再**新建一个自己的标签页**，每次都是干净现场。 */
  const ver = await (await fetch(CDP + '/json/version')).json();
  const bws = await conn(ver.webSocketDebuggerUrl);
  const list = await (await fetch(CDP + '/json/list')).json();
  for (const t of list.filter((x) => x.type === 'page' && /8011/.test(x.url || ''))) {
    await bws.send('Target.closeTarget', { targetId: t.id }).catch(() => {});
  }
  const nr = await (await fetch(CDP + '/json/new?' + encodeURIComponent(SITE), { method: 'PUT' })).json();
  const c = await conn(nr.webSocketDebuggerUrl);
  let passes = 0, fails = 0;
  const ck = (ok, msg) => { if (ok) { passes++; console.log('  ✓ ' + msg); } else { fails++; console.log('  × ' + msg); } };
  await c.send('Page.enable');
  await c.send('Runtime.enable');
  c.events.length = 0;

  const ev = async (expr) => {
    const r = await c.send('Runtime.evaluate', {
      expression: '(function(){' + expr + '})()', awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) {
      throw new Error((r.exceptionDetails.exception || {}).description || '页面里报错');
    }
    return r.result.value;
  };  const shot = async (name) => {
    const r = await c.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.data, 'base64'));
    console.log('   截图 ' + path.join(OUT, name));
  };

  await c.send('Page.navigate', { url: SITE });
  let ready = false;
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    try { ready = await ev('return !!(document.getElementById("ge-say") && document.getElementById("ge-ask"));'); } catch (e) { ready = false; }
    if (ready) break;
  }
  if (!ready) { console.log('页面没挂载成功'); process.exit(2); }
  console.log('页面已挂载');

  console.log('\n[0] 模板结构（C1/C2 的两块地皮）');
  ck(await ev('return !!document.getElementById("ge-mine");'),
     '#ge-mine 存在（"我补充过的内容"块）');

  // 真发一次描述，拿到问题卡（这一步会调模型，约十几秒）
  console.log('\n[1] 用一段真实项目描述跑一轮，拿到问题卡');
  /* 不点「换一个示例」按钮：实测它填不进 #ge-say（点了还是空），
   * 而空文本点发送会弹模态框 → 渲染进程被阻塞 → 后面全部 evaluate 不回包。
   * 直接赋值最稳，测的是"答题交互"而不是"示例按钮"。 */
  const DESC = '某机械加工项目，在现有厂区内新建一条喷涂生产线，年加工金属件 5000 吨。' +
    '项目总投资 800 万元，占地面积 3000 平方米。喷涂工序使用水性漆，废气经干式漆雾过滤后排放。' +
    '生活污水经化粪池处理后排入园区污水管网；产生的废漆渣、废活性炭委托有资质单位处置。' +
    '厂界东侧 200 米为居民点，工作时间每天 8 小时、年工作 300 天。';
  await ev('const t=document.getElementById("ge-say"); t.value=' + JSON.stringify(DESC) +
    '; t.dispatchEvent(new Event("input",{bubbles:true})); return t.value.length;');
  console.log('   描述已填入（' + (await ev('return document.getElementById("ge-say").value.length;')) + ' 字）');
  await ev('document.getElementById("ge-send").click(); return 1;');
  let nq = 0;
  for (let i = 0; i < 90; i++) {
    await sleep(1000);
    nq = await ev('return document.querySelectorAll("#ge-ask .ge-q").length;');
    if (nq > 0) break;
  }
  ck(nq > 0, '问题卡渲染出来（' + nq + ' 张）');
  if (c.dialogs.length) console.log('   （过程中出现过弹窗：' + c.dialogs.join(' / ').slice(0, 80) + '）');
  if (!nq) { console.log('拿不到问题卡，后面没法测'); process.exit(2); }

  // 换掉 fetch：/chat/answer 返回"未采信"，其余照旧 —— 确定性地复现 C1 场景
  /* 关键：应答里的 key/中文名/问题 必须**回显真实值**。
   * 第一版我编了 key:"k1"，结果"上次未被采信"状态行对不上 —— 那是测试假象：
   * 产品的匹配逻辑就是按 key（其次按中文名）认人，编造的 key 自然认不出来。
   * 这样改也顺带让"未采信面板 → 去补充信息"能走**能对上号**的主路径。 */
  const first = await ev(`const c=document.querySelector("#ge-ask .ge-q");
    return { key: c.getAttribute("data-key"), name: c.getAttribute("data-name"),
             q: c.querySelector(".ge-q-t").innerText.replace(/^\\d+\\.\\s*/, "") };`);
  console.log('   第一题：key=' + first.key + ' 中文名=' + first.name);
  await ev(`
    window.__calls = [];
    window.__realFetch = window.fetch;
    const FAKE = {
      ok: true, 采纳: false, 本次: '未采信：没有给出可核验的依据',
      已知: [], 还剩: 3,
      丢弃: [{ 字段: ${JSON.stringify(first.name)}, 原因: '没有给出可核验的依据' }],
      问题: [{ key: ${JSON.stringify(first.key)}, 中文名: ${JSON.stringify(first.name)},
               问题: ${JSON.stringify(first.q)}, 为什么问: '报告表需要',
               类型: 'str', 事实名: ${JSON.stringify(first.name)} }]
    };
    window.fetch = function (u, o) {
      window.__calls.push(String(u));
      if (String(u).indexOf('/chat/answer') >= 0) {
        return Promise.resolve(new Response(JSON.stringify(FAKE),
          { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return window.__realFetch.apply(window, arguments);
    };
    return 1;`);
  await ev(`
    const cards = document.querySelectorAll("#ge-ask .ge-q");
    const first = cards[0];
    first.querySelector("input").value = "排入园区污水处理厂";
    first.querySelector(".ge-ans").click();
    return 1;`);
  await sleep(1200);

  console.log('\n[2] 核心：点了「回答」到底有没有发出去（修复前这里必失败）');
  const calls = await ev('return window.__calls.slice();');
  ck(calls.some((x) => x.indexOf('/chat/answer') >= 0),
     '/chat/answer 真的发出了（记录：' + JSON.stringify(calls) + '）');
  const exs = c.events.filter((x) => /constant variable|TypeError/.test(x));
  ck(exs.length === 0, '没有 TypeError/常量赋值异常' + (exs.length ? '：' + exs[0].split('\n')[0] : ''));

  console.log('\n[3] C2：补充内容留在底部（"我补充过的内容"块）');
  const mine = await ev(`const b=document.getElementById("ge-mine");
    if(!b) return { none:true, n:0, bad:0, go:0, txt:"" };
    return { n: b.querySelectorAll(".ge-mine-row").length, txt: b.innerText.replace(/\\n/g," | "),
             bad: b.querySelectorAll(".ge-tag-bad").length,
             go: b.querySelectorAll(".ge-mine-go").length };`);
  ck(!mine.none, '#ge-mine 块存在');
  ck(mine.n >= 1, '出现补充记录（' + mine.n + ' 条）');
  ck(mine.bad >= 1, '带「未采信」徽标');
  ck(mine.go >= 1, '带「去补充信息」按钮');
  if (mine.txt) console.log('   块内文字：' + mine.txt.slice(0, 120));

  console.log('\n[4] C1：未采信内容面板 + 问题卡上的按钮');
  const drop = await ev(`const d=document.getElementById("ge-drop");
    return { rows: d.querySelectorAll(".ge-drop-row").length,
             go: d.querySelectorAll(".ge-drop-go").length };`);
  ck(drop.rows >= 1, '未采信面板列出条目（' + drop.rows + '）');
  ck(drop.go >= 1, '未采信面板每条带「去补充信息」');
  const card = await ev(`const c=document.querySelector("#ge-ask .ge-q");
    return { state: !!c.querySelector(".ge-q-state.bad"), go: !!c.querySelector(".ge-go"),
             key: c.getAttribute("data-key"), name: c.getAttribute("data-name"),
             still: !!c };`);
  ck(card.still && card.key === first.key, '问题卡仍在原地（data-key=' + card.key + '）');
  ck(card.state, '问题卡显示"上次未被采信"');
  ck(card.go, '问题卡上有「去补充信息」按钮');

  console.log('\n[5] 气泡带问题引用 + 点按钮能跳到输入框');
  const bub = await ev(`const rows=document.querySelectorAll("#ge-stream .ge-me");
    const last=rows[rows.length-1]; return last ? last.innerText.replace(/\\n/g," ") : "";`);
  ck(/回答：/.test(bub), '聊天流"我"气泡带问题引用：' + bub.slice(0, 46));
  await ev('const b=document.querySelector("#ge-drop .ge-drop-go"); if(b) b.click(); return 1;');
  await sleep(600);
  /* 严格断言：必须跳到**那张问题卡的输入框**（并且带着上次填过的值），
   * 而不是退回主输入框。第一版实现就是把字段名当 key 传、匹配不上而悄悄退回了，
   * 当时断言写成 `|| true` 放过了它 —— 这种"测了等于没测"的写法要避免。 */
  const focus1 = await ev(`const a=document.activeElement;
    const inCard = a && a.closest && a.closest("#ge-ask .ge-q");
    return { tag: a && a.tagName, id: a && a.id, val: a && a.value,
             inCard: !!inCard, cardKey: inCard ? inCard.getAttribute("data-key") : "" };`);
  ck(focus1.tag === "INPUT" && focus1.inCard,
     '点未采信面板的按钮 → 焦点落在对应问题卡的输入框（' + focus1.tag + ' in ' + focus1.cardKey + '）');
  ck((focus1.val || "").length > 0, '输入框里带着上次填过的值：' + String(focus1.val).slice(0, 24));
  await shot('01_补充记录与按钮.png');

  const goClicked = await ev(`const c=document.querySelector("#ge-ask .ge-q");
    const g=c.querySelector(".ge-go"); if(g){ g.click(); return true; } return false;`);
  await sleep(400);
  const flash = await ev('return document.querySelectorAll("#ge-ask .ge-q-flash").length;');
  ck(goClicked && flash >= 1, '点问题卡的「去补充信息」→ 卡片高亮提示');
  await shot('02_点去补充信息_高亮.png');

  console.log('\n[6] 回归：回车仍能发送（C3）、生成详情默认收起（C4）');
  await ev(`window.__calls.length = 0;
    const c=document.querySelector("#ge-ask .ge-q");
    const inp=c.querySelector("input"); inp.value="纳管后排入园区污水处理厂";
    inp.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));
    return 1;`);
  await sleep(900);
  const calls2 = await ev('return window.__calls.slice();');
  ck(calls2.some((x) => x.indexOf('/chat/answer') >= 0), '回车也能发出 /chat/answer');
  const c4 = await ev(`const b=document.getElementById("ge-logbox");
    return { open: b ? b.open : null, sum: b ? b.querySelector("summary").innerText.replace(/\\n/g," ") : "" };`);
  ck(c4.open === false, '生成详情默认收起（' + c4.sum + '）');

  console.log('\n[7] 新建报告要清掉补充记录');
  await ev('window.confirm = function(){ return true; }; document.getElementById("ge-new").click(); return 1;');
  await sleep(600);
  const after = await ev(`const b=document.getElementById("ge-mine");
    if(!b) return { none:true, rows:0, txt:1 };
    return { rows: b.querySelectorAll(".ge-mine-row").length, txt: b.innerText.trim().length };`);
  ck(!after.none && after.rows === 0 && after.txt === 0, '新建后"我补充过的内容"已清空');
  await shot('03_新建后已清空.png');

  console.log('\n==== 通过 ' + passes + ' / 失败 ' + fails + ' ====');
  await c.send('Browser.close').catch(() => {});
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.log('脚本出错：' + e.message); process.exit(2); });
