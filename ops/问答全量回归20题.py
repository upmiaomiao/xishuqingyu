#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""问答线全量回归（20 题）：P6 上线后第一次系统性复跑，也是 [025] 改前/改后的对照基线。

为什么是"拼"出来的 20 题：项目里的问答验收题**分散在几处**，各自只覆盖一类 ——
  · 5 个用户错例（B1–B5）在 `复测5个错例_B1B5.py`（本脚本**直接 import 复用**，不复制题干，
    免得两处题干将来不一致）；
  · 6 个"标准有原文"的数值题在 `AB对比_限值问答.py`；
  · 导则判定、危废鉴别、报告类题散在 `验证语料上限修法.py` / `验收关键数字.py`；
  · 法典时效类题（含"还有效吗/被谁废止"）**是新加的** —— 正是 [025] 要动的部分；
  · 另加"库里没有的标准号"这类**抗编造**题，专门看会不会硬编数值。

判分沿用 B1–B5 的规则（忽略空格比对 must_all；ban_rx 命中即算错，可带例外词；
可选 must_any；可选 min_sources），并对每条记录答案与引用，便于人工复核。

用法：
  python3 问答全量回归20题.py --site http://127.0.0.1:8011 --out /tmp/问答回归_改前.json
  python3 问答全量回归20题.py --compare 改前.json 改后.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                       # 0911训练/
B15 = os.path.join(BASE, "站点全量测试", "复测5个错例_B1B5.py")
if not os.path.isfile(B15):                        # 服务器上（/home/test）两个脚本同目录
    B15 = os.path.join(HERE, "复测5个错例_B1B5.py")

_spec = importlib.util.spec_from_loader("b15", SourceFileLoader("b15", B15))
b15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b15)                      # 复用它的 CASES / violation / LOOKAHEAD_CUES

squeeze = lambda s: re.sub(r"\s+", "", str(s))      # noqa: E731

# 对 import 进来的 5 个错例做**判分器校准**（只动判据，不动题干、不改原脚本）。
# 校准记录：
#  ① 2026-09-23 改前基线：B5 被判"违规"，但人工看答案 —— 模型引的是 GB8978 自己的 4.1.3 原文
#     （「排入设置二级污水处理厂的城镇排水系统的污水执行三级标准」）作为**背景说明**，
#     并明确拒绝把 0.05 mg/L 认定为三级标准（正确答案）。原 ban 正则没有例外词，把引文当真了。
#  ② 2026-09-23 改后：B1 被判"违规"，命中的是「仅表示该学习要点文件**当前有效**，
#     **并不代表**所引用的固废法仍然有效」—— 这是模型**正确地**区分"来源文件的状态"与"法律的状态"；
#     F4 命中的是「在 2026 年 8 月 15 日**之前仍然有效**，**但**自施行之日起被废止」—— 也是对的。
#     两句都属于"带限定的正确表述"，所以给 ban 正则补**例外词**（例外词出现在命中处后面 25 字内即豁免）。
#  ③ 同时把「必须点出废止依据（法典/第一千二百四十二条）」升级成**硬判据 must_any** ——
#     这正是 [025] 要修的东西，只有变成硬判据，"改前/改后"才有可判的差别（软命中只作参考）。
QUALIFY = (r"不", r"并非", r"并不", r"不代表", r"仅表示", r"之前", r"但", r"之日起",
           r"学习要点", r"文件", r"被废止", r"废止")
OVERRIDE = {
    "B1": {
        "must_any": ["法典", "第一千二百四十二条"],
        "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效", QUALIFY),
                   (r"继续适用", QUALIFY), (r"未见废止", QUALIFY),
                   (r"未显示废止", QUALIFY), (r"尚未废止", QUALIFY)],
    },
    "B2": {
        "must_any": ["法典", "第一千二百四十二条"],
        "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效", QUALIFY),
                   (r"继续适用", QUALIFY), (r"未见废止", QUALIFY), (r"未显示废止", QUALIFY),
                   (r"元数据[^。；]{0,24}(?:错误|有误|不一致|不准)", ()),
                   (r"(?:标注|标记)[^。；]{0,12}(?:错误|有误|不准确)", ())],
    },
    "B5": {"ban_rx": [(r"(?:属于|是|按|执行)[^。；]{0,10}三级标准",
                      (r"4\.1\.3", r"城镇排水", r"第二类", r"材料1中", r"规定",
                       r"不能", r"若", r"无法"))]},
}


def _cases() -> list:
    """5 个错例（可校准）+ 15 个新增题。"""
    got = []
    for c in b15.CASES:
        c = dict(c)
        c.update(OVERRIDE.get(c["id"], {}))
        c["类"] = "错例"
        got.append(c)
    return got + [dict(c) for c in EXTRA]

# ---- 另外 15 题（5 个错例由上面 import 进来） ----
EXTRA = [
    # ===== 数值题：标准里有原文，答不出具体数值就是没查到 =====
    {"id": "N1", "类": "数值", "name": "储油库 GB20950-2020 限值",
     "q": "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？",
     "must_all": ["NMHC", "25"], "soft": ["95", "处理效率"]},
    {"id": "N2", "类": "数值", "name": "制糖 GB21909-2008 限值",
     "q": "制糖工业水污染物排放标准 GB 21909-2008 规定的水污染物排放限值是多少？",
     "must_all": ["悬浮物"], "soft": ["100", "120", "五日生化需氧量"]},
    {"id": "N3", "类": "数值", "name": "海水水质 GB3097-1997 第一类",
     "q": "海水水质标准 GB 3097-1997 对第一类海水水质的要求是什么？",
     "must_all": ["第一类"], "soft": ["溶解氧", "pH", "人为造成"]},
    {"id": "N4", "类": "数值", "name": "危废名录 医疗废物代码",
     "q": "国家危险废物名录里，医疗废物对应的废物代码有哪些？",
     "must_all": ["HW01"], "soft": ["831-001", "841-001"]},
    {"id": "N5", "类": "数值", "name": "固废贮存场 I 类场防渗",
     "q": "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
     "must_all": ["渗透系数"], "soft": ["0.75", "1.5", "双层", "天然基础层"]},
    {"id": "N6", "类": "数值", "name": "焚烧排污许可规范内容",
     "q": "生活垃圾焚烧排污许可证申请与核发技术规范主要规定了哪些内容？",
     "must_all": ["焚烧"], "soft": ["许可", "自行监测", "台账"]},
    # ===== 时效题：[025] 要动的正是这类"依据说不说得出来" =====
    {"id": "F1", "类": "时效", "name": "放射性污染防治法是否有效",
     "q": "《中华人民共和国放射性污染防治法》现在还有效吗？废止它的是哪部法律？",
     "must_all": ["已废止"],
     "must_any": ["法典", "第一千二百四十二条", "2026年8月15日"],
     "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效", (r"不", r"并非", r"并不",
                                                                r"不代表", r"仅表示", r"之前", r"但")),
                (r"继续适用", ()), (r"未见废止", ()), (r"未显示废止", ())],
     "soft": ["法典", "1242", "第一千二百四十二条", "2026年8月15日"],
     "期望": "已废止，且能说出依据是《生态环境法典》第一千二百四十二条（[025] 修的正是后半句）"},
    {"id": "F2", "类": "时效", "name": "法典施行日期",
     "q": "《中华人民共和国生态环境法典》从什么时候开始施行？",
     "must_all": ["2026"], "soft": ["8月15日", "第一千二百四十二条", "废止"]},
    {"id": "F3", "类": "时效", "name": "反向题：循环经济促进法没被废止",
     "q": "《中华人民共和国循环经济促进法》被《生态环境法典》废止了吗？",
     "must_all": ["有效"], "ban_rx": [(r"循环经济促进法[^。；]{0,14}已(?:被)?废止", ())],
     "soft": ["未", "不在", "不包括", "仍"],
     "期望": "答「没有被废止、仍然有效」——法典第1242条确实没列它（反向题，防误报）"},
    {"id": "F4", "类": "时效", "name": "环境保护法是否有效",
     "q": "《中华人民共和国环境保护法》现在还有效吗？",
     # 2026-09-23 修判分器：真机答的是「自2026年8月15日起**被废止**」，比 must_all=["已废止"]
     # 更准确却被判错 → 改成多组必含（废止的三种说法算一组，法典依据算另一组）；
     # 并给 ban 补例外词（"在…之前仍然有效，但…"不算违规）
     "must_groups": [["已废止", "被废止", "废止"], ["法典", "第一千二百四十二条"]],
     "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效",
                 (r"不", r"并非", r"并不", r"不代表", r"仅表示", r"之前", r"但")),
                (r"继续适用", ())],
     "soft": ["法典", "2026年8月15日"]},
    # ===== 抗编造：库里没有这个标准号 =====
    {"id": "X1", "类": "抗编造", "name": "不存在的标准号",
     "q": "GB 99999-2099 规定的废气排放限值是多少？",
     # 2026-09-23 修判分器：真机答「无法回答…证据中不包含该标准的任何文本」，原词表漏了这几种说法
     "must_any": ["未收录", "没有", "未找到", "无法确认", "无法回答", "未提供", "未见",
                  "查不到", "不存在", "不包含", "不包括", "无此标准"],
     "期望": "必须说库里没有，不许编一个限值出来"},
    # ===== 报告类：只要求真答了、有引用（不空答、不无源作答） =====
    {"id": "R1", "类": "报告", "name": "金水河项目结论",
     "q": "郑州市金水河综合整治工程的环境影响评价结论是什么？",
     "min_sources": 1, "soft": ["金水河"]},
    {"id": "R2", "类": "报告", "name": "济宁焚烧二期结论",
     "q": "济宁市生活垃圾焚烧发电二期改扩建项目的环境影响结论？",
     "min_sources": 1, "soft": ["济宁", "焚烧"]},
    # ===== 导则/鉴别 =====
    {"id": "D1", "类": "导则", "name": "大气导则评价等级",
     "q": "大气环境影响评价的评价等级是怎么判定的？",
     # 2026-09-23 修判分器：真机答的是「最大地面浓度占标率 Pi 与 D10%」，用 Pi 不用 Pmax
     # （导则原文两种写法都有），所以判据改成更本质的「占标率」
     "must_all": ["占标率"], "soft": ["Pi", "Pmax", "D10%", "10%", "一级", "二级"]},
    {"id": "D2", "类": "导则", "name": "危废鉴别标准",
     "q": "危险废物的鉴别标准是什么？",
     "must_all": ["鉴别"], "soft": ["危险特性", "GB 5085"]},
]


def ask(site: str, q: str, timeout: int = 900) -> dict:
    req = urllib.request.Request(site, data=json.dumps({"query": q}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


def judge(c: dict, ans: str, srcs: list) -> dict:
    a = squeeze(ans)
    hit_must = [w for w in (c.get("must_all") or []) if squeeze(w) in a]
    miss_must = [w for w in (c.get("must_all") or []) if squeeze(w) not in a]
    hit_any = [w for w in (c.get("must_any") or []) if squeeze(w) in a]
    need_any = bool(c.get("must_any"))
    # must_groups：每一组里至少命中一个（用于"既要说过已废止、又要说出依据"这类双重条件）
    groups = c.get("must_groups") or []
    miss_groups = [g for g in groups if not any(squeeze(w) in a for w in g)]
    bad = [v for v in (b15.violation(ans, rx, ex) for rx, ex in (c.get("ban_rx") or [])) if v]
    hit_soft = [w for w in (c.get("soft") or []) if squeeze(w) in a]
    ok = (not miss_must) and (not need_any or bool(hit_any)) and (not miss_groups) \
        and (not bad) and len(srcs) >= int(c.get("min_sources") or 0)
    return {"ok": ok, "miss_must": miss_must, "hit_must": hit_must, "hit_any": hit_any,
            "miss_groups": [g[0] for g in miss_groups], "ban": bad, "soft": hit_soft,
            "n_sources": len(srcs)}


def run(site: str, label: str, out: str) -> int:
    cases = _cases()
    print("目标：%s（标签：%s）共 %d 题\n" % (site, label, len(cases)))
    rows, n_ok = [], 0
    for c in cases:
        t0 = time.time()
        try:
            d = ask(site, c["q"])
        except Exception as e:                                     # noqa: BLE001
            print("  %-4s %-22s ❌ 请求失败：%s" % (c["id"], c["name"], str(e)[:60]))
            rows.append({"id": c["id"], "name": c["name"], "类": c["类"], "q": c["q"],
                         "ok": False, "error": str(e)[:200]})
            continue
        ans = d.get("answer") or ""
        srcs = d.get("sources") or []
        r = judge(c, ans, srcs)
        rows.append({"id": c["id"], "name": c["name"], "类": c["类"], "q": c["q"],
                     "ok": r["ok"], "miss_must": r["miss_must"], "ban": r["ban"],
                     "soft": r["soft"], "n_sources": r["n_sources"],
                     "answer": ans, "sources": [s.get("source", "") for s in srcs][:6],
                     "secs": round(time.time() - t0, 1)})
        n_ok += 1 if r["ok"] else 0
        print("  %-4s %-22s %s  引用%d 软命中%d/%.1fs %s"
              % (c["id"], c["name"], "✅" if r["ok"] else "❌", r["n_sources"],
                 len(r["soft"]), time.time() - t0,
                 ("缺：" + ",".join(r["miss_must"])) if r["miss_must"] else
                 ("违规：" + str(r["ban"]) if r["ban"] else "")))
    print("\n==== 通过 %d / %d ====" % (n_ok, len(cases)))
    bad = [r["id"] for r in rows if not r["ok"]]
    if bad:
        print("   未通过：%s" % "、".join(bad))
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"site": site, "label": label, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "pass": n_ok, "total": len(cases), "cases": rows},
                      fh, ensure_ascii=False, indent=1)
        print("   已写：%s" % out)
    return 0 if n_ok == len(cases) else 1


def compare(a: str, b: str) -> int:
    A = json.load(open(a, encoding="utf-8"))
    B = json.load(open(b, encoding="utf-8"))
    ka = {c["id"]: c for c in A["cases"]}
    kb = {c["id"]: c for c in B["cases"]}
    print("%s：%d/%d      %s：%d/%d\n" % (A["label"], A["pass"], A["total"],
                                          B["label"], B["pass"], B["total"]))
    flip_bad = [i for i in ka if ka[i]["ok"] and i in kb and not kb[i]["ok"]]
    flip_good = [i for i in ka if not ka[i]["ok"] and i in kb and kb[i]["ok"]]
    for i in sorted(set(ka) & set(kb)):
        if ka[i]["ok"] != kb[i]["ok"]:
            print("  %-4s %s：%s → %s" % (i, kb[i]["name"],
                                          "✅" if ka[i]["ok"] else "❌",
                                          "✅" if kb[i]["ok"] else "❌"))
            if kb[i].get("soft"):
                print("       新答案软命中：%s" % kb[i]["soft"])
    print("\n转坏 %d 条%s；转好 %d 条%s" % (len(flip_bad), ("：" + "、".join(flip_bad)) if flip_bad else "",
                                           len(flip_good), ("：" + "、".join(flip_good)) if flip_good else ""))
    return 0


def rejudge(path: str) -> int:
    """对**已存下来的答案**重跑判分（不重问站点）。

    为什么需要它：判分器本身也会错（2026-09-23 就修了 4 处误判）。若改判据后直接重跑站点，
    "改前/改后"就是两把尺子量出来的，没法比。所以先把历史答案按新判据重判一遍，
    当作**同一把尺子下的改前基线**。
    """
    D = json.load(open(path, encoding="utf-8"))
    by_id = {c["id"]: c for c in _cases()}
    old_pass = D.get("pass")
    n_ok, flips = 0, []
    for row in D["cases"]:
        c = by_id.get(row["id"])
        if not c:
            n_ok += 1 if row.get("ok") else 0
            continue
        n_src = int(row.get("n_sources") or 0)
        # judge() 只看引用**条数**（min_sources），所以给个等长占位列表即可
        r = judge(c, row.get("answer") or "", [{}] * n_src)
        if bool(row.get("ok")) != bool(r["ok"]):
            flips.append((row["id"], row.get("name"), bool(row.get("ok")), bool(r["ok"]),
                          (r["miss_must"] + r["miss_groups"]), r["ban"]))
        row["ok"] = r["ok"]
        row["miss_must"] = r["miss_must"]
        row["ban"] = r["ban"]
        row["rejudged"] = True
        n_ok += 1 if r["ok"] else 0
    D["pass"] = n_ok
    D["rejudged_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out = path.replace(".json", "") + "_重判.json"
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(D, fh, ensure_ascii=False, indent=1)
    print("重判：%s（%s → %s）" % (path, old_pass, n_ok))
    for i, nm, a, b, miss, ban in flips:
        why = ("缺：" + ",".join(miss)) if miss else (("违规：" + str(ban)) if ban else "")
        print("  %-4s %-22s %s → %s %s" % (i, nm, "✅" if a else "❌", "✅" if b else "❌", why))
    print("  已写：%s" % out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="http://127.0.0.1:8011")
    ap.add_argument("--label", default="改后")
    ap.add_argument("--out", default="")
    ap.add_argument("--compare", nargs=2, default=None)
    ap.add_argument("--rejudge", default="", help="对已存结果按当前判据重判（不重问站点）")
    ap.add_argument("--only", default="", help="只跑这些 id，逗号分隔（调试用）")
    a = ap.parse_args()
    if a.compare:
        return compare(*a.compare)
    if a.rejudge:
        return rejudge(a.rejudge)
    site = a.site.rstrip("/")
    if not site.endswith("/hybrid_search"):
        site += "/hybrid_search"
    if a.only:
        keep = {x.strip() for x in a.only.split(",") if x.strip()}
        EXTRA[:] = [c for c in EXTRA if c["id"] in keep]
        b15.CASES[:] = [c for c in b15.CASES if c["id"] in keep]
    return run(site, a.label, a.out)


if __name__ == "__main__":
    sys.exit(main())
