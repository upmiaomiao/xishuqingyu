"""第 2 项实测：/doc/info 探测 + /doc/text 文本回退。

要证明的事：
  1. 环评报告那 592 条（只有 .md、没有 PDF）现在**能读到全文**了，
     而不是打开抽屉看到一坨 {"ok":false,"code":"E_DOC_NOT_FOUND",...}；
  2. 有 PDF 的资料仍然走 PDF，没有被误伤；
  3. 目录穿越仍然被挡住（加接口不能把安全约束弄丢）；
  4. /doc 本身的行为**没有变**（要活仍然 404 且是结构化 JSON）——
     变的是前端不再把那个 JSON 画出来。

必须带反向断言：只证明"没有 PDF 时能读文本"是不够的，
还要证明"有 PDF 时走的是 PDF"，否则把 /doc/info 写成永远返回
has_pdf=false 也能通过前几条，但那就把有 PDF 的资料全降级了。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"
FAILS = []


def check(cond, desc):
    print(("  OK   " if cond else "  FAIL ") + desc)
    if not cond:
        FAILS.append(desc)


def section(t):
    print()
    print("=== %s ===" % t)


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
section("一、找两条真实来源做样本")

# 环评报告：索引里有 .md，PDF 目录里没有
import os                                                     # noqa: E402
EIA_DIR = "/data/fagui_rag/okf_bundles/环评报告"
eia_files = sorted(os.listdir(EIA_DIR))
eia_src = "环评报告/" + eia_files[0]
print("  环评报告样本：%s" % eia_src)

# 法律法规：既有 .md 也有 PDF
LAW_DIR = "/data/fagui_pdf/生态环境法律法规"
law_pdf = None
for dirpath, _, names in os.walk(LAW_DIR):
    for n in names:
        if n.endswith(".pdf"):
            law_pdf = os.path.join(dirpath, n)
            break
    if law_pdf:
        break
law_src = os.path.relpath(law_pdf, "/data/fagui_pdf")[:-4] + ".md"
print("  法律法规样本：%s" % law_src)


# --------------------------------------------------------------------------
section("二、/doc/info 说清楚每条引用能怎么打开")

st, body = get("/doc/info?source=" + urllib.parse.quote(eia_src))
check(st == 200, "/doc/info 环评报告 → HTTP 200（实际 %s）" % st)
info = json.loads(body)
check(info.get("has_md") is True, "环评报告：has_md=true（有全文文本）")
check(info.get("has_pdf") is False, "环评报告：has_pdf=false（确实没有 PDF）")
check(info.get("md_bytes", 0) > 1000, "环评报告：文本 %d 字节" % info.get("md_bytes", 0))

st2, body2 = get("/doc/info?source=" + urllib.parse.quote(law_src))
check(st2 == 200, "/doc/info 法律法规 → HTTP 200")
info2 = json.loads(body2)
# ★ 反向断言：有 PDF 的资料必须仍然报 has_pdf=true，
#   否则就是把所有资料都降级成文本了。
check(info2.get("has_pdf") is True,
      "★ 反向：有 PDF 的资料 has_pdf=true（没有被误降级）")


# --------------------------------------------------------------------------
section("三、/doc/text 真的能拿到全文")

st, body = get("/doc/text?source=" + urllib.parse.quote(eia_src))
check(st == 200, "/doc/text → HTTP 200（实际 %s）" % st)
d = json.loads(body)
txt = d.get("text") or ""
check(len(txt) > 5000, "拿到全文 %d 字（要求 >5000）" % len(txt))
check("chars" in d and d["chars"] >= len(txt), "characters 字段给出原始总字数 %s" % d.get("chars"))
# YAML 头必须被剥掉 —— 那是索引元数据，不是正文，用户不该看到
check(not txt.startswith("---"), "YAML front matter 已剥掉（正文不以 --- 开头）")
check(txt.lstrip().startswith("#") or len(txt) > 0, "正文开头是文档标题或内容")
check("type: report" not in txt[:200], "索引元数据 type: report 没有漏进正文")
# 内容得真的是这份报告，不是随便什么文件
check(("拆解" in txt) or ("建设项目" in txt) or ("环境" in txt),
      "正文内容与环评报告相符（含'环境'/'建设项目'等词）")

print()
print("  正文开头 120 字：%s" % repr(txt[:120]))


# --------------------------------------------------------------------------
section("四、反向：安全约束没有被新接口弄丢")

# 非 .md 后缀必须拒绝
st, body = get("/doc/info?source=" + urllib.parse.quote("生态环境法律法规/固废法.pdf"))
check(st == 400, "非 .md 后缀 → 400（实际 %s）" % st)
check("E_PATH_UNSAFE" in body, "错误码是 E_PATH_UNSAFE")

# 目录穿越必须拒绝
for evil in ("../../etc/passwd.md", "环评报告/../../../etc/hosts.md"):
    st, body = get("/doc/text?source=" + urllib.parse.quote(evil))
    check(st == 400 and "E_PATH_UNSAFE" in body,
          "目录穿越被挡：%s → %s" % (evil, st))

# 存在但确实没有的文件 → 404，不是 500
st, body = get("/doc/text?source=" + urllib.parse.quote("环评报告/这个文件不存在啊.md"))
check(st == 404, "不存在的来源 → 404（实际 %s，不能是 500）" % st)
check("E_DOC_NOT_FOUND" in body, "错误码是 E_DOC_NOT_FOUND")


# --------------------------------------------------------------------------
section("五、/doc 自身行为没变（仍是有结构的 404）")

st, body = get("/doc?source=" + urllib.parse.quote(eia_src))
check(st == 404, "/doc 对没有 PDF 的环评报告仍然 404（实际 %s）" % st)
try:
    j = json.loads(body)
    check(j.get("ok") is False and j.get("code") == "E_DOC_NOT_FOUND",
          "/doc 的 404 仍然是结构化 JSON（前端不再画它，但接口契约没变）")
    check("request_id" in j, "带 request_id，便于和后端日志对上")
except Exception as exc:
    check(False, "/doc 的 404 应当是 JSON：%s" % exc)

st, body = get("/doc?source=" + urllib.parse.quote(law_src))
check(st == 200, "★ 反向：有 PDF 的资料 /doc 仍然 200 正常返回 PDF")
check(body[:4] == "%PDF", "返回的确实是 PDF（文件头 %%PDF）")


# --------------------------------------------------------------------------
print()
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for f in FAILS:
        print("  · " + f)
    sys.exit(1)
print("全部通过。")
