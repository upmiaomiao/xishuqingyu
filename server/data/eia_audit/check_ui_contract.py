#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核界面与后端接口的**字段契约**测试。

为什么需要：界面"打开是空白"最常见的原因不是样式，而是**字段名对不上**
（后端叫 `环评文件`、前端读 `文件`）。这类问题只有点开浏览器才发现，
而且不一定点得到那一步。这里把前端源码里读的字段逐个抽出来，
拿真实接口返回的 JSON 去核对。

跑法（服务器上）：/home/test/fagui_serve/.venv/bin/python /data/eia_audit/check_ui_contract.py
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011/audit/api"
UI = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js"
OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  √ " + name)
    else:
        FAIL += 1
        print("  × " + name + " " + extra)


def get(path):
    r = urllib.request.urlopen(BASE + path, timeout=120)
    return json.loads(r.read().decode("utf-8"))


def post(path):
    req = urllib.request.Request(BASE + path, method="POST")
    r = urllib.request.urlopen(req, timeout=120)
    return json.loads(r.read().decode("utf-8"))


def main():
    ui = open(UI, encoding="utf-8").read()

    print("[1] 报告清单 /api/reports")
    rep = get("/reports")
    check("ok=true", rep.get("ok") is True)
    check("reports 非空", bool(rep.get("reports")))
    first = rep["reports"][0]
    for f in ("name", "size"):
        check("reports[].{} 存在".format(f), f in first, str(list(first)))

    print("[2] 跑一次审核（关模型，快）")
    name = first["name"]
    run = post("/run?name=" + urllib.parse.quote(name) + "&use_llm=false")
    check("提交 ok", run.get("ok") is True, str(run)[:120])
    job = run["job"]
    res = None
    for _ in range(120):
        j = get("/job/" + job)
        for f in ("done", "pct", "stage"):
            if f not in j:
                check("job.{} 存在".format(f), False, str(list(j)))
                break
        if j.get("done"):
            check("job.error 为空", not j.get("error"), str(j.get("error")))
            res = j.get("result")
            break
        time.sleep(1)
    check("任务完成并带 result", bool(res))
    if not res:
        return 1

    print("[3] result 顶层字段（界面直接读的）")
    for f in ("file", "统计", "items", "判据输入", "报告自述", "专项评价自述", "抽取概况", "抽取明细"):
        check("result.{}".format(f), f in res, "缺字段")
    for f in ("name", "pages", "项目名称", "环评文件类型"):
        check("result.file.{}".format(f), f in res.get("file", {}), str(list(res.get("file", {}))))
    check("统计 覆盖五个状态",
          all(s in res.get("统计", {}) for s in
              ("存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用")),
          str(res.get("统计")))

    print("[4] 每个审核项的字段")
    items = res.get("items", [])
    check("items 非空", bool(items))
    need = ["审核项", "类别", "AI审核", "环评文件", "置信度", "参考依据", "理由", "证据", "需人工确认"]
    missing = set()
    for it in items:
        for f in need:
            if f not in it:
                missing.add(f)
    check("18 项都含全部字段", not missing, "缺 " + str(sorted(missing)))
    check("类别取值在界面分组表里",
          all(it["类别"] in ("法规符合性", "技术导则符合性", "环境风险（HJ 169）", "报告质量")
              for it in items),
          str(sorted({it["类别"] for it in items})))
    check("AI审核 取值是五种状态之一",
          all(it["AI审核"] in ("存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用")
              for it in items),
          str(sorted({it["AI审核"] for it in items})))

    print("[5] 证据字段（页码链接靠它）")
    ev = [e for it in items for e in it.get("证据", [])]
    check("有证据条目", bool(ev))
    miss = set()
    for e in ev:
        for f in ("page", "quote"):
            if f not in e:
                miss.add(f)
    check("证据含 page/quote", not miss, "缺 " + str(sorted(miss)))
    check("证据 page 是整数且在报告页数内",
          all(isinstance(e.get("page"), int) and 1 <= e["page"] <= res["file"]["pages"] for e in ev),
          "存在越界页码")

    print("[6] 人工复核 / 保存 / 导出")
    rv = get("/review/" + urllib.parse.quote(name))
    check("review ok", rv.get("ok") is True)
    check("review.items 是对象", isinstance(rv.get("items"), dict), str(type(rv.get("items"))))
    k = items[0]["审核项"]
    body = json.dumps({"name": name, "items": {k: {"人工修改": "无问题", "备注": "契约测试"}}}).encode()
    req = urllib.request.Request(BASE + "/save", data=body, method="POST",
                                headers={"Content-Type": "application/json"})
    sv = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    check("save ok 且返回条数", sv.get("ok") is True and sv.get("saved") == 1, str(sv)[:120])
    rv2 = get("/review/" + urllib.parse.quote(name))
    check("保存后能读回", k in rv2.get("items", {}), str(list(rv2.get("items", {})))[:120])
    ex = get("/export/" + urllib.parse.quote(name) + "?fmt=csv")
    check("export ok 且给文件名", ex.get("ok") is True and ex.get("file"), str(ex)[:120])
    raw = urllib.request.urlopen(BASE + "/download/" + urllib.parse.quote(ex["file"]), timeout=60).read()
    check("下载内容带 UTF-8 BOM（Excel 直接打开不乱码）", raw[:3] == b"\xef\xbb\xbf")
    check("CSV 含人工复核列", "人工修改".encode() in raw)

    print("[7] 前端源码里读的字段都在真实返回里出现过")
    # 有些字段只在特定情况下出现：如「时间」只在保存过人工复核后、
    # 「正则/模型/正则页码」只在抽取冲突（冲突）非空时才有。
    # 所以判据放宽为：**在真实返回里出现过，或后端源码里确实会产出该键**。
    payload = json.dumps(res, ensure_ascii=False) + json.dumps(rv2, ensure_ascii=False) + json.dumps(ex, ensure_ascii=False)
    src = ""
    for d, _, fs in os.walk("/data/eia_audit"):
        if "__pycache__" in d or "_cache" in d:
            continue
        for fn in fs:
            if fn.endswith(".py"):
                try:
                    src += open(os.path.join(d, fn), encoding="utf-8").read()
                except OSError:
                    pass
    keys = set(re.findall(r"\['([^']{2,20})'\]", ui)) | set(re.findall(r"\.(\w{2,20})\b", ui))
    read_fields = {k for k in keys if re.search(r"[\u4e00-\u9fff]", k) or k in
                   ("name", "size", "pages", "stage", "pct", "done", "error", "result",
                    "items", "file", "page", "quote", "source", "mark", "saved", "detail")}
    # 前端自身的局部变量/属性（如 state/review/filterState）不算接口字段
    local = {"state", "review", "result", "name", "running", "job", "filterState", "onlyNeed",
             "eviAll", "timer", "reports", "element", "reload", "render", "destroy", "run",
             "length", "value", "checked", "style", "display", "textContent", "innerHTML",
             "dataset", "classList", "onclick", "onchange", "parentNode", "firstChild",
             "appendChild", "createElement", "querySelector", "querySelectorAll", "forEach",
             "toFixed", "slice", "filter", "some", "map", "join", "indexOf", "keys", "push",
             "split", "test", "exec", "replace", "stringify", "parse", "state", "file", "size"}
    miss = sorted(f for f in read_fields - local if f not in payload and ('"%s"' % f) not in src
                  and ("'%s'" % f) not in src)
    check("界面读的字段名与后端一致（{} 个）".format(len(read_fields - local)), not miss,
          "对不上：" + str(miss))

    print("\n==== 通过 " + str(OK) + " / 失败 " + str(FAIL) + " ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())