from __future__ import annotations

import base64
import io
import os
import urllib.parse
import wave
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


def _value(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _headers(key_name: str) -> Dict[str, str]:
    key = _value(key_name)
    return {"Authorization": "Bearer " + key} if key else {}


def service_is_local(name: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(_value(name))
    except ValueError:
        return False
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def _reachable(base_url: str) -> bool:
    """Probe local services; remote configuration is not reported as healthy blindly."""
    if not base_url:
        return False
    parsed = urllib.parse.urlparse(base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    health_url = "%s://%s%s/health" % (
        parsed.scheme or "http",
        parsed.netloc,
        "" if not parsed.path or parsed.path == "/" else "",
    )
    try:
        response = httpx.get(health_url, timeout=0.8, trust_env=False)
        return response.status_code == 200
    except Exception:
        return False


def service_status() -> Dict[str, Dict[str, Any]]:
    """Return safe configuration state without exposing keys or service URLs."""
    embedding_base = _value("EMBEDDING_BASE_URL")
    rerank_base = _value("RERANK_BASE_URL") or embedding_base
    speech_base = _value("SPEECH_BASE_URL")
    acoustic_base = _value("ACOUSTIC_BASE_URL")
    vision_base = _value("VISION_BASE_URL")
    return {
        "memory_embedding": {"enabled": bool(embedding_base and (service_is_local("EMBEDDING_BASE_URL") or _value("EMBEDDING_API_KEY"))), "available": _reachable(embedding_base), "model": _value("EMBEDDING_MODEL", "BAAI/bge-m3")},
        "memory_reranker": {"enabled": bool(rerank_base and (service_is_local("RERANK_BASE_URL") or service_is_local("EMBEDDING_BASE_URL") or _value("RERANK_API_KEY") or _value("EMBEDDING_API_KEY"))), "available": _reachable(rerank_base), "model": _value("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")},
        "speech": {"enabled": bool(speech_base), "available": _reachable(speech_base), "model": _value("SPEECH_MODEL", "SenseVoiceSmall")},
        "acoustic": {"enabled": bool(acoustic_base), "available": _reachable(acoustic_base), "model": _value("ACOUSTIC_MODEL", "openSMILE-eGeMAPSv02")},
        "vision": {"enabled": bool(vision_base and (service_is_local("VISION_BASE_URL") or _value("VISION_API_KEY"))), "available": _reachable(vision_base), "model": _value("VISION_MODEL", "Qwen/Qwen2-VL-2B-Instruct")},
        "personal_voice": {"enabled": bool(_value("COSYVOICE_BASE_URL")), "available": _reachable(_value("COSYVOICE_BASE_URL")), "model": _value("COSYVOICE_MODEL", "Fun-CosyVoice3")},
        "memory_video": {"enabled": bool(_value("VIDEO_SERVICE_URL")), "model": _value("VIDEO_MODEL", "wan2.7-i2v-2026-04-25")},
        "cognition_research": {"enabled": bool(_value("COGNITION_MODEL_URL")), "model": _value("COGNITION_MODEL_NAME", "custom-validated-classifier")},
    }


def transcribe_audio(path: Path, mime_type: str) -> Optional[Dict[str, Any]]:
    base = _value("SPEECH_BASE_URL").rstrip("/")
    if not base:
        return None
    with path.open("rb") as stream:
        response = httpx.post(
            base + _value("SPEECH_TRANSCRIBE_PATH", "/v1/audio/transcriptions"),
            headers=_headers("SPEECH_API_KEY"),
            data={"model": _value("SPEECH_MODEL", "SenseVoiceSmall"), "language": _value("SPEECH_LANGUAGE", "zh"), "response_format": "verbose_json"},
            files={"file": (path.name, stream, mime_type or "audio/webm")},
            timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
            trust_env=False,
        )
    response.raise_for_status()
    data = response.json()
    return {
        "text": str(data.get("text") or data.get("transcript") or "").strip(),
        "provider": str(data.get("provider") or _value("SPEECH_MODEL", "SenseVoiceSmall")),
        "emotion": data.get("emotion") or "",
        "events": data.get("events") or [],
        "segments": data.get("segments") or [],
    }


def analyze_acoustics(path: Path, mime_type: str) -> Optional[Dict[str, Any]]:
    base = _value("ACOUSTIC_BASE_URL").rstrip("/")
    if not base:
        return None
    with path.open("rb") as stream:
        response = httpx.post(
            base + _value("ACOUSTIC_ANALYZE_PATH", "/analyze"),
            headers=_headers("ACOUSTIC_API_KEY"),
            data={"feature_set": _value("ACOUSTIC_FEATURE_SET", "eGeMAPSv02")},
            files={"file": (path.name, stream, mime_type or "audio/webm")},
            timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
            trust_env=False,
        )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else None


def analyze_photo(path: Path, caption: str = "") -> Optional[Dict[str, str]]:
    key = _value("VISION_API_KEY")
    base = _value("VISION_BASE_URL").rstrip("/")
    if not base or (not key and not service_is_local("VISION_BASE_URL")):
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    prompt = (
        "请客观描述这张老照片中可见的人物、环境、活动和可能的年代线索。"
        "不要猜测具体姓名、亲属关系或不存在的经历；不确定处明确写可能。"
        "用100字以内中文回答。已有说明：" + (caption or "无")
    )
    response = httpx.post(
        base + "/chat/completions",
        headers={**_headers("VISION_API_KEY"), "Content-Type": "application/json"},
        json={
            "model": _value("VISION_MODEL", "Qwen/Qwen2-VL-2B-Instruct"),
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, encoded)}}]}],
            "temperature": 0.2,
        },
        timeout=float(_value("VISION_TIMEOUT_SECONDS", _value("MODEL_TIMEOUT_SECONDS", "90"))),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return {"description": str(content).strip(), "provider": _value("VISION_MODEL", "Qwen/Qwen2-VL-2B-Instruct")}


def _pcm_to_wav(raw: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(raw)
    return output.getvalue()


def synthesize_personal_voice(text: str, prompt_path: Path, prompt_text: str) -> Optional[bytes]:
    base = _value("COSYVOICE_BASE_URL").rstrip("/")
    if not base or not prompt_path.exists():
        return None
    with prompt_path.open("rb") as stream:
        response = httpx.post(
            base + _value("COSYVOICE_PATH", "/inference_zero_shot"),
            headers=_headers("COSYVOICE_API_KEY"),
            data={"tts_text": text, "prompt_text": prompt_text},
            files={"prompt_wav": (prompt_path.name, stream, "audio/webm" if prompt_path.suffix.lower() == ".webm" else "audio/wav")},
            timeout=float(_value("TTS_TIMEOUT_SECONDS", "120")),
            trust_env=False,
        )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "wav" in content_type or response.content[:4] == b"RIFF":
        return response.content
    return _pcm_to_wav(response.content, int(_value("COSYVOICE_SAMPLE_RATE", "24000")))


def submit_memory_video(photo_path: Path, narration: str, title: str, audio_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """Submit either to DashScope Wan or to a compatible self-hosted wrapper."""
    base = _value("VIDEO_SERVICE_URL").rstrip("/")
    if not base or not photo_path.exists():
        return None
    provider = _value("VIDEO_PROVIDER", "dashscope").lower()
    if provider == "dashscope":
        mime = "image/png" if photo_path.suffix.lower() == ".png" else "image/jpeg"
        image_data = "data:%s;base64,%s" % (mime, base64.b64encode(photo_path.read_bytes()).decode("ascii"))
        response = httpx.post(
            base + "/services/aigc/video-generation/video-synthesis",
            headers={**_headers("VIDEO_API_KEY"), "X-DashScope-Async": "enable", "Content-Type": "application/json"},
            json={
                "model": _value("VIDEO_MODEL", "wan2.7-i2v-2026-04-25"),
                "input": {
                    "prompt": (title + "。" + narration).strip("。"),
                    "media": [{"type": "first_frame", "url": image_data}],
                },
                "parameters": {
                    "resolution": _value("VIDEO_RESOLUTION", "720P"),
                    "duration": int(_value("VIDEO_DURATION", "5")),
                    "prompt_extend": True,
                    "watermark": True,
                },
            },
            timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
            trust_env=False,
        )
        response.raise_for_status()
        output = response.json().get("output") or {}
        return {
            "job_id": str(output.get("task_id") or ""),
            "status": str(output.get("task_status") or "PENDING").lower(),
            "video_url": str(output.get("video_url") or ""),
            "provider": _value("VIDEO_MODEL", "wan2.7-i2v-2026-04-25"),
        }
    files: Dict[str, Any] = {"image": (photo_path.name, photo_path.read_bytes(), "image/jpeg")}
    if audio_path and audio_path.exists():
        files["audio"] = (audio_path.name, audio_path.read_bytes(), "audio/webm")
    response = httpx.post(
        base + _value("VIDEO_GENERATE_PATH", "/generate"),
        headers=_headers("VIDEO_API_KEY"),
        data={"model": _value("VIDEO_MODEL", "Wan2.2-TI2V-5B"), "prompt": narration, "title": title},
        files=files,
        timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "job_id": str(data.get("job_id") or data.get("task_id") or ""),
        "status": str(data.get("status") or "submitted"),
        "video_url": str(data.get("video_url") or data.get("url") or ""),
        "provider": str(data.get("provider") or _value("VIDEO_MODEL", "Wan2.2-TI2V-5B")),
    }


def poll_memory_video(job_id: str) -> Optional[Dict[str, str]]:
    base = _value("VIDEO_SERVICE_URL").rstrip("/")
    if not base or not job_id:
        return None
    provider = _value("VIDEO_PROVIDER", "dashscope").lower()
    path = "/tasks/" + job_id if provider == "dashscope" else _value("VIDEO_TASK_PATH", "/tasks/{job_id}").replace("{job_id}", job_id)
    response = httpx.get(
        base + path,
        headers=_headers("VIDEO_API_KEY"),
        timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    output = data.get("output") or data
    return {
        "job_id": job_id,
        "status": str(output.get("task_status") or output.get("status") or "unknown").lower(),
        "video_url": str(output.get("video_url") or output.get("url") or ""),
        "provider": _value("VIDEO_MODEL", "wan2.7-i2v-2026-04-25"),
    }


def download_video(url: str, target: Path) -> bool:
    if not url:
        return False
    with httpx.stream("GET", url, timeout=180.0, follow_redirects=True, trust_env=False) as response:
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
    return target.exists() and target.stat().st_size > 0


def estimate_cognitive_risk(daily_metrics: Any, voice_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Send aggregate features only; never send transcript text to the research model."""
    url = _value("COGNITION_MODEL_URL")
    if not url:
        return None
    safe_days = []
    for row in list(daily_metrics or [])[:90]:
        safe_days.append({
            key: row.get(key)
            for key in (
                "day", "sample_count", "lexical_diversity", "repetition_ratio",
                "filler_ratio", "coherence", "completeness", "quality",
            )
        })
    response = httpx.post(
        url,
        headers={**_headers("COGNITION_MODEL_API_KEY"), "Content-Type": "application/json"},
        json={"model": _value("COGNITION_MODEL_NAME", "custom-validated-classifier"), "daily_metrics": safe_days, "voice_summary": voice_summary},
        timeout=float(_value("MODEL_TIMEOUT_SECONDS", "90")),
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "risk_score": data.get("risk_score"),
        "level": str(data.get("level") or "unknown"),
        "model_version": str(data.get("model_version") or _value("COGNITION_MODEL_NAME", "custom-validated-classifier")),
        "validated": bool(data.get("validated", False)),
        "disclaimer": "研究型趋势信号，不是疾病诊断；需要由专业人员结合正式评估解释。",
    }
