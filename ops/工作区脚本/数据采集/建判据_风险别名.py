#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 `环境风险判据.json` 增补**报告常用缩写 → 表B.1 名称**的别名表，并记下无法对应的物质。

为什么必须做成数据而不是写在代码里：
  审核结论要能审计 —— "为什么把报告里的 NH3 认成氨气" 必须能从判据数据里查到出处，
  而不是埋在某个 if 里。别名表的每一条都只映射到**表B.1 里真实存在的名称**（脚本校验）。

为什么必须有别名表（实测）：
  报告的风险物质表常用 CO / HCl / NH3 这类缩写写；而表B.1 用的是中文全名。
  没有别名表就只能靠子串匹配，结果 "CO" 命中了 "CODCr 浓度≥10000mg/L 的有机废液"、
  "氨" 命中了 "2-氨基异丁烷" —— 假匹配会直接造出假结论。

用法：python 建判据_风险别名.py [--dry]
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
JSON_PATH = os.path.join(ROOT, "判据库", "环境风险判据.json")

# 缩写 → 表B.1 名称。只列**报告里常见、且表B.1 确有该物质**的。
ALIASES = {
    "CO": "一氧化碳", "HCl": "氯化氢", "NO": "一氧化氮", "NO2": "二氧化氮",
    "H2S": "硫化氢", "SO2": "二氧化硫", "NH3": "氨气", "CH4": "甲烷",
    "HCN": "氰化氢", "Cl2": "氯气", "Hg": "汞", "As": "砷",
    "Pb": "铅", "Cd": "", "Cr": "铬", "Cu": "铜", "Ni": "镍", "Zn": "锌",
    "甲醇": "甲醇", "乙醇": "乙醇", "苯": "苯", "甲苯": "甲苯", "二甲苯": "二甲苯",
    # 单字名不做子串匹配（"氨" 会命中 "2-氨基异丁烷"），只能靠别名表
    "氨": "氨气", "氯": "氯气", "砷化氢": "砷化氢", "光气": "光气",
    # 油类：表B.1 只有大类「油类物质（矿物油类…）」，报告按具体油品写，必须映射
    "柴油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
    "轻柴油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
    "汽油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
    "机油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
    "润滑油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
    "石油": "油类物质（矿物油类，如石油、汽油、柴油等；生物柴油等）",
}
# 报告里常见、但**表B.1 查不到**的物质 —— 记在这里，避免每次都要重新判断一遍。
# 注：HJ 169 表B.1 的注释说明其数据源自《企业突发环境事件风险分级方法》(HJ 941-2018) 附录A，
#     而 HJ 169 全文不含"二噁英"。要判断这类物质的临界量，必须先拿到 HJ 941 附录A。
UNMAPPED = {
    "二噁英": "表B.1 未列；HJ 169 全文不含该物质，需 HJ 941-2018 附录A 才能核对临界量",
}


def main():
    dry = "--dry" in sys.argv
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    names = {s["name"] for s in data.get("substances", [])}

    kept, dropped = {}, []
    for ab, full in ALIASES.items():
        if full in names:
            kept[ab] = full
        else:
            dropped.append(f"{ab}→{full}（表B.1 无此名称，未收录）")
    for k in UNMAPPED:
        if k in names:
            dropped.append(f"{k} 已在表B.1 中，无需记为未列")

    print(f"表B.1 物质 {len(names)} 条；别名收录 {len(kept)} 条，丢弃 {len(dropped)} 条")
    for d in dropped:
        print("   丢弃:", d)
    data["aliases"] = dict(sorted(kept.items()))
    data["aliases_note"] = ("报告常用缩写 → 表B.1 名称。仅收录表B.1 中真实存在的名称，"
                            "由 建判据_风险别名.py 校验后写入；子串匹配只作兜底且按词边界。")
    data["unmapped_note"] = UNMAPPED
    if dry:
        print("[dry] 未写入")
        return 0
    shutil.copy2(JSON_PATH, JSON_PATH + ".bak_before_aliases")
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已写入 {JSON_PATH}（备份 {os.path.basename(JSON_PATH)}.bak_before_aliases）")
    return 0


if __name__ == "__main__":
    sys.exit(main())