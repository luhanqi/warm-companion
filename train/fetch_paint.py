# -*- coding: utf-8 -*-
"""用 Python 3.12 拉取文生图。后端 3.8 的 OpenSSL 打不开这些站点。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from urllib.parse import quote

import httpx


def strip_watermark(data: bytes, mime: str) -> tuple[bytes, str]:
    """Preserve provider output; never conceal provenance or remove a watermark."""
    return data, mime


def fetch_pollinations(prompt: str) -> tuple[bytes, str]:
    seed = random.randint(1, 999999)
    encoded = quote(prompt, safe="")
    url = (
        "https://image.pollinations.ai/prompt/%s"
        "?width=768&height=768&nologo=true&nofeed=true&seed=%s"
        % (encoded, seed)
    )
    timeout = httpx.Timeout(90.0, connect=20.0)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Nuanban/1.0)"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        mime = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
        if not mime.startswith("image/") or len(resp.content) < 2000:
            raise RuntimeError("画图服务没有返回图片")
        return strip_watermark(resp.content, mime)


def fetch_siliconflow(prompt: str, key: str, model: str) -> tuple[bytes, str]:
    if not (key or "").strip():
        raise RuntimeError("还没有硅基流动密钥，无法用通义作画")
    timeout = httpx.Timeout(90.0, connect=20.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(
            "https://api.siliconflow.cn/v1/images/generations",
            headers={
                "Authorization": "Bearer %s" % key,
                "Content-Type": "application/json",
                "X-Enable-Watermark": "0",
            },
            json={"model": model, "prompt": prompt, "image_size": "1024x1024", "batch_size": 1},
        )
        resp.raise_for_status()
        payload = resp.json()
        images = payload.get("images") or payload.get("data") or []
        if not images:
            raise RuntimeError("通义作画没有返回图片")
        first = images[0]
        url = first.get("url") if isinstance(first, dict) else None
        b64 = first.get("b64_json") if isinstance(first, dict) else None
        if url:
            img = client.get(url)
            img.raise_for_status()
            mime = (img.headers.get("content-type") or "image/jpeg").split(";")[0]
            return strip_watermark(img.content, mime)
        if b64:
            import base64

            return strip_watermark(base64.b64decode(b64), "image/png")
        raise RuntimeError("通义作画返回格式不认识")


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    prompt = job["prompt"]
    out = Path(job["out"])
    provider = job.get("provider") or "pollinations"
    if provider == "siliconflow":
        data, mime = fetch_siliconflow(
            prompt, job["api_key"], job.get("model") or "Tongyi-MAI/Z-Image-Turbo"
        )
    else:
        data, mime = fetch_pollinations(prompt)
        provider = "pollinations"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    Path(job["meta"]).write_text(
        json.dumps({"mime": mime, "provider": provider}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
