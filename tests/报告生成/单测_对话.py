#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话式填报的单测：**不调真模型**，用假模型注入各种"坏输出"，验证代码侧的闸门。

为什么这么测：闸门（防编造）是这套东西的命门，必须**确定性**可复现地测，
而不是"跑一次真模型看着还行"。这里把 `intake._model_json` 换掉，注入：
  ① 编造值（用户没说）        ② 片段对不上（引的话不存在）
  ③ 片段真但值被攒过（项目名）④ 布尔乱填（拿"不新增河道取水"填"工业废水直排"）
  ⑤ key 漂移（「建设地点（建设地点）」）⑥ 数字单位换算（万元→元）
  ⑦ 模型返回非 JSON / 空对象  ⑧ 用户回答"不知道"

用法：python 单测_对话.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                      # 报告生成/
sys.path.insert(0, BASE)
os.environ.setdefault("GEN_HOME", BASE)

from gen import intake                            # noqa: E402
from gen import schema                            # noqa: E402

OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:100]) if detail else ""))


TEXT = ("我们公司要在临沂市兰山区汪沟镇建一台20吨/小时的生物质锅炉给生产线供蒸汽，"
        "项目是技术改造，总投资1200万元，其中环保投资85万元，用地面积3000平方米。"
        "锅炉配布袋除尘和双碱法脱硫，烟气走25米排气筒。厂界东北方向320米有个阳光村，"
        "大约120户480人。生产废水不外排，全部沉淀后回用于除尘，不新增河道取水。")


def with_fake(reply):
    """把模型换成固定返回，返回 parse_description 的结果。

    **必须连缓存一起换掉**：缓存键只看请求（system+user），假模型不改请求，
    第二个场景就会命中第一个场景的缓存 —— 本轮实测踩到，一堆断言失败全是这个原因。
    单测要的是确定性，直接绕过缓存。
    """
    orig_cached = intake._model_json_cached
    intake._model_json_cached = lambda system, user, max_tokens=1200: reply
    try:
        return intake.parse_description(TEXT)
    finally:
        intake._model_json_cached = orig_cached


def main() -> int:
    print("=" * 64)
    print("[1] 编造值必须被丢弃")
    r = with_fake({
        "项目名称": {"值": "兰山生物质供热站", "原文": "建一台20吨/小时的生物质锅炉"},   # 值不在片段里
        "建设地点": {"值": "临沂市兰山区汪沟镇", "原文": "在临沂市兰山区汪沟镇建一台20吨/小时的生物质锅炉"},
        "建设单位": {"值": "某公司", "原文": "我们公司"},                              # 不是已定义字段
    })
    check("编造的项目名称被丢弃", "项目名称" not in r["采纳"],
          [d["原因"] for d in r["丢弃"] if d["字段"] == "项目名称"])
    check("有依据的建设地点被采纳", r["采纳"].get("建设地点") == "临沂市兰山区汪沟镇")
    check("未定义字段被丢弃", any(d["字段"] == "建设单位" for d in r["丢弃"]))

    print("[2] 片段对不上必须被丢弃")
    r = with_fake({"建设地点": {"值": "临沂市兰山区汪沟镇", "原文": "在临沂市罗庄区建一台锅炉"}})
    check("引用了不存在的片段 → 丢弃", "建设地点" not in r["采纳"],
          [d["原因"] for d in r["丢弃"]])
    r = with_fake({"建设地点": {"值": "临沂市兰山区汪沟镇"}})          # 没有片段，但值确实在原话里
    check("没有片段但值在原话里 → 采纳并记明（降级为字面比对）",
          r["采纳"].get("建设地点") == "临沂市兰山区汪沟镇",
          [d["原因"] for d in r["丢弃"]])
    r = with_fake({"建设地点": {"值": "临沂市罗庄区"}})                # 没有片段，值也不在原话里
    check("没有片段且值不在原话 → 丢弃", "建设地点" not in r["采纳"],
          [d["原因"] for d in r["丢弃"]])

    print("[3] 布尔字段：拿不相干的话填是非必须被拒")
    r = with_fake({
        "是否新增工业废水直排": {"值": True, "原文": "不新增河道取水"},
        "是否新增河道取水": {"值": False, "原文": "不新增河道取水"},
    })
    check("「不新增河道取水」不能填成工业废水直排", "是否新增工业废水直排" not in r["采纳"],
          [d["原因"] for d in r["丢弃"]])
    check("同一句可以填「是否新增河道取水=false」", r["采纳"].get("是否新增河道取水") is False)
    r = with_fake({"是否新增工业废水直排": {"值": False, "原文": "生产废水不外排"}})
    check("「生产废水不外排」可填工业废水直排=false", r["采纳"].get("是否新增工业废水直排") is False)
    r = with_fake({"是否新增工业废水直排": {"值": False, "原文": "锅炉配布袋除尘"}})
    check("片段里没有否定表述 → 不能填 false", "是否新增工业废水直排" not in r["采纳"],
          [d["原因"] for d in r["丢弃"]])

    print("[4] key 漂移与嵌套括号")
    r = with_fake({"建设地点（建设地点）": {"值": "临沂市兰山区汪沟镇",
                                     "原文": "在临沂市兰山区汪沟镇建一台20吨/小时的生物质锅炉"},
                   "用地面积_m2（用地（用海）面积）": {"值": 3000, "原文": "用地面积3000平方米"}})
    check("「key（中文名）」能归一", r["采纳"].get("建设地点") == "临沂市兰山区汪沟镇")
    check("嵌套括号的 key 能归一（用海）", r["采纳"].get("用地面积_m2") == 3000.0,
          list(r["采纳"]))

    print("[5] 数字：等价写法要认，单位换算不认")
    r = with_fake({"用地面积_m2": {"值": 3000.0, "原文": "用地面积3000平方米"}})
    check("3000.0 与原文 3000 视为一致", r["采纳"].get("用地面积_m2") == 3000.0)
    r = with_fake({"总投资_万元": {"值": 12000000, "原文": "总投资1200万元"}})
    check("把 1200 万元换成 12000000 元 → 丢弃（数字对不上）",
          "总投资_万元" not in r["采纳"], [d["原因"] for d in r["丢弃"]])

    print("[6] 列表逐项过滤")
    r = with_fake({"环境保护目标": {"值": [{"名称": "阳光村", "方位": "东北"},
                                     {"名称": "编造的小学", "方位": "南"}],
                                 "原文": "厂界东北方向320米有个阳光村"}})
    kept = r["采纳"].get("环境保护目标") or []
    check("有依据的那一项保留", any(x.get("名称") == "阳光村" for x in kept), kept)
    check("无依据的那一项被删", not any(x.get("名称") == "编造的小学" for x in kept), kept)

    print("[7] 模型输出坏掉时不崩")
    for bad in (None, [], "不是JSON", {}):
        try:
            with_fake(bad)
            check("坏输出 %r 不抛异常" % (bad,), True)
        except Exception as exc:                                     # noqa: BLE001
            check("坏输出 %r 不抛异常" % (bad,), False, exc)

    print("[8] 用户回答")
    data = {"建设地点": "临沂市兰山区汪沟镇"}
    r = intake.apply_answer(data, {"key": "项目名称", "中文名": "建设项目名称", "类型": "str"},
                            "兰山生物质供热站技术改造项目")
    check("自由文本回答能落进字段", r["采纳"] and r["data"].get("项目名称") == "兰山生物质供热站技术改造项目",
          r["说明"])
    for na in ("不知道", "不清楚", "没有", "跳过"):
        r = intake.apply_answer(data, {"key": "项目名称", "中文名": "建设项目名称", "类型": "str"}, na)
        check("答「%s」不填值" % na, not r["采纳"] and "项目名称" not in r["data"], r["说明"])
    r = intake.apply_answer(data, {"key": "是否开工建设", "中文名": "是否开工建设", "类型": "bool"},
                            "还没开工，正在办手续")
    check("是非题按否定线索判 false", r["data"].get("是否开工建设") is False, r["说明"])

    print("[9] 提问：判定类不能占满名额，项目名称要进第一轮")
    g = intake.gaps(data, max_ask=6)
    keys = [x["key"] for x in g["要问"]]
    check("第一轮就问项目名称", "项目名称" in keys, keys)
    check("判定类最多占 2 席", sum(1 for x in g["要问"] if x["优先级"] <= 2) <= 2,
          [(x["key"], x["优先级"]) for x in g["要问"]])

    # ------------------------------------------------------------------
    # 2026-09-22 用户反馈两条，都补成确定性用例
    # ------------------------------------------------------------------
    print("[10] 「纳管/排园区厂」要能落成「不直排」（用户反馈：补答后判据仍说未抽到）")
    for q in ("本项目废水经厂内预处理后纳管排入园区污水处理厂",
              "生产废水接管进园区污水处理厂，不直接排入环境",
              "生产废水经市政管网进入城镇污水处理厂"):
        ok, why = intake.bool_ok(False, q, "是否新增工业废水直排")
        check("「%s…」→ 可填直排=false" % q[:14], ok, why)
    # 反例（方向不能反）：真的直排不能被"纳管"这类词吞掉
    ok, _ = intake.bool_ok(False, "本项目废水不纳管，经总排口直接排入厂外沟渠",
                           "是否新增工业废水直排")
    check("「不纳管、直接排放」不被当成非直排", not ok)
    ok, _ = intake.bool_ok(False, "锅炉配布袋除尘", "是否新增工业废水直排")
    check("不相干片段仍然拒绝", not ok)
    # 边界：说的是"生活污水"就不能拿去填"工业废水直排"（话题不匹配，宁可不填）
    ok, _ = intake.bool_ok(False, "生活污水经市政管网进入城镇污水处理厂",
                           "是否新增工业废水直排")
    check("生活污水的话不能填「工业废水直排」", not ok)

    print("[11] 枚举字段必须归一（否则整份生成被 schema 判 error → 不生成）")
    ENUM = ["新建", "改建", "扩建", "技术改造"]
    check("「这次是扩建」→ 扩建", intake.normalize_enum("这次是扩建", ENUM) == "扩建",
          intake.normalize_enum("这次是扩建", ENUM))
    check("「技改」→ 技术改造（缩写）", intake.normalize_enum("技改", ENUM) == "技术改造",
          intake.normalize_enum("技改", ENUM))
    check("「说不上来」→ 空（丢弃而不是硬塞）", intake.normalize_enum("说不上来", ENUM) == "")
    r = with_fake({"建设性质": {"值": "技改", "原文": "项目是技术改造"}})
    check("整段描述里的「技改」被归一成 技术改造", r["采纳"].get("建设性质") == "技术改造",
          r["采纳"])
    r = with_fake({"建设性质": {"值": "说不上来", "原文": "项目是技术改造"}})
    check("归不了就丢弃", "建设性质" not in r["采纳"], [d["原因"] for d in r["丢弃"]])
    # 因果链证据：这句就是"整份生成被拒"的根因
    check("未归一时 schema 报错（＝gen_routes 判 rejected、整份不生成）",
          any("建设性质" in str(e) for e in schema.validate({"建设性质": "技改"})["errors"]),
          schema.validate({"建设性质": "技改"})["errors"])
    check("归一后不再报错",
          not any("建设性质" in str(e)
                  for e in schema.validate({"建设性质": "技术改造"})["errors"]))

    print("=" * 64)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())