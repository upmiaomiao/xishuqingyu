#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""重新生成"与叙述缓存的单测（**不调真模型**，确定性）。

要证的四件事：
  ① 默认路径：同输入命中缓存 → 不再请求模型（这就是"点了很快就出报告"的原因）；
  ② 默认路径温度 = 0 → 同输入必同输出（可复现，不是预设）；
  ③ fresh=True（用户点"重新生成"）：跳过缓存、温度抬到 0.6 → 措辞会变；
  ④ fresh **不写缓存** → 不会把确定性的那一份基线覆盖掉。

用法：python 单测_重生成.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                       # 报告生成/
ROOT = os.path.dirname(BASE)                       # _脚本代码/
sys.path.insert(0, BASE)
# audit 包的位置：服务器上是 AUDIT_HOME（/data/eia_audit），本地是同级目录 _脚本代码/审核智能体。
# 第一版写死了本地相对路径，服务器上就 ModuleNotFoundError。
_audit = os.environ.get("AUDIT_HOME") or os.path.join(ROOT, "审核智能体")
sys.path.insert(0, _audit)
os.environ.setdefault("GEN_HOME", BASE)
os.environ.setdefault("AUDIT_HOME", _audit)

import audit.llm as llm          # noqa: E402
from gen import narrate          # noqa: E402

OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:90]) if detail else ""))


def main() -> int:
    # 缓存目录放工作区内，并且**用普通 mkdir、不要用 tempfile.mkdtemp**：
    # 本沙箱里 mkdtemp 建出来的目录写入会 PermissionError（实测两次，普通 mkdir 就没事）。
    tmp = os.path.join(HERE, "_tmp_cache_重生成")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    narrate.CACHE_DIR = tmp                  # 别污染真缓存

    calls = []

    def fake_model(messages, max_tokens=700, temperature=0.0, **kw):
        calls.append({"temperature": temperature, "n": len(calls)})
        return ("第一版正文 [F1]" if len(calls) == 1 else "第二版正文（措辞不同）[F1]")

    orig = llm.call_model
    llm.call_model = fake_model
    try:
        facts = [{"id": "F1", "text": "总投资 1200 万元"}]

        print("=" * 64)
        print("[1] 默认路径：缓存 + 温度 0")
        a = narrate.call_cached("小节A", "指令", facts)
        check("首次会请求模型", len(calls) == 1)
        check("首次温度 = 0（确定性）", calls[0]["temperature"] == 0.0, calls[0])
        check("首次结果写进了缓存", len(os.listdir(tmp)) == 1)
        b = narrate.call_cached("小节A", "指令", facts)
        check("再调用命中缓存、不再请求模型", len(calls) == 1 and b == a)
        check("同输入同输出（可复现）", a == b, a)

        print("[2] fresh=True：跳过缓存、换一版")
        c = narrate.call_cached("小节A", "指令", facts, fresh=True)
        check("fresh 会重新请求模型", len(calls) == 2)
        check("fresh 温度抬到 0.6（措辞才会变）", calls[1]["temperature"] == 0.6, calls[1])
        check("fresh 拿到的是新一版", c != a, c)

        print("[3] fresh 不污染确定性基线")
        d = narrate.call_cached("小节A", "指令", facts)
        check("之后默认调用仍拿到原基线", d == a, d)
        check("缓存目录里仍只有 1 条（fresh 没写进去）", len(os.listdir(tmp)) == 1,
              os.listdir(tmp))

        print("[4] narrate() 会把「重新生成」标记带出去")
        n = narrate.narrate({"项目名称": "X"}, {"名录": {}, "专项": {}}, sections=[], fresh=True)
        check("结果里标了 重新生成=True", n.get("重新生成") is True, n.get("重新生成"))
        n2 = narrate.narrate({"项目名称": "X"}, {"名录": {}, "专项": {}}, sections=[])
        check("默认路径标 False", n2.get("重新生成") is False, n2.get("重新生成"))
    finally:
        llm.call_model = orig
        shutil.rmtree(tmp, ignore_errors=True)

    print("=" * 64)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())