/* 悉数清宇 · 问答主页脚本模块：ask.js
 *
 * 提问与流式接收（SSE）。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 */

import { state, current, fmtSecs } from './util.js';
import { save, render } from './store.js';
import { renderMessages, probeDocInfo } from './message.js';
import { pendingImage, clearPendingImage } from './image.js';

/* ============================================================
 *  ask.js
 * ============================================================ */


let busy = false; // 防重复提交；只有本模块用

/* ------------------------------------------------------------
 * 处理过程（步骤时间线）
 *
 * 背景：照片研判这类通路，模型要先读图、再检索、再把整段 JSON 生成完才能渲染成报告 ——
 * 中途确实没有正文可以逐字流式。原先只在角落里显示一句「生成专业研判…」，
 * 几十秒不动会被当成卡死。所以把后端的 status 事件攒成一条步骤时间线：
 * 每一步都能看到「在跑 / 已完成 / 花了多久」，正在跑的那步还带一个走动的秒表。
 *
 * 后端约定：{"stage","message","state":"run"|"done","detail","progress"}
 * ------------------------------------------------------------ */
function applyStatus(am, p) {
  if (!am.steps) am.steps = [];
  const stage = p.stage || 'step';
  const last = am.steps[am.steps.length - 1];
  const close = (s, why) => {
    s.state = 'done';
    // 兜底收尾时补一句说明，否则 detail 会是 undefined ——
    // 存进 localStorage 的是 undefined、渲染时又要靠 `|| ''` 兜，两边都不干净。
    if (why && !s.detail) s.detail = why;
    s.ms = Date.now() - (s.t0 || Date.now());
  };
  if (p.state === 'done') {
    const target = last && last.stage === stage ? last : null;
    if (target) {
      target.message = p.message || target.message;
      target.detail = p.detail || '';
      close(target);
    } else {
      // 没见到对应的 run（比如中途刷新）也要记下来，别让这一步凭空消失
      am.steps.push({
        stage,
        message: p.message || '',
        state: 'done',
        detail: p.detail || '',
        ms: 0,
      });
    }
    return;
  }
  if (last && last.stage === stage && last.state === 'running') {
    // 同一步的进度刷新（照片研判每 0.8s 报一次已生成字数）
    last.message = p.message || last.message;
    if (p.progress) last.progress = p.progress;
    return;
  }
  // 上一步还没收到 done 就开了新步：兜底把它收掉，否则会一直转圈
  if (last && last.state === 'running') close(last, '已完成');
  am.steps.push({
    stage,
    message: p.message || '',
    state: 'running',
    t0: Date.now(),
    progress: p.progress || 0,
  });
}

/* 收掉所有还在跑的步骤（谁还在跑就把谁标成完成）。
 *
 * 返回收掉了几步，方便调用方按需提示。reason 写进 detail，
 * 让展开时间线的人知道这一步是"到点收工"而不是"正常完成"。 */
function closeRunningSteps(am, reason) {
  const now = Date.now();
  let n = 0;
  for (const s of am.steps || []) {
    if (s.state === 'running') {
      s.state = 'done';
      s.detail = s.detail || reason;
      s.ms = now - (s.t0 || now);
      n++;
    }
  }
  return n;
}

/* 组装发给模型的历史。
 *
 * ★ 图片那一轮整体不进历史（2026-09-18 修「发完图之后，下一轮问什么都还在答图片」）。
 *
 * 用户报的现象：第一轮发图，第二轮输入「111」，回答仍然在讲图片。
 * 定位过程与实测数据（_脚本代码/站点全量测试/查历史粘图片.py、比修法_历史处理.py）：
 *   · 图片本身**没有**被重发 —— 请求体里 image=null、report=null，已实测确认；
 *   · 真正的原因是把上一轮那份照片研判报告**原样当成助手的上一句话**发了回去。
 *     报告两三千字，彻底主导上下文。同样问「111」的对照组：
 *         带完整报告        5/5 次都在讲图片
 *         只带用户空消息    0/5
 *         完全不带历史      0/5
 *   · 这不是"提示词没写清楚"：rag 路径本来就带 HISTORY_RULE
 *     （"不要把历史中其他问题的结论混进本次回答"），仍然 5/5 被带跑。
 *   · 换措辞也没用：报告只留开头 200 字 4/4、换成一句话摘要 4/4、
 *     换成一句笼统占位 1/4 —— 但占位会让模型**编造**别的研判报告（"某工地扬尘"
 *     "某次噪声报警不属实"），比原 bug 更糟。只要历史里还留着报告的实质内容，
 *     话题就被粘住。
 *
 * 做法：图片轮（用户发的图 + 助手对它的分析）整轮跳过。
 * 与用户给的建议一致（"有图片可以每次都不带以前的聊天记录"），
 * 也与行业做法一致 —— 不每轮把图片结论塞回上下文
 * （OpenAI 开发者社区 how-to-efficiently-include-image-inputs-in-a-multi-turn-chat）。
 * 代价：用户追问"报告第二条是什么意思"时模型看不到报告原文；报告就在屏幕上，
 * 重新上传即可 —— 比每轮都被它牵着走要好。
 *
 * 另：当前这轮如果带图，历史一律不发，让图片分析自成一体、不受前文干扰。 */
function buildHistory(messages, hasImageNow) {
  if (hasImageNow) return [];
  const out = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (!m) continue;
    if (m.role === 'user' && m.image) {
      // 跳过这一轮的提问，以及紧随其后对它的回答
      if (messages[i + 1] && messages[i + 1].role === 'assistant') i++;
      continue;
    }
    const text = String(m.content || '').trim();
    if (!text) continue; // 空内容（正在流式、还没吐字的回答）不发，免得模型看到空话轮
    out.push({ role: m.role, content: text });
  }
  return out.slice(-12);
}

/* 错误码 → 给用户看的话。
 *
 * 用户的要求（2026-09-18）：「在界面中进行不显示错误，显示：当前网络繁忙，
 * 正在重新处理，然后可以在后端日志中显示实际错误，或者是在控制台打印错误」。
 *
 * 分两层：
 *   · 界面上只出现下面这张表里的话 —— 不出现 code、不出现 HTTP 状态码、
 *     不出现异常堆栈。真实内容一律 console.error，并在消息上留
 *     errorCode / errorTech，折叠在"详情"里供排查。
 *   · ★ 已知的业务错误**不能**说成"网络繁忙"。比如"这份资料没有原文"，
 *     说成网络繁忙会让用户一直重试一件永远不会成功的事。
 *     所以按码分支：网络/服务类才说"正在重新处理"，业务类说实话。
 */
const FRIENDLY_ERROR = {
  // —— 网络/服务类：重试有意义，用"正在重新处理"的措辞
  E_MODEL_UNAVAILABLE: '当前网络繁忙，正在重新处理…',
  E_TIMEOUT: '当前网络繁忙，正在重新处理…',
  E_INTERNAL: '当前网络繁忙，正在重新处理…',
  E_ENGINE_UNAVAILABLE: '当前网络繁忙，正在重新处理…',
  // —— 业务类：说清楚是什么事，别让用户白重试
  E_RETRIEVE_FAILED: '资料检索暂时不可用，请稍后再试',
  E_VISION_FAILED: '图片没能识别出来，换一张更清晰的图片通常可以解决',
  E_IMAGE_TOO_LARGE: '图片太大了，压缩后再发一次',
  E_IMAGE_FORMAT: '图片格式不支持，请上传 PNG / JPG / WebP',
  E_QUERY_EMPTY: '请先输入问题或上传图片',
  E_DOC_NOT_FOUND: '这份资料暂时没有可打开的原文',
  E_VALIDATION: '提交的内容有问题，请检查后重试',
  E_BAD_REQUEST: '提交的内容有问题，请检查后重试',
  E_TOO_MANY_REQUESTS: '操作太频繁了，稍等一下再试',
  E_PHOTO_NEEDS_IMAGE: '现场照片专业研判需要先上传一张照片',
};
/* 导出仅为可测：错误文案映射与错误记录都是纯逻辑，
   测试据此直接断言"界面上不会出现技术词汇"。 */
export function friendlyError(code) {
  const c = String(code || '');
  if (FRIENDLY_ERROR[c]) return FRIENDLY_ERROR[c];
  // 5xx 一律当"服务端一时的问题"，说网络繁忙是合理的
  if (/^E_HTTP_5/.test(c)) return '当前网络繁忙，正在重新处理…';
  return '刚才没能完成这次请求，请稍后再试';
}

/* 把一次错误记下来：控制台留真实内容，界面只留友好文案。 */
export function recordError(am, code, info) {
  const o = info && typeof info === 'object' ? info : { message: String(info == null ? '' : info) };
  // 真实错误进控制台（用户明确要求）。带 request_id，便于和后端日志对上。
  console.error('[悉数清宇] 请求出错', {
    code: code || '(无错误码)',
    message: o.message,
    techDetail: o.tech_detail,
    requestId: o.request_id,
    payload: info,
  });
  am.route = 'error';
  am.errorCode = code || '';
  am.errorTech = o.tech_detail || o.message || '';
  am.errorRequestId = o.request_id || '';
  const friendly = friendlyError(code);
  am.content = friendly;
  return friendly;
}

export function useExample(el) {
  document.getElementById('q').value = el.textContent;
  ask();
}
export async function ask() {
  if (busy) return;
  const input = document.getElementById('q'),
    q = input.value.trim();
  if (!q && !pendingImage) return;
  const c = current();
  const sentImage = pendingImage;
  if (sentImage) clearPendingImage();
  const prior = buildHistory(c.messages, !!sentImage);
  c.messages.push({ role: 'user', content: q, image: sentImage ? sentImage.thumb : '' });
  if (c.title === '新对话')
    c.title = (q || '图片提问').slice(0, 22) + ((q || '图片提问').length > 22 ? '…' : '');
  c.updated = Date.now();
  state.chats.sort((a, b) => b.updated - a.updated);
  input.value = '';
  input.style.height = 'auto';
  busy = true;
  document.getElementById('ask').disabled = true;
  document.getElementById('state').textContent = '识别意图…';
  save();
  render();
  const am = { role: 'assistant', content: '', reasoning: '', sources: [], route: '', latency: 0, streaming: true };
  c.messages.push(am);
  const update = () => {
    c.updated = Date.now();
    save();
    renderMessages();
  };
  /* 顶栏与状态栏只在"还停在这个会话"时才改。
   *
   * 为什么：用户完全可能在等待期间点「新对话」或切到别的历史会话 —— 那时
   * resetChatChrome() 已经把这三处恢复成空闲态了。这个请求还在流式返回，
   * 每一批事件（status / error / 最终完成）都会再写一次，结果新对话的顶栏
   * 显示着上一个会话的路由和「识别意图…」，看起来像新对话自己卡住了。
   * 所以所有 chrome 写入都走这两个函数，不再直接碰 document。 */
  const setState = (t) => {
    if (current() === c) document.getElementById('state').textContent = t;
  };
  const setPill = (t) => {
    if (current() === c) document.getElementById('routePill').textContent = t;
  };
  /* 秒表：只改正在跑那一行的耗时文本，不重新渲染整个消息列表 ——
     renderMessages() 会重建 innerHTML，每秒重建一次既浪费又会把用户展开的
     <details> 收回去、滚动位置也会跳。所以这里直接改那一个节点。 */
  const tick = setInterval(() => {
    const run = (am.steps || []).filter((s) => s.state === 'running').pop();
    if (!run) return;
    const el = document.querySelector('.trace-row.running .trace-time');
    if (el) el.textContent = ((Date.now() - run.t0) / 1000).toFixed(1) + 's';
  }, 200);
  try {
    const r = await fetch('/hybrid_search/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: q,
        history: prior,
        image: sentImage ? sentImage.full : null,
        report: sentImage && document.getElementById('photoMode').checked ? 'photo' : null,
      }),
    });
    if (!r.ok) {
      /* 改动前这里把**整个响应体原文**当提示抛出：后端 400 回的是
         {"detail":"query不能为空"}，用户看到的是 `请求失败：{"detail":"query不能为空"}`
         这种原始 JSON；422 时更是一整串 JSON 数组。
         后端现在统一回 {ok:false, code, message, detail, request_id}，取 message。
         仍要防住"响应体不是 JSON"（代理塞 HTML、网关 502）。 */
      const raw = await r.text();
      let d = null;
      if (raw) {
        try {
          d = JSON.parse(raw);
        } catch {
          d = raw;
        }
      }
      let msg = `HTTP ${r.status}`;
      if (d && typeof d === 'object') {
        msg = d.message || (typeof d.detail === 'string' ? d.detail : '') || msg;
        if (Array.isArray(d.detail)) msg = '请求参数有误';
      } else if (typeof d === 'string' && d.trim() && d.length <= 200) {
        msg = d.trim();
      }
      const err = new Error(msg);
      err.code = (d && d.code) || `E_HTTP_${r.status}`;
      err.status = r.status;
      throw err;
    }
    const reader = r.body.getReader(),
      decoder = new TextDecoder();
    let buf = '',
      ev = '',
      data = '';
    const flush = () => {
      if (!ev) return;
      try {
        const p = JSON.parse(data);
        if (ev === 'reasoning') am.reasoning = (am.reasoning || '') + p;
        else if (ev === 'chunk') am.content = (am.content || '') + p;
        else if (ev === 'meta') {
          am.route = p.route;
          am.sources = p.sources || [];
          /* 引用一到就问清"每条能不能打开"，好让按钮文案说实话
             （有 PDF / 只有文本版 / 都没有）。探测是异步的，回来后重渲染一次；
             结果按 source 缓存，同一份文件被引多次也只探一次。 */
          probeDocInfo(am.sources).then((fresh) => fresh && update());
        } else if (ev === 'done') {
          am.route = p.route;
          am.sources = p.sources || [];
          am.latency = p.latency_s;
          probeDocInfo(am.sources).then((fresh) => fresh && update());
          // 降级回答（模型失败、改成资料直出）要在界面上标出来，
          // 否则用户会以为"直接罗列资料"就是系统本来的回答风格。
          am.degraded = !!p.degraded;
          am.cached = !!p.cached;
        } else if (ev === 'vision') {
          am.vision = p.text || '';
          update();
        } else if (ev === 'status') {
          applyStatus(am, p);
          setState(p.message || '');
        } else if (ev === 'error') {
          /* 载荷可能是 {"code","message","tech_detail"}（后端已结构化），
             也可能是旧式的裸字符串。两种都认，但**都不直接显示** ——
             统一走 recordError：界面只出现友好文案，真实内容进控制台。
             改动前是把 message 原样塞进正文，于是用户会看到
             "模型服务异常：ConnectError(...)" 这种话。 */
          const obj = p && typeof p === 'object' ? p : { message: String(p == null ? '' : p) };
          setState(recordError(am, obj.code || '', obj));
        }
      } catch (e) {}
      ev = '';
      data = '';
      update();
    };
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        const s = line.trim();
        if (s.startsWith('event:')) {
          ev = s.slice(6).trim();
        } else if (s.startsWith('data:')) {
          data += s.slice(5).trim();
        } else if (s === '') {
          flush();
        }
      }
    }
    flush();
    /* ★ 流读完 = 生成确实结束了，把还在跑的那步收掉（2026-09-18 修「转圈不停」）。
     *
     * 根因：后端**普通问答**路径只发 status(generate, run)，然后直接发 done，
     * 没有配对的 generate done（只有照片研判那条路径才发）。实测三条路径：
     *     发图+文字·普通 → intent、generate 都没有 done
     *     只发图·普通    → intent、generate 都没有 done
     *     发图+文字·研判 → 齐全（vision/retrieve/generate/render/verify 都有）
     * 于是时间线最后一步永远是 running，CSS 里 .trace-row.running .trace-mark
     * 的 trace-spin 动画就无限转下去。
     * 这个现象**每次普通提问都会发生**，不限于发图 —— 用户是因为照片研判耗时长、
     * 时间线一直摆在眼前才注意到的。
     *
     * 为什么修在这里而不是只修后端：能读到流的 EOF，就是最权威的"全干完了"信号。
     * 收尾统一在这里做，后端将来再漏发 done 也不会让用户看到停不下来的转圈。
     * 后端那边也补齐了 done（双保险），但这里才是兜底的那一道。 */
    closeRunningSteps(am, '已完成');
    // 生成结束 → 图片识别内容与分析过程收起来，只留正文（用户要求）
    am.streaming = false;
    setPill(
      am.route === 'direct_chat'
        ? '直接对话 · Thinking'
        : am.route === 'general'
          ? '科普问答 · Thinking'
          : 'RAG · Thinking',
    );
    setState(`完成 · ${fmtSecs(am.latency)}`);
  } catch (e) {
    /* 网络层失败（fetch 抛异常 / 非 2xx）：同样只显示友好文案。
       真实原因（HTTP 状态码、响应体、堆栈）进控制台 —— 用户的要求是
       "界面不显示错误，后端日志/控制台显示实际错误"。 */
    setState(recordError(am, e.code || 'E_NETWORK', {
      message: e.message,
      tech_detail: String((e && e.stack) || ''),
    }));
    // 异常退出时也要把还在跑的那步收掉，否则时间线会一直转圈
    closeRunningSteps(am, '已中断');
    am.streaming = false;
  } finally {
    clearInterval(tick);
    c.updated = Date.now();
    save();
    renderMessages();
    busy = false;
    document.getElementById('ask').disabled = false;
    input.focus();
  }
}
