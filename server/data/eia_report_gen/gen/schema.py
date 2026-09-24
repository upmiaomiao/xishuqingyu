# -*- coding: utf-8 -*-
"""项目信息填报表：字段定义、校验、模板导出。

为什么先做这个：生成质量的上限由**输入**决定。填报表里没有的东西，
工具必须写"需人工补充"而不是编一个像样的值 —— 所以字段定义要明确标出
"必填/选填""单位""这一项会被用来算什么"。

字段分三类（与 `判据库/报告表结构.json` 的「本工具归类」一致）：
  填报      使用者必须给；工具不猜
  判定输入  给判据层算结论用（专项评价设置、名录档级）
  需资料    必须有人提供原始资料（监测/踏勘），工具只留占位
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

TYPES = ("str", "float", "int", "bool", "list", "enum")


@dataclass
class Field:
    key: str
    name: str                      # 中文名（写进报告表用）
    type: str
    required: bool = True
    unit: str = ""
    note: str = ""                 # 这一项用来算什么 / 填报要求
    choices: list = field(default_factory=list)
    group: str = "表一"            # 归属哪张表
    source: str = "填报"           # 填报 / 判定输入 / 需资料
    guide_page: int = 0            # 指南页码（能对上就写，便于复查）


FIELDS: list[Field] = [
    # ---------------- 表一 建设项目基本情况 ----------------
    Field("项目名称", "建设项目名称", "str", note="立项批复名；无批复用可研/设计文件名称", guide_page=2),
    Field("项目代码", "项目代码", "str", required=False, note="发改部门核发；未核发填「无」", guide_page=2),
    Field("建设地点", "建设地点", "str", note="具体建设地址", guide_page=2),
    Field("地理坐标", "地理坐标", "str", note="中心坐标，度分秒（秒保留 3 位小数）", guide_page=2),
    Field("建设性质", "建设性质", "enum", choices=["新建", "改建", "扩建", "技术改造"], guide_page=2),
    Field("国民经济行业类别", "国民经济行业类别", "str", note="《国民经济行业分类》小类", guide_page=2),
    Field("建设项目行业类别", "建设项目行业类别", "str",
          note="《分类管理名录》中的行业具体类别 —— **名录档级靠它匹配**", guide_page=2),
    Field("是否开工建设", "是否开工建设", "bool", note="存在未批先建的，须填已建设内容与处罚情况", guide_page=2),
    Field("未批先建情况", "未批先建情况", "str", required=False, guide_page=2),
    Field("用地面积_m2", "用地（用海）面积", "float", unit="m²",
          note="土地水平投影面积；租用建筑填租用面积", guide_page=2),
    Field("总投资_万元", "总投资", "float", unit="万元", source="填报"),
    Field("环保投资_万元", "环保投资", "float", unit="万元", source="填报"),
    Field("规划情况", "规划情况", "str", required=False, note="无相关规划填「无」", guide_page=2),
    Field("规划环评情况", "规划环境影响评价情况", "str", required=False, note="未开展填「无」", guide_page=2),

    # ---------------- 表一 专项评价判定的输入（判据层用） ----------------
    Field("废气污染物清单", "废气污染物清单", "list", group="表一", source="判定输入",
          note="用于判定是否需设大气专项评价：是否含《有毒有害大气污染物名录》物质、"
               "二英、苯并[a]芘、氰化物、氯气"),
    Field("厂界外500m内有环境空气保护目标", "厂界外500m内有环境空气保护目标", "bool",
          group="表一", source="判定输入", note="大气专项评价的第二个条件（AND）"),
    Field("是否新增工业废水直排", "新增工业废水直排", "bool", group="表一", source="判定输入",
          note="槽罐车外送污水处理厂的除外"),
    Field("是否槽罐车外送污水处理厂", "槽罐车外送污水处理厂", "bool", group="表一", source="判定输入",
          note="若为「是」，则「直排」不成立（地表水专项评价的除外情形）"),
    Field("是否新增废水直排污水集中处理厂", "新增废水直排的污水集中处理厂", "bool",
          group="表一", source="判定输入", note="判据表1 的第二条情形（直排的集中处理厂）"),
    Field("是否新增河道取水", "新增河道取水", "bool", group="表一", source="判定输入",
          note="生态专项评价的第一个条件"),
    Field("取水口下游500m有三场一通道", "取水口下游500m内有重要水生生物三场一通道", "bool",
          group="表一", source="判定输入", note="生态专项评价的第二个条件（AND）"),
    Field("是否直接向海排放污染物", "直接向海排放污染物的海洋工程", "bool",
          group="表一", source="判定输入"),
    Field("是否涉及特殊地下水资源保护区", "涉及集中式饮用水水源等特殊地下水资源保护区", "bool",
          group="表一", source="判定输入", note="地下水专项评价：原则上不开展，涉及则开展"),
    Field("是否印刷电路板制造", "印刷电路板制造类建设项目", "bool", group="表一",
          source="判定输入", note="专项评价数量上限：一般≤2 项，PCB≤3 项"),
    Field("危险物质", "有毒有害和易燃易爆危险物质", "list", group="表一", source="判定输入",
          note="每项 {名称, 最大贮存量t}；环境风险专项评价按是否超过 HJ 169 临界量判定"),
    Field("补充事实", "补充事实（供名录/专项条件比对）", "list", required=False, group="表一",
          source="判定输入",
          note="每项 {名称, 值, 单位}。判定层说「缺事实」时，**照它引用的名录/判据原文**填这一项，"
               "例如名录条件「燃煤、燃油锅炉总容量65吨/小时以上的」，就填 "
               "{名称:'燃煤、燃油锅炉总容量', 值:0, 单位:'吨/小时'}（本项目无此类锅炉则填 0）。"
               "名称要与条件原文的关键词对得上，否则仍会判为缺事实。"),

    # ---------------- 表二 建设项目工程分析 ----------------
    Field("产品及产能", "主要产品及产能", "list", group="表二",
          note="每项 {名称, 产能, 单位}", guide_page=4),
    Field("主要原辅材料", "主要原辅材料及燃料", "list", group="表二",
          note="每项 {名称, 年用量, 单位, 是否危险物质}；名录档级也会用到", guide_page=4),
    Field("主要生产设备", "主要生产设施及设施参数", "list", group="表二",
          note="每项 {名称, 数量, 规格}", guide_page=4),
    Field("工艺流程简述", "主要工艺流程", "str", group="表二", guide_page=4),
    Field("产排污环节", "产排污环节", "list", group="表二",
          note="每项 {环节, 污染物, 排放去向}；指南（二）要求明确产排污环节", guide_page=4),
    Field("环保措施", "环境保护措施", "list", group="表四",
          note="每项 {要素, 措施内容, 排放去向或执行方式}；表四与表五的监督检查清单由此填写。"
               "**工具不编措施** —— 没填就写【需人工补充】", guide_page=6),
    Field("劳动定员", "劳动定员", "int", unit="人", group="表二", guide_page=4),
    Field("工作制度", "工作制度", "str", group="表二", note="如年工作 300 天、两班制", guide_page=4),
    Field("水平衡说明", "水平衡分析", "str", required=False, group="表二",
          note="产生工业废水的项目应开展水平衡分析", guide_page=4),
    Field("原有环境污染问题", "与项目有关的原有环境污染问题", "str", required=False,
          group="表二", source="需资料", guide_page=5),

    # ---------------- 表三 现状、保护目标与标准 ----------------
    Field("环境保护目标", "环境保护目标", "list", group="表三",
          note="每项 {名称, 方位, 距离_m, 规模}；须现场核实", guide_page=5),
    Field("区域环境质量现状", "区域环境质量现状", "str", required=False, group="表三",
          source="需资料", note="需监测数据或引用有效监测报告，工具不生成", guide_page=4),
    Field("总量控制指标", "总量控制指标", "str", required=False, group="表三",
          source="填报", guide_page=5),
]


def by_key() -> dict:
    return {f.key: f for f in FIELDS}


def template() -> dict:
    """生成填报模板：键齐全、值留空、带说明，避免使用者漏项。"""
    out = {}
    for f in FIELDS:
        blank = {"list": [], "bool": None, "float": None, "int": None}.get(f.type, "")
        out[f.key] = blank
    out["_说明"] = {
        "用法": "把本文件填好后交给 生成_报告表.py；空着的必填项会被明确报错，不会被猜。",
        "必填": [f.key for f in FIELDS if f.required],
        "选填": [f.key for f in FIELDS if not f.required],
        "字段含义": {f.key: {"中文名": f.name, "类型": f.type + (f"（{f.unit}）" if f.unit else ""),
                            "选项": f.choices, "说明": f.note, "来源": f.source}
                     for f in FIELDS},
        "注意": "bool 类型要写 true/false（不要留空表示「否」——留空会被当成「没填」并要求人工确认）。",
    }
    return out


def validate(data: dict, strict: bool = True) -> dict:
    """校验填报数据。返回 {ok, errors, missing_required, warnings, 已填字段数, 字段总数}。

    原则：**不允许静默使用默认值**。必填项缺失就报错并列全（不是只报第一个），
    判定输入缺失就进 warnings（会让相关项只能给"需人工确认"，而不是替使用者拍板）。

    strict=False 用于**对话式填报**：用户在聊天里可能有几项确实不知道，
    这时不拦着生成，而是把缺项列进 `missing_required` 由草稿标注"需人工补充"；
    类型错误照旧拦截（那是数据错误，不是缺信息）。
    """
    errors, missing, warnings = [], [], []
    ks = by_key()
    unknown = [k for k in data if k not in ks and not k.startswith("_")]
    if unknown:
        warnings.append("填报里有未定义字段（会被忽略）：" + "、".join(unknown[:8]))
    for f in FIELDS:
        v = data.get(f.key)
        empty = v is None or v == "" or (f.type == "list" and v == [])
        if empty:
            (missing if f.required else warnings).append(f"{f.key}（{f.name}）")
            continue
        if f.type == "bool" and not isinstance(v, bool):
            errors.append(f"{f.key} 应为 true/false，实际是 {type(v).__name__}")
        if f.type in ("float", "int") and not isinstance(v, (int, float)):
            errors.append(f"{f.key} 应为数字，实际是 {type(v).__name__}")
        if f.type == "enum" and f.choices and v not in f.choices:
            errors.append(f"{f.key} 只能是 {'/'.join(f.choices)}，实际是 {v!r}")
        if f.type == "list" and not isinstance(v, list):
            errors.append(f"{f.key} 应为列表")
        if f.type == "str" and not isinstance(v, str):
            errors.append(f"{f.key} 应为文本")
    if missing and strict:
        errors.append("缺少必填项：" + "、".join(missing))
    known = sum(1 for f in FIELDS if not (data.get(f.key) in (None, "", []) or f.key not in data))
    return {"ok": not errors, "errors": errors, "missing_required": missing,
            "warnings": warnings, "已填字段数": known, "字段总数": len(FIELDS),
            "strict": strict}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    import sys
    base = __file__.rsplit("gen", 1)[0]
    out = base + "模板/项目信息表.填报模板.json"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(template(), f, ensure_ascii=False, indent=1)
    print("已写出填报模板：", out)
    print("字段 %d 个（必填 %d）" % (len(FIELDS), sum(1 for f in FIELDS if f.required)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())