"""Independent SenseVoice + openSMILE service for 暖伴.

Use Python 3.10 or 3.11. Keep this environment separate from backend/.venv.
FFmpeg must be available on PATH so browser WebM recordings can be decoded.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

app = FastAPI(title="暖伴语音模型服务")
_speech_model = None
_smile_models: Dict[str, Any] = {}


def speech_model():
    global _speech_model
    if _speech_model is None:
        from funasr import AutoModel

        _speech_model = AutoModel(
            model=os.getenv("SENSEVOICE_MODEL_DIR", "iic/SenseVoiceSmall"),
            vad_model=os.getenv("VAD_MODEL_DIR", "fsmn-vad"),
            vad_kwargs={"max_single_segment_time": 30000},
            device=os.getenv("SPEECH_DEVICE", "cpu"),
            disable_update=True,
        )
    return _speech_model


def wav_path(source: Path, directory: Path) -> Path:
    if source.suffix.lower() == ".wav":
        return source
    target = directory / "decoded.wav"
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
    return target


def save_upload(file: UploadFile, directory: Path) -> Path:
    suffix = Path(file.filename or "voice.webm").suffix or ".webm"
    target = directory / ("input" + suffix)
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return target


def parse_rich_text(raw: str) -> Dict[str, Any]:
    emotion_match = re.search(r"<\|([A-Z]+)\|>", raw or "")
    events = re.findall(r"<\|(BGM|Speech|Applause|Laughter|Cry|Sneeze|Breath|Cough)\|>", raw or "", re.I)
    clean = re.sub(r"<\|[^>]+\|>", "", raw or "").strip()
    return {"text": clean, "emotion": emotion_match.group(1) if emotion_match else "", "events": events}


def basic_acoustic_metrics(audio: Path) -> Dict[str, Any]:
    """Derive pause and energy metrics used by the longitudinal trend code."""
    with wave.open(str(audio), "rb") as source:
        sample_rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        raw = source.readframes(source.getnframes())
    if width != 2:
        raise HTTPException(422, "声学分析需要 16 位 PCM 音频")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if not samples.size:
        raise HTTPException(422, "录音中没有可分析的声音")
    samples /= 32768.0
    frame_size = max(1, int(sample_rate * 0.02))
    usable = samples[: (len(samples) // frame_size) * frame_size]
    if not usable.size:
        usable = np.pad(samples, (0, frame_size - len(samples)))
    frames = usable.reshape(-1, frame_size)
    energies = np.sqrt(np.mean(frames * frames, axis=1))
    noise_floor = float(np.percentile(energies, 20)) if energies.size else 0.0
    # A percentile alone can land inside speech for clips with little silence.
    # Cap the adaptive threshold so normal speech is not classified as silence.
    threshold = max(0.008, min(0.05, noise_floor * 2.5))
    voiced = energies >= threshold
    silence_ratio = float(1.0 - np.mean(voiced))
    silent_run = 0
    pause_count = 0
    longest_pause_frames = 0
    speech_segments = 0
    in_speech = False
    for is_voiced in voiced.tolist():
        if is_voiced:
            if silent_run >= 10:
                pause_count += 1
            longest_pause_frames = max(longest_pause_frames, silent_run)
            silent_run = 0
            if not in_speech:
                speech_segments += 1
                in_speech = True
        else:
            silent_run += 1
            in_speech = False
    longest_pause_frames = max(longest_pause_frames, silent_run)
    crossings = np.mean(np.abs(np.diff(np.signbit(samples)).astype(np.float32))) if len(samples) > 1 else 0
    return {
        "silence_ratio": round(max(0.0, min(1.0, silence_ratio)), 4),
        "pause_count": int(pause_count),
        "longest_pause_ms": int(longest_pause_frames * 20),
        "speech_segments": int(speech_segments),
        "rms": round(float(np.sqrt(np.mean(samples * samples))), 6),
        "peak": round(float(np.max(np.abs(samples))), 6),
        "zero_crossing_rate": round(float(crossings), 6),
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "speech": "SenseVoiceSmall", "acoustic": "openSMILE"}


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    model: str = Form("SenseVoiceSmall"),
    language: str = Form("zh"),
    response_format: str = Form("verbose_json"),
) -> Dict[str, Any]:
    del model, response_format
    with tempfile.TemporaryDirectory(prefix="nuanban-speech-") as temp:
        directory = Path(temp)
        source = save_upload(file, directory)
        audio = wav_path(source, directory)
        results = speech_model().generate(
            input=str(audio),
            cache={},
            language=language or "zh",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        raw = "".join(str(item.get("text") or "") for item in (results or []))
        parsed = parse_rich_text(raw)
        parsed.update({"provider": "SenseVoiceSmall", "segments": results or []})
        return parsed


@app.post("/analyze")
def analyze(file: UploadFile = File(...), feature_set: str = Form("eGeMAPSv02")) -> Dict[str, Any]:
    import opensmile

    allowed = {
        "eGeMAPSv02": opensmile.FeatureSet.eGeMAPSv02,
        "ComParE_2016": opensmile.FeatureSet.ComParE_2016,
    }
    chosen = feature_set if feature_set in allowed else "eGeMAPSv02"
    if chosen not in _smile_models:
        _smile_models[chosen] = opensmile.Smile(
            feature_set=allowed[chosen], feature_level=opensmile.FeatureLevel.Functionals
        )
    with tempfile.TemporaryDirectory(prefix="nuanban-acoustic-") as temp:
        directory = Path(temp)
        source = save_upload(file, directory)
        audio = wav_path(source, directory)
        frame = _smile_models[chosen].process_file(str(audio))
        if frame.empty:
            raise HTTPException(422, "录音中没有可分析的声音")
        row = frame.iloc[0]
        selected = {
            name: round(float(value), 6)
            for name, value in row.items()
            if any(token in name for token in ("F0", "Loudness", "jitter", "shimmer", "HNR", "VoicedSegments"))
        }
        return {
            "provider": "openSMILE",
            "feature_set": chosen,
            "features": selected,
            **basic_acoustic_metrics(audio),
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8003")))
