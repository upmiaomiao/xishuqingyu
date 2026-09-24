#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网站图片通路端到端测试（SSE 流式，与前端走的接口一致）。

用法：
  python 网站_图片通路E2E.py --base http://10.201.31.10:8012
  python 网站_图片通路E2E.py --base http://10.201.31.10:8011 --only regression
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time

import httpx
from PIL import Image, ImageDraw, ImageFont


def make_png(lines: list[str], size=(780, 300)) -> str:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, 24)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    d.multiline_text((18, 24), "\n".join(lines), fill="black", font=font, spacing=12)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def stream(base: str, payload: dict, timeout: float = 300.0) -> dict:
    """跑一次流式请求，汇总事件。"""
    out = {"status": [], "chunks": 0, "reasoning": 0, "answer": "", "vision": "", "route": "",
           "sources": 0, "error": "", "elapsed": 0.0}
    t0 = time.time()
    try:
        with httpx.stream("POST", f"{base}/hybrid_search/stream", json=payload, timeout=timeout) as r:
            if r.status_code != 200:
                out["error"] = f"HTTP {r.status_code}: {r.read()[:200]!r}"
                return out
            ev = data = None
            for line in r.iter_lines():
                s = line.strip()
                if s.startswith("event:"):
                    ev = s[6:].strip()
                elif s.startswith("data:"):
                    data = s[5:].strip()
                elif s == "":
                    if not ev:
                        continue
                    try:
                        p = json.loads(data) if data else None
                    except Exception:
                        p = None
                    if ev == "status":
                        out["status"].append(p.get("message") if isinstance(p, dict) else p)
                    elif ev == "reasoning":
                        out["reasoning"] += 1
                    elif ev == "chunk":
                        out["chunks"] += 1
                        out["answer"] += p if isinstance(p, str) else ""
                    elif ev == "vision":
                        out["vision"] = (p or {}).get("text", "")
                    elif ev == "meta":
                        out["route"] = (p or {}).get("route", "")
                        out["sources"] = len((p or {}).get("sources") or [])
                    elif ev == "done":
                        out["route"] = (p or {}).get("route", out["route"])
                        out["sources"] = len((p or {}).get("sources") or [])
                    elif ev == "error":
                        out["error"] = p if isinstance(p, str) else str(p)
                    ev = data = None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["elapsed"] = round(time.time() - t0, 1)
    return out


def brief(o: dict) -> str:
    tag = "❌" if o["error"] else "✅"
    return (f"{tag} route={o['route'] or '-'} 引用={o['sources']} chunk={o['chunks']} "
            f"reasoning={o['reasoning']} 耗时={o['elapsed']}s "
            f"识别={len(o['vision'])}字 答案={len(o['answer'])}字"
            + (f" ERROR={o['error'][:160]}" if o["error"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://10.201.31.10:8012")
    ap.add_argument("--only", default="", help="regression / image")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"=== 目标 {base} ===")
    try:
        h = httpx.get(f"{base}/health", timeout=15)
        print(f"health {h.status_code} {h.text}")
    except Exception as e:
        sys.exit(f"health 失败：{e}")

    img_notice = make_png([
        "生活垃圾焚烧发电厂 自动监测数据",
        "点位：1#焚烧炉 烟气排放口",
        "颗粒物 日均值 12.5 mg/m³",
        "氮氧化物 日均值 268.4 mg/m³",
        "日期：2026-01-13",
    ])
    img_photo = make_png([
        "排污许可证（副本）",
        "证号：91130200MA0XXXXX",
        "有效期：2023-06-01 至 2028-05-31",
        "排放口：1#烟气排放口 DA001",
    ])

    fails = []

    if args.only in ("", "regression"):
        print("\n--- [A] 回归：纯文本专业问题（不应受影响） ---")
        a = stream(base, {"query": "危险废物转移联单的确认期限是多久？", "history": []})
        print(brief(a)); print("   ", (a["answer"] or a["error"])[:120].replace("\n", " "))
        if a["error"] or a["route"] != "rag":
            fails.append("A")

        print("\n--- [B] 回归：纯文本日常科普 ---")
        b = stream(base, {"query": "外卖餐盒算哪类垃圾？", "history": []})
        print(brief(b)); print("   ", (b["answer"] or b["error"])[:120].replace("\n", " "))
        if b["error"]:
            fails.append("B")

    if args.only in ("", "image"):
        print("\n--- [C] 新功能：图片 + 文字问题 ---")
        c = stream(base, {"query": "这张图里的氮氧化物超标了吗？", "history": [], "image": img_notice})
        print(brief(c)); print("   ", (c["answer"] or c["error"])[:200].replace("\n", " "))
        if c["error"] or not c["answer"]:
            fails.append("C")
        if "268" not in (c["answer"] + c["vision"]):
            fails.append("C:答案未用到图中数值")
        if not c["vision"]:
            fails.append("C:未回传图片识别内容")

        print("\n--- [D] 新功能：只发图不打字 ---")
        d = stream(base, {"query": "", "history": [], "image": img_photo})
        print(brief(d))
        print("    识别结果:", (d["vision"] or "(空)")[:220].replace("\n", " "))
        if d["error"] or not d["vision"]:
            fails.append("D")
        if "91130200MA0XXXXX" not in d["vision"] and "有效期" not in d["vision"]:
            fails.append("D:识别结果未含图中关键字段")

        print("\n--- [E] 边界：非图片 data URL ---")
        r = httpx.post(f"{base}/hybrid_search", json={"query": "x", "image": "data:text/plain;base64,aGk="},
                       timeout=60)
        print(f"   HTTP {r.status_code} {r.text[:120]}")
        if r.status_code != 400:
            fails.append(f"E(期望400，实际{r.status_code})")

        print("\n--- [F] 边界：超大图片 ---")
        r = httpx.post(f"{base}/hybrid_search",
                       json={"query": "x", "image": "data:image/png;base64," + "A" * 9_500_000},
                       timeout=120)
        print(f"   HTTP {r.status_code} {r.text[:120]}")
        if r.status_code != 413:
            fails.append(f"F(期望413，实际{r.status_code})")

        print("\n--- [G] 边界：既无文字也无图片 ---")
        r = httpx.post(f"{base}/hybrid_search/stream", json={"query": "", "history": []}, timeout=60)
        print(f"   HTTP {r.status_code} {r.text[:120]}")
        if r.status_code != 400:
            fails.append(f"G(期望400，实际{r.status_code})")

    if args.only in ("", "photo"):
        print("\n--- [H] 现场照片专业研判（三态核验清单）---")
        photo_path = r"D:\项目\中节能\0911训练\image\固废垃圾.png"
        if not os.path.exists(photo_path):
            print("   跳过：找不到本机示例照片", photo_path)
        else:
            img = Image.open(photo_path).convert("RGB")
            s = min(1.0, 1600 / max(img.size))
            if s < 1.0:
                img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            photo_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            h = stream(base, {"query": "", "history": [], "image": photo_url, "report": "photo"},
                       timeout=600)
            print(brief(h))
            body = h["answer"]
            checks = {
                "路由=photo": h["route"] == "photo",
                "有检索依据": h["sources"] > 0,
                "含【二、图中可见事实】": "【二、图中可见事实】" in body,
                "含【三、核验清单】": "【三、核验清单】" in body,
                "含固定表头": "| 检查项 | 图中可见情况 | 判定 | 依据 |" in body,
                "表格有分隔行": "| --- |" in body,
                "判定只用三态": all(t in body for t in ("满足",)) and
                                not re.search(r"\| *(基本满足|部分满足|疑似满足|不适用) *\|", body),
                "含【六、需要补充的信息】": "【六、需要补充的信息】" in body,
                "含代码追加的结论边界": "【七、结论边界】" in body,
                "未出现免责尾段':此外…无法判断'": "无法对该" not in body[:0] + body,
            }
            for k, v in checks.items():
                print(f"      {'✓' if v else '✗'} {k}")
                if not v:
                    fails.append(f"H:{k}")
            print("\n----- 报告正文（前 1600 字） -----")
            print(body[:1600])
            print("----- 正文结束 -----")

    print("\n=== 结果 ===")
    print("全部通过 ✅" if not fails else f"失败项：{fails}")


if __name__ == "__main__":
    main()
