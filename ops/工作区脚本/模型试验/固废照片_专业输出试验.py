#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固废现场照片 · 专业输出对照试验

A) 现状：走线上网站既有通路（含 RAG 检索），只给一个普通提问
B) 加专业契约：直连 .12:8000 的 v5，用固废/焚烧现场照片的专业输出契约

用法：
  python 固废照片_专业输出试验.py --image "D:\\...\\固废垃圾.png"
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time

import httpx
from PIL import Image

SITE = "http://10.201.31.10:8011"
V5 = "http://10.201.31.12:8000/v1/chat/completions"
V5_NAME = "xishu-qingyu-v5"

QUESTION = "这张照片里的固体废物属于哪一类？现场贮存需要满足哪些合规要求？"

# ===== 专业输出契约（针对固废/焚烧现场照片）=====
PHOTO_CONTRACT = """你是固废与垃圾焚烧领域的现场检查专家。用户上传了一张现场照片，请给出一份专业、克制、可核验的初步研判。

严格按以下七节输出，每节标题原样保留：

【一、图片类型】一行。是固体废物贮存/堆场、运输环节、处置设施、烟气排放、还是厂区其他部位。

【二、图中可见事实】只写照片里能直接看到的东西：物料形态与构成、颜色与锈蚀/污染特征、混入物、堆体与场地状态（是否露天、有无覆盖、有无围挡）、可见的设施或标识、天气与光照。每条都要能被照片证实。

【三、固废属性初判】给出最可能的固废类别（如"废钢铁/金属废料属一般工业固体废物"），并明确写：若要认定《国家危险废物名录》中的属性，必须依据物料来源与成分检测，**仅凭照片不能认定，也不能排除**。

【四、合规要点与依据】列出与本节图片相关的贮存/管理要求（如一般工业固体废物贮存场地的防扬散、防流失、防渗漏要求；固废法中关于贮存、转移、台账的义务）。**只写你能确认名称与内容的依据**；引用条款时必须写明法规/标准全称，不确定条款号就不要写条号。

【五、风险提示】按可能性从高到低排序，每条注明是"照片已显示"还是"照片未显示、需现场核实"。

【六、需要补充的信息】列出判断所必需但照片给不出的信息（物料来源、企业性质、场地手续、防渗与排水设施、监测数据、台账等）。

【七、结论边界】一句话说明本研判的性质：属于现场初判，不构成违法认定，不能替代现场检查与取样检测。

写作要求：
1. 严格区分"照片看到的"与"你推断的"；凡是照片里看不到的，一律写成"照片未显示，需核实"，不要用肯定语气描述。
2. 不要编造照片中不存在的细节（例如具体企业名称、具体数值、具体设施数量）。
3. 术语用规范名称，不要口语化；不要写"根据现有证据""材料显示"这类措辞。
4. 先在<think></think>中推理，再输出上述七节正文，正文不要再重复推理内容。"""


def load_image(path: str, max_edge: int = 1600) -> tuple[str, tuple[int, int]]:
    img = Image.open(path).convert("RGB")
    orig = img.size
    s = min(1.0, max_edge / max(img.size))
    if s < 1.0:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    if img.width < 40 or img.height < 40:
        raise SystemExit("图片太小")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), orig


def stream_site(image: str, query: str) -> dict:
    out = {"answer": "", "reasoning": "", "sources": [], "route": "", "error": "", "elapsed": 0.0}
    t0 = time.time()
    with httpx.stream("POST", f"{SITE}/hybrid_search/stream",
                      json={"query": query, "history": [], "image": image}, timeout=600) as r:
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
                if ev == "chunk":
                    out["answer"] += p if isinstance(p, str) else ""
                elif ev == "reasoning":
                    out["reasoning"] += p if isinstance(p, str) else ""
                elif ev in ("meta", "done") and isinstance(p, dict):
                    out["route"] = p.get("route", out["route"])
                    if p.get("sources"):
                        out["sources"] = p["sources"]
                elif ev == "error":
                    out["error"] = p if isinstance(p, str) else str(p)
                ev = data = None
    out["elapsed"] = round(time.time() - t0, 1)
    return out


def direct_v5(image: str, system: str, user: str, max_tokens: int = 3000) -> dict:
    payload = {
        "model": V5_NAME,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": image}},
            ]},
        ],
        "temperature": 0,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": True},
        "stream": False,
    }
    t0 = time.time()
    r = httpx.post(V5, json=payload, timeout=600)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:300]}", "elapsed": round(time.time() - t0, 1)}
    m = r.json()["choices"][0]["message"]
    content = m.get("content") or ""
    reasoning = ""
    if "</think>" in content:
        reasoning, _, content = content.partition("</think>")
    return {"answer": content.strip(), "reasoning": reasoning.strip(),
            "elapsed": round(time.time() - t0, 1)}


def show(title: str, res: dict) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    if res.get("error"):
        print("ERROR:", res["error"])
        return
    print(f"[耗时 {res['elapsed']}s  路由 {res.get('route','-')}  引用 {len(res.get('sources') or [])} 条  "
          f"推理 {len(res.get('reasoning') or '')} 字  答案 {len(res['answer'])} 字]")
    print("-" * 78)
    print(res["answer"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=r"D:\项目\中节能\0911训练\image\固废垃圾.png")
    args = ap.parse_args()

    data_url, orig = load_image(args.image)
    print(f"图片：{os.path.basename(args.image)}  原始 {orig[0]}x{orig[1]}  "
          f"压缩后 {len(data_url)*3//4//1024} KB（长边≤1600）")

    a = stream_site(data_url, QUESTION)
    show(f"A · 现状（走线上网站既有通路，提问：「{QUESTION}」）", a)
    if a.get("sources"):
        print("-" * 78)
        print("引用资料：")
        for s in a["sources"][:8]:
            print(f"  [{s.get('index')}] {s.get('title')}  <- {s.get('source','')}")

    b = direct_v5(data_url, "你是固废与垃圾焚烧领域的现场检查专家。", PHOTO_CONTRACT)
    show("B · 加专业输出契约（直连 v5，无检索）", b)


if __name__ == "__main__":
    main()
