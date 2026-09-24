"""知识图谱加载与子图检索。

（由 website_split.py 从单文件服务端机械切分；逻辑未改。）"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

# ---- 同包依赖 ----
from .config import KG_PATH   # noqa: E402


_kg_cache: dict[str, Any] | None = None

def load_knowledge_graph() -> dict[str, Any]:
    """Load and index the compact NetworkX export on first use."""
    global _kg_cache
    if _kg_cache is not None:
        return _kg_cache
    if not KG_PATH.exists():
        _kg_cache = {"nodes": {}, "edges": [], "adjacency": {}, "degrees": {}}
        return _kg_cache
    payload = json.loads(KG_PATH.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", {})
    edges = payload.get("edges", [])
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.get("from_id", "")].append(edge)
        adjacency[edge.get("to_id", "")].append(edge)
    _kg_cache = {
        "nodes": nodes,
        "edges": edges,
        "adjacency": dict(adjacency),
        "degrees": {node_id: len(adjacency.get(node_id, [])) for node_id in nodes},
    }
    return _kg_cache

def graph_node_name(node_id: str, node: dict[str, Any]) -> str:
    props = node.get("props", {})
    return str(
        props.get("name_zh")
        or props.get("full_name")
        or props.get("title")
        or props.get("name")
        or node_id
    )

def graph_node_json(node_id: str, node: dict[str, Any], matched: bool = False) -> dict[str, Any]:
    props = {
        str(key): str(value)[:500]
        for key, value in node.get("props", {}).items()
        if value not in (None, "", [], {})
    }
    return {
        "id": node_id,
        "label": node.get("label", "Document"),
        "name": graph_node_name(node_id, node),
        "props": props,
        "matched": matched,
    }

def search_graph(query: str, depth: int = 1, limit: int = 70) -> dict[str, Any]:
    graph = load_knowledge_graph()
    nodes = graph["nodes"]
    adjacency = graph["adjacency"]
    q = query.strip().casefold()
    terms = [item for item in re.findall(r"[\w\u4e00-\u9fff.-]{2,}", q) if len(item) >= 2]
    scored: list[tuple[int, int, str]] = []
    for node_id, node in nodes.items():
        name = graph_node_name(node_id, node).casefold()
        searchable = " ".join(str(value) for value in node.get("props", {}).values()).casefold()
        score = 0
        if q:
            if q == name:
                score = 200
            elif q in name:
                score = 140
            elif name and len(name) >= 2 and name in q:
                score = 120 + min(len(name), 30)
            else:
                score = sum(18 for term in terms if term in searchable)
        if score:
            scored.append((score, graph["degrees"].get(node_id, 0), node_id))
    scored.sort(reverse=True)
    roots = [item[2] for item in scored[:8]]
    if not roots:
        roots = [
            item[0]
            for item in sorted(graph["degrees"].items(), key=lambda item: item[1], reverse=True)[:12]
        ]
    matched_ids = set(roots)
    selected: set[str] = set()
    queue = deque((node_id, 0) for node_id in roots)
    while queue and len(selected) < limit:
        node_id, current_depth = queue.popleft()
        if node_id in selected or node_id not in nodes:
            continue
        selected.add(node_id)
        if current_depth >= depth:
            continue
        neighbours = sorted(
            adjacency.get(node_id, []),
            key=lambda edge: max(
                graph["degrees"].get(edge.get("from_id", ""), 0),
                graph["degrees"].get(edge.get("to_id", ""), 0),
            ),
            reverse=True,
        )
        for edge in neighbours:
            other = edge.get("to_id") if edge.get("from_id") == node_id else edge.get("from_id")
            if other and other not in selected:
                queue.append((other, current_depth + 1))
    links = [
        {
            "source": edge.get("from_id"),
            "target": edge.get("to_id"),
            "type": edge.get("rel", "RELATED_TO"),
        }
        for edge in graph["edges"]
        if edge.get("from_id") in selected and edge.get("to_id") in selected
    ]
    return {
        "query": query,
        "nodes": [graph_node_json(node_id, nodes[node_id], node_id in matched_ids) for node_id in selected],
        "links": links,
        "matched": len(scored),
    }

def graph_evidence(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Add entity-centred graph facts to RAG only when an entity name occurs in the question."""
    graph = load_knowledge_graph()
    matches: list[tuple[int, str]] = []
    for node_id, node in graph["nodes"].items():
        name = graph_node_name(node_id, node).strip()
        if len(name) >= 2 and name in query:
            matches.append((len(name), node_id))
    matches.sort(reverse=True)
    results: list[dict[str, Any]] = []
    for _, node_id in matches[:limit]:
        node = graph["nodes"][node_id]
        name = graph_node_name(node_id, node)
        relations = []
        for edge in graph["adjacency"].get(node_id, [])[:12]:
            other_id = edge.get("to_id") if edge.get("from_id") == node_id else edge.get("from_id")
            other = graph["nodes"].get(other_id, {})
            relations.append(f"{edge.get('rel', 'RELATED_TO')} → {graph_node_name(other_id, other)}")
        props = "；".join(f"{key}：{value}" for key, value in node.get("props", {}).items() if value)
        text = f"实体类型：{node.get('label', '')}。{props}"
        if relations:
            text += "。关联关系：" + "；".join(relations)
        results.append({"title": name, "source": f"知识图谱 · {node.get('label', '')}", "text": text})
    return results

def _suggest_display_name(node_id: str, node: dict[str, Any]) -> str:
    """推荐词用的显示名。**只在推荐里用**，不改 graph_node_name。

    为什么不直接改 graph_node_name：它还负责回答正文里的实体链接
    （find_entities），改了会连带改变"正文里哪些词可点"的行为 ——
    那是另一个功能，不该被这次改动顺带改掉。

    Article 节点是个特例：它们**没有 name 属性**，只有
    article_no / parent_doc / text_preview，于是 graph_node_name 会回退成
    节点 id，推荐出来就是
    「Article_混合存放危险废物与非危险废物类案件学习要点_第一百一十二条_e8e3d7a2」
    —— 用户看到只会觉得图谱坏了。这里用「《所属文件》第N条」拼一个人话名字。

    拼不出人话名字的（回退成 id 且没有可用属性）返回空串，调用方会跳过它。
    """
    name = graph_node_name(node_id, node).strip()
    if name and name != node_id:
        return name
    props = node.get("props", {}) or {}
    parent = str(props.get("parent_doc") or "").strip()
    art = str(props.get("article_no") or "").strip()
    if parent and art:
        return "《%s》%s" % (parent, art)
    if art:
        return art
    return ""


def graph_suggestions(per_label: int = 4) -> dict[str, Any]:
    """按类型给出**真实存在**的代表性实体，供图谱页做「推荐关键词」。

    为什么需要（2026-09-18 用户反馈）：
    用户原话「我也不知道有哪些字段，你让我自己搜索好像不太现实，可以放几个
    推荐的关键词」。空搜索框 + 一句"输入关键词探索知识图谱"等于把发现成本
    全推给用户 —— 而图谱里有 2000 多个节点、14 种类型，没人猜得出来。

    四个设计决定：

    1. **只推有真名字的节点。** 名字回退成节点 id 的（主要是 Article）
       看起来像乱码，宁可这类不给例子，也不能让用户以为图谱是坏的。
       实测 114 个 Article 节点里有相当一部分能拼出「《文件》第N条」，
       拼得出的照常推荐，拼不出的跳过。

    2. **按类型分组，组内按连接数降序。** 度数高 = 关系丰富 = 点进去有内容；
       度数 0 的节点点进去是一张只有它自己的图，做成推荐反而像坏了。
       分组本身还回答了"图谱里有哪些字段"：用户扫一眼就知道这里能查
       法律、标准、条款、污染物、行业、案例……

    3. **类型之间是独立的**，不做全局排序 —— 全局排序会被最大的类型垄断
       （Document 697 个、Region 里的「全国」度数 2519），
       14 个推荐位全被它们占满，用户看不到图谱的全貌。
       前端那排"推荐关键词"用轮转法跨类型取，也是同一个理由。

    4. **返回的是节点名本身**（能搜到的那种）。前端点了直接拿去搜索，
       保证命中（search_graph 里 `q == name` 得 200 分，是所有分支里最高的）。
       如果推荐词是自己编的，用户点了一个没结果，比不给推荐更糟。
    """
    graph = load_knowledge_graph()
    by_label: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    unnamed: dict[str, int] = defaultdict(int)      # 有节点但拼不出名字的，按类型计数
    for node_id, node in graph["nodes"].items():
        label = node.get("label", "Document")
        degree = graph["degrees"].get(node_id, 0)
        if degree <= 0:
            continue                      # 没有关系的节点不适合当推荐入口
        name = _suggest_display_name(node_id, node)
        # 单字名（「水」「气」）当关键词太泛，搜出来是一团；find_entities 同理
        if not name or len(name) < 2:
            if not name:
                unnamed[label] += 1
            continue
        by_label[label].append((degree, name, node_id))

    types: list[dict[str, Any]] = []
    for label, items in by_label.items():
        items.sort(key=lambda t: (-t[0], t[1]))
        types.append({
            "label": label,
            "count": len(items) + unnamed.get(label, 0),
            "max_degree": items[0][0],
            "examples": [
                {"id": nid, "name": nm, "degree": deg} for deg, nm, nid in items[:per_label]
            ],
        })
    # 类型按实体数量降序：用户先看到"这里最多的是什么"
    types.sort(key=lambda t: (-t["count"], t["label"]))
    return {
        "ok": True,
        "total_nodes": len(graph["nodes"]),
        "total_links": len(graph["edges"]),
        "type_count": len(types),
        "types": types,
    }


def find_entities(text: str, limit: int = 40) -> list[dict[str, Any]]:
    """在给定文本里找出知识图谱中的实体名，供回答正文做可点击标记。

    与 graph_evidence 的区别：那个是给 RAG 用的，返回拼好的说明文本；
    这里要的是**实体本身**（id / 名称 / 类型），前端拿它把正文里的机构名、
    法规名、污染物名下划线，点了跳到知识图谱。

    为什么放在服务端：图谱有 2097 个节点，全量下发到浏览器是几 MB，
    而且图谱一更新前端就过期。服务端本来就是内存里的索引，扫一遍很便宜。
    """
    graph = load_knowledge_graph()
    if not text:
        return []
    found: list[dict[str, Any]] = []
    for node_id, node in graph["nodes"].items():
        name = graph_node_name(node_id, node).strip()
        # 只认 2 字以上的名字：「水」「气」这种单字会在正文里到处误命中
        if len(name) < 2 or name not in text:
            continue
        # 度数 0 的节点没有任何关系，点进去是一张只有它自己的图 ——
        # 做成可点击反而像坏了，不如不给它下划线。
        if graph["degrees"].get(node_id, 0) <= 0:
            continue
        found.append({
            "id": node_id,
            "name": name,
            "label": node.get("label", "Document"),
            "degree": graph["degrees"].get(node_id, 0),
        })
    # 长名字优先：前端替换时先换长的，短名字（可能是长名字的子串）就不会把它切碎
    found.sort(key=lambda item: (-len(item["name"]), -item["degree"]))
    kept: list[dict[str, Any]] = []
    for item in found:
        if any(item["name"] != k["name"] and item["name"] in k["name"] for k in kept):
            continue
        kept.append(item)
        if len(kept) >= limit:
            break
    return kept

