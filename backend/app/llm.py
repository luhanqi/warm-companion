from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextvars import ContextVar, Token
from typing import Dict, Iterator, List, Optional

from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_CLOUD_PROCESSING_ALLOWED: ContextVar[bool] = ContextVar(
    "nuanban_cloud_processing_allowed", default=False
)


def bind_cloud_processing(allowed: bool) -> Token:
    return _CLOUD_PROCESSING_ALLOWED.set(bool(allowed))


def reset_cloud_processing(token: Token) -> None:
    _CLOUD_PROCESSING_ALLOWED.reset(token)


def cloud_processing_allowed() -> bool:
    return _CLOUD_PROCESSING_ALLOWED.get()

SYSTEM_PROMPT = """你是「暖伴」，专门陪老年人聊天的朋友。
要求：
- 自称暖伴。语气慢、句子短、用口语。
- 一次只问一个问题。
- 会自然提起记忆里的家人或爱好，不要像在念档案。
- 听不清或不确定就请对方再说，不要编造姓名或事实。
- 不诊断疾病、不指导用药、不替代家人。
- 不要提及你是人工智能、大模型或智能体。
- 回复控制在 80 字以内。"""


def llm_enabled() -> bool:
    return bool(os.getenv("LLM_API_KEY", "").strip())


def uses_local_model() -> bool:
    base = os.getenv("LLM_BASE_URL", "")
    return "127.0.0.1" in base or "localhost" in base


def deepseek_key() -> str:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key
    key = (os.getenv("LLM_API_KEY") or "").strip()
    if key and key.lower() != "local":
        return key
    return ""


def deepseek_enabled() -> bool:
    return bool(deepseek_key())


def _deepseek_headers() -> Dict[str, str]:
    return {
        "Authorization": "Bearer %s" % deepseek_key(),
        "Content-Type": "application/json",
    }


def _deepseek_url() -> str:
    base = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    if not base.endswith("/chat/completions"):
        base = base + "/chat/completions"
    return base


def _deepseek_model() -> str:
    return os.getenv("DEEPSEEK_MODEL") or "deepseek-flash"


def _deepseek_open(payload: dict, timeout: float):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _deepseek_url(),
        data=body,
        headers=_deepseek_headers(),
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": "Bearer %s" % os.getenv("LLM_API_KEY", "").strip(),
        "Content-Type": "application/json",
    }


def _endpoint() -> str:
    base = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if not base.endswith("/chat/completions"):
        base = base + "/chat/completions"
    return base


def stream_chat(messages: List[Dict[str, str]]) -> Iterator[str]:
    if not uses_local_model() and not cloud_processing_allowed():
        raise PermissionError("老人尚未授权云端对话处理")
    payload = {
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "stream": True,
        "temperature": 0.7,
    }
    timeout = httpx.Timeout(300.0, connect=30.0) if uses_local_model() else httpx.Timeout(60.0)
    with httpx.Client(timeout=timeout, trust_env=not uses_local_model()) as client:
        with client.stream("POST", _endpoint(), headers=_headers(), json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="ignore")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (((chunk.get("choices") or [{}])[0]).get("delta") or {}).get("content")
                if delta:
                    yield delta


def complete_json(prompt: str) -> Optional[dict]:
    if not llm_enabled():
        return None
    if not uses_local_model() and not cloud_processing_allowed():
        return None
    payload = {
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "只输出 JSON，不要解释。"},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(_endpoint(), headers=_headers(), json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end < 0:
            return None
        return json.loads(content[start : end + 1])
    except Exception:
        return None


def complete_deepseek_json(prompt: str) -> Optional[dict]:
    if not deepseek_enabled() or not cloud_processing_allowed():
        return None
    payload = {
        "model": _deepseek_model(),
        "messages": [
            {"role": "system", "content": "只输出 JSON 对象，不要解释，不要用 markdown。"},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        with _deepseek_open(payload, 45.0) as resp:
            content = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end < 0:
            return None
        return json.loads(content[start : end + 1])
    except Exception as exc:
        print("DeepSeek JSON 调用失败：", exc)
        return None


PAGE_CHAT_PROMPT = """你是「暖伴」，陪老人说话。自称暖伴，句子短，口语。
不诊断、不指导用药、不提自己是模型。回复控制在 80 字以内。
用户现在在「%s」这一页。能帮他办这一页的事就办；只是闲聊就好好陪着。"""


def stream_deepseek(page_title: str, user_text: str) -> Iterator[str]:
    if not deepseek_enabled():
        return
        yield  # pragma: no cover
    if not cloud_processing_allowed():
        raise PermissionError("老人尚未授权云端对话处理")
    payload = {
        "model": _deepseek_model(),
        "messages": [
            {"role": "system", "content": PAGE_CHAT_PROMPT % (page_title or "暖伴")},
            {"role": "user", "content": user_text},
        ],
        "stream": True,
        "temperature": 0.7,
    }
    yield from _stream_deepseek_payload(payload)


def stream_deepseek_messages(messages: List[Dict[str, str]]) -> Iterator[str]:
    """Use DeepSeek for the main companion chat while retaining RAG context."""
    if not deepseek_enabled():
        return
        yield  # pragma: no cover
    if not cloud_processing_allowed():
        raise PermissionError("老人尚未授权云端对话处理")
    payload = {
        "model": _deepseek_model(),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages),
        "stream": True,
        "temperature": 0.7,
    }
    yield from _stream_deepseek_payload(payload)


def _stream_deepseek_payload(payload: dict) -> Iterator[str]:
    try:
        with _deepseek_open(payload, 60.0) as resp:
            while True:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (((chunk.get("choices") or [{}])[0]).get("delta") or {}).get("content")
                if delta:
                    yield delta
    except urllib.error.HTTPError as exc:
        print("DeepSeek 对话失败：", exc.read().decode("utf-8", errors="ignore")[:300])
        raise
    except Exception as exc:
        print("DeepSeek 对话失败：", exc)
        raise
