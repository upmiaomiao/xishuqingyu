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
