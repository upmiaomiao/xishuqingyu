#!/usr/bin/env node
/* 模块挂载冒烟测试（Node，无需浏览器）
 *
 * 为什么需要它：这一轮出的故障是"页面点开右栏全没样式"，根因是**模块忘了包 .ge-shell**，
 * 而 --ge-* 变量全声明在 .ge-shell 上 → var(--ge-white) 之类静默失效（不报错、不抛异常），
 * 背景/边框/按钮配色全丢，"发送"按钮白字透明底直接看不见。
 * 我在没有浏览器的情况下靠肉眼截图才发现，太晚。所以这里用最小 DOM 垫片把模块**真跑一遍**，
 * 把"结构性错误"变成断言。
 *
 * 查的几条：
 *   ① 注入的 HTML 必须正好包一层 <div class="ge-shell">（变量作用域的根）
 *   ② 源码里所有 $("id") 引用的元素，注入的 HTML 里都必须真有 id="..."（防拼写/漏元素）
 *   ③ 挂载幂等（重复调用不产生第二份）
 *   ④ setGenEmbedded 切的是 .ge-shell 上的类（否则 .ge-shell.ge-embedded 选不中）
 *   ⑤ 挂载过程不抛异常
 *
 * 用法：node 查模块挂载.js [gen_ui.js]
 *      加 --break-shell 参数可**故意去掉** .ge-shell 包裹，验证本测试确实能抓到（缺陷注入）。
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ARG = process.argv.slice(2);
const BREAK = ARG.includes("--break-shell");
const FILE = ARG.find(function (a) { return !a.startsWith("--"); }) ||
  path.join(__dirname, "static", "gen_ui.js");

let src = fs.readFileSync(FILE, "utf8");
if (BREAK) {
  // 缺陷注入：把包裹去掉，模拟"忘了包 .ge-shell"
  src = src.replace('\'<div class="ge-shell">\' + TEMPLATE + "</div>"', "TEMPLATE");
  if (src.indexOf("TEMPLATE") < 0) { console.error("注入失败：找不到包裹语句"); process.exit(2); }
}

const OK = [], BAD = [];
function check(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log("  " + (cond ? "√" : "×") + " " + name + (detail !== undefined ? "　" + String(detail).slice(0, 110) : ""));
}

function makeEl(tag) {
  const el = {
    tagName: (tag || "div").toUpperCase(), innerHTML: "", textContent: "", style: {},
    scrollTop: 0, scrollHeight: 0, hidden: false, disabled: false, value: "", href: "", src: "",
    className: "", checked: false, attrs: {},
    classList: {
      _s: new Set(),
      add: function (c) { this._s.add(c); },
      remove: function (c) { this._s.delete(c); },
      contains: function (c) { return this._s.has(c); },
      toggle: function (c, on) {
        if (on === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); }
        else { on ? this._s.add(c) : this._s.delete(c); }
      }
    },
    setAttribute: function (k, v) { this.attrs[k] = v; },
    getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener: function () {}, appendChild: function () {}, focus: function () {},
    scrollIntoView: function () {}, querySelector: function () { return makeEl("div"); },
    querySelectorAll: function () { return []; }
  };
  return el;
}

// ---- 最小 DOM 垫片 ----
const byId = {};
const shell = makeEl("div");
const container = makeEl("div");
// 忠实一点：注入的 HTML 里没有 .ge-shell 时，querySelector 就该返回 null
// （否则"忘了包 .ge-shell"时，ROOT 仍会拿到假元素，下面第 ③ 条就抓不到了）
container.querySelector = function (sel) {
  if (sel === ".ge-shell" && container.innerHTML.indexOf('class="ge-shell"') >= 0) return shell;
  return null;
};
global.document = {
  body: { classList: { contains: function () { return false; } } },
  head: { appendChild: function () {} },
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { return (byId[id] = byId[id] || makeEl("div")); },
  querySelector: function (sel) { return sel === ".ge-shell" ? shell : null; },
  addEventListener: function () {}
};
global.window = global;
global.alert = function () {};
global.fetch = function () {
  return Promise.resolve({
    ok: true, status: 200,
    json: function () {
      return Promise.resolve({ ok: true, 字段数: 39, docx: "1.2.0", files: [], 示例: "x" });
    }
  });
};

console.log("=".repeat(62));
console.log("模块：", FILE, BREAK ? "（已注入缺陷：去掉 .ge-shell 包裹）" : "");

check("模块加载并暴露 mountGenUI", (function () {
  try { new Function(src)(); } catch (e) { console.log("   加载异常：" + e.message); return false; }
  return typeof window.mountGenUI === "function";
})());

let threw = null;
try { window.mountGenUI(container); } catch (e) { threw = e; }
check("挂载不抛异常", !threw, threw && threw.message);

const html = container.innerHTML;

console.log("[1] 变量作用域的根");
check("注入的 HTML 以 <div class=\"ge-shell\"> 开头",
  html.indexOf('<div class="ge-shell">') === 0, html.slice(0, 40));
check("只有一层 .ge-shell（不会定义两份变量）",
  html.split('<div class="ge-shell">').length - 1 === 1);
check("闭合完整（结尾是 </div>）", html.slice(-6) === "</div>", html.slice(-6));
check("挂了标记 data-ge-mounted", container.getAttribute("data-ge-mounted") === "1");

console.log("[2] $(\"id\") 引用的元素都必须真存在");
// genBody 是**宿主页给的挂载点**（独立页/问答页各自提供），不由模块注入，单独放行
const HOST_IDS = ["genBody"];
const ids = [];
const re = /\$\("([^"]+)"\)/g;
let m;
while ((m = re.exec(src))) { if (ids.indexOf(m[1]) < 0) ids.push(m[1]); }
const missing = ids.filter(function (id) {
  return HOST_IDS.indexOf(id) < 0 && html.indexOf('id="' + id + '"') < 0;
});
check("引用 " + ids.length + " 个 id（宿主提供的 " + HOST_IDS.join("/") + " 除外），全部存在",
  missing.length === 0, missing);

console.log("[3] 幂等与嵌入切换");
const before = container.innerHTML.length;
window.mountGenUI(container);
check("重复挂载不产生第二份", container.innerHTML.length === before);
check("setGenEmbedded 切在 .ge-shell 上（.ge-shell.ge-embedded 才选得中）", (function () {
  window.setGenEmbedded(true);
  const on = shell.classList.contains("ge-embedded");
  window.setGenEmbedded(false);
  return on && !shell.classList.contains("ge-embedded");
})());

console.log("[4] 关键区块都在");
["ge-left", "ge-right", "ge-log", "ge-prev", "ge-history", "ge-modal", "ge-known", "ge-say", "ge-gen"]
  .forEach(function (k) { check("含 " + k, html.indexOf(k) >= 0); });

console.log("=".repeat(62));
console.log("==== 通过 " + OK.length + " / 失败 " + BAD.length + " ====");
BAD.forEach(function (b) { console.log("   失败：" + b); });
process.exit(BAD.length ? 1 : 0);
