#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库数字化 (4-v2)：专项评价设置判据（污染影响类 + 生态影响类）→ 可执行 JSON。

v2 相对 v1 的修正与增补（v1 见交付记录的 P0 记录）：
  1. **修正生态条漏字**：v1 的 evidence 漏掉了限定语「新增河道取水的污染类建设项目」，
     该限定语实质收窄了适用范围，必须补回，且判据逻辑需要两个输入
     （是否新增河道取水 ∧ 下游 500 m 内是否有三场一通道）。
  2. **补大气条脚注**：有毒有害污染物**不包括无排放标准的污染物**（表1 注1）。
  3. **补生态影响类**（报告表另一套规则）：7 个专项类别按「涉及项目类别」列举，编码为可执行条件。
  4. **闭合环境风险缺口**：临界量改指 HJ 169-2018 附录B（见 环境风险判据.json）。

说明（重要，不吹高自动化程度）：条文是自然语言，本 JSON 的规则由**人工整理编码**；
每条规则保留官方原行 evidence，关键词 match 仅用于定位候选，结论仍需页码级事实支撑。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CRIT_DIR = os.environ.get("CRIT_DIR", os.path.join(ROOT, "判据库"))
OUT = os.path.join(CRIT_DIR, "专项评价设置判据.json")
OUT_TOXIC = os.path.join(CRIT_DIR, "有毒有害大气污染物名录2018.json")

# ---- 《有毒有害大气污染物名录（2018年）》：11 种（官方公告附件表格） ----
TOXIC_AIR = [
    {"no": 1, "name": "二氯甲烷"},
    {"no": 2, "name": "甲醛"},
    {"no": 3, "name": "三氯甲烷"},
    {"no": 4, "name": "三氯乙烯"},
    {"no": 5, "name": "四氯乙烯"},
    {"no": 6, "name": "乙醛"},
    {"no": 7, "name": "镉及其化合物"},
    {"no": 8, "name": "铬及其化合物"},
    {"no": 9, "name": "汞及其化合物"},
    {"no": 10, "name": "铅及其化合物"},
    {"no": 11, "name": "砷及其化合物"},
]

# ---- 污染影响类 表1 专项评价设置原则（官方原行） ----
EVIDENCE_INDUSTRIAL = {
    "大气": "排放废气含有毒有害污染物1、二噁英、苯并[a]芘、氰化物、氯气且厂界外500 米范围内有环境空气保护目标2的建设项目",
    "地表水": "新增工业废水直排建设项目（槽罐车外送污水处理厂的除外）；新增废水直排的污水集中处理厂",
    "环境风险": "有毒有害和易燃易爆危险物质存储量超过临界量3的建设项目",
    "生态": "取水口下游500 米范围内有重要水生生物的自然产卵场、索饵场、越冬场和洄游通道的新增河道取水的污染类建设项目",
    "海洋": "直接向海排放污染物的海洋工程建设项目",
}
FOOTNOTES_INDUSTRIAL = {
    "1": "废气中有毒有害污染物指纳入《有毒有害大气污染物名录》的污染物（不包括无排放标准的污染物）。",
    "2": "环境空气保护目标指自然保护区、风景名胜区、居住区、文化区和农村地区中人群较集中的区域。",
    "3": "临界量及其计算方法可参考《建设项目环境风险评价技术导则》（HJ 169）附录B、附录C。",
}
EXTRA_AIR = ["\u4e8c\u5641\u82f1", "苯并[a]\u82d8", "氰化物", "氯气"]  # 二噁英 / 苯并[a]芘

# ---- 生态影响类 表1 专项评价设置原则（按涉及项目类别列举） ----
EVIDENCE_ECOLOGICAL = [
    {
        "category": "地表水",
        "evidence": "水力发电：引水式发电、涉及调峰发电的项目；人工湖、人工湿地：全部；水库：全部；"
                    "引水工程：全部（配套的管线工程等除外）；防洪除涝工程：包含水库的项目；"
                    "河湖整治：涉及清淤且底泥存在重金属污染的项目",
        "conditions": [
            {"desc": "水力发电：引水式发电、涉及调峰发电的项目",
             "all_of": ["水力发电"], "any_of": ["引水式", "调峰"]},
            {"desc": "人工湖、人工湿地：全部", "any_of": ["人工湖", "人工湿地"]},
            {"desc": "水库：全部", "any_of": ["水库"]},
            {"desc": "引水工程：全部（配套的管线工程等除外）", "any_of": ["引水工程"]},
            {"desc": "防洪除涝工程：包含水库的项目",
             "all_of": ["防洪", "除涝"], "any_of": ["水库"]},
            {"desc": "河湖整治：涉及清淤且底泥存在重金属污染的项目",
             "all_of": ["河湖整治", "清淤"], "any_of": ["重金属"]},
        ],
    },
    {
        "category": "地下水",
        "evidence": "陆地石油和天然气开采：全部；地下水（含矿泉水）开采：全部；"
                    "水利、水电、交通等：含穿越可溶岩地层隧道的项目",
        "conditions": [
            {"desc": "陆地石油和天然气开采：全部",
             "any_of": ["石油开采", "天然气开采", "油气开采"]},
            {"desc": "地下水（含矿泉水）开采：全部",
             "any_of": ["地下水开采", "矿泉水开采", "地热水开采"]},
            {"desc": "水利、水电、交通等：含穿越可溶岩地层隧道的项目",
             "all_of": ["隧道"], "any_of": ["可溶岩", "岩溶"]},
        ],
    },
    {
        "category": "生态",
        "evidence": "涉及环境敏感区（不包括饮用水水源保护区，以居住、医疗卫生、文化教育、科研、"
                    "行政办公为主要功能的区域，以及文物保护单位）的项目",
        "conditions": [
            {"desc": "涉及环境敏感区（排除饮用水水源保护区、居住/医疗/文教/科研/行政办公功能区、文物保护单位）",
             "all_of": ["涉及环境敏感区"],
             "exclude_if": ["仅涉及饮用水水源保护区", "仅涉及居住区", "仅涉及文物保护单位"]},
        ],
    },
    {
        "category": "大气",
        "evidence": "油气、液体化工码头：全部；干散货（含煤炭、矿石）、件杂、多用途、通用码头："
                    "涉及粉尘、挥发性有机物排放的项目",
        "conditions": [
            {"desc": "油气、液体化工码头：全部",
             "all_of": ["码头"], "any_of": ["油气", "液体化工"]},
            {"desc": "干散货（含煤炭、矿石）、件杂、多用途、通用码头：涉及粉尘、挥发性有机物排放的项目",
             "all_of": ["码头"],
             "any_of": ["干散货", "煤炭", "矿石", "件杂", "多用途", "通用"],
             "and_any_of": ["粉尘", "挥发性有机物"]},
        ],
    },
    {
        "category": "噪声",
        "evidence": "公路、铁路、机场等交通运输业涉及环境敏感区（以居住、医疗卫生、文化教育、科研、"
                    "行政办公为主要功能的区域）的项目；"
                    "城市道路（不含维护，不含支路、人行天桥、人行地道）：全部",
        "conditions": [
            {"desc": "公路、铁路、机场等交通运输业涉及环境敏感区",
             "any_of": ["公路", "铁路", "机场"],
             "and_any_of": ["环境敏感区", "居住区", "学校", "医院", "机关"]},
            {"desc": "城市道路（不含维护，不含支路、人行天桥、人行地道）：全部",
             "all_of": ["城市道路"],
             "exclude_if": ["仅维护", "支路", "人行天桥", "人行地道"]},
        ],
    },
    {
        "category": "环境风险",
        "evidence": "石油和天然气开采：全部；油气、液体化工码头：全部；"
                    "原油、成品油、天然气管线（不含城镇天然气管线、企业厂区内管线），"
                    "危险化学品输送管线（不含企业厂区内管线）：全部",
        "conditions": [
            {"desc": "石油和天然气开采：全部",
             "any_of": ["石油开采", "天然气开采", "油气开采"]},
            {"desc": "油气、液体化工码头：全部",
             "all_of": ["码头"], "any_of": ["油气", "液体化工"]},
            {"desc": "原油、成品油、天然气管线；危险化学品输送管线（不含城镇及企业厂区内管线）",
             "any_of": ["原油管线", "成品油管线", "天然气管线", "危险化学品输送管线"],
             "exclude_if": ["城镇天然气管线", "企业厂区内管线"]},
        ],
    },
]

GLOBAL_RULES = {
    "土壤": "不开展专项评价",
    "声环境": "不开展专项评价",
    "地下水": "原则上不开展；涉及集中式饮用水水源和热水、矿泉水、温泉等特殊地下水资源保护区的开展",
    "数量上限": "一般不超过两项；印刷电路板制造类建设项目不超过三项",
}

CRITERIA = {
    "version": "2026-09-16-v2",
    "source": {
        "doc_industrial": "《建设项目环境影响报告表编制技术指南（污染影响类）》（试行）",
        "doc_ecological": "《建设项目环境影响报告表编制技术指南（生态影响类）》（试行）",
        "issuer": "生态环境部办公厅 环办环评〔2020〕33号",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk05/202101/t20210104_815870.html",
        "table": "表1 专项评价设置原则表",
        "note": "条文为自然语言，本 JSON 的规则由人工整理编码；evidence 保留官方原行便于审计。",
    },
    "v2_changes": [
        "修正污染影响类『生态』条 evidence：补回限定语『新增河道取水的污染类建设项目』",
        "补入表1 注1：有毒有害污染物不包括无排放标准的污染物",
        "新增生态影响类 7 个专项类别判据（按涉及项目类别列举）",
        "环境风险临界量闭合到 HJ 169-2018 附录B/附录C（见 环境风险判据.json）",
    ],
    "toxic_air_list": {
        "source": "《有毒有害大气污染物名录（2018年）》公告 2019年 第4号",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/201901/t20190131_691779.html",
        "issuer": ["生态环境部", "国家卫生健康委员会"],
        "substances": TOXIC_AIR,
        "names": [s["name"] for s in TOXIC_AIR],
    },
    "global_rules": GLOBAL_RULES,
    "industrial": {
        "report_form": "污染影响类",
        "footnotes": FOOTNOTES_INDUSTRIAL,
        "extra_air_substances": EXTRA_AIR,
        "rules": [
            {
                "element": "大气",
                "evidence": EVIDENCE_INDUSTRIAL["大气"],
                "inputs": ["废气污染物清单", "厂界外500米内是否有环境空气保护目标"],
                "logic": {"all": [
                    {"any_of": [s["name"] for s in TOXIC_AIR] + EXTRA_AIR, "match": "废气污染物清单"},
                    {"is_true": "厂界外500米内是否有环境空气保护目标"},
                ]},
                "caveat": "注1：不包括无排放标准的污染物 —— 污染物即使列入名录，若无排放标准则不构成条件",
            },
            {
                "element": "地表水",
                "evidence": EVIDENCE_INDUSTRIAL["地表水"],
                "inputs": ["废水是否直排", "是否槽罐车外送污水处理厂", "是否为污水集中处理厂"],
                "logic": {"any": [
                    {"all": [{"is_true": "废水是否直排"}, {"is_false": "是否槽罐车外送污水处理厂"}]},
                    {"all": [{"is_true": "废水是否直排"}, {"is_true": "是否为污水集中处理厂"}]},
                ]},
            },
            {
                "element": "环境风险",
                "evidence": EVIDENCE_INDUSTRIAL["环境风险"],
                "inputs": ["危险物质清单[{名称, cas, 最大存在总量t}]"],
                "logic": "存在任一危险物质 q ≥ 其临界量 Q（见 环境风险判据.json 表B.1/B.2）",
                "criteria_ref": "环境风险判据.json",
            },
            {
                "element": "生态",
                "evidence": EVIDENCE_INDUSTRIAL["生态"],
                "inputs": ["是否新增河道取水", "取水口下游500米内是否有重要水生生物三场一通道"],
                "logic": {"all": [
                    {"is_true": "是否新增河道取水"},
                    {"is_true": "取水口下游500米内是否有重要水生生物三场一通道"},
                ]},
                "v1_defect_fixed": "v1 的 evidence 漏掉『新增河道取水的污染类建设项目』这一限定语",
            },
            {
                "element": "海洋",
                "evidence": EVIDENCE_INDUSTRIAL["海洋"],
                "inputs": ["是否直接向海排放污染物的海洋工程"],
                "logic": {"is_true": "是否直接向海排放污染物的海洋工程"},
            },
        ],
    },
    "ecological": {
        "report_form": "生态影响类",
        "rules": EVIDENCE_ECOLOGICAL,
        "match_semantics": {
            "all_of": "全部关键词都必须出现",
            "any_of": "至少一个关键词出现",
            "and_any_of": "在 all_of/any_of 成立的基础上，这一组里至少一个也要出现",
            "exclude_if": "出现任一排除词则该条件不成立",
        },
    },
}


def main():
    os.makedirs(CRIT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(CRITERIA, f, ensure_ascii=False, indent=1)
    with open(OUT_TOXIC, "w", encoding="utf-8") as f:
        json.dump({"source": CRITERIA["toxic_air_list"]["source"],
                   "url": CRITERIA["toxic_air_list"]["url"],
                   "count": len(TOXIC_AIR), "substances": TOXIC_AIR},
                  f, ensure_ascii=False, indent=1)

    print(f"专项评价判据 v2 → {OUT}")
    print(f"  污染影响类规则 {len(CRITERIA['industrial']['rules'])} 条"
          f"（含脚注 {len(FOOTNOTES_INDUSTRIAL)} 条）")
    print(f"  生态影响类类别 {len(EVIDENCE_ECOLOGICAL)} 个，"
          f"条件合计 {sum(len(r['conditions']) for r in EVIDENCE_ECOLOGICAL)} 条")
    print(f"  有毒有害大气污染物名录 {len(TOXIC_AIR)} 种 → {OUT_TOXIC}")

    # 自检：生态条限定语是否已补回
    ev = next(r for r in CRITERIA["industrial"]["rules"] if r["element"] == "生态")["evidence"]
    print(f"\n[自检] 生态条 evidence 含限定语『新增河道取水的污染类建设项目』: "
          f"{'新增河道取水的污染类建设项目' in ev}")


if __name__ == "__main__":
    sys.exit(main())