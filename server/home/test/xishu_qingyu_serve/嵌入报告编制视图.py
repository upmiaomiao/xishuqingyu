#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「报告编制」**嵌进问答页**（像「报告审核」那样切视图，不跳转）。

照审核页现成的做法接线，不另发明一套：
    .au-view{display:none;flex:1;min-height:0;background:var(--page)}
    .au-view.open{display:flex;flex-direction:column}
    #auditBody{flex:1;min-height:0;display:flex;flex-direction:column}
    <section class="au-view" id="auditView"><div id="auditBody"></div></section>
    openAudit() → 隐藏聊天区、给视图加 .open、设标题、ensureAuditUI() 后再 mountAuditUI(容器)

本脚本做四件事（幂等、改前备份、打印改动上下文）：
  ① 侧栏按钮由 window.open('/gen') 改为 openGen()
  ② 追加 <section class="au-view" id="genView"><div id="genBody"></div></section>
  ③ 追加 #genBody 的高度规则（复用 .au-view 的显隐）
  ④ 追加 openGen/closeGen/ensureGenUI，并把 openAudit/openKnowledgeGraph/newConversation 包一层
     （互相切换时先关掉报告编制视图，避免两个视图叠着）

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 嵌入报告编制视图.py
"""
from __future__ import annotations

import os
import shutil
import sys
import time

SERVE = "/home/test/xishu_qingyu_serve"
INDEX = os.path.join(SERVE, "frontend", "index.html")
STAMP = time.strftime("%Y%m%d")

BTN_OLD = '<button class="new-chat kg-entry" onclick="window.open(\'/gen\',\'_blank\')">'
BTN_NEW = '<button class="new-chat kg-entry" onclick="openGen()">'
VIEW_ANCHOR = '<section class="au-view" id="auditView"><div id="auditBody"></div></section>'
VIEW_ADD = '<section class="au-view" id="genView"><div id="genBody"></div></section>'
CSS_ANCHOR = "#auditBody{flex:1;min-height:0;display:flex;flex-direction:column}"
CSS_ADD = ("#genBody{flex:1;min-height:0;display:flex;flex-direction:column}"
           "#genBody>.ge-shell{border-radius:0}")
JS_ANCHOR = "function closeAudit(){var v=document.getElementById('auditView');if(v){v.classList.remove('open')}}"
JS_ADD = """
/* ---------------- 报告编制视图（与报告审核同一套挂载方式） ---------------- */
function openGen(){closeKnowledgeGraph();closeAudit();
  document.getElementById('messages').style.display='none';
  document.querySelector('.composer-wrap').style.display='none';
  document.getElementById('genView').classList.add('open');
  document.getElementById('chatTitle').textContent='报告编制';
  document.getElementById('routePill').textContent='报告编制';
  closeSidebar();
  ensureGenUI(function(){
    window.mountGenUI(document.getElementById('genBody'));
    if(window.setGenEmbedded){window.setGenEmbedded(true)}
  });
}
function closeGen(){var v=document.getElementById('genView');if(v){v.classList.remove('open')}}
function ensureGenUI(cb){
  if(!document.getElementById('geCss')){var l=document.createElement('link');l.id='geCss';
    l.rel='stylesheet';l.href='/gen/static/gen_ui.css';document.head.appendChild(l)}
  if(window.mountGenUI){cb();return}
  var s=document.getElementById('geJs');
  if(s){s.addEventListener('load',cb);return}
  s=document.createElement('script');s.id='geJs';s.async=true;
  s.src='/gen/static/gen_ui.js';s.onload=cb;document.head.appendChild(s);
}
/* 切到别的视图时先收起报告编制，避免叠着 */
(function(){var f=window.openAudit;window.openAudit=function(){closeGen();return f.apply(this,arguments)};
  var g=window.openKnowledgeGraph;window.openKnowledgeGraph=function(){closeGen();return g.apply(this,arguments)};
  var n=window.newConversation;window.newConversation=function(){closeGen();return n.apply(this,arguments)}})();
"""


def backup(path: str, tag: str) -> str:
    b = "%s.bak_%s_%s" % (path, tag, STAMP)
    if not os.path.exists(b):
        shutil.copy2(path, b)
        print("  已备份 →", b)
    else:
        print("  备份已存在 →", b)
    return b


def show(text: str, needle: str, before=60, after=90, label=""):
    i = text.find(needle)
    if i < 0:
        print("    （找不到 %s）" % label)
        return
    print("    %s…%s…" % (label, text[max(0, i - before):i + len(needle) + after]
                          .replace("\n", " ⏎ ")))


def main() -> int:
    print("[报告编制] 嵌入问答页：", INDEX)
    with open(INDEX, encoding="utf-8") as f:
        text = f.read()
    if "id='genView'" in text or 'id="genView"' in text:
        print("  已嵌入（幂等跳过）")
        return 0

    if BTN_OLD not in text:
        print("  ✗ 找不到侧栏按钮锚点，拒绝改动")
        return 1
    if VIEW_ANCHOR not in text or CSS_ANCHOR not in text or JS_ANCHOR not in text:
        print("  ✗ 锚点不全（视图/样式/JS），拒绝改动")
        return 1
    backup(INDEX, "before_gen_embed")

    text = text.replace(BTN_OLD, BTN_NEW, 1)
    text = text.replace(VIEW_ANCHOR, VIEW_ANCHOR + VIEW_ADD, 1)
    text = text.replace(CSS_ANCHOR, CSS_ANCHOR + "\n" + CSS_ADD, 1)
    text = text.replace(JS_ANCHOR, JS_ANCHOR + JS_ADD, 1)
    with open(INDEX, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print("  ① 按钮：")
    show(text, "onclick=\"openGen()\"", 70, 40)
    print("  ② 视图容器：")
    show(text, VIEW_ADD, 40, 20)
    print("  ③ 样式：")
    show(text, "#genBody{flex:1", 10, 60)
    print("  ④ 脚本：")
    for k in ("function openGen()", "function closeGen()", "function ensureGenUI(cb)",
              "window.openAudit=function()"):
        print("     %-28s %s" % (k, k in text))
    print("  文件大小：%d → %d 字节" % (os.path.getsize(INDEX + ".bak_before_gen_embed_" + STAMP),
                                     os.path.getsize(INDEX)))
    print("完成。刷新首页即可看到「✎ 报告编制」在原页面内切换（不再跳转）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())