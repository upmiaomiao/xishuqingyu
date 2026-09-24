#!/usr/bin/env node
/* 示例题库的 DOM 垫片测试（Node，无需浏览器）
 *
 * 为什么需要：题库是"点一条直接发给模型"的交互，最容易错的不是数据、而是**点击路由** ——
 * 「全文」按钮长在条目里面，判断顺序一写反，点全文就会把题发出去；条目用 data-g/data-i
 * 索引取题，索引算错就会发出别的题。这两类错误静态检查一条都抓不到。
 * 后来入口挪到欢迎页、又加了"点别处收起"和"10 秒自动轮换"，于是又多三类要看的行为：
 * 浮层是不是真的挂在 body 上（挂在欢迎页里会被重渲染连带销毁）、点外面/Esc/回车能不能收起、
 * 轮换定时器的周期与停启（聊起来之后必须停，否则一直空转）。
 *
 * 做法照 tests/查模块挂载.js：用手搓的最小 DOM 垫片把模块**真跑一遍**，把行为变成断言。
 * 两点不同：① questions.js 是 ES 模块，用动态 import（不是 new Function），
 *            所以本文件自己是 CommonJS —— 和隔壁那条测试保持同一种用法；
 *          ② ask() 会**同步清空输入框**再发请求，所以断言点放在"消息有没有进会话状态"上，
 *            而不是输入框的值（那已经被 ask() 清掉了）。
 *
 * 用法：node 查题库面板.js [站点目录] [--break-more]
 *      --break-more 去掉「全文」分支，验证本测试确实能抓到顺序写反（缺陷注入）。
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");

const HERE = __dirname;
const ARGS = process.argv.slice(2);
const BREAK = ARGS.includes("--break-more");
const SITE = ARGS.find(function (a) { return !a.startsWith("--"); }) || path.resolve(HERE, "..");
const FE = path.join(SITE, "frontend");
const BANK = JSON.parse(fs.readFileSync(path.join(FE, "data", "question-bank.json"), "utf8"));

const OK = [], BAD = [];
function check(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log("  " + (cond ? "√" : "×") + " " + name +
    (detail !== undefined ? "　" + String(detail).slice(0, 130) : ""));
}

/* ---------------------------------------------------------------- DOM 垫片 */

const byId = {};

function makeEl(tag) {
  return {
    tagName: (tag || "div").toUpperCase(), innerHTML: "", textContent: "", value: "",
    hidden: false, disabled: false, scrollTop: 0, scrollHeight: 0, style: {},
    dataset: {}, attrs: {}, children: [], parentNode: null, _handlers: {}, _q: {}, _full: null,
    classList: {
      _s: new Set(),
      add: function (c) { this._s.add(c); },
      remove: function (c) { this._s.delete(c); },
      contains: function (c) { return this._s.has(c); }
    },
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener: function (type, fn) {
      (this._handlers[type] = this._handlers[type] || []).push(fn);
    },
    appendChild: function (child) {
      this.children.push(child);
      child.parentNode = this;
      if (child.id) byId[child.id] = child;      // 挂上去之后就该能被 getElementById 找到
      return child;
    },
    focus: function () {}, scrollIntoView: function () {},
    querySelector: function (sel) {
      /* 同一个选择器返回同一个节点：实现里是「建好外壳 → querySelector 拿引用」，
         垫片要是不缓存，测试拿到的和实现拿到的就不是一个东西（踩过）。 */
      if (sel === ".qb-full") {
        /* 渲染出来的 HTML 是 <div class="qb-full" hidden>，垫片得跟着初始隐藏，
           否则「点全文」取反后会变成"收起"，测试会误判成产品 bug（也踩过）。 */
        if (!this._full) { this._full = makeEl("div"); this._full.hidden = true; }
        return this._full;
      }
      if (!this._q[sel]) this._q[sel] = makeEl("div");
      return this._q[sel];
    },
    querySelectorAll: function (sel) {
      /* 欢迎页那三个示例按钮：message.js 的轮换定时器要按这批节点改文字。
         垫片不解析 innerHTML，所以按选择器发三个替身，测试才有东西可断言。 */
      if (sel === ".welcome .example") {
        if (!this._btns) this._btns = [makeEl("button"), makeEl("button"), makeEl("button")];
        return this._btns;
      }
      return [];
    },
    closest: function () { return null; }
  };
}

/* 欢迎页那段 HTML 是字符串塞进 #messages 的，垫片不解析它。
   所以 init 之后那句"还停在欢迎页就刷新一下"要走 document.querySelector，
   这里让它命中（否则那条分支在测试里永远走不到）。 */
const welcomeVisible = makeEl("div");
global.document = {
  body: makeEl("body"), head: makeEl("head"), documentElement: makeEl("html"),
  _handlers: {},
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { return (byId[id] = byId[id] || makeEl("div")); },
  querySelector: function (sel) { return sel === ".welcome .examples" ? welcomeVisible : null; },
  querySelectorAll: function () { return []; },
  addEventListener: function (type, fn) {
    (this._handlers[type] = this._handlers[type] || []).push(fn);
  }
};
global.window = global;
/* 依赖链里（kg.js 等）会在模块顶层绑窗口事件、摸一些浏览器全局，
   垫片得把这些补齐，否则 import 阶段就炸 —— 与题库本身无关。 */
global.addEventListener = function () {};
global.removeEventListener = function () {};
global.requestAnimationFrame = function (fn) { return setTimeout(fn, 0); };
global.cancelAnimationFrame = function (id) { clearTimeout(id); };
global.getComputedStyle = function () {
  return { getPropertyValue: function () { return ""; } };
};
global.matchMedia = function () {
  return { matches: false, addEventListener: function () {}, addListener: function () {} };
};
global.devicePixelRatio = 1;
global.ResizeObserver = function () { this.observe = function () {}; this.disconnect = function () {}; };
global.localStorage = { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} };
/* 只喂题库；其余请求挂起 —— 本测试验到"发送已发起"为止，不去模拟后端 */
global.fetch = function (url) {
  if (String(url).indexOf("question-bank.json") >= 0) {
    return Promise.resolve({ ok: true, status: 200, json: function () { return Promise.resolve(BANK); } });
  }
  return new Promise(function () {});
};
process.on("unhandledRejection", function () {});     // 挂起的请求不算失败

/* 定时器换成探针：10 秒轮换不能靠真等 10 秒来测（也不能为了好测就把周期做成可注入的参数）。
   记下 setInterval 的回调与周期，测试自己"拨钟"。 */
const timers = [];
global.setInterval = function (fn, ms) {
  timers.push({ fn: fn, ms: ms, dead: false });
  return timers.length;
};
global.clearInterval = function (id) {
  if (timers[id - 1]) timers[id - 1].dead = true;
};
/* 只认轮换那一个。ask.js 里还有个 200ms 的秒表定时器（第 250 行，流式跑着的时候挂着），
   它不属于本次要验的东西 —— 而且因为 fetch 在这里是挂起的，它永远不会自己结束。
   最初这条断言把**所有**定时器都数进去了，于是被那个秒表绊了个假失败。 */
const ROTATE_MS = 10000;
const rotTimers = function () {
  return timers.filter(function (t) { return t.ms === ROTATE_MS; });
};
const liveRotations = function () {
  return rotTimers().filter(function (t) { return !t.dead; });
};

/* ---------------------------------------------------------------- 事件工厂 */

/* 实现里是"全挂在 document 一层"的委托，所以点击事件得按它关心的选择器回答。 */
const evToggle = function () {
  return { target: { closest: function (s) { return s === "#qbToggle" ? {} : null; } } };
};
const evOutside = function () {
  return { target: { closest: function () { return null; } } };
};
const evInPanel = function (inner) {
  return { target: { closest: function (s) {
    if (s === "#qbPanel") return {};
    return inner(s);
  } } };
};
const evRow = function (g, i) {
  return evInPanel(function (s) {
    return s === ".qb-row"
      ? { getAttribute: function (k) { return { "data-g": String(g), "data-i": String(i) }[k]; } }
      : null;
  });
};
const evTab = function (i) {
  return evInPanel(function (s) {
    return s === "[data-tab]" ? { getAttribute: function () { return String(i); } } : null;
  });
};
const evMore = function (item) {
  return evInPanel(function (s) {
    if (s === "[data-more]") return { closest: function () { return item; } };
    if (s === ".qb-row") return { getAttribute: function () { return "0"; } };
    return null;
  });
};

const flush = function () { return new Promise(function (r) { setImmediate(r); }); };

/* ---------------------------------------------------------------- 主流程 */

async function main() {
  console.log("=".repeat(62));
  console.log("站点：", SITE);

  /* Node 版本预检：服务器上是 Node 12，而前端 util.js 用了 ?? （空值合并，Node 14 才有），
     Node 12 会把 .js 当 CJS 解析并在 import 阶段直接 SyntaxError —— 报错很难看懂。
     这里提前说清楚：这条测试要在**本机新版 Node** 上跑，线上跑契约检查（ops/查题库契约.py）。 */
  const major = Number(process.versions.node.split(".")[0]);
  if (major < 14) {
    console.error("本测试需要 Node ≥ 14（当前 v" + process.versions.node + "）。");
    console.error("原因：前端模块用了 ?? 空值合并语法，Node 12 无法解析 ES 模块。");
    console.error("线上请改用：python3 /home/test/查题库契约.py（查静态契约与资源可达性）");
    return 2;
  }

  const util = await import(pathToFileURL(path.join(FE, "js", "util.js")).href);
  util.state.chats = [{ id: "c1", title: "新对话", messages: [], updated: Date.now() }];
  util.state.activeId = "c1";

  let modPath = pathToFileURL(path.join(FE, "js", "questions.js")).href;
  if (BREAK) {
    const src = fs.readFileSync(path.join(FE, "js", "questions.js"), "utf8");
    let broken = src.replace(
      /const more = ev\.target\.closest\('\[data-more\]'\);[\s\S]*?\n  \}\n/, "");
    if (broken === src) { console.error("注入失败：找不到「全文」分支"); return 2; }
    /* 改写后的副本放在临时目录，相对导入 './ask.js' 之类会解析不到 ——
       逐个换成绝对 file:// URL。不改站点目录，免得留文件被同步工具当成"线上新增"。 */
    broken = broken.replace(/'\.\/([a-zA-Z]+)\.js'/g, function (m, name) {
      return JSON.stringify(pathToFileURL(path.join(FE, "js", name + ".js")).href);
    });
    const dst = path.join(os.tmpdir(), "_questions_break.mjs");
    fs.writeFileSync(dst, broken);
    modPath = pathToFileURL(dst).href;
    console.log("（已注入缺陷：去掉「全文」分支）");
  }

  let mod = null, err = null;
  try { mod = await import(modPath); } catch (e) { err = e; }
  check("模块能加载（依赖链在垫片下不炸）", !!mod && !err, err && err.message);
  if (!mod) return 1;

  let threw = null;
  try { mod.initQuestionBank(); } catch (e) { threw = e; }
  check("initQuestionBank 不抛异常", !threw, threw && threw.message);
  check("点击委托挂在 document 上（入口在欢迎页里，挂按钮会随重渲染失效）",
    (document._handlers.click || []).length === 1);
  check("键盘也挂在 document 上", (document._handlers.keydown || []).length === 1);

  const panel = byId.qbPanel;
  check("浮层建好并挂在 body 上（不是聊天区里）",
    !!panel && document.body.children.indexOf(panel) >= 0);
  check("浮层初始是收起的", !!panel && panel.hidden === true);

  await flush(); await flush();

  /* ---- 欢迎页：轮换的示例问题 + 入口 ---- */
  const welcome1 = byId.messages.innerHTML;
  check("欢迎页渲染了三个示例问题", (welcome1.match(/class="example"/g) || []).length === 3,
    (welcome1.match(/class="example"/g) || []).length);
  check("欢迎页有题库入口", welcome1.indexOf('id="qbToggle"') >= 0);
  check("入口上带总条数 71", welcome1.indexOf("> 71 条<") >= 0);
  check("已去掉「点一条直接发给模型」那句提示",
    welcome1.indexOf("点一条直接发给模型") < 0 && welcome1.indexOf("qb-tip") < 0);

  /* 简单题池 = 固废的「简单」+「日常」两组 */
  const waste = BANK.tabs.find(function (t) { return t.name === "固废"; });
  const pool = waste.groups
    .filter(function (g) { return /简单|日常/.test(g.name); })
    .reduce(function (a, g) { return a.concat(g.items); }, []);
  check("简单题池 = 简单 5 + 日常 20 = 25 条", pool.length === 25, pool.length + " 条");

  const picked1 = util.pickWelcomeExamples(3, "c1");
  check("三个问题都取自简单题池", picked1.length === 3 &&
    picked1.every(function (q) { return pool.indexOf(q) >= 0; }),
    picked1.length + " 条：" + picked1[0].slice(0, 18));
  check("欢迎页显示的正是这三个",
    picked1.every(function (q) { return welcome1.indexOf(q) >= 0; }));
  check("题库到位后已把兜底问题换掉（不再是写死那三条）",
    welcome1.indexOf("危险废物转移联单的确认期限是多久？") < 0);

  /* 轮换：换个会话顺延一组；同一会话重复渲染则不动 */
  util.state.chats.push({ id: "c2", title: "新对话", messages: [], updated: Date.now() });
  util.state.activeId = "c2";
  const msgMod = await import(pathToFileURL(path.join(FE, "js", "message.js")).href);
  msgMod.renderMessages();
  const picked2 = util.pickWelcomeExamples(3, "c2");   // key 没变 → 拿到的就是刚渲染的那一组
  check("换一个新会话：示例问题轮换了一组",
    picked2.join("|") !== picked1.join("|"), picked2[0].slice(0, 18));
  check("新会话的三个问题也来自简单题池",
    picked2.every(function (q) { return pool.indexOf(q) >= 0; }));
  util.state.activeId = "c1";
  msgMod.renderMessages();
  const welcome3 = byId.messages.innerHTML;
  msgMod.renderMessages();
  check("同一会话重复渲染：问题保持不动（不会在眼皮底下乱换）",
    byId.messages.innerHTML === welcome3);

  /* ---- 每 10 秒自动换一组（用户要求：默认 10 秒换一次问题） ---- */
  check("欢迎页同时只挂一个轮换定时器（重新渲染先停旧的，不泄漏）",
    liveRotations().length === 1, liveRotations().length + " 个");
  check("轮换周期是 10 秒", liveRotations()[0] && liveRotations()[0].ms === 10000,
    liveRotations()[0] ? liveRotations()[0].ms + "ms" : "没有轮换定时器");
  const btns = byId.messages.querySelectorAll(".welcome .example");
  check("垫片拿到 3 个示例按钮", btns.length === 3, btns.length + " 个");

  const tick = function () {
    const t = liveRotations()[0];
    if (!t) return null;
    t.fn();
    return 1;
  };
  tick();
  const t1 = btns.map(function (b) { return b.textContent; });
  check("过 10 秒：三个问题都换成池子里的题",
    t1.length === 3 && t1.every(function (q) { return !!q && pool.indexOf(q) >= 0; }), t1[0]);
  tick();
  const t2 = btns.map(function (b) { return b.textContent; });
  check("再过 10 秒：又换了一组（不是原地不动）", t2.join("|") !== t1.join("|"), t2[0]);
  check("每组内部不重复（同屏不会出现同一道题两次）",
    new Set(t1).size === 3 && new Set(t2).size === 3);
  check("轮换出来的问题都能在池子里找到", t2.every(function (q) { return pool.indexOf(q) >= 0; }));

  /* ---- 打开浮层 ---- */
  const click = document._handlers.click[0];
  click(evToggle());
  check("点入口打开浮层", panel.hidden === false);
  check("打开后 aria-expanded=true", byId.qbToggle.getAttribute("aria-expanded") === "true");

  const tabs = panel.querySelector(".qb-tabs").innerHTML;
  let body = panel.querySelector(".qb-body").innerHTML;
  const nBurn = BANK.tabs[0].groups.reduce(function (n, g) { return n + g.items.length; }, 0);
  const nWaste = BANK.tabs[1].groups.reduce(function (n, g) { return n + g.items.length; }, 0);
  check("渲染出 2 个分类页签", (tabs.match(/class="qb-tab/g) || []).length === 2,
    (tabs.match(/class="qb-tab/g) || []).length);
  check("默认页签渲染 " + nBurn + " 条", (body.match(/class="qb-row"/g) || []).length === nBurn,
    (body.match(/class="qb-row"/g) || []).length);
  check("分组标题都在", BANK.tabs[0].groups.every(function (g) { return body.indexOf(g.name) >= 0; }));

  const q0 = BANK.tabs[0].groups[0].items[0];
  const firstText = (body.match(/<div class="qb-text">([\s\S]*?)<\/div>/) || [])[1] || "";
  check("长题首条只显示摘要（截断并带省略号）",
    firstText.length > 0 && firstText.length < q0.length && firstText.slice(-1) === "…",
    firstText.length + " 字 / 原题 " + q0.length + " 字");
  check("全文仍在条目里（折叠的 hidden 块）", (body.split(q0.slice(-24)).length - 1) === 1);

  /* ---- 页签 / 点条目发送 ---- */
  click(evTab(1));
  body = panel.querySelector(".qb-body").innerHTML;
  check("切到「固废」渲染 " + nWaste + " 条",
    (body.match(/class="qb-row"/g) || []).length === nWaste,
    (body.match(/class="qb-row"/g) || []).length);

  const g = 2, i = 1;
  const wanted = BANK.tabs[1].groups[g].items[i];
  click(evRow(g, i));
  const msgs = util.state.chats[0].messages;
  /* ask() 会推两条：先是用户消息，紧接着一条助手的流式占位（content 为空）。
     所以这里断言的是"第一条是用户消息、内容等于该题全文"，不是消息总数。 */
  check("点条目：该条全文进入会话消息",
    msgs.length === 2 && msgs[0].role === "user" && msgs[0].content === wanted &&
    msgs[1].role === "assistant",
    msgs.length + " 条；" + (msgs[0] && msgs[0].content === wanted ? "内容一致" : "内容不一致"));
  check("点条目：真的发起了发送（ask() 置灰发送键）", byId.ask.disabled === true);
  check("点条目：浮层收起", panel.hidden === true);

  msgMod.renderMessages();               // 这个会话已经有消息了
  check("开始聊之后轮换定时器就停了（不留空转的定时器）",
    liveRotations().length === 0,
    rotTimers().map(function (t) { return t.ms + (t.dead ? "死" : "活"); }).join(",") || "一个都没有");

  /* ---- 点「全文」只展开，不发送 ---- */
  click(evToggle());
  const item = makeEl("div");
  const nBefore = util.state.chats[0].messages.length;
  /* 判据用**输入框有没有被改写**，不是消息数有没有涨：
     上面那次发送已经把 ask() 置成 busy，就算「全文」误走发送分支，ask() 也会提前返回、
     消息数照样不变 —— 只看消息数会假通过（真踩过：缺陷注入时这条还是绿的）。 */
  const inputBefore = byId.q.value;
  click(evMore(item));
  check("点「全文」没有被当成发送（输入框没被改写）", byId.q.value === inputBefore,
    "输入框：" + String(byId.q.value).slice(0, 24));
  check("点「全文」没有多出消息", util.state.chats[0].messages.length === nBefore);
  check("点「全文」展开了正文", !!item._full && item._full.hidden === false);
  check("点「全文」后浮层仍然开着", panel.hidden === false);

  /* ---- 点别处 / Esc / 输入框回车 → 自动收起（本次需求） ---- */
  click(evOutside());
  check("点浮层外面自动收起", panel.hidden === true);

  click(evToggle());
  check("再次点入口能打开", panel.hidden === false);
  click(evToggle());
  check("再点一次入口自己收起", panel.hidden === true);

  click(evToggle());
  document._handlers.keydown[0]({ key: "Escape", target: {} });
  check("按 Esc 收起", panel.hidden === true);

  click(evToggle());
  document._handlers.keydown[0]({ key: "Enter", shiftKey: false, target: { id: "q" } });
  check("在输入框回车发送时也收起（不然浮层盖着刚发出去的对话）", panel.hidden === true);

  click(evToggle());
  document._handlers.keydown[0]({ key: "a", target: { id: "q" } });
  check("普通按键不会误收起", panel.hidden === false);

  console.log("=".repeat(62));
  console.log("==== 通过 " + OK.length + " / 失败 " + BAD.length + " ====");
  BAD.forEach(function (b) { console.log("   失败：" + b); });
  return BAD.length ? 1 : 0;
}

main().then(function (code) { process.exit(code); },
  function (e) { console.error("测试自身异常：" + (e && e.stack || e)); process.exit(2); });
