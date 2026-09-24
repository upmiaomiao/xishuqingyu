#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图谱「推荐关键词」实测（打线上 HTTP）。

用户原话：「知识图谱，我也不知道有哪些字段，你让我自己搜索好像不太现实，
可以放几个推荐的关键词」。

这个测试的核心不是"接口返回 200"，而是一条**语义断言**：
**推荐出去的每一个词，拿去搜索都必须真的有结果。**
推荐一个搜不到的词的后果，比不给推荐更糟 —— 用户会以为图谱是坏的。
所以下面会对每个例子真发一次 /kg/search 验证。

用法：
  python 查图谱推荐词_实测.py --base http://10.201.31.10:8011
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"
ok = 0
bad = []


def say(m):
    sys.stdout.write(m + "\n")
    sys.stdout.flush()


def check(name, cond, extra=""):
    global ok
    if cond:
        say("  OK   %s%s" % (name, ("　" + extra) if extra else ""))
        ok += 1
    else:
        say("  ★    %s%s" % (name, ("　" + extra) if extra else ""))
        bad.append(name)


def get(path, timeout=30):
    url = BASE + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()
    BASE = a.base.rstrip("/")
    say("目标：%s" % BASE)
    say("")

    say("=== 1. /kg/suggest 基本形状 ===")
    try:
        st, d = get("/kg/suggest?per_label=4")
    except Exception as e:
        say("  ★    请求失败：%r" % (e,))
        say("")
        say("==== 通过 0 / 失败 1 ====")
        sys.exit(1)
    check("HTTP 200", st == 200, "status=%s" % st)
    check("ok 为真", isinstance(d, dict) and d.get("ok") is True)
    check("有 types 数组", isinstance(d.get("types"), list) and len(d["types"]) > 0,
          "类型数=%s" % (len(d.get("types") or [])))
    check("total_nodes 是正数", isinstance(d.get("total_nodes"), int) and d["total_nodes"] > 0,
          "节点数=%s" % d.get("total_nodes"))
    check("total_links 是正数", isinstance(d.get("total_links"), int) and d["total_links"] > 0,
          "关系数=%s" % d.get("total_links"))
    check("type_count 与 types 长度一致", d.get("type_count") == len(d.get("types") or []),
          "%s vs %s" % (d.get("type_count"), len(d.get("types") or [])))

    types = d.get("types") or []
    if not types:
        say("")
        say("==== 通过 %d / 失败 %d ====" % (ok, len(bad)))
        sys.exit(1)

    say("")
    say("=== 2. 每种类型的结构 ===")
    check("每种类型都有 label", all(t.get("label") for t in types))
    check("每种类型都有 count 且为正",
          all(isinstance(t.get("count"), int) and t["count"] > 0 for t in types))
    check("每种类型都有 examples 且非空",
          all(isinstance(t.get("examples"), list) and t["examples"] for t in types))
    check("每种类型每种最多 per_label=4 个",
          all(len(t["examples"]) <= 4 for t in types),
          "最大=%d" % max(len(t["examples"]) for t in types))
    # 度数必须 > 0：没有关系的节点点进去是一张只有它自己的图，像坏了
    all_ex = [e for t in types for e in t["examples"]]
    check("所有例子的 degree 都 > 0（没有孤立节点被推荐）",
          all(isinstance(e.get("degree"), int) and e["degree"] > 0 for e in all_ex),
          "最小 degree=%s" % min((e.get("degree") or 0) for e in all_ex))
    check("例子里没有单字名（单字太泛，搜出来是一团）",
          all(len(e.get("name") or "") >= 2 for e in all_ex))
    check("例子都有 id 和 name", all(e.get("id") and e.get("name") for e in all_ex))

    # ★ 这一条是第一版实测**真的踩到**的：Article 节点没有 name 属性，
    #   名字回退成了节点 id，推荐出来是
    #   「Article_混合存放危险废物与非危险废物类案件学习要点_第一百一十二条_e8e3d7a2」。
    #   用户看到只会觉得图谱坏了。现在要么拼出「《文件》第N条」，要么不推荐。
    PREFIXES = ("Article_", "Document_", "Law_", "Standard_", "Case_", "Pollutant_",
                "Organization_", "Region_", "Industry_", "Violation_", "Penalty_",
                "Regulation_", "TreatmentTech_", "PollutionSource_")
    idlike = [e["name"] for e in all_ex if e["name"].startswith(PREFIXES)]
    check("★ 推荐词里没有回退成节点 id 的（看起来像乱码）", not idlike,
          ("像 id 的：" + "; ".join(idlike[:3])) if idlike else "全是人话名字")
    check("★ 推荐词里没有以 _ 结尾的截断名（属性被截到 500 字符的痕迹）",
          not [e["name"] for e in all_ex if e["name"].endswith("_")],
          "无" if not [e for e in all_ex if e["name"].endswith("_")] else "有")
    check("推荐词名字长度都 >= 2", all(len(e["name"]) >= 2 for e in all_ex))
    check("没有整段超长名字（> 60 字，说明是正文片段冒充名字）",
          not [e["name"] for e in all_ex if len(e["name"]) > 60],
          "最长 %d 字" % max(len(e["name"]) for e in all_ex))

    # 类型按实体数降序：用户先看到"这里最多的是什么"
    counts = [t["count"] for t in types]
    check("类型按实体数降序排列", counts == sorted(counts, reverse=True),
          "前 5 个=%s" % counts[:5])

    say("")
    say("=== 3. 类型中文名覆盖情况（这回答了「有哪些字段」）===")
    ZH = {
        "Law": "法律", "Regulation": "行政法规", "Standard": "标准",
        "Article": "条款", "Pollutant": "污染物", "PollutionSource": "污染源",
        "Industry": "行业", "TreatmentTech": "治理技术", "Violation": "违法行为",
        "Penalty": "行政处罚", "Case": "案例", "Organization": "机构",
        "Region": "区域", "Document": "文档",
    }
    unknown = [t["label"] for t in types if t["label"] not in ZH]
    say("  实际类型（%d 种）：" % len(types))
    for t in types:
        say("      %-18s %-6s %5d 个   例：%s" % (
            t["label"], ZH.get(t["label"], "?"), t["count"],
            "、".join(e["name"][:14] for e in t["examples"][:2])))
    check("所有类型都有中文名（界面不会露出英文）", not unknown,
          ("缺：" + ",".join(unknown)) if unknown else "全有")

    say("")
    say("=== 4. ★ 核心断言：每个推荐词拿去搜索都必须真的有结果 ===")
    # 这是整个功能成立的前提。抽前 14 个跨类型推荐词（前端"推荐关键词"那一排
    # 就是按 degree 排序取前 14 个）逐个真搜一遍。
    flat = sorted(all_ex, key=lambda e: -(e.get("degree") or 0))[:14]
    miss = []
    for e in flat:
        try:
            st2, d2 = get("/kg/search?query=%s&depth=0&limit=70" %
                          urllib.parse.quote(e["name"]))
        except Exception as ex:
            miss.append((e["name"], "请求失败 %r" % (ex,)))
            continue
        matched = (d2 or {}).get("matched") if isinstance(d2, dict) else None
        if not matched:
            miss.append((e["name"], "matched=%s" % matched))
    check("前 14 个推荐词全部搜得到", not miss,
          ("搜不到：" + "; ".join("%s(%s)" % m for m in miss)) if miss else "14/14 命中")
    say("      抽查明细：")
    for e in flat[:6]:
        st2, d2 = get("/kg/search?query=%s&depth=0&limit=70" % urllib.parse.quote(e["name"]))
        hit = (d2 or {}).get("matched")
        nodes = (d2 or {}).get("nodes") or []
        # 断言要查"精确同名节点在不在**命中集合**里"，
        # 而不是"nodes[0] 是不是它"—— nodes 是按 BFS 展开的子图，
        # 第一个往往是邻居而不是命中项。第一版就是这么写错的，误报了 4 条。
        matched_nodes = [n for n in nodes if n.get("matched")]
        exact = any(n.get("name") == e["name"] for n in matched_nodes)
        first_matched = (matched_nodes[0].get("name") if matched_nodes else "")
        say("        %-22s → matched=%-4s 精确同名在命中里=%s（第一个命中：%s）" %
            (e["name"][:22], hit, exact, first_matched[:22]))
        if not exact:
            bad.append("推荐词的精确同名不在命中集合里：" + e["name"])

    say("")
    say("=== 5. 按类型抽查：每类的第一个例子也要搜得到 ===")
    miss2 = []
    for t in types:
        e = t["examples"][0]
        st2, d2 = get("/kg/search?query=%s&depth=0&limit=70" % urllib.parse.quote(e["name"]))
        if not (isinstance(d2, dict) and d2.get("matched")):
            miss2.append("%s/%s" % (t["label"], e["name"]))
    check("每类代表实体都搜得到", not miss2,
          ("搜不到：" + "; ".join(miss2)) if miss2 else "%d 类全命中" % len(types))

    say("")
    say("=== 6. 反向断言：编造的词必须搜不到 ===")
    # 如果随便什么词都有结果，那上面第 4 条就毫无意义 —— 说明 matched
    # 根本没在起作用（比如后端退回"度数最高的 12 个"时 matched 会是 0）。
    fake = "紫电青霜玄铁重剑不存在的实体xyzzy"
    st3, d3 = get("/kg/search?query=%s&depth=0&limit=70" % urllib.parse.quote(fake))
    m3 = (d3 or {}).get("matched") if isinstance(d3, dict) else None
    check("编造的词 matched 为 0", m3 == 0, "matched=%s" % m3)

    say("")
    say("=== 7. per_label 参数边界 ===")
    for n in (1, 8):
        st4, d4 = get("/kg/suggest?per_label=%d" % n)
        got = max((len(t["examples"]) for t in ((d4 or {}).get("types") or [])), default=0)
        check("per_label=%d 生效" % n, st4 == 200 and got <= n, "实际最多=%d" % got)
    try:
        get("/kg/suggest?per_label=99")
        check("per_label=99 被拒（上限 8）", False, "居然返回了 200")
    except urllib.error.HTTPError as e:
        check("per_label=99 被拒（上限 8）", e.code == 422, "HTTP %s" % e.code)

    say("")
    say("==== 通过 %d / 失败 %d ====" % (ok, len(bad)))
    if bad:
        for b in bad:
            say("  失败：" + b)
        sys.exit(1)


if __name__ == "__main__":
    main()
