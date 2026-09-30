# -*- coding: utf-8 -*-
"""现成文生图。真正的下载走 train/.venv（Python 3.12），避开后端 3.8 的 TLS 问题。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
FETCH = ROOT / "train" / "fetch_paint.py"


def _paint_python() -> Path:
    """Pick a working modern Python instead of the deleted train/.venv runtime."""
    configured = (os.getenv("PAINT_PYTHON") or "").strip()
    candidates = [
        Path(configured) if configured else None,
        ROOT / ".venv-models" / "Scripts" / "python.exe",
        ROOT / "train" / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise RuntimeError("找不到可用的绘图 Python 环境")

STYLES = {
    "ink": {
        "label": "国画",
        "hint": "宣纸水墨，留白",
        "lead": "traditional Chinese ink painting",
    },
    "water": {
        "label": "水彩",
        "hint": "米色纸，柔边",
        "lead": "soft watercolor on cream paper",
    },
    "oil": {
        "label": "油画",
        "hint": "厚涂暖色",
        "lead": "warm nostalgic oil painting",
    },
    "story": {
        "label": "故事画",
        "hint": "温和绘本",
        "lead": "gentle storybook illustration",
    },
}


def style_meta() -> Dict[str, Dict[str, str]]:
    return {
        key: {"id": key, "label": item["label"], "hint": item["hint"]}
        for key, item in STYLES.items()
    }


def build_prompt(user_text: str, style: str) -> str:
    chosen = STYLES.get(style) or STYLES["water"]
    text = " ".join((user_text or "").strip().split())[:180]
    scene = _scene_en(text)
    extra = ""
    if any(word in text for word in ("院子", "麦田", "胡同", "槐树", "村子", "学校", "老家")):
        extra = ", nostalgic Chinese countryside, wide view"
    return (
        "%s of %s%s, the main subject must match the request, "
        "no letters, no watermark, no random landscape if not asked"
        % (chosen["lead"], scene, extra)
    )


def _scene_en(text: str) -> str:
    cleaned = text
    for prefix in ("请帮我画", "请画一个", "请画一幅", "请画", "画一个", "画一幅", "画一张", "画"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip(" ，、")
            break
    mapping = (
        ("奥特曼", "Ultraman, the Japanese tokusatsu giant hero in a silver red suit, full body"),
        ("孙悟空", "Sun Wukong the Monkey King"),
        ("嫦娥", "Chang'e the moon goddess"),
        ("村子口", "the entrance of an old Chinese village"),
        ("大槐树", "a huge old locust tree"),
        ("槐树", "an old locust tree"),
        ("乘凉", "people sitting in the summer shade"),
        ("老家的院子", "the courtyard of an old family home"),
        ("院子", "a traditional Chinese courtyard"),
        ("金色麦田", "a golden wheat field"),
        ("麦田", "a wheat field"),
        ("老北京胡同", "an old Beijing hutong alley"),
        ("胡同", "a Beijing hutong alley"),
        ("小时候的学校", "a rural primary school from decades ago"),
        ("学校", "an old village school"),
        ("夏天", "in summer"),
    )
    leftover = cleaned
    bits = []
    for cn, en in mapping:
        if cn in leftover:
            bits.append(en)
            leftover = leftover.replace(cn, "")
    leftover = leftover.replace("，", " ").replace("、", " ").strip(" ，。")
    if leftover:
        bits.append(leftover)
    if not bits:
        bits.append(cleaned or text)
    return ", ".join(bits)


def _provider() -> str:
    named = (os.getenv("PAINT_PROVIDER") or "").strip().lower()
    if named:
        return named
    if os.getenv("PAINT_API_KEY", "").strip() or os.getenv("SILICONFLOW_API_KEY", "").strip():
        return "siliconflow"
    return "pollinations"


def paint_status() -> Dict[str, object]:
    provider = _provider()
    key_present = bool(
        os.getenv("PAINT_API_KEY", "").strip()
        or os.getenv("SILICONFLOW_API_KEY", "").strip()
    )
    return {
        "enabled": provider == "pollinations" or key_present,
        "provider": provider,
        "model": os.getenv("PAINT_MODEL", "Tongyi-MAI/Z-Image-Turbo"),
    }


def generate_image(user_text: str, style: str) -> Tuple[bytes, str, str]:
    if not FETCH.exists():
        raise RuntimeError("找不到绘图下载脚本")
    paint_python = _paint_python()
    prompt = build_prompt(user_text, style)
    provider = _provider()
    with tempfile.TemporaryDirectory(prefix="nuanban-paint-") as temp:
        work = Path(temp)
        out = work / "art.bin"
        meta_path = work / "meta.json"
        job = work / "job.json"
        job.write_text(
            json.dumps(
                {
                    "prompt": prompt,
                    "out": str(out),
                    "meta": str(meta_path),
                    "provider": provider,
                    "api_key": os.getenv("PAINT_API_KEY", "").strip()
                    or os.getenv("SILICONFLOW_API_KEY", "").strip(),
                    "model": os.getenv("PAINT_MODEL", "Tongyi-MAI/Z-Image-Turbo"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(paint_python), str(FETCH), str(job)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or not out.exists():
            err = (result.stderr or result.stdout or "").strip()[-400:]
            raise RuntimeError(err or "画图脚本没有跑完")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return out.read_bytes(), meta.get("mime") or "image/jpeg", meta.get("provider") or provider
