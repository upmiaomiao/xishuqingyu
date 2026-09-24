/* 独立页 /audit 的入口。
 *
 * 审核界面本身在 audit_ui.js（ES 模块，问答首页内嵌时用的是同一份），
 * 这里只负责「挂到哪个容器」和「是不是被 iframe 嵌入」这两件外壳的事。
 *
 * 2026-09-18 重构（阶段 3）：从 audit.html 的内联 <script> 抽出。
 */
import { mountAuditUI } from './audit_ui.js';

if (/[?&]embed=1/.test(location.search)) {
  document.body.classList.add('au-embed');
}
mountAuditUI(document.getElementById('auditRoot'));
