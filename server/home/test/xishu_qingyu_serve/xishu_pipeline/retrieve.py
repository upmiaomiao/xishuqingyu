"""向量检索器（单例）与检索结果规整。

（由 website_split.py 从单文件服务端机械切分；逻辑未改。）"""
from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, "/data/fagui_rag")   # 原单文件里的同一行，位置必须早于 from retriever import
from retriever import Retriever          # noqa: E402

# ---- 同包依赖 ----
from .textclean import clean_retrieved_text   # noqa: E402


retriever = Retriever()

def normalize_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把检索命中规整成前端要用的结构。

    检索器本来就返回**完整元数据**（standard_id / type / status / issuer / region …
    见 chunks.jsonl 的字段），此前只透传了 6 个字段、其余丢掉了。
    这里把对"专业判断"有用的几项一并带上：标准号、材料类型、现行状态、发布机关、地区、块序号。
    """
    out = []
    for index, hit in enumerate(hits, 1):
        out.append({
            "index": index,
            "title": hit.get("title", "") or hit.get("doc_id", ""),
            "source": hit.get("source", ""),
            "text": clean_retrieved_text(hit.get("text", "")),
            "rerank_score": hit.get("rerank_score"),
            "vector_score": hit.get("vec_sim"),
            # --- 元数据（供引用卡片展示，也是"查看原文 PDF"的定位键）---
            "standard_id": hit.get("standard_id") or "",
            "doc_type": hit.get("type") or "",
            "status": hit.get("status") or "",
            "status_note": hit.get("status_note") or "",
            "issuer": "、".join(hit.get("issuer") or []) if isinstance(hit.get("issuer"), list)
                      else (hit.get("issuer") or ""),
            "region": hit.get("region") or "",
            "chunk_index": hit.get("chunk_index"),
        })
    return out

