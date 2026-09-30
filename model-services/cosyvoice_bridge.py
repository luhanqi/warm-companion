"""Run this file inside the official CosyVoice Python 3.10 environment.

It accepts the browser's WebM prompt recording, converts it to 16 kHz WAV with
FFmpeg, and exposes the endpoint expected by the warm-companion backend.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

repo_dir = Path(os.getenv("COSYVOICE_REPO", "")).expanduser()
if str(repo_dir) not in ("", "."):
    sys.path.insert(0, str(repo_dir.resolve()))
    sys.path.insert(0, str((repo_dir / "third_party" / "Matcha-TTS").resolve()))

from cosyvoice.cli.cosyvoice import AutoModel

app = FastAPI(title="暖伴 CosyVoice 服务")
model = AutoModel(model_dir=os.getenv("COSYVOICE_MODEL_DIR", "pretrained_models/Fun-CosyVoice3-0.5B"))


def to_wav(source: Path, target: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg = "ffmpeg"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-ac", "1", "-ar", "16000", str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise HTTPException(500, "请安装 FFmpeg 并确保 ffmpeg 命令可用") from exc


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    values = np.clip(samples, -1, 1)
    pcm = (values * 32767).astype(np.int16).tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(pcm)
    return output.getvalue()


@app.get("/health")
def health():
    return {"status": "ok", "model": os.getenv("COSYVOICE_MODEL_DIR", "Fun-CosyVoice3-0.5B")}


@app.post("/inference_zero_shot")
def inference_zero_shot(
    tts_text: str = Form(...), prompt_text: str = Form(...), prompt_wav: UploadFile = File(...)
) -> Response:
    if not tts_text.strip() or not prompt_text.strip():
        raise HTTPException(400, "合成文字和音色样本文字不能为空")
    with tempfile.TemporaryDirectory(prefix="nuanban-cosy-") as temp:
        directory = Path(temp)
        source = directory / ("prompt" + (Path(prompt_wav.filename or "voice.webm").suffix or ".webm"))
        with source.open("wb") as output:
            shutil.copyfileobj(prompt_wav.file, output)
        if source.suffix.lower() == ".wav":
            decoded = source
        else:
            decoded = directory / "decoded.wav"
            to_wav(source, decoded)
        # CosyVoice 3 requires the instruction boundary in both target and
        # prompt text.  Older model releases did not, so only add it when the
        # caller has not supplied one.
        boundary = "You are a helpful assistant.<|endofprompt|>"
        target_text = tts_text.strip()
        reference_text = prompt_text.strip()
        if "<|endofprompt|>" not in target_text:
            target_text = boundary + target_text
        if "<|endofprompt|>" not in reference_text:
            reference_text = boundary + reference_text
        chunks = []
        for result in model.inference_zero_shot(
            target_text, reference_text, str(decoded), stream=False
        ):
            chunks.append(result["tts_speech"].detach().cpu().numpy().reshape(-1))
        if not chunks:
            raise HTTPException(500, "模型没有生成音频")
        audio = wav_bytes(np.concatenate(chunks), int(getattr(model, "sample_rate", 24000)))
        return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "50000")))
