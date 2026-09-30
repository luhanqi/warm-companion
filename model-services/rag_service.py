"""Local BGE-M3 embedding and reranking service for Warm Companion.

The routes intentionally match the OpenAI/SiliconFlow-shaped API already used
by the backend.  Models are loaded lazily, so starting the service is quick and
RAM is only consumed after the first real request.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import List, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="暖伴本地记忆检索服务")

MODEL_ROOT = Path(os.getenv("NUANBAN_MODEL_ROOT", str(Path(__file__).resolve().parents[1] / "models")))
EMBEDDING_DIR = Path(os.getenv("BGE_MODEL_DIR", str(MODEL_ROOT / "bge-m3")))
RERANK_DIR = Path(os.getenv("RERANK_MODEL_DIR", str(MODEL_ROOT / "bge-reranker-v2-m3")))

_embedding_model = None
_reranker_model = None
_embedding_lock = Lock()
_reranker_lock = Lock()


class EmbeddingRequest(BaseModel):
    model: str = "BAAI/bge-m3"
    input: Union[str, List[str]]


class RerankRequest(BaseModel):
    model: str = "BAAI/bge-reranker-v2-m3"
    query: str
    documents: List[str]
    top_n: int = Field(default=5, ge=1)
    return_documents: bool = False


def embedding_model():
    global _embedding_model
    if _embedding_model is None:
        if not EMBEDDING_DIR.exists():
            raise RuntimeError(f"BGE-M3 模型目录不存在：{EMBEDDING_DIR}")
        from FlagEmbedding import BGEM3FlagModel

        _embedding_model = BGEM3FlagModel(str(EMBEDDING_DIR), use_fp16=False)
    return _embedding_model


def reranker_model():
    global _reranker_model
    if _reranker_model is None:
        if not RERANK_DIR.exists():
            raise RuntimeError(f"BGE 重排模型目录不存在：{RERANK_DIR}")
        from FlagEmbedding import FlagReranker

        _reranker_model = FlagReranker(str(RERANK_DIR), use_fp16=False)
    return _reranker_model


@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": "cpu",
        "embedding_model": "BAAI/bge-m3",
        "embedding_downloaded": EMBEDDING_DIR.exists(),
        "embedding_loaded": _embedding_model is not None,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_downloaded": RERANK_DIR.exists(),
        "reranker_loaded": _reranker_model is not None,
    }


@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest):
    texts = [request.input] if isinstance(request.input, str) else request.input
    texts = [str(text).strip() for text in texts]
    if not texts or any(not text for text in texts):
        raise HTTPException(422, "input 不能为空")
    try:
        with _embedding_lock:
            output = embedding_model().encode(
                texts,
                batch_size=min(4, len(texts)),
                max_length=int(os.getenv("BGE_MAX_LENGTH", "1024")),
            )
        vectors = output["dense_vecs"]
        return {
            "object": "list",
            "model": request.model,
            "data": [
                {"object": "embedding", "index": index, "embedding": vector.tolist()}
                for index, vector in enumerate(vectors)
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"本地向量模型运行失败：{exc}") from exc


@app.post("/v1/rerank")
@app.post("/rerank")
def rerank(request: RerankRequest):
    if not request.query.strip() or not request.documents:
        raise HTTPException(422, "query 和 documents 不能为空")
    pairs = [[request.query, document] for document in request.documents]
    try:
        with _reranker_lock:
            scores = reranker_model().compute_score(pairs, normalize=True)
        if isinstance(scores, (float, int)):
            scores = [float(scores)]
        ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)
        results = []
        for index, score in ranked[: min(request.top_n, len(ranked))]:
            row = {"index": index, "relevance_score": float(score)}
            if request.return_documents:
                row["document"] = {"text": request.documents[index]}
            results.append(row)
        return {"model": request.model, "results": results}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"本地重排模型运行失败：{exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8004")))
