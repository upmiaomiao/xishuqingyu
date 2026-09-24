/* 悉数清宇 · 问答主页脚本模块：store.js
 *
 * 会话存取（localStorage）、历史列表（置顶 / 项目分组 / 重命名 / 分享 / 删除）、总渲染。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 *
 * 2026-09-18 第二轮回改：加置顶、项目分组、重命名、分享（用户要求第 4、5 项）。
 */

import { state, esc, uid, current, STORE } from './util.js';
import { renderMessages, closeSidebar } from './message.js';
import { closeKnowledgeGraph } from './views.js';

/* ============================================================
 *  store.js
 * ============================================================ */

/* 折叠状态只活在内存里，不持久化 —— 它是"当前这一次浏览"的临时视图状态，
   存起来反而会让用户下次打开时纳闷"我的项目去哪了"。 */
const collapsedGroups = new Set();

export function load() {
  try {
    state.chats = JSON.parse(localStorage.getItem(STORE) || '[]');
  } catch {
    state.chats = [];
  }
  if (!Array.isArray(state.chats)) state.chats = [];
  /* 老数据没有 pinned / project 字段。这里**不**做一次性迁移写回，
     而是在读取处用 `!!c.pinned` / `c.project || ''` 兜底 ——
     迁移写回要动 localStorage，一旦中途失败会把历史写坏，风险不对等。 */
  if (!state.chats.length) newConversation(false);
  else state.activeId = state.chats[0].id;
  render();
}
export function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify(state.chats));
  } catch (e) {
    /* 配额满：丢掉历史里的图片缩略图再存一次，保证文字历史不丢 */ state.chats.forEach((c) =>
      (c.messages || []).forEach((m) => {
        delete m.image;
        delete m.vision;
      }),
    );
    try {
      localStorage.setItem(STORE, JSON.stringify(state.chats));
    } catch (e2) {}
  }
}
export function newConversation(doRender = true) {
  const c = { id: uid(), title: '新对话', created: Date.now(), updated: Date.now(), messages: [] };
  state.chats.unshift(c);
  state.activeId = c.id;
  save();
  if (doRender) {
    closeKnowledgeGraph();
    render();
  }
  closeSidebar();
}
export function selectChat(id) {
  state.activeId = id;
  closeKnowledgeGraph();
  render();
  closeSidebar();
}
export function deleteChat(id, e) {
  if (e) e.stopPropagation();
  const c = state.chats.find((x) => x.id === id);
  /* 删除会**永久丢掉整段对话**，而且是历史里唯一不可撤销的操作。
     原先点一下 × 就没了，没有二次确认。 */
  if (c && (c.messages || []).length && !confirm(`删除「${c.title}」？此操作不可撤销。`)) return;
  state.chats = state.chats.filter((x) => x.id !== id);
  if (!state.chats.length) newConversation(false);
  if (id === state.activeId) state.activeId = state.chats[0].id;
  save();
  render();
}

/* ------------------------------------------------------------
 * 置顶
 *
 * 排序规则：置顶优先，其次按 updated 倒序。
 * 排序在渲染时算，不改动 state.chats 的存储顺序 ——
 * 直接 sort 数组会让"取消置顶后回到原位"变成"回到最前面"，不符合预期。
 * ------------------------------------------------------------ */
export function togglePin(id, e) {
  if (e) e.stopPropagation();
  const c = state.chats.find((x) => x.id === id);
  if (!c) return;
  c.pinned = !c.pinned;
  save();
  render();
}

/* 会话列表的最终顺序。置顶的一组在前，组内都按最近更新排。 */
function ordered(chats) {
  return [...chats].sort((a, b) => {
    const pa = a.pinned ? 1 : 0,
      pb = b.pinned ? 1 : 0;
    if (pa !== pb) return pb - pa;
    return (b.updated || 0) - (a.updated || 0);
  });
}

/* ------------------------------------------------------------
 * 重命名
 *
 * 用行内 <input> 而不是 prompt()：prompt 是阻塞式的，样式不可控，
 * 而且某些浏览器会把它拦掉。行内编辑还能顺手看到原标题。
 * ------------------------------------------------------------ */
let renamingId = '';

export function renameChat(id, e) {
  if (e) e.stopPropagation();
  renamingId = id;
  render();
  const box = document.querySelector('.history-rename');
  if (box) {
    box.focus();
    box.select();
  }
}
export function commitRename(id, value) {
  const c = state.chats.find((x) => x.id === id);
  renamingId = '';
  const t = String(value || '').trim();
  if (c && t && t !== c.title) {
    c.title = t;
    save();
  }
  render();
}
export function cancelRename() {
  renamingId = '';
  render();
}
/* 行内输入框的键盘处理：Enter 提交、Esc 取消。
   失焦**不**提交 —— 用户按 Esc 之后紧接着的 blur 会把取消又变成提交。 */
export function renameKey(id, ev) {
  if (ev.key === 'Enter') {
    ev.preventDefault();
    commitRename(id, ev.target.value);
  } else if (ev.key === 'Escape') {
    ev.preventDefault();
    cancelRename();
  }
}

/* ------------------------------------------------------------
 * 项目分组
 * ------------------------------------------------------------ */
export function allProjects() {
  return [...new Set(state.chats.map((c) => c.project).filter(Boolean))].sort();
}
export function setProject(id, name) {
  const c = state.chats.find((x) => x.id === id);
  if (!c) return;
  const p = String(name || '').trim();
  if (p) c.project = p;
  else delete c.project; // 空串 = 未分组，直接删字段，别在数据里留 ""
  save();
  render();
}
export function toggleGroup(name) {
  if (collapsedGroups.has(name)) collapsedGroups.delete(name);
  else collapsedGroups.add(name);
  render();
}

/* ------------------------------------------------------------
 * 分享
 *
 * 对话只存在浏览器 localStorage 里，服务端没有这份数据，所以**做不出真正的分享链接**
 * —— 硬做一个 `#share=xxx` 的假链接，别人打开只会是空的。
 * 能做且真有用的是把对话导出成 Markdown：贴进群里、存进文档、发给同事都能用。
 * 因此这里只提供「复制」和「下载」两种，不假装有在线分享。
 * ------------------------------------------------------------ */
export function chatToMarkdown(c) {
  const lines = [`# ${c.title}`, '', `> 导出自悉数清宇大模型 · ${new Date().toLocaleString('zh-CN')}`, ''];
  for (const m of c.messages || []) {
    if (m.role === 'user') {
      lines.push('## 我', '', m.image ? '（含上传图片）' : '', m.content || '', '');
    } else {
      lines.push('## 悉数清宇', '', m.content || '', '');
      if (m.sources && m.sources.length) {
        lines.push('### 引用资料', '');
        for (const s of m.sources) {
          lines.push(`- [${s.index}] ${s.title || ''}${s.standard_id ? '（' + s.standard_id + '）' : ''}`);
        }
        lines.push('');
      }
    }
  }
  return lines.filter((x) => x !== '').join('\n').replace(/\n{3,}/g, '\n\n');
}
export function downloadChat(id) {
  const c = state.chats.find((x) => x.id === id);
  if (!c) return;
  const md = chatToMarkdown(c);
  const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = (c.title || '对话').replace(/[\\/:*?"<>|]/g, '_') + '.md';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('已下载 Markdown 文件');
}
export async function copyChat(id) {
  const c = state.chats.find((x) => x.id === id);
  if (!c) return;
  const md = chatToMarkdown(c);
  try {
    /* navigator.clipboard 只在 https 或 localhost 下可用。
       本站是 http://<内网 IP>:8011，属于"不安全上下文"，
       navigator.clipboard 很可能是 undefined —— 所以必须先判存在，
       否则 TypeError 会让整个菜单无声失败。 */
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(md);
      toast('已复制到剪贴板');
      return;
    }
    throw new Error('clipboard unavailable');
  } catch {
    /* 退路：老式 execCommand。已废弃但在这个内网 http 场景下是唯一能用的。 */
    try {
      const ta = document.createElement('textarea');
      ta.value = md;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand && document.execCommand('copy');
      ta.remove();
      toast(ok ? '已复制到剪贴板' : '复制失败，可改用「下载」');
    } catch {
      toast('复制失败，可改用「下载」');
    }
  }
}

/* 轻提示。侧栏里没有别的提示位，用一个临时浮层，1.8s 自动消失。 */
let toastTimer = 0;
function toast(msg) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('open');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('open'), 1800);
}

/* ------------------------------------------------------------
 * 行内菜单（⋯）
 *
 * 为什么不用一串平铺的图标：重命名 / 置顶 / 移入项目 / 分享 / 删除 是 5 个动作，
 * 全铺在 240px 宽的一行里会把标题挤没。收进一个菜单，行内只留「⋯」和「×」。
 * ------------------------------------------------------------ */
export function openRowMenu(id, ev) {
  if (ev) {
    ev.stopPropagation();
    ev.preventDefault();
  }
  closeRowMenu();
  const c = state.chats.find((x) => x.id === id);
  if (!c) return;
  const projects = allProjects();
  const items = [
    ['重命名', () => renameChat(id)],
    [c.pinned ? '取消置顶' : '置顶', () => togglePin(id)],
    ['移入项目…', () => openProjectPicker(id)],
    ['复制为 Markdown', () => copyChat(id)],
    ['下载为 .md 文件', () => downloadChat(id)],
    ['删除', () => deleteChat(id), 'danger'],
  ];
  if (projects.length) items.splice(3, 0, ['移出项目', () => setProject(id, '')]);

  const menu = document.createElement('div');
  menu.className = 'row-menu';
  menu.id = 'rowMenu';
  menu.innerHTML = items
    .map(([label, , kind], i) => `<button class="row-menu-item${kind ? ' ' + kind : ''}" data-i="${i}">${esc(label)}</button>`)
    .join('');
  menu.addEventListener('click', (e2) => {
    const b = e2.target.closest('.row-menu-item');
    if (!b) return;
    e2.stopPropagation();
    closeRowMenu();
    const fn = items[Number(b.dataset.i)][1];
    if (fn) fn();
  });

  // 定位：贴在触发按钮的下方。用 fixed + 视口坐标，避开侧栏的 overflow:auto 裁剪。
  const r = ev && ev.currentTarget ? ev.currentTarget.getBoundingClientRect() : { left: 20, bottom: 60 };
  menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 180)) + 'px';
  menu.style.top = Math.min(r.bottom + 4, window.innerHeight - 8 - items.length * 32) + 'px';
  document.body.appendChild(menu);
  /* 外部点击关闭。用 setTimeout(0) 注册：否则注册的这一次点击事件本身
     （正在冒泡中的那一发）会立刻触发关闭，菜单一闪就没。 */
  setTimeout(() => {
    document.addEventListener('click', closeRowMenu, { once: true });
    document.addEventListener('keydown', escCloseMenu, { once: true });
  }, 0);
}
function escCloseMenu(e) {
  if (e.key === 'Escape') closeRowMenu();
}
export function closeRowMenu() {
  const m = document.getElementById('rowMenu');
  if (m) m.remove();
  const p = document.getElementById('projPicker');
  if (p) p.remove();
}

/* 项目选择器：列出已有项目 + 新建 + 未分组。 */
function openProjectPicker(id) {
  closeRowMenu();
  const projects = allProjects();
  const cur = (state.chats.find((x) => x.id === id) || {}).project || '';
  const box = document.createElement('div');
  box.className = 'row-menu';
  box.id = 'projPicker';
  box.innerHTML =
    `<div class="row-menu-title">移入项目</div>` +
    projects
      .map(
        (p) =>
          `<button class="row-menu-item${p === cur ? ' on' : ''}" data-p="${esc(p)}">${p === cur ? '✓ ' : ''}${esc(p)}</button>`,
      )
      .join('') +
    `<button class="row-menu-item" data-new="1">＋ 新建项目…</button>` +
    (cur ? `<button class="row-menu-item" data-p="">移出项目（未分组）</button>` : '');
  box.addEventListener('click', (e) => {
    const b = e.target.closest('.row-menu-item');
    if (!b) return;
    e.stopPropagation();
    if (b.dataset.new) {
      const name = prompt('新建项目名称：');
      if (name && name.trim()) setProject(id, name);
      else closeRowMenu();
      return;
    }
    setProject(id, b.dataset.p || '');
  });
  box.style.left = '16px';
  box.style.top = '120px';
  document.body.appendChild(box);
  setTimeout(() => {
    document.addEventListener('click', closeRowMenu, { once: true });
    document.addEventListener('keydown', escCloseMenu, { once: true });
  }, 0);
}

/* ------------------------------------------------------------
 * 历史列表渲染
 *
 * 分组顺序：置顶 → 各项目（按名称）→ 未分组。
 * 空组不渲染 —— 否则侧栏会出现一堆只有标题没内容的空壳。
 * ------------------------------------------------------------ */
function rowHtml(c) {
  const active = c.id === state.activeId ? ' active' : '';
  const pinned = c.pinned ? ' pinned' : '';
  if (c.id === renamingId) {
    return (
      `<div class="history-row${active}${pinned}">` +
      `<input class="history-rename" value="${esc(c.title)}" ` +
      `onkeydown="renameKey('${c.id}',event)" onblur="cancelRename()">` +
      `</div>`
    );
  }
  return (
    `<div class="history-row${active}${pinned}">` +
    (c.pinned ? `<span class="pin-mark" title="已置顶">★</span>` : '') +
    `<button class="history-name" onclick="selectChat('${c.id}')" title="${esc(c.title)}">${esc(c.title)}</button>` +
    `<button class="row-more" title="更多操作" onclick="openRowMenu('${c.id}',event)">⋯</button>` +
    `<button class="delete-chat" title="删除" onclick="deleteChat('${c.id}',event)">×</button>` +
    `</div>`
  );
}
function groupHtml(name, chats, collapsible) {
  const key = name || '';
  const isCollapsed = collapsedGroups.has(key);
  const head = collapsible
    ? `<div class="history-group" onclick="toggleGroup('${esc(key)}')">` +
      `<span class="history-group-arrow">${isCollapsed ? '▸' : '▾'}</span>` +
      `<span class="history-group-name">${esc(name || '未分组')}</span>` +
      `<span class="history-group-count">${chats.length}</span></div>`
    : '';
  if (collapsible && isCollapsed) return head;
  return head + ordered(chats).map(rowHtml).join('');
}
function renderHistory() {
  const chats = state.chats;
  const pinned = chats.filter((c) => c.pinned);
  const rest = chats.filter((c) => !c.pinned);
  const projects = [...new Set(rest.map((c) => c.project).filter(Boolean))].sort();
  const ungrouped = rest.filter((c) => !c.project);

  let html = '';
  if (pinned.length) html += groupHtml('置顶', pinned, false);
  for (const p of projects) html += groupHtml(p, rest.filter((c) => c.project === p), true);
  /* 只有一个分组时不必再加一层"未分组"标题 —— 那是纯噪音。 */
  const showUngroupedHead = projects.length > 0;
  html += groupHtml('未分组', ungrouped, showUngroupedHead);

  document.getElementById('history').innerHTML = html;
}
export function render() {
  renderHistory();
  renderMessages();
}
