#!/usr/bin/env node
/* 知识图谱「重置」的回归测试（用户提的：「搜索以后没办法重置为原来的默认界面」）
 *
 * 要验的是一件事：**搜索过之后再点重置，界面要回到最初那个样子**。
 * 这件事最容易做一半 —— 清了输入框却留着匹配列表、留了列表却还画着图、
 * 图清了但右侧详情栏还停在上一个实体上。所以这里逐项断言，不用"看起来对了"当判据。
 *
 * 关键顺序：**先把干净界面搭好，再 import kg.js** —— 模块加载时会从 HTML 里抓一份
 * "默认界面"的原文（KG_IDLE），抓的时候 DOM 是什么样，重置就还原成什么样。
 * 反过来先弄脏再 import，抓到的就是脏的那份，测试会假通过。
 *
 * 用法：node 查图谱重置.js [站点目录] [--break-matches]
 *      --break-matches 去掉"收起匹配列表"那一步，验证本测试确实能抓到做一半的重置。
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");

const ARGS = process.argv.slice(2);
const BREAK_MATCHES = ARGS.includes("--break-matches");
const SITE = ARGS.find(function (a) { return !a.startsWith("--"); }) ||
  path.resolve(__dirname, "..");
const FE = path.join(SITE, "frontend");

const OK = [], BAD = [];
function check(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log("  " + (cond ? "√" : "×") + " " + name +
    (detail !== undefined ? "　" + String(detail).slice(0, 120) : ""));
}

/* ---------------------------------------------------------------- DOM 垫片 */

const byId = {};
const fetches = [];

function makeEl(tag) {
  const el = {
    tagName: (tag || "div").toUpperCase(), innerHTML: "", textContent: "", value: "",
    hidden: false, disabled: false, scrollTop: 0, scrollHeight: 0, clientHeight: 0,
    clientWidth: 800, width: 0, height: 0, style: {}, dataset: {}, attrs: {}, _ctx: null,
    children: [], parentNode: null, _handlers: {},
    classList: {
      _s: new Set(),
      add: function (c) { this._s.add(c); },
      remove: function (c) { this._s.delete(c); },
      contains: function (c) { return this._s.has(c); }
    },
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener: function (t, fn) { (this._handlers[t] = this._handlers[t] || []).push(fn); },
    removeEventListener: function () {},
    appendChild: function (c) { this.children.push(c); c.parentNode = this; return c; },
    focus: function () {}, scrollIntoView: function () {},
    querySelector: function () { return makeEl("div"); },
    querySelectorAll: function () { return []; },
    closest: function () { return null; },
    getBoundingClientRect: function () {
      return { top: 0, left: 0, right: 800, bottom: 600, width: 800, height: 600 };
    },
    /* canvas 上下文：全是空操作，只数 clearRect —— 重置后画布该是空白，
       而 drawKnowledgeGraph 开头正是靠 clearRect 清屏的。 */
    getContext: function () {
      if (el._ctx) return el._ctx;
      const noop = function () {};
      const ctx = {
        _cleared: 0,
        canvas: el,
        setTransform: noop, save: noop, restore: noop, translate: noop, scale: noop,
        clearRect: function () { ctx._cleared += 1; },
        beginPath: noop, closePath: noop, moveTo: noop, lineTo: noop, arc: noop,
        quadraticCurveTo: noop, stroke: noop, fill: noop, fillRect: noop,
        fillText: noop, strokeText: noop, setLineDash: noop,
        measureText: function () { return { width: 24 }; }
      };
      el._ctx = ctx;
      return ctx;
    }
  };
  return el;
}

global.document = {
  body: makeEl("body"), head: makeEl("head"), documentElement: makeEl("html"),
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { return (byId[id] = byId[id] || makeEl("div")); },
  querySelector: function () { return makeEl("div"); },
  querySelectorAll: function () { return []; },
  addEventListener: function () {}
};
global.window = global;
global.addEventListener = function () {};
global.removeEventListener = function () {};
global.requestAnimationFrame = function (fn) { return setTimeout(fn, 0); };
global.cancelAnimationFrame = function (id) { clearTimeout(id); };
global.getComputedStyle = function () { return { getPropertyValue: function () { return ""; } }; };
global.matchMedia = function () { return { matches: false, addEventListener: function () {} }; };
global.devicePixelRatio = 1;
global.ResizeObserver = function () { this.observe = function () {}; this.disconnect = function () {}; };
global.setInterval = function () { return 0; };
global.clearInterval = function () {};
global.localStorage = { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} };

const j = function (o) {
  return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(JSON.stringify(o)); } });
};
global.fetch = function (url) {
  const u = String(url);
  fetches.push(u);
  if (u.indexOf("/kg/stats") >= 0) {
    return j({ available: true, nodes: 2117, links: 9436, labels: { Law: 120, Standard: 340 } });
  }
  if (u.indexOf("/kg/suggest") >= 0) {
    return j({ total_nodes: 2117, total_links: 9436, type_count: 2,
               types: [{ label: "Law", count: 120, examples: [{ name: "环境保护法" }] },
                       { label: "Standard", count: 340, examples: [{ name: "GB 18485" }] }] });
  }
  return new Promise(function () {});
};
process.on("unhandledRejection", function () {});

const flush = function () { return new Promise(function (r) { setImmediate(r); }); };
/** 取元素（垫片里的 getElementById 会按需创建，跟真实 DOM 的"缺失返回 null"不同，
 *  所以测试里一律走这个函数，而不是直接摸 byId 的字段）。 */
const E = function (id) { return document.getElementById(id); };

/* --------------- 先把"默认界面"搭好（必须在 import kg.js 之前） --------------- */

/* 这两段就是 index.html 里的初始内容。kg.js 加载时会抓一份，重置就还原成它。 */
const IDLE_EMPTY = "输入关键词探索知识图谱";
const IDLE_DETAIL = '<h3>知识图谱</h3><span class="kg-type">节点详情</span>' +
  '<div class="kg-props">输入关键词搜索后，先从匹配列表里选一个实体。</div>';
E("kgEmpty").textContent = IDLE_EMPTY;
E("kgDetail").innerHTML = IDLE_DETAIL;
E("kgMatches").style.display = "none";

/* ---------------------------------------------------------------- 主流程 */

async function main() {
  console.log("=".repeat(62));
  console.log("站点：", SITE);

  const major = Number(process.versions.node.split(".")[0]);
  if (major < 14) {
    console.error("本测试需要 Node ≥ 14（当前 v" + process.versions.node + "）：前端模块用了 ?? 空值合并。");
    return 2;
  }

  let modPath = pathToFileURL(path.join(FE, "js", "kg.js")).href;
  if (BREAK_MATCHES) {
    const src = fs.readFileSync(path.join(FE, "js", "kg.js"), "utf8");
    const broken = src.replace(/  const matches = kgEl\('kgMatches'\);[\s\S]*?\n  \}\n/, "");
    if (broken === src) { console.error("注入失败：找不到「收起匹配列表」那一步"); return 2; }
    const dst = path.join(os.tmpdir(), "_kg_break.mjs");
    fs.writeFileSync(dst, broken.replace(/'\.\/([a-zA-Z]+)\.js'/g, function (m, name) {
      return JSON.stringify(pathToFileURL(path.join(FE, "js", name + ".js")).href);
    }));
    modPath = pathToFileURL(dst).href;
    console.log("（已注入缺陷：去掉「收起匹配列表」这一步）");
  }

  let kg = null, err = null;
  try { kg = await import(modPath); } catch (e) { err = e; }
  check("模块能加载（垫片下不炸）", !!kg && !err, err && err.message);
  if (!kg) return 1;

  check("导出了 kgResetAll（HTML 的 onclick 才调得到）", typeof kg.kgResetAll === "function");
  check("重置与 kgResetView 是两个函数（前者清搜索，后者只管视图）",
    typeof kg.kgResetView === "function" && kg.kgResetAll !== kg.kgResetView);

  /* ---- 变成"搜过一次之后"的样子 ---- */
  E("kgQuery").value = "固体废物";
  E("kgEmpty").textContent = "请从右侧列表中选择一个实体";
  E("kgEmpty").style.display = "grid";
  E("kgMatches").innerHTML = '<div class="kg-match-head">匹配 3 个实体</div>' +
    '<button class="kg-match">固体废物</button>';
  E("kgMatches").style.display = "";
  E("kgDetail").innerHTML = '<h3>固体废物</h3><span class="kg-type">污染物</span>';
  E("kgStats").textContent = "只看「固体废物」的直接关系：12 个邻居";
  E("kgSuggest").hidden = true;
  const before = fetches.length;

  /* ---- 点重置 ---- */
  let threw = null;
  try { kg.kgResetAll(); } catch (e) { threw = e; }
  check("kgResetAll 不抛异常", !threw, threw && threw.message);
  await flush(); await flush();

  check("① 搜索框清空", E("kgQuery").value === "", JSON.stringify(E("kgQuery").value));
  check("③ 空白提示回到了默认那句", E("kgEmpty").textContent === IDLE_EMPTY, E("kgEmpty").textContent);
  check("③ 提示的 display 被清空（交回 CSS，而不是写死一个和 CSS 重复的值）",
    E("kgEmpty").style.display === "", JSON.stringify(E("kgEmpty").style.display));
  check("③ 画布被重画成空白（clearRect 走过了）",
    !!(E("kgCanvas")._ctx && E("kgCanvas")._ctx._cleared > 0),
    E("kgCanvas")._ctx ? E("kgCanvas")._ctx._cleared + " 次 clearRect" : "没拿到画布上下文");
  check("④ 匹配列表清空", E("kgMatches").innerHTML === "", E("kgMatches").innerHTML.slice(0, 40));
  check("④ 匹配列表收起（回到 HTML 里的初始状态）",
    E("kgMatches").style.display === "none", JSON.stringify(E("kgMatches").style.display));
  check("⑤ 详情栏回到初始说明", E("kgDetail").innerHTML === IDLE_DETAIL,
    E("kgDetail").innerHTML.slice(0, 48));
  check("⑥ 推荐关键词面板放回来了", E("kgSuggest").hidden === false);
  check("⑦ 重新拉了一次图谱统计（统计与图例回到整图口径）",
    fetches.slice(before).some(function (u) { return u.indexOf("/kg/stats") >= 0; }),
    fetches.slice(before).join(" , ") || "没有新请求");
  check("⑦ 统计文案回到「N 个节点 · M 条关系」（不再是「只看某个节点」）",
    E("kgStats").textContent.indexOf("个节点") >= 0, E("kgStats").textContent);

  console.log("=".repeat(62));
  console.log("==== 通过 " + OK.length + " / 失败 " + BAD.length + " ====");
  BAD.forEach(function (b) { console.log("   失败：" + b); });
  return BAD.length ? 1 : 0;
}

main().then(function (c) { process.exit(c); },
  function (e) { console.error("测试自身异常：" + (e && e.stack || e)); process.exit(2); });
