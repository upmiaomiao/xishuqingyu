#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给两份新标准的限值表各加一段「逐项表述」——文字由表格自动生成，不手抄，避免数字错。

为什么加（2026-09-21 实测证据，见 _工作记录/诊断表块排名 输出）：
  GB 18484-2020 表 3 的完整块（775 字，含全部 14 项限值）在向量召回里排第 8，
  但重排把它压到 72 条中的第 28（rr=0.477）；排第 1（0.999）的反而是环评报告里
  用文字复述同一组限值的块。重排模型对管道表格（| 序号 | 污染物 | … |）打分偏低，
  于是问「重金属、二噁英类限值是多少」时，标准本体拼不过报告的转述。
  对策：保留原表的同时，紧挨着给一段由表格逐行生成的文字表述（数值同表），
  让「标准本体 + 文字化数值」也能被重排看见。

用法：python 加表文字表述.py            # 直接改（先备份到 _原文备份/）
      python 加表文字表述.py --dry-run  # 只看生成结果
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
STD = WS / "_中间产物" / "待入库标准"
BAK = STD / "_原文备份"
DRY = "--dry-run" in sys.argv

# 每份文件里要处理的表：caption 关键字 → 表号
TARGETS = {
    "GB 18485-2014 生活垃圾焚烧污染控制标准.md": ["表 1", "表 4", "表 5"],
    "GB 18484-2020 危险废物焚烧污染控制标准.md": ["表 1", "表 3"],
}
HEIGHT_COLS = ("烟囱最低允许高度（米）", "排气筒最低允许高度（m）")
CAP_COLS = ("焚烧处理能力（吨/日）", "焚烧处理能力（kg/h）")


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def find_table(lines: list[str], cap_kw: str) -> tuple[int, int]:
    """找到 caption 行与其后第一张表，返回 (caption 行号, 表结束行号 不含)"""
    for i, ln in enumerate(lines):
        if ln.strip().startswith("**") and cap_kw in ln and "表" in ln:
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("|"):
                j += 1
            if j >= len(lines):
                continue
            k = j
            while k < len(lines) and lines[k].strip().startswith("|"):
                k += 1
            return i, k
    return -1, -1


def prose_from_table(rows: list[list[str]], cap: str, unit_hint: str = "") -> str:
    """把表逐行拼成一句话；同项目的多行合并为『取值时间 值』。"""
    head, body = rows[0], [r for r in rows[1:] if any(c for c in r)]
    col = {name: idx for idx, name in enumerate(head)}

    def get(row: list[str], *names: str) -> str:
        for n in names:
            if n in col and col[n] < len(row):
                v = row[col[n]]
                if v and v != "—":
                    return v
        return ""

    # 第一列是「焚烧处理能力」这类分档表：标签=第一列，数值=其余列里唯一的那列
    cap_col = next((c for c in CAP_COLS if c in col), None)
    clauses: list[str] = []
    for r in body:
        if cap_col:
            others = [c for c in head if c not in (cap_col, "取值时间")]
            label = get(r, cap_col)
            m = re.search(r"（(.+?)）", cap_col)
            if label and m:
                label += f" {m.group(1)}"
            val = get(r, others[0]) if others else ""
            unit = ""
            if others and "米" in others[0]:
                unit = "米"
            elif others and re.search(r"（(m|m3|m³)）", others[0]):
                unit = "m"
            when = get(r, "取值时间")
        else:
            label = get(r, "污染物项目", "项目")
            # 表头形如「序号 | 指标 | 限值」的，用第二列当标签
            if not label and len(head) > 1 and col.get("序号") == 0:
                label = get(r, head[1])
            val = get(r, "限值", "指标")
            # 标签自带单位的（如「二噁英类（ng TEQ/Nm³）」）不再补表头单位
            own_unit = re.search(r"（[^）]*?(?:mg|ng|μg|℃|%|TEQ|Nm³|m³|米|秒)[^）]*?）", label)
            unit = get(r, "单位") or (
                unit_hint if val and not own_unit
                and re.fullmatch(r"[<>≥≤]?\s*[\d.]+", val) else "")
            when = get(r, "取值时间")
        if not (label and val):
            continue
        piece = f"{label} {val}" + (f" {unit}" if unit else "")
        if when:
            piece += f"（{when}）"
        # 同项目相邻行合并（如颗粒物的 1 小时均值 / 24 小时均值）
        if clauses and clauses[-1].startswith(label + " "):
            clauses[-1] = clauses[-1] + "、" + piece[len(label) + 1:]
        else:
            clauses.append(piece)
    return f"{cap} 的数值逐项表述（与下表一致）：" + "；".join(clauses) + "。"


def main() -> int:
    BAK.mkdir(exist_ok=True)
    for name, caps in TARGETS.items():
        p = STD / name
        lines = p.read_text(encoding="utf-8").split("\n")
        inserts: list[tuple[int, str]] = []
        for kw in caps:
            i, k = find_table(lines, kw)
            if i < 0:
                print(f"  ⚠ {name}：没找到 {kw} 的表")
                continue
            rows = [split_row(x) for x in lines[i + 1: k]
                    if x.strip().startswith("|") and not set(x.strip()) <= set("|-: ")]
            if len(rows) < 2:
                print(f"  ⚠ {name}：{kw} 表解析异常")
                continue
            cap = re.sub(r"\*\*|（.*?）|\s+$", "", lines[i]).strip()
            # caption 与表格之间可能有「单位：mg/m³」这类行
            hint = ""
            for x in lines[i + 1: k]:
                m = re.match(r"^单位[：:]\s*(.+?)\s*$", x.strip())
                if m:
                    hint = m.group(1)
                    break
            text = prose_from_table(rows, cap, hint)
            inserts.append((i, text))
            print(f"\n【{name} · {kw}】caption@L{i} 表行 {i + 1}~{k}，解析出 {len(rows)} 行")
            print(f"  表头：{rows[0]}")
            if len(rows) < 3:
                print(f"  前两行：{rows[1:3]}")
            print(f"  → {text}")

        if DRY or not inserts:
            continue
        shutil.copy2(p, BAK / name)
        for i, text in sorted(inserts, reverse=True):
            lines.insert(i, text + "\n")
        p.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  ✅ {name}：插入 {len(inserts)} 段（原文备份在 _原文备份/）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
