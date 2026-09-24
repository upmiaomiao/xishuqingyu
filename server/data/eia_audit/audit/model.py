#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判定层共享原语：四态常量、审核项数据结构、判据出处串。

单独成文件的原因：审核项 1-4 在 judge.py、5-18 在 items_extra.py，
两边都要用这些定义；如果 items_extra 反过来从 judge 导入就会**循环导入**。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 四态（顺序即严重度，用于取最严）
S_PROBLEM = "存在问题"
S_SUSPECT = "存在疑似问题"
S_SUGGEST = "优化调整建议"
S_OK = "无问题"
S_NA = "不适用"
SEVERITY = {S_PROBLEM: 3, S_SUSPECT: 2, S_SUGGEST: 1, S_OK: 0, S_NA: 0}

# 判据出处串
GUIDE = "《建设项目环境影响报告表编制技术指南（污染影响类）（试行）》表1"
GUIDE_ECO = "《建设项目环境影响报告表编制技术指南（生态影响类）（试行）》表1"
CATALOG = "《建设项目环境影响评价分类管理名录（2021年版）》"
HJ169 = "《建设项目环境风险评价技术导则》（HJ 169-2018）"
TIER_ORDER = {"登记表": 1, "报告表": 2, "报告书": 3}


@dataclass
class Evidence:
    page: int
    quote: str
    source: str = ""          # 该项事实怎么来的
    mark: str = ""            # 报告自己的页标（如 3-8）


@dataclass
class Item:
    审核项: str
    类别: str = "法规符合性"
    适用: bool = True
    AI审核: str = S_OK
    人工修改: str = ""
    参考依据: str = ""
    环评文件: str = ""
    理由: str = ""
    证据: list = field(default_factory=list)
    判据轨迹: dict = field(default_factory=dict)
    置信度: str = "中"
    需人工确认: list = field(default_factory=list)

    def to_json(self):
        return asdict(self)


# 18 项审核项清单（用于自检与前端分组展示；不参与判定逻辑）
ITEM_PLAN = [
    ("环评类别准确性", "法规符合性"),
    ("大气专项评价设置", "技术导则符合性"),
    ("地表水专项评价设置", "技术导则符合性"),
    ("地下水专项评价设置", "技术导则符合性"),
    ("生态专项评价设置", "技术导则符合性"),
    ("海洋专项评价设置", "技术导则符合性"),
    ("环境风险专项评价设置", "技术导则符合性"),
    ("土壤专项评价设置", "技术导则符合性"),
    ("声环境专项评价设置", "技术导则符合性"),
    ("专项评价数量上限", "技术导则符合性"),
    ("风险物质识别完整性", "环境风险（HJ 169）"),
    ("风险物质临界量引用正确性", "环境风险（HJ 169）"),
    ("风险物质 Q 值计算正确性", "环境风险（HJ 169）"),
    ("环境风险潜势与评价等级", "环境风险（HJ 169）"),
    ("环境保护目标表完整性", "报告质量"),
    ("编制要素完整性", "报告质量"),
    ("引用标准编号正确性", "报告质量"),
    ("结论章节与主要问题响应", "报告质量"),
]