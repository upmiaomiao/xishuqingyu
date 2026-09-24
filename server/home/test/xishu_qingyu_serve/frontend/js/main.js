/* 悉数清宇 · 问答主页脚本模块：main.js
 *
 * 入口：绑定事件、把需要在 HTML 里 onclick 调用的函数暴露到 window、初始化。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 */

import {
  load, newConversation, selectChat, deleteChat,
  togglePin, renameChat, renameKey, commitRename, cancelRename,
  openRowMenu, closeRowMenu, toggleGroup, setProject, copyChat, downloadChat,
} from './store.js';
import { toggleSidebar, showCitation, applySidebarCollapse, toggleSidebarCollapse, openDoc, closeDoc } from './message.js';
import { ask, useExample } from './ask.js';
import { clearPendingImage, onPickImage, openImage } from './image.js';
import { initQuestionBank } from './questions.js';
import {
  searchKnowledgeGraph, pickKgMatch, kgZoom, kgDirectOnly, kgExpandLayer, kgResetView,
  openKgEntity, initKgSuggest,
} from './kg.js';
import { openKnowledgeGraph, openAudit, openGen, closeKnowledgeGraph, closeGen } from './views.js';

/* ============================================================
 *  main.js
 * ============================================================ */


const q = document.getElementById('q');
q.addEventListener('input', () => {
  q.style.height = 'auto';
  q.style.height = Math.min(q.scrollHeight, 180) + 'px';
});
q.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    // 2026-09-22 自查发现：中文输入法在候选框上按回车是"选词"，不是"发送"。
    // 少了这道判断，用户打"太湖流域"选词的那一下就会把半截拼音当问题发出去。
    //   isComposing：标准属性；keyCode 229：部分浏览器/输入法只给这个信号。
    if (e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    ask();
  }
});
load();
/* 侧栏收起状态要在首次渲染后就应用 —— 放在 load() 之后，
   因为 setSidebarCollapsed() 会去改 #sideToggle 的文字，而那个按钮
   在 HTML 里，不依赖 load()；但和 load() 一起做能保证首屏不闪一下再收起。 */
applySidebarCollapse();
/* 图谱推荐关键词面板的事件委托。挂一次即可 ——
   面板内容每次都是整块重渲染，用委托就不用跟着重新绑事件。 */
initKgSuggest();
/* 示例题库入口（输入框上方那条）。事件委托挂在 #qbPanel 上，
   所以不往 WINDOW_API 里加东西 —— HTML 里没有它的 onclick。 */
initQuestionBank();



/* ============================================================
 *  暴露到 window —— HTML 里的 onclick="..." 只能调到全局函数。
 *  这一份清单就是 HTML 与 JS 之间的**全部契约**，改 HTML 时对照这里。
 * ============================================================ */
const WINDOW_API = {
  // 侧栏与视图切换
  newConversation, selectChat, deleteChat, toggleSidebar,
  toggleSidebarCollapse,
  openKnowledgeGraph, closeKnowledgeGraph, openAudit, openGen,
  // 历史记录：置顶 / 重命名 / 项目分组 / 分享
  togglePin, renameChat, renameKey, commitRename, cancelRename,
  openRowMenu, closeRowMenu, toggleGroup, setProject, copyChat, downloadChat,
  // 图谱
  searchKnowledgeGraph, pickKgMatch, kgZoom, kgDirectOnly, kgExpandLayer, kgResetView,
  openKgEntity,
  // 提问
  ask, useExample,
  // 消息内交互
  showCitation, openImage,
  // 原文预览抽屉
  openDoc, closeDoc,
  // 图片
  onPickImage, clearPendingImage,
};
Object.assign(window, WINDOW_API);

/* 切到别的视图时先收起报告编制，避免叠着。
   原代码用一段 IIFE 猴补 window.openAudit / openKnowledgeGraph / newConversation，
   这里改成显式包装 —— 等价，但不用先挂到 window 再改 window。 */
const _openAudit = openAudit,
  _openKnowledgeGraph = openKnowledgeGraph,
  _newConversation = newConversation;
window.openAudit = () => {
  closeGen();
  _openAudit();
};
window.openKnowledgeGraph = () => {
  closeGen();
  _openKnowledgeGraph();
};
window.newConversation = () => {
  closeGen();
  _newConversation();
};
