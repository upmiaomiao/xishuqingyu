/* 悉数清宇 · 问答主页脚本模块：util.js
 *
 * 共享状态与工具函数。所有模块都从这里取，所以它不能反过来依赖任何模块。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 */

/* ============================================================
 *  util.js
 * ============================================================ */


export const STORE = 'xishu_qingyu_chats_v2';
export const state = { chats: [], activeId: '' };
export const esc = (s) =>
  String(s ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
export function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
export function current() {
  return state.chats.find((x) => x.id === state.activeId);
}
/* 耗时统一显示成一位小数。
 * 服务端给的是 round(..., 3)，直接显示就成了「6.672s」—— 又长又假精确
 * （模型耗时本来就没有毫秒级意义，三个小数位只是把内部精度漏到了界面上）。
 * 在渲染时格式化而不是在存储时四舍五入：这样**已经存在 localStorage 里的历史记录**
 * 也会跟着变整齐，不用等用户重新提问。 */
export const fmtSecs = (v) => (v ? (Math.round(Number(v) * 10) / 10).toFixed(1) + 's' : '');

/* ============================================================
 *  欢迎页示例问题的轮换池
 *
 *  欢迎页在 message.js 里同步渲染，题目却来自题库 JSON（questions.js 负责加载）。
 *  如果 message.js 直接 import questions.js，就会绕回去形成循环
 *  （message → questions → ask → message）。util.js 是依赖图最底层、谁都能引，
 *  于是让它当这个"信箱"：questions.js 投递，message.js 取用。
 *  池子为空（题库还没到位／读失败）时，message.js 退回家写的那三个示例问题。
 * ============================================================ */

export const welcomeBank = { simple: [], total: 0 };
let cursor = 0;          // 当前窗口在池子里的起点
let lastKey = null;      // 上次是按哪个会话取的（换会话就顺延一组）

export function registerWelcomeBank(simple, total) {
  welcomeBank.simple = Array.isArray(simple) ? simple : [];
  welcomeBank.total = Number(total) || 0;
  cursor = 0;
  lastKey = null;
}

function windowOf(n) {
  const pool = welcomeBank.simple;
  const out = [];
  for (let i = 0; i < Math.min(n, pool.length); i += 1) {
    out.push(pool[(cursor + i) % pool.length]);
  }
  return out;
}

/* 取当前该显示的那 n 条。同一个会话（key 相同）取到的是同一组 —— 否则消息区随便重渲染一次，
 * 问题就在用户眼皮底下换掉了；换一个新会话才顺延下一组。 */
export function pickWelcomeExamples(n, key) {
  if (!welcomeBank.simple.length) return [];
  const k = String(key == null ? '' : key);
  if (lastKey !== null && k !== lastKey) cursor = (cursor + n) % welcomeBank.simple.length;
  lastKey = k;
  return windowOf(n);
}

/* 定时轮换用：直接顺延一组（不看会话）。首页那个 10 秒的定时器走这里 ——
 * 走 pickWelcomeExamples 的话 key 没变就不会动。 */
export function rotateWelcomeExamples(n) {
  if (!welcomeBank.simple.length) return [];
  cursor = (cursor + n) % welcomeBank.simple.length;
  return windowOf(n);
}
