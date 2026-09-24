# -*- coding: utf-8 -*-
"""调试：枚举归一与"纳管"等价否定的实际行为（不调模型）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WS = HERE
while not os.path.isdir(os.path.join(WS, "_脚本代码")):
    WS = os.path.dirname(WS)
sys.path.insert(0, os.path.join(WS, "_脚本代码", "报告生成"))
os.environ.setdefault("GEN_HOME", os.path.join(WS, "_脚本代码", "报告生成"))

import json  # noqa: E402
from gen import intake  # noqa: E402
from gen import schema  # noqa: E402

print("=== normalize_enum 直接测 ===")
for v in ("这次是扩建", "技改", "扩建", "说不上来", "新建项目"):
    print("  %-10s -> %r" % (v, intake.normalize_enum(v, ["新建", "改建", "扩建", "技术改造"])))

print("\n=== schema 里 建设性质 的定义 ===")
f = next((x for x in schema.FIELDS if x.key == "建设性质"), None)
print("  ", f, "choices=", getattr(f, "choices", None), "type=", getattr(f, "type", None))

print("\n=== parse_description（假模型：建设性质=技改）===")
intake._model_json_cached = lambda system, user, max_tokens=1200: {
    "建设性质": {"值": "技改", "原文": "项目是技术改造"}}
r = intake.parse_description("我们公司要在临沂建一台锅炉，项目是技术改造。")
print("  采纳:", json.dumps(r.get("采纳"), ensure_ascii=False))
print("  丢弃:", json.dumps(r.get("丢弃"), ensure_ascii=False))

print("\n=== bool_ok 方向性检查（QUIV 等价否定）===")
cases = [
    (False, "本项目废水经厂内预处理后纳管排入园区污水处理厂", "是否新增工业废水直排"),
    (False, "本项目废水不纳管，经总排口直接排入厂外沟渠", "是否新增工业废水直排"),
    (False, "生产废水不外排", "是否新增工业废水直排"),
    (False, "锅炉配布袋除尘", "是否新增工业废水直排"),
    (True, "本项目废水直接排入厂外沟渠", "是否新增工业废水直排"),
]
for val, q, nm in cases:
    print("  bool_ok(%s, %-28s) -> %s" % (val, q[:26], intake.bool_ok(val, q, nm)))
