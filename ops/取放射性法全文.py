#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取《中华人民共和国放射性污染防治法》官方全文（多源兜底版）。

上一次失败的原因记下来：生态环境部那个页面是**导航壳**（返回 1.9k 字全是部门链接），
正文不在页面里 —— 本项目在语料侧已多次踩过"壳文档"。

所以改成按可信度依次尝试：
  ① 陕西省生态环境厅 PDF（政府站，通常有文本层）—— 用 PyMuPDF 抽
  ② 广东省人民政府 法规规章库 HTML
  ③ 陕西省政府公报 HTML
抽到正文后做体检（条文数应 ≥ 55、字数 ≥ 8000），合格才写：
  /tmp/fsx_body.txt（入库正文）与 /tmp/fsx_spec.json（front matter，status=已废止）
只打印摘要，不把全文灌进对话。

用法：/data/fagui_rag/.venv_tools/bin/python 取放射性法全文.py
"""
from __future__ import annotations

import html
import io
import json
import re
import urllib.request

TITLE = "中华人民共和国放射性污染防治法"
PDF_SRC = "https://sthjt.shaanxi.gov.cn/upload/d/file/sthjbhzfdlb/xsxx/20190617/1560758988694791.pdf"
HTML_SRC = [
    ("广东省人民政府", "http://www.gd.gov.cn/zwgk/wjk/zcfgk/content/post_2521546.html"),
    ("陕西省政府公报", "https://www.shaanxi.gov.cn/zfxxgk/zfgb/2003/d20q_4361/200806/t20080625_1641034.html"),
]
BODY_OUT = "/tmp/fsx_body.txt"
SPEC_OUT = "/tmp/fsx_spec.json"
PDF_OUT = "/tmp/fsx.pdf"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122"


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    return raw


def html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(p|div|tr|h[1-6]|li)>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(h).replace("\u3000", " ").replace("\xa0", " ")
    lines = [ln.strip() for ln in h.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def trim(text: str) -> str:
    # 页面通常先出现一次标题（导航/面包屑），正文标题在后面 —— 优先从**后一次**标题切，
    # 这样能把「首页 > 政务公开 > 文件库」这类面包屑甩掉。
    first = text.find(TITLE)
    second = text.find(TITLE, first + len(TITLE)) if first >= 0 else -1
    i = second if second >= 0 and second < first + 800 else first
    body = text[i:] if i >= 0 else text
    # 正文真正的起点是"（2003年6月28日…通过"这行发布信息，前面的时间/来源/打印按钮都是页面家具
    k = body.find("（2003年6月28日")
    if 0 <= k < 600:
        body = body[k:]
    for cut in ("中国政府网", "版权所有", "网站声明", "相关链接", "ICP备案", "扫一扫", "主办单位",
                "承办单位", "【字体：", "分享到", "（2003年6月28日第十届全国人民代表大会常务委员会"):
        j = body.find(cut)
        if j > 500:
            body = body[:j]
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def health(body: str) -> tuple:
    arts = re.findall(r"第[一二三四五六七八九十百]+条", body)
    return len(body), (arts[0] if arts else "无"), (arts[-1] if arts else "无"), len(arts)


def try_pdf() -> str:
    print("① 尝试 PDF：%s" % PDF_SRC)
    raw = http_get(PDF_SRC)
    io.open(PDF_OUT, "wb").write(raw)
    print("   下载 %d 字节；头 5 字节 %r" % (len(raw), raw[:5]))
    if raw[:4] != b"%PDF":
        print("   不是 PDF，跳过")
        return ""
    import fitz                                                  # noqa: PLC0415
    doc = fitz.open(PDF_OUT)
    txt = "\n".join(p.get_text() for p in doc)
    print("   %d 页，抽出 %d 字" % (doc.page_count, len(txt)))
    return trim(txt)


def try_html(tag: str, url: str) -> str:
    print("  尝试 %s：%s" % (tag, url))
    raw = http_get(url)
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            t = html_to_text(raw.decode(enc))
            print("   %s 解码 %s → %d 字" % (tag, enc, len(t)))
            return trim(t)
        except UnicodeDecodeError:
            continue
    return ""


def main() -> int:
    body = ""
    src = ""
    try:
        body = try_pdf()
        src = PDF_SRC
    except Exception as exc:                                     # noqa: BLE001
        print("   PDF 源失败：%s" % exc)
    if not body:
        for tag, url in HTML_SRC:
            try:
                body = try_html(tag, url)
            except Exception as exc:                             # noqa: BLE001
                print("   %s 失败：%s" % (tag, exc))
                body = ""
            if body:
                src = url
                break

    n, a0, a1, na = health(body)
    print("\n体检：%d 字；条文标记 %d 处；首 %s；末 %s" % (n, na, a0, a1))
    print("开头 140 字：%s" % body[:140].replace("\n", " "))
    print("结尾 140 字：%s" % body[-140:].replace("\n", " "))
    if n < 6000 or na < 55 or a1 != "第六十三条":
        print("\n❌ 不合格（2003 年该法为 8 章 63 条：要求 ≥6000 字、≥55 处条文、末条为第六十三条），"
              "未写出任何文件；需要人工提供来源")
        return 2

    io.open(BODY_OUT, "w", encoding="utf-8", newline="\n").write(body + "\n")
    spec = {
        "rel_dir": "生态环境法律法规/法律/法律_43/中华人民共和国放射性污染防治法",
        "file_base": TITLE,
        "front": {
            "type": "law",
            "title": TITLE,
            "description": "国家法律（已废止）：中华人民共和国放射性污染防治法",
            "tags": ["法律法规", "法律", "国家"],
            "status": "已废止",
            "issuer": ["全国人民代表大会常务委员会"],
            "region_type": "国家",
            "region": "全国",
            "status_note": "《中华人民共和国生态环境法典》第一千二百四十二条：本法自2026年8月15日起施行，"
                           "《中华人民共和国放射性污染防治法》同时废止。",
            "source_url": src,
            "retrieved_at": "2026-09-22",
            "source_note": "官方全文（政府网站公开件），2026-09-22 取得；正文去标签后入库",
        },
        "body_file": BODY_OUT,
    }
    spec["pdf"] = PDF_OUT if src == PDF_SRC else None
    if not spec["pdf"]:
        spec.pop("pdf")
    io.open(SPEC_OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(spec, ensure_ascii=False, indent=2))
    print("\n✅ 已写 %s（%d 字）与 %s" % (BODY_OUT, n, SPEC_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
