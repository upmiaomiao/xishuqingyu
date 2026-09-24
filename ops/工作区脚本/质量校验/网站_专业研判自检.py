#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专业研判流水线自检（缺陷注入式）：依据校验器 + JSON 提取 + 报告渲染器。

在 .10 上用站点 venv 运行：
  /home/test/fagui_serve/.venv/bin/python 网站_专业研判自检.py <site.py>
"""
import importlib.util
import json
import sys

SITE = sys.argv[1] if len(sys.argv) > 1 else "/home/test/xishu_qingyu_serve/xishu_qingyu_qa.py"
spec = importlib.util.spec_from_file_location("site_under_test", SITE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = []


def check(desc, ok, detail=""):
    print(f"{'✓' if ok else '✗'} {desc}" + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(desc)


print(f"被测文件：{SITE}\n")
print("========== 一、依据白名单校验器 ==========")

SOURCES = [
    {"index": 1, "title": "排污许可证申请与核发技术规范 工业固体废物（试行）",
     "source": "生态环境标准规范/排污许可/…HJ 1200—2021…md",
     "text": "一般工业固体废物贮存应满足防渗漏、防雨淋、防扬尘要求。"
             "环境管理与设施运行维护应符合 GB 18599、GB 15562.2 和 HJ 2035 等标准。"},
    {"index": 2, "title": "一般工业固体废物贮存和填埋污染控制标准",
     "source": "生态环境标准规范/…GB 18599-2020…md",
     "text": "贮存场应设置防扬散、防流失、防渗漏设施，并设置标志。"},
    {"index": 3, "title": "中华人民共和国固体废物污染环境防治法",
     "source": "生态环境法律法规/法律/法律_43/中华人民共和国固体废物污染环境防治法/…md",
     "text": "产生工业固体废物的单位应当采取措施防止或者减少固体废物对环境的污染。"},
]
CITE_CASES = [
    ("有据：GB 18599 在资料里", "应符合 GB 18599 的要求。", False),
    ("有据：破折号写法不同", "依据 HJ 1200-2021 的要求。", False),
    ("有据：带年份且与资料一致", "依据 HJ 1200—2021 的要求。", False),
    ("有据：资料里出现过的标准名", "依据《一般工业固体废物贮存和填埋污染控制标准》。", False),
    ("★张冠李戴：GB 30485（真实踩过的坑）", "应符合 GB 18599、GB 30485 和 HJ 2035 等标准。", True),
    ("★年份不符：GB 18599—2023（实为 2020 版）", "按 GB 18599—2023 第 7.5 条执行。", True),
    ("编造标准号 HJ 9999-2099", "按 HJ 9999-2099 执行。", True),
    ("编造文件名", "依据《固体废物现场检查技术指南》。", True),
    ("不该误伤：普通引号内容", "所谓《三防》即防扬散、防流失、防渗漏。", False),
    ("不该误伤：法名简称", "依据《固废法》的相关义务。", False),
    ("不该误伤：省略「中华人民共和国」前缀", "依据《固体废物污染环境防治法》第四十条。", False),
    ("不该误伤：写成全称也匹配", "依据《中华人民共和国固体废物污染环境防治法》。", False),
    ("应抓到：指南类文件", "依据《生活垃圾焚烧发电厂现场监督检查技术指南》。", True),
]
for desc, ans, expect in CITE_CASES:
    miss = mod.verify_citations(ans, SOURCES)
    check(desc, bool(miss) == expect, f"命中={miss}")

# 确定性：同一输入重复 50 次结果必须完全一致（此前用 set 迭代 token，结果会随机）
base_ans = "应符合 GB 18599、GB 30485 和 HJ 2035 等标准，按 GB 18599—2023 执行。"
runs = {tuple(mod.verify_citations(base_ans, SOURCES)) for _ in range(50)}
check("校验结果确定性（50 次一致）", len(runs) == 1, f"出现了 {len(runs)} 种结果")
check("年份不符带专门说明",
      any("其它年份" in x for x in mod.verify_citations("按 GB 18599—2023 执行。", SOURCES)),
      str(mod.verify_citations("按 GB 18599—2023 执行。", SOURCES)))

print("\n========== 二、JSON 提取器 ==========")
GOOD = {"image_type": "固废贮存堆场", "visible_facts": ["锈蚀型钢与管材", "露天堆放无覆盖"],
        "checklist": [{"item": "防扬散（覆盖/围挡/喷淋）", "observed": "无覆盖、无围挡",
                       "verdict": "不满足", "basis": "GB 18599"}],
        "risks": [{"level": "高", "stance": "照片已显示", "text": "扬尘风险"}],
        "waste_class": "疑似一般工业固废（废钢铁）；危废属性需 HJ 298 鉴别。",
        "missing_info": ["物料来源"], "uncertainty": "单图初判"}
check("裸 JSON", mod.extract_json_object(json.dumps(GOOD, ensure_ascii=False)) is not None)
check("```json 围栏",
      mod.extract_json_object("```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```") is not None)
check("think 块之后",
      mod.extract_json_object("推理内容…</think>\n" + json.dumps(GOOD, ensure_ascii=False)) is not None)
check("前后有废话",
      mod.extract_json_object("好的，结果如下：\n" + json.dumps(GOOD, ensure_ascii=False) + "\n以上。") is not None)
check("坏 JSON → None", mod.extract_json_object('{"image_type": "x", ') is None)
check("无 JSON → None", mod.extract_json_object("这张照片显示露天堆放的废金属。") is None)

print("\n========== 三、报告渲染器（词表/项目库强制）==========")
report, stats = mod.render_photo_report(GOOD)
for sec in ("【一、图片类型】", "【二、图中可见事实】", "【三、核验清单】", "【四、风险提示】",
            "【五、固废属性初判】", "【六、需要补充的信息】", "【七、结论边界】"):
    check(f"含 {sec}", sec in report)
check("含固定表头", "| 检查项 | 图中可见情况 | 判定 | 依据 |" in report)
check("含表格分隔行", "| --- | --- | --- | --- |" in report)
check("正常输入无降级", stats == {"dropped_items": 0, "coerced_verdicts": 0, "coerced_stance": 0},
      str(stats))

bad = dict(GOOD)
bad["checklist"] = [
    {"item": "防扬散（覆盖/围挡/喷淋）", "observed": "无覆盖", "verdict": "基本满足", "basis": "依据不足"},
    {"item": "现场整洁度", "observed": "杂乱", "verdict": "不满足", "basis": "依据不足"},
    {"item": "雨污分流", "observed": "a|b", "verdict": "无法判断", "basis": "依据不足"},
]
bad["risks"] = [{"level": "高", "stance": "可能已显示", "text": "扬尘"}]
rep2, st2 = mod.render_photo_report(bad)
check("越界判定降级为「无法判断」", st2["coerced_verdicts"] == 1, str(st2))
check("项目库外的检查项被丢弃", st2["dropped_items"] == 2, str(st2))
check("越界风险立场被规范", st2["coerced_stance"] == 1, str(st2))
check("降级后的行仍渲染出三态值", "| 防扬散（覆盖/围挡/喷淋） | 无覆盖 | 无法判断 | 依据不足 |" in rep2)
check("被丢弃的项没有出现在报告里", "现场整洁度" not in rep2)

empty_rep, st3 = mod.render_photo_report({})
check("空 JSON 也能产出完整骨架（不崩）",
      all(s in empty_rep for s in ("【一、图片类型】", "【七、结论边界】")), str(st3))
check("checklist 为空时给出兜底行", "模型未给出有效的核验项" in empty_rep)

print("\n========== 四、告警文案 ==========")
w = mod.citation_warning(["GB 30485", "《固体废物现场检查技术指南》"])
check("告警文案包含全部条目", "GB 30485" in w and "固体废物现场检查技术指南" in w)
check("无缺失时不产生告警", mod.citation_warning([]) == "")

print("\n结论：" + ("全部符合预期 ✅" if not fails else f"{len(fails)} 项不符合预期 ❌ {fails}"))
sys.exit(0 if not fails else 1)
