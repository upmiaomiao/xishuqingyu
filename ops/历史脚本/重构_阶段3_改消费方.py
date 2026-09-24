#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3（消费方）：把「往 head 插 <script src>」改成动态 import()，并整理两个宿主页。

为什么要改：gen_ui.js / audit_ui.js 现在是 ES 模块，传统 <script src> 一读到
export 语句就语法报错、整页白屏。必须换成 import()。

顺带修掉的两处不一致：
  · audit.html 有 2 段内联（<style> + <script>），而 gen.html 是纯外壳 —— 同一类页面两种做法；
  · 内联样式外置成 audit_page.css（页面外壳样式，不属于可挂载组件，所以不塞进 audit_ui.css）。
"""
from __future__ import annotations

import hashlib
import io
import re

FE = r"_中间产物/重构工作区/frontend"
ST = r"_中间产物/重构工作区/xishu_pipeline/static"


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def report(name, before, after):
    print("  %-18s %6d -> %6d 字节   md5 %s -> %s"
          % (name, len(before.encode()), len(after.encode()), md5(before)[:12], md5(after)[:12]))


# ============================================================ 1. views.js
p = FE + "/js/views.js"
src = io.open(p, encoding="utf-8").read()
marker = "export function openAudit() {"
assert src.count(marker) == 1
head = src[:src.index(marker)]

new_tail = '''export function openAudit() {
  closeKnowledgeGraph();
  document.getElementById('messages').style.display = 'none';
  document.querySelector('.composer-wrap').style.display = 'none';
  document.getElementById('auditView').classList.add('open');
  document.getElementById('chatTitle').textContent = '环评报告审核';
  document.getElementById('routePill').textContent = '报告审核';
  closeSidebar();
  ensureAuditUI(function (m) {
    m.mountAuditUI(document.getElementById('auditBody'));
  });
}
function closeAudit() {
  const v = document.getElementById('auditView');
  if (v) {
    v.classList.remove('open');
  }
}
/* ---------------- 报告编制视图（与报告审核同一套挂载方式） ---------------- */
export function openGen() {
  closeKnowledgeGraph();
  closeAudit();
  document.getElementById('messages').style.display = 'none';
  document.querySelector('.composer-wrap').style.display = 'none';
  document.getElementById('genView').classList.add('open');
  document.getElementById('chatTitle').textContent = '报告编制';
  document.getElementById('routePill').textContent = '报告编制';
  closeSidebar();
  ensureGenUI(function (m) {
    m.mountGenUI(document.getElementById('genBody'));
    m.setEmbedded(true);
  });
}
export function closeGen() {
  const v = document.getElementById('genView');
  if (v) {
    v.classList.remove('open');
  }
}

/* ============================================================
 *  两个子界面的**按需加载**
 *
 *  阶段 3 之前是往 <head> 里插一个 <script src>，靠 window.mountGenUI 通信。
 *  那两个文件现在是 ES 模块，传统 <script> 读到 export 就会语法报错、整页白屏，
 *  所以改成动态 import()。
 *
 *  好处：浏览器原生缓存模块，来回切视图不会重复请求；也不用再往 window 上挂东西。
 *  注意：CSS 仍是独立的 <link> —— 在模块里 import CSS 需要打包器，这套站点没有。
 * ============================================================ */
let genMod = null,
  genLoading = null;
let auditMod = null,
  auditLoading = null;

function loadCssOnce(id, href) {
  if (document.getElementById(id)) return;
  const l = document.createElement('link');
  l.id = id;
  l.rel = 'stylesheet';
  l.href = href;
  document.head.appendChild(l);
}

function ensureGenUI(cb) {
  loadCssOnce('geCss', '/gen/static/gen_ui.css');
  if (genMod) {
    cb(genMod);
    return;
  }
  genLoading = genLoading || import('/gen/static/gen_ui.js');
  genLoading
    .then(function (m) {
      genMod = m;
      cb(m);
    })
    .catch(function (e) {
      console.error('报告编制界面加载失败', e);
    });
}

/* 审核界面模块按需加载：没用过就不下载（不拖慢问答页首屏）。
   模块自身幂等（重复挂载返回同一个实例），所以来回切换不会重建界面、不丢审核结果。 */
function ensureAuditUI(cb) {
  loadCssOnce('auCss', '/audit/static/audit_ui.css');
  if (auditMod) {
    cb(auditMod);
    return;
  }
  auditLoading = auditLoading || import('/audit/static/audit_ui.js');
  auditLoading
    .then(function (m) {
      auditMod = m;
      cb(m);
    })
    .catch(function (e) {
      console.error('审核界面加载失败', e);
    });
}
'''
after = head + new_tail
report("js/views.js", src, after)
io.open(p, "w", encoding="utf-8", newline="\n").write(after)
assert "window.mountGenUI(" not in after and "window.mountAuditUI(" not in after, \
    "views.js 里还有对 window.mount* 的真实调用"
assert "createElement('script')" not in after and 'createElement("script")' not in after, \
    "views.js 里还有动态插 script 标签的代码"
print("     残留 window.mount*：0；残留 document.createElement('script')：0")

# ============================================================ 2. gen.html
p = FE + "/gen.html"
src = io.open(p, encoding="utf-8").read()
old = '<script src="/gen/static/gen_ui.js"></script>'
assert src.count(old) == 1
after = src.replace(old, '<script type="module" src="/gen/static/gen_ui.js"></script>', 1)
report("gen.html", src, after)
io.open(p, "w", encoding="utf-8", newline="\n").write(after)
print("     script 标签改为 type=module（模块自带 DOMContentLoaded 自动挂载）")

# ============================================================ 3. audit.html
p = FE + "/audit.html"
src = io.open(p, encoding="utf-8").read()
m = re.search(r"<style>(.*?)</style>\n?", src, re.S)
assert m, "audit.html 里找不到内联 <style>"
css_body = m.group(1)

# 3a. 内联样式 -> audit_page.css
css_header = """/* 独立页 /audit 的**外壳**样式（页头、embed 模式、根容器）。
 *
 * 为什么不并进 audit_ui.css：audit_ui.css 是可挂载组件的样式，问答首页内嵌时也会加载。
 * 而这里的东西只属于独立页外壳（比如 body.embed header），混进去会污染组件样式表。
 *
 * 2026-09-18 重构（阶段 3）：从 audit.html 的内联 <style> 抽出。
 * 起因：audit.html 有内联样式、gen.html 没有 —— 同一类页面两种做法。
 */
"""
css_out = css_header + css_body.strip() + "\n"
io.open(ST + "/audit_page.css", "w", encoding="utf-8", newline="\n").write(css_out)
print("  %-18s 新建 %6d 字节（从 audit.html 内联抽出）" % ("audit_page.css", len(css_out.encode())))

# 3b. audit_page.js
page_js = """/* 独立页 /audit 的入口。
 *
 * 审核界面本身在 audit_ui.js（ES 模块，问答首页内嵌时用的是同一份），
 * 这里只负责「挂到哪个容器」和「是不是被 iframe 嵌入」这两件外壳的事。
 *
 * 2026-09-18 重构（阶段 3）：从 audit.html 的内联 <script> 抽出。
 */
import { mountAuditUI } from './audit_ui.js';

if (/[?&]embed=1/.test(location.search)) {
  document.body.classList.add('embed');
}
mountAuditUI(document.getElementById('auditRoot'));
"""
io.open(ST + "/audit_page.js", "w", encoding="utf-8", newline="\n").write(page_js)
print("  %-18s 新建 %6d 字节" % ("audit_page.js", len(page_js.encode())))

# 3c. audit.html 重写
new_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>环评报告审核 · 悉数清宇</title>
<!-- 界面在 /audit/static/audit_ui.js（ES 模块）；本页只是外壳，
     问答首页内嵌时用的是同一份模块，逻辑不会走偏。 -->
<link rel="stylesheet" href="/audit/static/audit_ui.css">
<link rel="stylesheet" href="/audit/static/audit_page.css">
</head>
<body>
<header>
  <span>环评报告审核</span>
  <span class="sub">18 项审核项 · 结论可追溯到原文页码 · 判不出来的写「疑似」</span>
  <a href="/" target="_top">← 返回法规问答</a>
</header>
<div id="auditRoot"></div>
<script type="module" src="/audit/static/audit_page.js"></script>
</body>
</html>
"""
report("audit.html", src, new_html)
io.open(p, "w", encoding="utf-8", newline="\n").write(new_html)
print("     内联 <style> 与内联 <script> 均已外置；剩内联块 %d 个"
      % len(re.findall(r"<(?:style|script)(?![^>]*\bsrc=)[^>]*>[^<]", new_html)))

# ============================================================ 4. 汇总
print()
print("阶段 3 消费方改动完成。新增文件：")
for f in ("audit_page.css", "audit_page.js"):
    t = io.open(ST + "/" + f, encoding="utf-8").read()
    print("  %-18s %6d 字节  md5 %s" % (f, len(t.encode()), md5(t)[:12]))
