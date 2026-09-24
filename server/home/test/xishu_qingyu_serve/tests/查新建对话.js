#!/usr/bin/env node
/* 新建对话的回归测试（用户报的 bug：「我居然可以一直新建对话」）
 *
 * 原来的 newConversation() 无条件 unshift 一个新会话 —— 连点「新对话」就能点出无限多个
 * 长得一模一样的空壳，历史列表被刷屏、localStorage 也白占。
 * 现在的规矩：**当前会话本来就是空壳就复用它**；加载时把历史里多余的空壳裁到最多一个。
 *
 * 为什么单开一条测试、而不是并进 查题库面板.js：那是题库浮层的测试，两件事不该混。
 * 这里的断言很短，但都是"用户一点就能撞上"的行为，值得有个地方盯着。
 *
 * 用法：node 查新建对话.js [站点目录]
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const HERE = __dirname;
const SITE = process.argv.slice(2).find(function (a) { return !a.startsWith("--"); }) ||
  path.resolve(HERE, "..");
const FE = path.join(SITE, "frontend");

const OK = [], BAD = [];
function check(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log("  " + (cond ? "√" : "×") + " " + name +
    (detail !== undefined ? "　" + String(detail).slice(0, 130) : ""));
}

/* ---------------------------------------------------------------- DOM 垫片 */

const byId = {};
const store = {};                       // 假 localStorage：load() 要从这里读

function makeEl(tag) {
  return {
    tagName: (tag || "div").toUpperCase(), innerHTML: "", textContent: "", value: "",
    hidden: false, disabled: false, scrollTop: 0, scrollHeight: 0, style: {},
    dataset: {}, attrs: {}, children: [], parentNode: null, _handlers: {},
    classList: {
      _s: new Set(),
      add: function (c) { this._s.add(c); },
      remove: function (c) { this._s.delete(c); },
      contains: function (c) { return this._s.has(c); }
    },
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener: function () {}, removeEventListener: function () {},
    appendChild: function (c) { this.children.push(c); c.parentNode = this; if (c.id) byId[c.id] = c; return c; },
    focus: function () {}, scrollIntoView: function () {},
    querySelector: function () { return makeEl("div"); },
    querySelectorAll: function () { return []; },
    closest: function () { return null; }
  };
}

global.document = {
  body: makeEl("body"), head: makeEl("head"), documentElement: makeEl("html"),
  _handlers: {},
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { return (byId[id] = byId[id] || makeEl("div")); },
  querySelector: function () { return null; },
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
global.localStorage = {
  getItem: function (k) { return k in store ? store[k] : null; },
  setItem: function (k, v) { store[k] = String(v); },
  removeItem: function (k) { delete store[k]; }
};
global.fetch = function () { return new Promise(function () {}); };
process.on("unhandledRejection", function () {});

/* ---------------------------------------------------------------- 主流程 */

async function main() {
  console.log("=".repeat(62));
  console.log("站点：", SITE);

  const major = Number(process.versions.node.split(".")[0]);
  if (major < 14) {
    console.error("本测试需要 Node ≥ 14（当前 v" + process.versions.node + "）：前端模块用了 ?? 空值合并。");
    return 2;
  }

  const st = await import(pathToFileURL(path.join(FE, "js", "store.js")).href);
  const util = await import(pathToFileURL(path.join(FE, "js", "util.js")).href);

  /* ---- 连点「新对话」不该越点越多 ---- */
  st.load();                                   // 空历史 → 自动建一个
  check("空历史会有一个新对话", util.state.chats.length === 1, util.state.chats.length + " 个");
  for (let i = 0; i < 10; i += 1) st.newConversation(false);
  check("连点 10 次「新对话」仍然只有一个空对话",
    util.state.chats.length === 1, util.state.chats.length + " 个");
  check("当前会话就是这个空对话", util.state.activeId === util.state.chats[0].id);

  /* ---- 说过话的会话不受影响，之后再点会真的新建 ---- */
  util.state.chats[0].messages.push({ role: "user", content: "你好" });
  st.newConversation(false);
  check("聊过的会话之后再点：正常新建", util.state.chats.length === 2, util.state.chats.length + " 个");
  check("新建的会话是当前会话", util.state.activeId === util.state.chats[0].id);
  check("新建出来的会话是空的", util.state.chats[0].messages.length === 0);

  /* 空对话 + 已经聊过的那条：再点仍然只有"复用"，不会再多 ---- */
  st.newConversation(false);
  st.newConversation(false);
  check("空对话上再连点两次，还是 2 个（复用不新增）",
    util.state.chats.length === 2, util.state.chats.length + " 个");

  /* ---- 加载时把历史里多余的空壳裁掉 ---- */
  store[util.STORE] = JSON.stringify([
    { id: "e1", title: "新对话", created: 1, updated: 5, messages: [] },
    { id: "e2", title: "新对话", created: 1, updated: 4, messages: [] },
    { id: "e3", title: "新对话", created: 1, updated: 3, messages: [] },
    { id: "k1", title: "固废怎么处置", created: 1, updated: 2, messages: [{ role: "user", content: "x" }] },
    { id: "e4", title: "改过名字的空对话", created: 1, updated: 1, messages: [] }
  ]);
  st.load();
  const ids = util.state.chats.map(function (c) { return c.id; });
  check("加载时多余的空壳被裁掉（e2/e3 不在）",
    ids.indexOf("e2") < 0 && ids.indexOf("e3") < 0, "剩：" + ids.join(","));
  check("留下的是最新的那个空壳（e1）", ids.indexOf("e1") >= 0);
  check("有内容的会话一律不动（k1）", ids.indexOf("k1") >= 0);
  check("改过名字的空对话不算空壳（用户动过就不替他删）", ids.indexOf("e4") >= 0);
  check("裁完共 3 个", util.state.chats.length === 3, util.state.chats.length + " 个");

  console.log("=".repeat(62));
  console.log("==== 通过 " + OK.length + " / 失败 " + BAD.length + " ====");
  BAD.forEach(function (b) { console.log("   失败：" + b); });
  return BAD.length ? 1 : 0;
}

main().then(function (c) { process.exit(c); },
  function (e) { console.error("测试自身异常：" + (e && e.stack || e)); process.exit(2); });
