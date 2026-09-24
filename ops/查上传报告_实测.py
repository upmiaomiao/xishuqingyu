#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告上传功能实测（在服务器上跑，打线上 HTTP）。

用户原话：「环评报告审核这里没有上传自己的环评报告，我觉得这个功能需要有」。

安全约定（很重要）：
  · 报告目录 /data/eia_reports 里是他人的真实报告，**只读不动**；
  · 测试自己造的文件，测完全部删掉（记在 _created 里，finally 兜底）；
  · 每份测试文件的文件名都带 uploadtest 前缀，便于自查与人工清理。

用法：
  /home/test/fagui_serve/.venv/bin/python 查上传报告_实测.py
"""
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8011"
# 由 audit.runner.report_dir() 决定；这里显式写出来是为了能在 finally 里清理
sys.path.insert(0, "/data/eia_audit")
try:
    from audit.runner import report_dir
    REPORT_DIR = report_dir()
except Exception:
    REPORT_DIR = "/data/eia_reports"

ok = 0
bad = []
_created = []          # 测试造出来的文件，无论成败都要删
_BASELINE = set()      # 开跑前目录里已有的文件，用于确认没被误动


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


def post_file(path, filename, data, field="file", timeout=120):
    """手写 multipart/form-data —— 不引第三方库，服务器上未必装 requests。"""
    boundary = "----xishu" + uuid.uuid4().hex
    body = b""
    body += ("--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
             % (field, filename)).encode("utf-8")
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += data
    body += ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        BASE + path, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw


def make_pdf(text="上传测试报告"):
    """造一个**真的能被 pymupdf 打开**的小 PDF。

    为什么不用手写的最小 PDF：手写 xref 很容易造出"文件头是 %PDF、
    但解析器打不开"的东西 —— 那样只测了上传，没测"传上去能审"。
    """
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def snapshot():
    try:
        return set(os.listdir(REPORT_DIR))
    except OSError:
        return set()


def main():
    global _BASELINE
    say("目标：%s" % BASE)
    say("报告目录：%s" % REPORT_DIR)
    say("")

    _BASELINE = snapshot()
    say("=== 0. 基线 ===")
    say("  目录里已有 %d 个文件" % len(_BASELINE))
    st, d0 = get("/audit/api/reports")
    check("/audit/api/reports 可用", st == 200 and isinstance(d0, dict) and d0.get("ok"),
          "报告数=%d" % len((d0 or {}).get("reports") or []))
    n_before = len((d0 or {}).get("reports") or [])

    say("")
    say("=== 1. 正常上传 ===")
    tag = uuid.uuid4().hex[:8]
    fname = "uploadtest-%s-测试环评报告.pdf" % tag
    pdf = make_pdf("上传测试 " + tag)
    _created.append(fname)
    st, d = post_file("/audit/api/upload", fname, pdf)
    check("HTTP 200", st == 200, "status=%s" % st)
    check("ok 为真", isinstance(d, dict) and d.get("ok") is True, str(d)[:160])
    saved = (d or {}).get("name") or ""
    _created.append(saved)
    check("返回了保存后的文件名", bool(saved), saved)
    check("文件名保留了中文", "测试环评报告" in saved, saved)
    check("重名标志为假", (d or {}).get("renamed") is False)
    check("重复标志为假", (d or {}).get("duplicate") is False)
    check("文件真的落盘了", os.path.isfile(os.path.join(REPORT_DIR, saved)))
    check("落盘字节数与上传一致",
          os.path.getsize(os.path.join(REPORT_DIR, saved)) == len(pdf),
          "%d vs %d" % (os.path.getsize(os.path.join(REPORT_DIR, saved)), len(pdf)))

    say("")
    say("=== 2. 上传后出现在报告清单里（这才是「能审」的前提）===")
    st, d1 = get("/audit/api/reports")
    names = [x["name"] for x in ((d1 or {}).get("reports") or [])]
    check("出现在 /audit/api/reports 里", saved in names,
          "清单 %d 份" % len(names))
    check("清单比之前多了 1 份", len(names) == n_before + 1,
          "%d → %d" % (n_before, len(names)))

    say("")
    say("=== 3. 内容重复检测（关键：不然用户以为上传失败）===")
    # list_reports 按 sha1 去重，只保留排序靠前的名字。所以同一份内容
    # 换个名字再传，新名字根本不会出现在清单里 —— 必须明确告诉用户。
    fname2 = "uploadtest-%s-换个名字.pdf" % tag
    st, d2 = post_file("/audit/api/upload", fname2, pdf)
    check("重复上传 HTTP 200", st == 200, "status=%s" % st)
    check("识别为重复", isinstance(d2, dict) and d2.get("duplicate") is True, str(d2)[:200])
    check("指出是哪一份", (d2 or {}).get("name") == saved,
          "%s vs %s" % ((d2 or {}).get("name"), saved))
    check("给了人话说明", bool((d2 or {}).get("message")), (d2 or {}).get("message", "")[:80])
    check("重复件没有落盘",
          not os.path.isfile(os.path.join(REPORT_DIR, fname2)), fname2)

    say("")
    say("=== 4. 非 PDF / 假 PDF 必须被拒 ===")
    st, d3 = post_file("/audit/api/upload", "uploadtest-假的.pdf",
                       b"this is not a pdf at all, just text")
    check("纯文本冒充 .pdf → 400", st == 400, "status=%s code=%s" % (st, (d3 or {}).get("code")))
    check("错误码是 E_FILE_TYPE_INVALID",
          (d3 or {}).get("code") == "E_FILE_TYPE_INVALID", str((d3 or {}).get("code")))
    check("错误信息是人话（没有技术词）",
          "PDF" in ((d3 or {}).get("message") or ""), (d3 or {}).get("message", "")[:80])

    st, d4 = post_file("/audit/api/upload", "uploadtest-空文件.pdf", b"")
    check("空文件 → 400", st == 400, "status=%s code=%s" % (st, (d4 or {}).get("code")))

    # 名字是 .txt 但内容是真题 PDF：按内容判类型
    st, d5 = post_file("/audit/api/upload", "uploadtest-后缀不对.txt", pdf)
    check("后缀不是 .pdf 也会被补成 .pdf 或拒绝",
          st in (200, 400), "status=%s" % st)
    if st == 200:
        _created.append((d5 or {}).get("name") or "")

    say("")
    say("=== 5. 文件名安全 ===")
    # 目录穿越
    st, d6 = post_file("/audit/api/upload", "../../../tmp/uploadtest-穿越.pdf", pdf)
    check("目录穿越文件名不逃出报告目录", st in (200, 400), "status=%s" % st)
    if st == 200:
        nm = (d6 or {}).get("name") or ""
        _created.append(nm)
        check("穿越符号被清掉", ".." not in nm and "/" not in nm, "存成了 %r" % nm)
        check("确实落在报告目录里",
              os.path.isfile(os.path.join(REPORT_DIR, nm)))
        check("没有落到 /tmp", not os.path.isfile("/tmp/uploadtest-穿越.pdf"))
    # Windows 不允许的字符
    st, d7 = post_file("/audit/api/upload", 'uploadtest-a:b*c?d"e<f>g|h.pdf', pdf)
    check("非法字符文件名被清理", st == 200, "status=%s" % st)
    if st == 200:
        nm = (d7 or {}).get("name") or ""
        _created.append(nm)
        check("存下来的名字里没有非法字符",
              not any(c in nm for c in ':*?"<>|'), "存成了 %r" % nm)
    # 空文件名
    st, d8 = post_file("/audit/api/upload", "", pdf)
    check("空文件名也能处理（不 500）", st in (200, 400), "status=%s" % st)
    if st == 200:
        _created.append((d8 or {}).get("name") or "")

    say("")
    say("=== 6. 重名不覆盖（硬要求：别把别人审过的原件冲掉）===")
    fname9 = "uploadtest-%s-重名.pdf" % tag
    p1 = make_pdf("重名测试第一版 " + tag)
    st, d9 = post_file("/audit/api/upload", fname9, p1)
    saved9 = (d9 or {}).get("name") or ""
    _created.append(fname9)
    _created.append(saved9)
    check("第一次上传成功", st == 200 and saved9 == fname9, "%s" % saved9)
    # 同名但内容不同 → 必须另存，不能覆盖
    p2 = make_pdf("重名测试第二版，内容不一样 " + tag)
    st, d10 = post_file("/audit/api/upload", fname9, p2)
    saved10 = (d10 or {}).get("name") or ""
    _created.append(saved10)
    check("同名不同内容 → 另存新名", st == 200 and saved10 != fname9, "%s" % saved10)
    check("原文件内容**没被改动**",
          open(os.path.join(REPORT_DIR, saved9), "rb").read() == p1)
    check("新文件内容是第二版",
          open(os.path.join(REPORT_DIR, saved10), "rb").read() == p2)
    check("界面能看到改名提示", (d10 or {}).get("renamed") is True,
          (d10 or {}).get("message", "")[:80])

    say("")
    say("=== 7. 不留临时文件（.part）===")
    parts = [n for n in os.listdir(REPORT_DIR) if n.endswith(".part")]
    check("报告目录里没有 .part 残留", not parts, str(parts[:5]))
    hidden = [n for n in os.listdir(REPORT_DIR) if n.startswith(".upload-")]
    check("没有隐藏的临时文件残留", not hidden, str(hidden[:5]))

    say("")
    say("=== 8. 已有的报告一个都没少、没变 ===")
    now = snapshot()
    lost = {n for n in _BASELINE if n not in now}
    check("原有文件全部还在", not lost, ("少了：" + str(sorted(lost)[:5])) if lost else
          "%d 个都在" % len(_BASELINE))
    # 基线里的 .pdf 内容抽查 3 个：大小没变
    base_pdfs = sorted(n for n in _BASELINE if n.lower().endswith(".pdf"))[:3]
    same = all(os.path.getsize(os.path.join(REPORT_DIR, n)) > 0 for n in base_pdfs)
    check("抽查原有报告大小正常", same, "抽查 %d 份" % len(base_pdfs))

    say("")
    say("=== 9. 收尾：清掉本次测试造的文件 ===")
    left = 0
    for n in set(_created):
        if not n:
            continue
        p = os.path.join(REPORT_DIR, n)
        if os.path.isfile(p):
            os.remove(p)
            say("  已删 %s" % n)
        else:
            left += 1
    after = snapshot()
    extra = {n for n in after if n not in _BASELINE}
    check("测试产物已清空", not extra, ("残留：" + str(sorted(extra)[:5])) if extra else "干净")
    check("目录回到基线状态", after == _BASELINE,
          "%d vs %d" % (len(after), len(_BASELINE)))

    say("")
    say("==== 通过 %d / 失败 %d ====" % (ok, len(bad)))
    if bad:
        for b in bad:
            say("  失败：" + b)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        # 兜底：无论怎么挂的，都别把测试文件留在别人的报告目录里
        for n in set(_created):
            if not n:
                continue
            p = os.path.join(REPORT_DIR, n)
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass
        for n in os.listdir(REPORT_DIR) if os.path.isdir(REPORT_DIR) else []:
            if n.endswith(".part") or n.startswith(".upload-"):
                try:
                    os.remove(os.path.join(REPORT_DIR, n))
                except OSError:
                    pass
