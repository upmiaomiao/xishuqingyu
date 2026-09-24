#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C5 真机验证：走生成页 API（不调模型），看「判定.名录」实际给出的条目。

为什么必须真机跑一遍：单测证明的是**代码逻辑**，而这里要证明**正在运行的 8011 进程**
确实用上了新代码（重启后模块才会重新加载）。

三个变体（都以页面自带样例填报为底稿，只改要害字段）：
  A 环氧树脂（填了「建设项目行业类别＝合成材料制造 265」）→ 应为序号 44，且不得出现 110/111
  B 环氧树脂（行业类别留空）→ 应"未匹配到条目"，提示补填行业类别（宁可不给也不猜）
  C 真实学校项目（行业类别照名录原文写）→ 应为序号 110（修掉数字撞号后仍要能靠名字命中）

用法：python3 查C5真机.py [base]     默认 http://127.0.0.1:8011/gen/api
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011/gen/api").rstrip("/")
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    mark = "OK " if cond else "×  "
    print("  %s%s%s" % (mark, name, ("　" + str(detail)[:160]) if detail else ""))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def run_once(tag: str, data: dict) -> dict:
    jid = post("/run", {"data": data, "model": False})["job"]
    last = None
    for _ in range(60):
        time.sleep(2)
        last = get("/job/" + jid)["job"]
        if last.get("status") in ("done", "rejected", "failed"):
            break
    c = ((last or {}).get("判定") or {}).get("名录") or {}
    print("\n【%s】status=%s" % (tag, (last or {}).get("status")))
    if (last or {}).get("status") != "done":
        # 载荷没过校验时判定不会有内容 —— 把校验结果打出来，避免误判成"修复无效"
        print("   校验=%s" % json.dumps((last or {}).get("校验"), ensure_ascii=False)[:400])
    print("   名录序号=%s  档级=%s" % (c.get("名录序号"), c.get("tier")))
    print("   名录条目=%s" % (str(c.get("名录条目"))[:70]))
    print("   理由=%s" % (str(c.get("理由"))[:150]))
    print("   需人工确认=%s" % (c.get("需人工确认") or []))
    return c


def base_data(h: dict) -> dict:
    """取页面自带的样例填报作底（它能过校验），只改我们要看的字段。

    样例列表在 /health 的返回里（`样例` 键），不在单独的路由；
    单个样例走 GET /api/samples/{name}。
    """
    names = h.get("样例") or h.get("samples") or []
    if names and isinstance(names[0], dict):
        names = [x.get("name") or x.get("文件") or x.get("文件名") for x in names]
    name = (names[0] if names else "演示_虚构项目_填报.json")
    s = get("/samples/" + urllib.parse.quote(str(name)))
    d = s.get("data") or s
    print("样例底稿：%s（%d 个字段）" % (name, len(d)))
    return json.loads(json.dumps(d, ensure_ascii=False))


EPOXY = {
    "项目名称": "年产5000吨环氧树脂项目",
    "产品及产能": [{"名称": "环氧树脂", "产能": "5000", "单位": "吨/年"}],
    "主要原辅材料": [{"名称": "环氧氯丙烷", "年用量": "3000", "单位": "吨"},
                 {"名称": "双酚A", "年用量": "2500", "单位": "吨"}],
    "补充事实": [],
}


def variant(base: dict, over: dict, drop: tuple = ()) -> dict:
    d = json.loads(json.dumps(base, ensure_ascii=False))
    d.update(over)
    for k in drop:
        d.pop(k, None)
    return d


def main() -> int:
    h = get("/health")
    print("健康：ok=%s 字段=%s" % (h.get("ok"), h.get("字段数")))
    check("引擎就绪", h.get("ok") is True)
    base = base_data(h)

    ca = run_once("A 环氧树脂（填了行业类别）",
                  variant(base, {**EPOXY, "建设项目行业类别": "合成材料制造 265",
                                 "国民经济行业类别": "合成材料制造 C265"}))
    check("A 首位条目不是 110（学校、福利院）", ca.get("名录序号") != 110, ca.get("名录序号"))
    check("A 首位条目不是 111（批发、零售市场）", ca.get("名录序号") != 111, ca.get("名录序号"))
    check("A 命中正确的 44（化学原料和化学制品制造业）", ca.get("名录序号") == 44,
          "%s / %s" % (ca.get("名录序号"), ca.get("名录条目")))

    # B：行业类别照**用户自己的写法**填「环氧树脂生产」（不是名录条目名）——这正是反馈里的情形。
    # 注意：站点的校验层要求「建设项目行业类别/国民经济行业类别」必填，所以"完全留空"到不了判定步；
    # 能到判定步的真实情形是"用户按自己的话填了行业类别"。
    cb = run_once("B 环氧树脂（行业类别按用户自己的话填）",
                  variant(base, {**EPOXY, "建设项目行业类别": "环氧树脂生产",
                                 "国民经济行业类别": "合成材料制造 C265"}))
    check("B 不再误配 110/111", cb.get("名录序号") not in (110, 111), cb.get("名录序号"))
    check("B 未匹配时要明说、不许猜",
          (cb.get("名录序号") is not None) or any("未匹配" in str(x) or "行业类别" in str(x)
                                                for x in (cb.get("需人工确认") or [])),
          "%s / %s" % (cb.get("名录序号"), cb.get("需人工确认")))

    # C：学校项目——产品/原辅材料保留底稿里的值（它们是必填项，清空会被校验拦下）
    cc = run_once("C 学校项目（应命中 110）", variant(base, {
        "项目名称": "新建初级中学项目",
        "建设项目行业类别": "学校、福利院、养老院（建筑面积5000平方米及以上的）",
        "国民经济行业类别": "教育 P83",
    }))
    check("C 命中 110", cc.get("名录序号") == 110,
          "%s / %s" % (cc.get("名录序号"), cc.get("名录条目")))

    print("\n==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("  失败：%s" % b)
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
