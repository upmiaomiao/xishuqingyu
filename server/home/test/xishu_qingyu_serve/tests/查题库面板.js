#!/usr/bin/env node
/* 示例题库面板的 DOM 垫片测试（Node，无需浏览器）
 *
 * 为什么需要：题库是"点一条直接发给模型"的交互，最容易错的不是数据、而是**点击路由** ——
 * 「全文」按钮长在条目里面，判断顺序一写反，点全文就会把题发出去；条目用 data-g/data-i
 * 索引取题，索引算错就会发出别的题。这两类错误静态检查一条都抓不到。
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
    (detail !== undefined ? "　" + String(detail).slice(0, 120) : ""));
}

/* ---------------------------------------------------------------- DOM 垫片 */

function makeEl(tag) {
  return {
    tagName: (tag || "div").toUpperCase(), innerHTML: "", textContent: "", value: "",
    hidden: false, disabled: false, scrollTop: 0, scrollHeight: 0, style: {},
    dataset: {}, attrs: {}, _handlers: {}, _full: null,
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
    appendChild: function () {}, focus: function () {}, scrollIntoView: function () {},
    querySelector: function (sel) {
      if (sel === ".qb-full") {
        /* 渲染出来的 HTML 是 <div class="qb-full" hidden>，垫片得跟着初始隐藏，
           否则「点全文」取反后会变成"收起"，测试会误判成产品 bug（踩过）。 */
        if (!this._full) { this._full = makeEl("div"); this._full.hidden = true; }
        return this._full;
      }
      return null;
    },
    querySelectorAll: function () { return []; },
    closest: function () { return null; }
  };
}

const byId = {};
global.document = {
  body: makeEl("body"), head: makeEl("head"), documentElement: makeEl("html"),
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { return (byId[id] = byId[id] || makeEl("div")); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {}
};
global.window = global;
/* 依赖链里（kg.js 等）会在模块顶层绑窗口事件、摸一些浏览器全局，
   垫片得把这些补齐，否则 import 阶段就炸 —— 与题目面板本身无关。 */
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
    let src = fs.readFileSync(path.join(FE, "js", "questions.js"), "utf8");
    const broken = src.replace(
      /const more = ev\.target\.closest\('\[data-more\]'\);[\s\S]*?\n  \}\n/, "");
    if (broken === src) { console.error("注入失败：找不到「全文」分支"); return 2; }
    /* 改写后的副本放在临时目录，相对导入 './ask.js' 会解析不到 ——
       换成绝对 file:// URL。不改站点目录，免得留文件被同步工具当成"线上新增"。 */
    src = broken.replace("'./ask.js'",
      JSON.stringify(pathToFileURL(path.join(FE, "js", "ask.js")).href));
    const dst = path.join(os.tmpdir(), "_questions_break.mjs");
    fs.writeFileSync(dst, src);
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
  check("入口按钮绑了 click", (byId.qbToggle._handlers.click || []).length === 1);
  check("面板绑了委托 click", (byId.qbPanel._handlers.click || []).length === 1);

  await mod.openQuestionBank();
  // openQuestionBank() 自身不是 async（内部走 .then 链），所以 await 它拿不到渲染结果，
  // 得让事件循环转一圈，等 fetch + renderBank 的回调跑完。
  await new Promise(function (r) { setImmediate(r); });
  await new Promise(function (r) { setImmediate(r); });
  const tabs = byId.qbTabs.innerHTML;
  let body = byId.qbBody.innerHTML;
  const nBurn = BANK.tabs[0].groups.reduce(function (n, g) { return n + g.items.length; }, 0);
  const nWaste = BANK.tabs[1].groups.reduce(function (n, g) { return n + g.items.length; }, 0);

  check("面板展开", byId.qbPanel.hidden === false);
  check("渲染出 2 个分类页签", (tabs.match(/class="qb-tab/g) || []).length === 2,
    (tabs.match(/class="qb-tab/g) || []).length);
  check("默认页签渲染 " + nBurn + " 条", (body.match(/class="qb-row"/g) || []).length === nBurn,
    (body.match(/class="qb-row"/g) || []).length);
  check("分组标题都在", BANK.tabs[0].groups.every(function (g) { return body.indexOf(g.name) >= 0; }));
  check("入口按钮上显示了总条数", byId.qbN.textContent === String(nBurn + nWaste), byId.qbN.textContent);

  const q0 = BANK.tabs[0].groups[0].items[0];
  const firstText = (body.match(/<div class="qb-text">([\s\S]*?)<\/div>/) || [])[1] || "";
  check("长题首条只显示摘要（截断并带省略号）",
    firstText.length > 0 && firstText.length < q0.length && firstText.slice(-1) === "…",
    firstText.length + " 字 / 原题 " + q0.length + " 字");
  check("全文仍在条目里（折叠的 hidden 块）", (body.split(q0.slice(-24)).length - 1) === 1);

  const click = byId.qbPanel._handlers.click[0];

  click({ target: { closest: function (s) { return s === "[data-tab]" ? { getAttribute: function () { return "1"; } } : null; } } });
  body = byId.qbBody.innerHTML;
  check("切到「固废」渲染 " + nWaste + " 条", (body.match(/class="qb-row"/g) || []).length === nWaste,
    (body.match(/class="qb-row"/g) || []).length);

  /* 点条目 → 该条全文必须原样进入会话消息 */
  const g = 2, i = 1;
  const wanted = BANK.tabs[1].groups[g].items[i];
  click({
    target: {
      closest: function (s) {
        return s === ".qb-row"
          ? { getAttribute: function (k) { return { "data-g": String(g), "data-i": String(i) }[k]; } }
          : null;
      }
    }
  });
  const msgs = util.state.chats[0].messages;
  /* ask() 会推两条：先是用户消息，紧接着一条助手的流式占位（content 为空）。
     所以这里断言的是"第一条是用户消息、内容等于该题全文"，不是消息总数。 */
  check("点条目：该条全文进入会话消息",
    msgs.length === 2 && msgs[0].role === "user" && msgs[0].content === wanted &&
    msgs[1].role === "assistant",
    msgs.length + " 条；" + (msgs[0] && msgs[0].content === wanted ? "内容一致" : "内容不一致") +
    "；实际首条：" + (msgs.length ? String(msgs[0].content).slice(0, 30) : "-") +
    "…期望首条：" + wanted.slice(0, 30) + "…");
  check("点条目：真的发起了发送（ask() 置灰发送键）", byId.ask.disabled === true);
  check("点条目：面板收起", byId.qbPanel.hidden === true);

  /* 点「全文」→ 只能展开，绝不能被当成发送 */
  byId.qbPanel.hidden = false;
  const item = makeEl("div");
  const nBefore = util.state.chats[0].messages.length;
  click({
    target: {
      closest: function (s) {
        if (s === "[data-tab]") return null;
        if (s === "[data-more]") return { closest: function () { return item; } };
        if (s === ".qb-row") return { getAttribute: function () { return "0"; } };
        return null;
      }
    }
  });
  check("点「全文」没有被当成发送", util.state.chats[0].messages.length === nBefore);
  check("点「全文」展开了正文", !!item._full && item._full.hidden === false);
  check("点「全文」后面板仍然开着", byId.qbPanel.hidden === false);

  console.log("=".repeat(62));
  console.log("==== 通过 " + OK.length + " / 失败 " + BAD.length + " ====");
  BAD.forEach(function (b) { console.log("   失败：" + b); });
  return BAD.length ? 1 : 0;
}

main().then(function (code) { process.exit(code); },
  function (e) { console.error("测试自身异常：" + (e && e.stack || e)); process.exit(2); });
