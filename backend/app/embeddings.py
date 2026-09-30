from __future__ import annotations

import math
import os
import re
import hashlib
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx


def embedding_enabled() -> bool:
    base = os.getenv("EMBEDDING_BASE_URL", "").strip()
    return bool(base and (embedding_is_local() or os.getenv("EMBEDDING_API_KEY", "").strip()))


def embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3").strip()


def _loopback_url(value: str) -> bool:
    try:
        return (urlparse(value).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


def embedding_is_local() -> bool:
    return _loopback_url(os.getenv("EMBEDDING_BASE_URL", ""))


def reranker_is_local() -> bool:
    base = os.getenv("RERANK_BASE_URL") or os.getenv("EMBEDDING_BASE_URL") or ""
    return _loopback_url(base)


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Use any OpenAI-compatible embedding service when configured.

    No personal memory leaves the device unless the elder has explicitly enabled
    external memory processing and an operator has configured this provider.
    """
    key = os.getenv("EMBEDDING_API_KEY", "").strip()
    base = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
    if not texts or (not key and not _loopback_url(base)):
        return None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    response = httpx.post(
        base + "/embeddings",
        headers=headers,
        json={"model": embedding_model(), "input": texts},
        timeout=30.0,
        trust_env=False,
    )
    response.raise_for_status()
    rows = sorted(response.json().get("data") or [], key=lambda item: item.get("index", 0))
    vectors = [row.get("embedding") or [] for row in rows]
    return vectors if len(vectors) == len(texts) and all(vectors) else None


def rerank_documents(query: str, documents: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Use a SiliconFlow-compatible rerank endpoint when configured."""
    key = (os.getenv("RERANK_API_KEY") or os.getenv("EMBEDDING_API_KEY") or "").strip()
    base = (os.getenv("RERANK_BASE_URL") or os.getenv("EMBEDDING_BASE_URL") or "").strip().rstrip("/")
    if not base or not query or not documents or (not key and not _loopback_url(base)):
        return None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    response = httpx.post(
        base + "/rerank",
        headers=headers,
        json={
            "model": (os.getenv("RERANK_MODEL") or "BAAI/bge-reranker-v2-m3").strip(),
            "query": query,
            "documents": [item.get("text") or "" for item in documents],
            "top_n": min(5, len(documents)),
            "return_documents": False,
        },
        timeout=30.0,
        trust_env=False,
    )
    response.raise_for_status()
    ranked = []
    for row in response.json().get("results") or []:
        index = int(row.get("index", -1))
        if 0 <= index < len(documents):
            item = dict(documents[index])
            item["rerank_score"] = float(row.get("relevance_score") or row.get("score") or 0)
            ranked.append(item)
    return ranked or None


def hashed_vector(text: str, dimensions: int = 384) -> List[float]:
    """Private local fallback: a normalized hashed Chinese unigram/bigram vector."""
    chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", (text or "").lower())
    features = chars + ["".join(chars[index : index + 2]) for index in range(len(chars) - 1)]
    vector = [0.0] * dimensions
    for token, count in Counter(features).items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest, "big") % dimensions
        vector[index] += 1.0 + math.log(max(1, count))
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a, b = list(left), list(right)
    if not a or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
