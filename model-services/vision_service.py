"""OpenAI-compatible local photo understanding service for Warm Companion.

The model is loaded lazily so starting the project does not immediately occupy
several gigabytes of RAM.  The API intentionally matches the existing
``/v1/chat/completions`` adapter used by the backend.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List

import torch
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field


app = FastAPI(title="暖伴本地照片理解服务")

# PyTorch used only one CPU core on this Windows machine unless configured.
# A modest cap speeds up Qwen2-VL without starving the chat and RAG services.
torch.set_num_threads(max(1, min(8, os.cpu_count() or 4)))
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

MODEL_ROOT = Path(os.getenv("NUANBAN_MODEL_ROOT", str(Path(__file__).resolve().parents[1] / "models")))
MODEL_DIR = Path(os.getenv("VISION_MODEL_DIR", str(MODEL_ROOT / "Qwen2-VL-2B-Instruct")))
MODEL_NAME = os.getenv("VISION_MODEL_NAME", "Qwen/Qwen2-VL-2B-Instruct")
MAX_PIXELS = int(os.getenv("VISION_MAX_PIXELS", str(448 * 448)))
MAX_NEW_TOKENS = int(os.getenv("VISION_MAX_NEW_TOKENS", "32"))

_processor = None
_model = None
_load_lock = Lock()
_inference_lock = Lock()


class ChatRequest(BaseModel):
    model: str = MODEL_NAME
    messages: List[Dict[str, Any]]
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=512)


def _load_model():
    global _processor, _model
    if _model is not None and _processor is not None:
        return _processor, _model
    with _load_lock:
        if _model is not None and _processor is not None:
            return _processor, _model
        if not (MODEL_DIR / "config.json").exists():
            raise RuntimeError(f"照片理解模型目录不存在或下载未完成：{MODEL_DIR}")
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        _processor = AutoProcessor.from_pretrained(
            str(MODEL_DIR),
            local_files_only=True,
            use_fast=False,
            min_pixels=56 * 56,
            max_pixels=MAX_PIXELS,
        )
        # BF16 is not supported by every CPU.  Use FP32 on CPU so the service
        # fails less often; CUDA can retain BF16 when the device supports it.
        dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float32
        _model = Qwen2VLForConditionalGeneration.from_pretrained(
            str(MODEL_DIR),
            local_files_only=True,
            dtype=dtype,
            attn_implementation="eager",
            low_cpu_mem_usage=True,
        ).eval()
        if torch.cuda.is_available():
            _model = _model.to("cuda")
    return _processor, _model


def _decode_image(value: str) -> Image.Image:
    if not value.startswith("data:image/") or ";base64," not in value:
        raise HTTPException(422, "本地照片理解仅接受 data:image/...;base64 格式")
    try:
        encoded = value.split(",", 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert("RGB")
    except Exception as exc:
        raise HTTPException(422, "图片数据无法解析") from exc


def _extract_user_content(messages: List[Dict[str, Any]]) -> tuple[str, Image.Image]:
    texts: List[str] = []
    image = None
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        for item in content or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
            elif item.get("type") == "image_url":
                image_value = item.get("image_url") or {}
                if isinstance(image_value, dict):
                    image_value = image_value.get("url") or ""
                image = _decode_image(str(image_value))
    if image is None:
        raise HTTPException(422, "请求中缺少图片")
    return "\n".join(text for text in texts if text.strip()), image


@app.get("/health")
def health():
    complete = (MODEL_DIR / "model-00001-of-00002.safetensors").exists() and (
        MODEL_DIR / "model-00002-of-00002.safetensors"
    ).exists()
    return {
        "status": "ok" if complete else "model_incomplete",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "loaded": _model is not None,
        "model": MODEL_NAME,
        "model_dir": str(MODEL_DIR),
        "downloaded": complete,
        "loaded": _model is not None,
    }


@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest):
    prompt, image = _extract_user_content(request.messages)
    try:
        processor, model = _load_model()
        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt or "请客观描述这张照片。"},
                ],
            }
        ]
        rendered = processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[rendered], images=[image], padding=True, return_tensors="pt")
        device = next(model.parameters()).device
        for key, value in list(inputs.items()):
            if torch.is_floating_point(value):
                inputs[key] = value.to(device=device, dtype=model.dtype)
            else:
                inputs[key] = value.to(device=device)
        with _inference_lock, torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=min(request.max_tokens or MAX_NEW_TOKENS, MAX_NEW_TOKENS),
                do_sample=False,
                use_cache=True,
            )
        trimmed = generated[:, inputs.input_ids.shape[1] :]
        answer = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
        return {
            "id": "local-qwen2-vl",
            "object": "chat.completion",
            "model": request.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": int(inputs.input_ids.numel()), "completion_tokens": int(trimmed.numel())},
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"本地照片理解模型运行失败：{exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8005")))
