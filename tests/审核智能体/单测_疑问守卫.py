#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缺陷注入：验证「疑问/不确定守卫」真的挡住了误判，且没把明确回答误杀。

背景（真实事故）：报告里写「废水去向未抽到（无法判断是否直排）」，抽取层的 True 规则
读到"废水…直排"，判成"本项目新增工业废水直排"，最终报**存在问题** ——
而项目铁律是"缺事实只判疑似，绝不判存在问题"。

本脚本用**假报告对象**直接喂 `derive_special_inputs`，不依赖任何 PDF：
  ① 注入"无法判断是否直排" → 必须**推不出**结论（value is None）
  ② 注入"是否直排：否"       → 必须推出 False（守卫不能把明确回答误杀）
  ③ 注入"废水直接排入环境"   → 必须推出 True（正常断言仍要能识别）
  ④ 注入"废水非直排"         → 必须推出 False（原有的否定规则不能回归）

用法：python 单测_疑问守卫.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_ROOT = os.path.dirname(HERE)                         # _脚本代码/审核智能体
sys.path.insert(0, AUDIT_ROOT)

from audit.extract import derive_special_inputs           # noqa: E402

OK, BAD = [], []


class FakeRep:
    """最小可用的假报告：search 按正则在整个文本里找，返回页码与片段。"""

    def __init__(self, text: str):
        self.text = text

    def search(self, pattern, max_hits=1, ctx=80):
        import re
        out = []
        for m in re.finditer(pattern, self.text):
            a = max(0, m.start() - ctx // 2)
            out.append({"page": 1, "mark": None, "snippet": self.text[a:m.end() + ctx // 2]})
            if len(out) >= max_hits:
                break
        return out


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:100]) if detail else ""))


def val_of(text):
    r = derive_special_inputs(FakeRep(text))
    return r["废水是否直排"]


def main() -> int:
    print("=" * 60)
    print("[1] 不确定措辞不得当成事实断言")
    for t in ("地表水专项评价：废水去向未抽到（无法判断是否直排）。",
              "本项目废水是否直排？尚不明确。",
              "废水去向待核实，需人工确认。",
              "废水是否直排无法确定。"):
        v = val_of(t)
        check("「%s」→ 推不出结论" % t[:22], v is None or v.get("value") is None,
              None if v is None else v.get("value"))

    print("[2] 明确回答仍要能识别（守卫不能误杀）")
    for t, want in (("本项目废水是否直排：否。", False),
                    ("废水经沉淀后全部回用，不外排。", False),
                    ("生活污水排入市政污水处理厂。", False),
                    ("本项目生产废水直接排入厂区南侧沟渠。", True)):
        v = val_of(t)
        check("「%s」→ %s" % (t[:22], want), v is not None and v.get("value") is want,
              None if v is None else v.get("value"))

    print("[3] 判据层的理由措辞不得再触发自身抽取规则")
    from audit import criteria
    import inspect
    src = inspect.getsource(criteria)
    check("criteria 里没有「无法判断是否直排」这种句式", "无法判断是否直排" not in src)

    print("=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())