"""
Fagui RAG Proxy.

OpenAI-compatible /v1/chat/completions wrapper that retrieves law/regulation
context from /data/fagui_rag (BGE-M3 :33004 + BGE-rerank :33005) and forwards
to the fagui-v3 vLLM at :8100 with the retrieved context prepended as system.
"""
import sys
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever

import os

UPSTREAM = "http://127.0.0.1:8100/v1/chat/completions"
UPSTREAM_MODEL = "qwen36-fagui-v3"
PROXY_MODEL = "qwen36-fagui-v3-rag"
TOP_K_VEC = 20
TOP_K_FINAL = 5
MIN_RERANK = float(os.environ.get("RAG_MIN_RERANK", "0.5"))

app = FastAPI(title="Fagui RAG Proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = Retriever()


def build_rag_system(query: str, original_system: str | None) -> tuple[str, list]:
    base = (original_system or
            "你是悉数清宇大模型，由中节能训练的环保法规问答助手。")
    hits = retriever.retrieve(query, top_k_vec=TOP_K_VEC, top_k_final=TOP_K_FINAL)
    top = max((h.get("rerank_score") or 0.0) for h in hits) if hits else 0.0
    if not hits or top < MIN_RERANK:
        return base, []
    parts = []
    for i, h in enumerate(hits, 1):
        title = h.get("title", "") or h.get("doc_id", "")
        source = h.get("source", "")
        text = h.get("text", "") or ""
        parts.append(f"[{i}] 《{title}》（{source}）\n{text}")
    ctx = "\n\n".join(parts)
    sys_msg = (
        f"{base}\n\n"
        "以下是从环保法规知识库中检索到的相关条文，请优先依据这些条文回答用户问题，"
        "并在回答末尾用 [编号] 形式给出引用。如果检索结果与问题不相关，请如实告知。\n\n"
        f"<法规条文>\n{ctx}\n</法规条文>"
    )
    return sys_msg, hits


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{
            "id": PROXY_MODEL,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "fagui-rag-proxy",
        }],
    }


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    messages: list[dict[str, Any]]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool | None = False


@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    msgs = list(req.messages or [])
    user_query = None
    for m in reversed(msgs):
        if m.get("role") == "user":
            user_query = (m.get("content") or "").strip()
            break
    if not user_query:
        raise HTTPException(status_code=400, detail="no user message")

    original_system = None
    rest = []
    for m in msgs:
        if m.get("role") == "system" and original_system is None:
            original_system = m.get("content")
            continue
        rest.append(m)

    sys_msg, hits = build_rag_system(user_query, original_system)
    augmented = [{"role": "system", "content": sys_msg}] + rest

    payload: dict[str, Any] = {
        "model": UPSTREAM_MODEL,
        "messages": augmented,
        "stream": False,
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.top_p is not None:
        payload["top_p"] = req.top_p
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            r = await client.post(UPSTREAM, json=payload)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"upstream error: {e}")

    data = r.json()
    data["model"] = PROXY_MODEL
    data["rag_citations"] = [
        {"index": i + 1,
         "title": h.get("title", "") or h.get("doc_id", ""),
         "source": h.get("source", ""),
         "rerank_score": h.get("rerank_score"),
         "vec_sim": h.get("vec_sim")}
        for i, h in enumerate(hits)
    ]

    if hits and data.get("choices"):
        msg = data["choices"][0].get("message", {}) or {}
        body = msg.get("content") or ""
        lines = ["", "──────────────", "参考资料："]
        for i, h in enumerate(hits, 1):
            title = h.get("title", "") or h.get("doc_id", "")
            src = h.get("source", "") or ""
            rerank = h.get("rerank_score")
            rerank_s = f"{rerank:.3f}" if isinstance(rerank, (int, float)) else "n/a"
            snippet = (h.get("text") or "").strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:160] + "…"
            lines.append(f"[{i}] 《{title}》  相关性 {rerank_s}")
            lines.append(f"    片段：{snippet}")
            lines.append(f"    来源：{src}")
        msg["content"] = body.rstrip() + "\n" + "\n".join(lines)
        data["choices"][0]["message"] = msg

    return data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)
