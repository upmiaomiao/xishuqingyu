#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把两份标准的「编者按」从语料正文里剥出来，另存为工作记录。

为什么剥：
  2026-09-21 实测——GB 18485 入语料后，问「生活垃圾焚烧炉的技术性能要求」时，
  检索到的不是真正的表 1 块（含 850℃／≥2 秒／≤5%），而是文末「## 待核对」和
  「关于限值的说明」这两段编者按：它们把表 1/表 4/850/热灼减率/0.1 ng 等词
  全堆在一起，重排分最高，反而把真条款挤掉，模型据此回答「材料未提供该指标」。
  语料应当只装权威正文；核对过程留痕放到工作记录里。

产物：
  _工作记录/2026-09-21-标准本体核对记录.md    ← 剥出来的编者按 + 来源清单（留痕）
  两个标准 md 就地更新（去掉编者按）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
STD = WS / "_中间产物" / "待入库标准"
REC = WS / "_工作记录" / "2026-09-21-标准本体核对记录.md"

FILES = ["GB 18485-2014 生活垃圾焚烧污染控制标准.md",
         "GB 18484-2020 危险废物焚烧污染控制标准.md"]
# 要剥掉的段落特征
CUT_HEAD = re.compile(r"^##\s*待核对\s*$", re.M)
CUT_CALLOUT = re.compile(r"^\*\*关于限值的说明（重要）：\*\*.*?(?=\n##\s|\n\*\*|\Z)", re.M | re.S)


def main() -> int:
    rec_parts = [
        "# 标准本体核对记录（GB 18485-2014 / GB 18484-2020）\n",
        "\n> 2026-09-21 由子代理取正文并交叉核对，本文件保存**从语料正文里剥离的编者按**"
        "（待核对清单、关于限值的说明）。\n"
        "> 剥离原因：这些编者按关键词密度高于标准条款本身，入库后会挤掉真正的表 1／表 4 块，"
        "实测导致「生活垃圾焚烧炉技术性能要求」一题答成「材料未提供」（详见 "
        "`_工作记录/探标准_换语料前.json` 与 `探标准_换语料后.json`）。\n",
    ]
    for name in FILES:
        p = STD / name
        text = p.read_text(encoding="utf-8")
        before = len(text)

        # 1) 「## 待核对」到文末
        m = CUT_HEAD.search(text)
        cut_tail = ""
        if m:
            cut_tail = text[m.start():]
            text = text[:m.start()].rstrip() + "\n"

        # 2) 「关于限值的说明（重要）：」整段
        cut_call = ""
        m2 = CUT_CALLOUT.search(text)
        if m2:
            cut_call = m2.group(0)
            text = text[:m2.start()] + text[m2.end():]
            text = re.sub(r"\n{3,}", "\n\n", text)

        p.write_text(text, encoding="utf-8")
        rec_parts.append(f"\n\n---\n\n## {name}\n")
        if cut_call:
            rec_parts.append("\n### 剥离：关于限值的说明（重要）\n\n" + cut_call.strip() + "\n")
        if cut_tail:
            rec_parts.append("\n### 剥离：待核对\n\n" + cut_tail.split("\n", 1)[1].strip() + "\n")
        print(f"{name}：{before} → {len(text)} 字节"
              f"（剥离 关于限值的说明 {len(cut_call)} 字符、待核对 {len(cut_tail)} 字符）")

    REC.write_text("".join(rec_parts), encoding="utf-8")
    print(f"\n编者按留痕 → {REC.relative_to(WS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
