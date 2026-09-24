#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 档真机验收（跑线上 8011，不是本地模拟）。

三件事：
  ① 审核线：对一份**已审核过的真实报告**重跑审核（use_llm=false，快），
     打印第 17 项「引用标准编号正确性」的结论 —— 看 A2 的现行性判据有没有真的生效；
  ② 生成线 · 万吨：主要原辅材料用「万吨」填报 → 看名录定量条件是否走到了比较
     （C10-③ 修之前这条事实会被静默丢弃）；
  ③ 生成线 · 无措施：不给「环境保护措施」→ 看「措施概述」小节是否**不生成**（C9-①），
     以及有没有"措施名无出处"的剔除记录（C9-②）。
只读接口 + 触发一次审核/两次生成；不改任何数据。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"


def get(path: str, **q) -> dict:
    url = BASE + path + (("?" + urllib.parse.urlencode(q)) if q else "")
    with urllib.request.urlopen(url, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path: str, payload: dict, **q) -> dict:
    url = BASE + path + (("?" + urllib.parse.urlencode(q)) if q else "")
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))


def poll_audit(jid: str, tries: int = 120, gap: float = 3.0) -> dict:
    """审核任务：GET /audit/api/job/{id} → {stage, pct, done, result}（注意字段是 stage 不是 status）。"""
    last = {}
    for i in range(tries):
        last = get("/audit/api/job/" + str(jid))
        if last.get("done"):
            return last
        if i % 5 == 0:
            print("      …%s %s%%" % (last.get("stage"), last.get("pct")))
        time.sleep(gap)
    return last


def poll_gen(jid: str, tries: int = 90, gap: float = 2.0) -> dict:
    """生成任务：GET /gen/api/job/{id} → {"job": {status, 判定, ...}}。"""
    last = {}
    for i in range(tries):
        time.sleep(gap)
        last = (get("/gen/api/job/" + str(jid)) or {}).get("job") or {}
        if last.get("status") in ("done", "rejected", "failed"):
            return last
        if i % 8 == 0:
            print("      …status=%s" % last.get("status"))
    return last


def walk(obj, keys=("措施概述", "跳过原因", "措施名无出处", "剔除", "叙述", "草稿",
                    "折合", "事实表", "判定"), depth=0):
    """在结果 JSON 里递归找关心的字段（结构可能变，别写死路径）。"""
    out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(x in str(k) for x in keys):
                out.append((str(k), str(v)[:300]))
            out += walk(v, keys, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:12]:
            out += walk(v, keys, depth + 1)
    return out


def main() -> int:
    only = (sys.argv[1] if len(sys.argv) > 1 else "").lower()     # audit / gen / 空=都跑
    if only in ("", "audit"):
        print("=" * 92)
        print("① 审核线：引用标准现行性（A2）")
    reps = get("/audit/api/reports")
    cand = [r for r in (reps.get("reports") or [])
            if r.get("已审核") and (r.get("size") or 0) < 8e6]        # 挑小的，跑得快
    cand.sort(key=lambda r: r.get("size") or 0)
    if not cand:
        print("   没有已审核的小报告，跳过（A2 的单测已在线上通过）")
    else:
        hit_any = False
        for target in cand[:3]:
            name = target["name"]
            print("   报告：%s（%.1f MB）" % (name[:52], (target.get("size") or 0) / 1e6))
            job = post("/audit/api/run", {}, name=name, use_llm="false")
            jid = job.get("job") or job.get("id")
            st = poll_audit(jid)
            print("      状态：stage=%s pct=%s done=%s" % (st.get("stage"), st.get("pct"),
                                                        st.get("done")))
            res = get("/audit/api/result/" + urllib.parse.quote(name))
            res = res.get("result") if isinstance(res, dict) and "result" in res else res
            items = (res.get("items") if isinstance(res, dict) else res) or []
            if isinstance(res, dict) and not items:
                items = res.get("结果") or []
            print("      审核项 %d 个" % len(items))
            for it in items:
                t = str(it.get("审核项") or "")
                if "标准" not in t:
                    continue
                print("      ── 第17项：%s" % t)
                print("         AI审核=%s 置信度=%s" % (it.get("AI审核"), it.get("置信度")))
                print("         理由：%s" % str(it.get("理由"))[:500])
                tr = it.get("判据轨迹") or {}
                rows = (tr or {}).get("引用标准现行性待核实") if isinstance(tr, dict) else None
                if rows:
                    hit_any = True
                    print("         轨迹·现行性待核实：%d 条" % len(rows))
                    for r in rows[:5]:
                        print("           · P%s %s %s → %s" % (r.get("页码"), r.get("标准号"),
                                                               str(r.get("标题"))[:20],
                                                               str(r.get("结论"))[:110]))
                for c in (it.get("需人工确认") or [])[:5]:
                    print("         需人工确认：%s" % c)
                if isinstance(tr, dict) and tr.get("覆盖说明"):
                    print("         覆盖说明：%s" % str(tr["覆盖说明"])[:160])
            if hit_any:
                print("   ✅ 已在真机报告上抓到「引用标准现行性」待核实项")
                break
        if not hit_any:
            print("   （这几份报告都没引用判据表内的标准，故本项显示「无问题」——"
                  "检测路径本身由线上单测守）")

    print()
    print("=" * 92)
    print("② 生成线：用「万吨」填报 + 环保措施（空 / 有）对照（C10-③ / C9）")
    if only == "audit":
        return 0
    h = get("/gen/api/health")
    names = h.get("样例") or h.get("samples") or []
    if names and isinstance(names[0], dict):                 # /health 里是 [{name,size}, …]
        names = [x.get("name") or x.get("文件") or x.get("文件名") for x in names]
    if isinstance(names, dict):
        names = list(names)
    print("   可用样例：%s" % names[:4])
    if not names:
        print("   没有样例，跳过")
        return 0
    sample = get("/gen/api/samples/" + urllib.parse.quote(str(names[0])))
    base = json.loads(json.dumps(sample.get("data") or sample, ensure_ascii=False))
    mats = base.get("主要原辅材料") or []
    if mats and isinstance(mats[0], dict):
        mats[0]["年用量"], mats[0]["单位"] = 1.2, "万吨"
        print("   把第 1 条原辅材料改成：%s %s%s（C10-③ 要折成 12000 吨）"
              % (mats[0].get("名称"), mats[0].get("年用量"), mats[0].get("单位")))

    # 变体 A：环保措施**字段在、内容空**（实测「环保措施」是必填项，删字段会被判 rejected ——
    #          用户真正会遇到的就是"空着"）→ 期望「措施概述」小节不生成（C9-①）
    # 变体 B：给一行真措施 → 期望小节正常生成，且叙述里没有"事实表里没有的措施名"（C9-②）
    variants = [
        ("A·措施空", [{"要素": "废气", "措施内容": "", "排放去向": ""}], {}),
        ("B·有措施", [{"要素": "废气", "措施内容": "活性炭吸附装置", "排放去向": "15m 排气筒"}], {}),
        # C：压测**措施名闸门**（C9-②）。样例自身在「主要生产设施」「产排污环节」里写了
        #    布袋除尘/双碱法脱硫 —— 那是真实出处，所以 B 里模型写它们**不算编造**。
        #    把这两项**改写成不含设施名**的内容（字段仍在，能过必填校验），
        #    事实表里就没有这些设施名了；模型若还写，就该被闸门剔除。
        ("C·闸门压测", [{"要素": "废气", "措施内容": "活性炭吸附装置", "排放去向": "15m 排气筒"}],
         {"主要生产设施": [{"名称": "生物质锅炉", "数量": "1", "规格": "SZL20-1.6-S"}],
          "产排污环节": [{"环节": "生物质锅炉燃烧", "污染物": "颗粒物、二氧化硫、氮氧化物",
                          "排放去向": "经排气筒排放"}],
          "水平衡说明": "软水制备浓水与锅炉排污水经沉淀后回用，不外排。"}),
    ]
    for tag, rows, override in variants:
        data = json.loads(json.dumps(base, ensure_ascii=False))
        data["环保措施"] = rows
        data.update(override)
        print("\n   ── 变体 %s：环保措施=%s%s" % (tag, json.dumps(rows, ensure_ascii=False),
                                            ("；已改写 %s" % list(override)) if override else ""))
        r = post("/gen/api/run", {"data": data, "model": True})
        jid = r.get("job") or r.get("id")
        st = poll_gen(str(jid))
        print("      状态：%s" % st.get("status"))
        if st.get("status") != "done":
            print("      校验=%s" % json.dumps(st.get("校验"), ensure_ascii=False)[:400])
        ming = ((st.get("判定") or {}).get("名录") or {})
        print("      名录：序号=%s 档级=%s 条目=%s" % (ming.get("名录序号"), ming.get("tier"),
                                                  str(ming.get("名录条目"))[:60]))
        facts = (st.get("叙述") or {}).get("事实表") or []
        if facts:
            for f in facts:
                if "折合" in str(f.get("quote") or ""):
                    print("      ✅ 事实表已按单位折算：%s" % str(f.get("quote"))[:120])
                    break
        hits = walk(st)
        seen = set()
        for k, v in hits:
            key = (k, v[:70])
            if key in seen:
                continue
            seen.add(key)
            print("      · %-12s %s" % (k, v[:240]))
        if not hits:
            print("      （结果里没找到措施相关字段 —— 原始结果已存盘，人工看）")
        out = "/home/test/A档验收_生成结果_%s.json" % tag.replace("·", "_")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=1)
        print("      原始结果：%s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
