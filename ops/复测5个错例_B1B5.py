#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复测用户反馈里的 5 个错例（B1–B5）：改完状态标记之后，模型还会不会答错。

每个错例的"正确结论"来自用户反馈原件（`_中间产物/用户反馈/反馈全文.txt`，UTF-16），
判定方式分三层，避免"看着像对了"：
  1. **必含词**：正确答案里的关键事实（如「已废止」「DB32/1072」「第一类污染物」「车间」）；
  2. **禁含断言**：改之前错在哪就禁什么 —— 但只禁**断言**，不禁"提及"：
     第一轮就吃过这个亏：`ban=["仍有效"]` 把模型那句「因此**不能回答**『仍有效』」判成违规（假失败），
     `ban=["DB33/2169"]` 把「浙江项目执行 DB33/2169……**不能将**江苏结论推广至全国」也判成违规。
     现在按**正则断言 + 否定/引号豁免**判断：出现在「不能/不得/而非/并非/不是」之后、
     或被「」“” 引起来的，都算"正确地提到它"，不算违规。
  3. **引用体检**：命中的块里已废止材料的条数、权威材料是否被召回。

用法：python 复测5个错例_B1B5.py <标签>        # 标签如 改后
输出：_工作记录/复测5个错例_<标签>.json
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SITE = "http://10.201.31.10:8011/hybrid_search"
OUT_PATH = ""                                       # --out 指定的结果路径（服务器上用）
ABOLISHED = ("已废止", "废止", "已失效", "已作废")
NEG_CUES = ("不", "非", "未", "无", "拒绝", "错误", "误", "不可", "勿")
LOOKAHEAD_CUES = ("不能", "不得", "不适用", "仅适用", "并非", "而非", "不等于", "只适用")
QUOTE_PAIRS = (("「", "」"), ("“", "”"), ("‘", "’"))
SENT_SPLIT = re.compile(r"[。；\n]")


def violation(text: str, rx: str, exempt: tuple = ()) -> str | None:
    """返回第一处**违规断言**的上下文；全是"正确地提到"就返回 None。

    按**句子**判（先切 。；换行），一句话里做三重豁免：
      · `exempt`：整句命中就不看（例如"浙江项目执行 DB33/2169"是在做省际对比，不是错答）；
      · 引号：`「仍有效」`／`“仍有效”` 是在引用这个说法，不是在主张；
      · 否定：断言前 20 字内有"不/非/未/无"等，或断言后 25 字内有"不能/不得/而非"。
    离线自测（拿上一轮的答案 + 用户原始错答双向验）见 `自测断言.py`。
    """
    for sent in SENT_SPLIT.split(text):
        if not sent.strip():
            continue
        if any(re.search(e, sent) for e in exempt):
            continue
        for m in re.finditer(rx, sent):
            s, e = m.start(), m.end()
            if (sent[max(0, s - 1):s], sent[e:e + 1]) in QUOTE_PAIRS:
                continue
            # 否定词在**匹配段内部**也要豁免：「执行一级标准，不能适用三级标准」里
            # 「不能」被正则一起吃进了 match，只看前后窗口会漏（自测断言脚本抓到的）
            if any(c in m.group(0) for c in NEG_CUES + LOOKAHEAD_CUES):
                continue
            if any(c in sent[max(0, s - 30):s] for c in NEG_CUES):
                continue
            if any(c in sent[e:e + 25] for c in LOOKAHEAD_CUES):
                continue
            return "%s ｜该句：%s" % (m.group(0), sent.strip()[:110])
    return None


CASES = [
    {
        "id": "B1", "name": "固废法还能用吗",
        "q": "《固体废物污染环境防治法》现在还能用吗？",
        "must_all": ["已废止"],
        # 2026-09-23 校准：真机答「…仅表示该学习要点文件**当前有效**，并不代表所引用的固废法仍然有效」
        # —— 这是**正确地**区分"来源文件的状态"与"法律的状态"，属带限定的正确表述，不该判违规。
        "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效",
                    (r"不", r"并非", r"并不", r"不代表", r"仅表示", r"之前", r"但",
                     r"学习要点", r"文件")),
                   (r"继续适用", ()), (r"未见废止", ()), (r"未显示废止", ()), (r"尚未废止", ())],
        "want_cite": ["生态环境法典"],
        "correct": "已废止（法典自2026-08-15施行，固废法同时废止）",
        "soft": ["法典", "1242", "2026年8月15日"],
    },
    {
        "id": "B2", "name": "环评法最近修订与是否适用",
        "q": "《环境影响评价法》最近一次修订是什么时候？现在还适用吗？",
        "must_all": ["已废止"],
        "ban_rx": [(r"(?:仍|目前|现在|当前)[^。；，]{0,4}(?:为)?有效", ()),
                   (r"继续适用", ()), (r"未见废止", ()), (r"未显示废止", ()),
                   (r"元数据[^。；]{0,24}(?:错误|有误|不一致|不准)", ()),
                   (r"(?:标注|标记)[^。；]{0,12}(?:错误|有误|不准确)", ())],
        "want_cite": ["生态环境法典"],
        "correct": "2018-12-29 第二次修正（对），但已随法典施行废止",
        "soft": ["法典", "1242", "2026年8月15日"],
    },
    {
        "id": "B3", "name": "GB3095 PM10 年均二级",
        "q": "GB3095-2012 PM10年平均二级浓度限值是多少？",
        "must_all": ["70"],
        "ban_rx": [(r"(?:现行|目前|现在)[^。；]{0,16}(?:为|是|执行)?\s*50\b", ())],
        "want_cite": ["3095"],
        "correct": "2012版 70 μg/m³；现行为 GB3095—2026，过渡期(2026-03-01～2030-12-31) 60，2031 起 50",
        "soft": ["2026", "60", "废止"],
    },
    {
        "id": "B4", "name": "江苏太湖 氨氮执行标准",
        "q": "江苏太湖地区城镇污水处理厂，氨氮执行国标一级A还是地方标准？",
        "must_all": ["DB32/1072"],
        # 只禁"断言江苏/太湖执行 DB33"；提到浙江、温州做省际对比时不豁免会误判
        "ban_rx": [(r"(?:执行|适用|依据|采用|应执行)[^。；]{0,12}DB33/2169", (r"浙江", r"温州", r"其他省", r"不同省"))],
        "want_cite": ["1072"],
        "correct": "江苏省 DB32/1072-2018；表1 氨氮 3(5)、表2 氨氮 4(6)，均严于 GB18918 一级A 的 5(8)",
        "soft": ["2018", "表1", "表2"],
    },
    {
        "id": "B5", "name": "GB8978 总汞采样口与分级",
        "q": "GB8978总汞0.05 mg/L，是排到哪类排放口？是三级标准吗？",
        "must_all": ["第一类污染物", "车间"],
        # 2026-09-23 校准：真机把 GB8978 自己的 4.1.3 原文（「排入设置二级污水处理厂的城镇排水系统的
        # 污水执行三级标准」）作为**背景**引用，并明确说"不能仅凭问题中的数值就认定其为三级标准"
        # —— 正确答案，原 ban 无例外词把它当真了。例外词限定在**引文语境**，断言式回答仍会被抓。
        "ban_rx": [(r"(?:属于|是|按|执行)[^。；]{0,10}三级标准",
                    (r"4\.1\.3", r"城镇排水", r"第二类", r"材料1中", r"规定",
                     r"不能", r"若", r"无法"))],
        "want_cite": ["8978"],
        "correct": "第一类污染物，一律在车间或车间处理设施排放口采样，不分一/二/三级",
        "soft": ["不分", "车间或车间处理设施"],
    },
]


def ask(q: str, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        SITE, data=json.dumps({"query": q}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


def main() -> int:
    # 2026-09-22：加 --site，便于对**影子实例**（如 8013 上新索引）复测，不影响原用法。
    # 2026-09-23：加 --out（服务器上没有工作区目录时用它指定结果路径）。
    global SITE, OUT_PATH
    args = sys.argv[1:]
    label = "改后"
    i = 0
    while i < len(args):
        if args[i] == "--site" and i + 1 < len(args):
            SITE = args[i + 1].rstrip("/")
            if not SITE.endswith("/hybrid_search"):
                SITE += "/hybrid_search"
            i += 2
            continue
        if args[i] == "--out" and i + 1 < len(args):
            OUT_PATH = args[i + 1]
            i += 2
            continue
        if not args[i].startswith("--"):
            label = args[i]
        i += 1
    print("目标：%s（标签：%s）" % (SITE, label))
    out_rows = []
    n_ok = n_bad = 0
    for c in CASES:
        t0 = time.time()
        try:
            d = ask(c["q"])
        except Exception as e:
            print(f"\n【{c['id']}】{c['name']}  ❌ 请求失败：{e}")
            n_bad += 1
            continue
        ans = d.get("answer") or ""
        srcs = d.get("sources") or []
        abolished = [s for s in srcs if str(s.get("status") or "") in ABOLISHED]
        # 2026-09-22：必含词改成**忽略空格**比对。起因：新索引（表格回填后）让模型按 PDF 原文
        # 写成「DB 32/1072-2018」（标准号里有空格），而断言写的是「DB32/1072」——判成未通过，
        # 但答案内容其实更准（明确"执行地方标准、而非国标一级A"）。这里要比的是"答对没答对"，
        # 不是"空格对不对"，所以两边都去掉空白再比。
        squeeze = lambda s: re.sub(r"\s+", "", str(s))          # noqa: E731
        ans_c = squeeze(ans)
        hit_must = [w for w in c["must_all"] if squeeze(w) in ans_c]
        hit_ban = [v for v in (violation(ans, rx, ex) for rx, ex in c.get("ban_rx", [])) if v]
        cite_txt = " ".join(str(s.get("title") or "") + str(s.get("standard_id") or "") +
                            str(s.get("text") or "")[:200] for s in srcs)
        cite_c = squeeze(cite_txt)
        hit_cite = [w for w in c.get("want_cite", []) if squeeze(w) in cite_c]
        hit_soft = [w for w in c.get("soft", []) if squeeze(w) in ans_c]
        ok = len(hit_must) == len(c["must_all"]) and not hit_ban
        n_ok += 1 if ok else 0
        n_bad += 0 if ok else 1
        print(f"\n{'='*96}\n【{c['id']}】{c['name']}　{'✅ 通过' if ok else '❌ 未通过'}"
              f"　引用 {len(srcs)} 条（其中已废止 {len(abolished)} 条）　{time.time()-t0:.0f}s")
        print(f"  问题：{c['q']}")
        print(f"  应然：{c['correct']}")
        print(f"  实答：{ans[:400].replace(chr(10),' ')}")
        print(f"  必含词命中 {hit_must}/{c['must_all']}　违规断言 {hit_ban or '无'}"
              f"　期望引用命中 {hit_cite or '无'}　加分项命中 {hit_soft or '无'}")
        for s in srcs[:6]:
            st = str(s.get("status") or "") or "（空）"
            print(f"    [{s.get('index')}] status={st:<6} {str(s.get('title'))[:46]}")
        out_rows.append({"id": c["id"], "name": c["name"], "q": c["q"], "answer": ans,
                         "ok": ok, "must_hit": hit_must, "ban_hit": hit_ban,
                         "cite_hit": hit_cite, "soft_hit": hit_soft,
                         "n_sources": len(srcs), "n_abolished": len(abolished),
                         "sources": [{k: s.get(k) for k in
                                      ("index", "title", "status", "standard_id", "doc_type")}
                                     for s in srcs]})
    print(f"\n{'='*96}\n【{label}】通过 {n_ok} / 未通过 {n_bad}")
    # 2026-09-23 修：原先写死 WS/_工作记录/…，上传到服务器（WS 解析成 "/"）就会
    # FileNotFoundError 崩掉，而且**结论已经算完了**才崩，很误导。改成：
    # 优先 --out；否则用工作区路径（存在才写）；再否则退到当前目录。
    out = None
    if OUT_PATH:
        out = Path(OUT_PATH)
    else:
        cand = WS / "_工作记录" / f"复测5个错例_{label}.json"
        out = cand if cand.parent.is_dir() else Path(f"复测5个错例_{label}.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"label": label, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                   "rows": out_rows}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"→ {out.resolve()}")
    except OSError as exc:
        print(f"（结果文件没写成：{exc}；上面结论有效）")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
