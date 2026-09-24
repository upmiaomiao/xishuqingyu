#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本清洗单测：公式必须"翻译"成可读数值，垃圾必须清掉。

关键一条是**反向自测**：先用旧实现的清洗逻辑证明"数值真的会被删掉"，
再用新实现证明它被保住了 —— 没有这个反向断言，测试可能只是碰巧通过。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

SRC = Path(r"D:\项目\中节能\0911训练\服务器会话\xishu_site\xishu_pipeline\textclean.py")
spec = importlib.util.spec_from_file_location("tc", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

ok = fail = 0
def say(cond: bool, msg: str) -> None:
    global ok, fail
    if cond:
        ok += 1; print(f"  ✅ {msg}")
    else:
        fail += 1; print(f"  ❌ {msg}")

def old_clean(text: str) -> str:
    """旧实现（线上 2026-09-19 之前）：$...$ 整段删掉。"""
    out = re.sub(r"\$[^$\n]{1,160}\$", " ", text)
    out = re.sub(r"\\[a-zA-Z]{2,}", " ", out)
    out = re.sub(r"\$\s*\([^)]{0,8}\)\s*\$", " ", out)
    out = re.sub(r"[（(]\s*[）)]", "", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()

GB = ("5.2.1 当天然基础层饱和渗透系数不大于$1.0{\\times}10^{-5}\\,\\mathrm{cm/s}$，"
      "且厚度不小于$0.75~\\mathrm{m}$时，可以采用天然基础层作为防渗衬层。")

print("===== ① 反向自测：旧实现确实会把数值删掉 =====")
old_out = old_clean(GB)
say("1.0" not in old_out, "旧实现输出里已经没有 1.0（这就是线上答『数值缺失』的根因）")
say("10^{-5}" not in old_out and "cm/s" not in old_out, "旧实现把单位 cm/s 也删掉了")
print(f"     旧实现输出：{old_out[:90]}")

print("\n===== ② 新实现：数值、单位、上标都要保住 =====")
new_out = m.clean_retrieved_text(GB)
print(f"     新实现输出：{new_out[:150]}")
say("1.0×10⁻⁵" in new_out, "保住上标数值 1.0×10⁻⁵（不是被拉平成 10-5）")
say("cm/s" in new_out, "保住单位 cm/s")
say("0.75" in new_out and re.search(r"0\.75\s*m\b", new_out) is not None, "保住 0.75 m")
say("$" not in new_out, "没有残留的 $")
say("\\" not in new_out, "没有残留的反斜杠命令")

print("\n===== ③ 其他常见形态 =====")
cases = [
    ("有机质含量小于$2\\%$（煤矸石除外）", ["2%", "煤矸石"], "%"),
    ("单位：$\\mathrm{mg/m}^{3}$（二噁英类除外）", ["mg/m³"], "上标数字"),
    ("渗透系数不应大于$1.0\\!\\times\\!10^{\\cdot7}\\,\\mathrm{cm/s}$", ["1.0×10⁻⁷", "cm/s"], "点号上标要还原成负号"),
    ("浓度限值$0.1\\,\\mathrm{ng\\ TEQ/m^{3}}$", ["0.1", "ng TEQ/m³"], "带空格的单位"),
    ("$\\mathrm{SO_{2}}$、$\\mathrm{NO_{x}}$ 排放", ["SO2", "NOx"], "化学式下标"),
    ("排放口6个（）已完成", ["排放口6个", "已完成"], "空括号清理"),
    ("$\\quad$", [], "纯空白公式不应留下 $"),
]
for src, must, why in cases:
    got = m.clean_retrieved_text(src)
    hit = all(x in got for x in must)
    say(hit and "$" not in got and "\\" not in got, f"{why}：「{src[:34]}」→「{got[:44]}」")

print("\n===== ④ 反向：没有公式的正文必须原样保留（不许误伤）=====")
plains = [
    "该项目位于工业园区内，主要污染物为颗粒物、二氧化硫和氮氧化物。",
    "环境影响报告书应当包括建设项目概况、周围环境现状、环境影响预测等内容。",
    "排污许可证有效期为5年。需要延续的，应当在有效期届满60日前提出申请。",
    "河北地方标准 DB 13/ 2169-2018 规定了钢铁工业大气污染物超低排放限值。",
]
for p in plains:
    got = m.clean_retrieved_text(p)
    say(got == p, f"原文保留：{p[:30]}…")

print("\n===== ⑤ 反向：普通文本里的数字一个都不能少 =====")
for s in plains:
    n_in = len(re.findall(r"\d", s))
    n_out = len(re.findall(r"\d", m.clean_retrieved_text(s)))
    say(n_in == n_out, f"数字个数不变（{n_in} → {n_out}）：{s[:26]}…")

print(f"\n==== 通过 {ok} / 失败 {fail} ====")
sys.exit(1 if fail else 0)
