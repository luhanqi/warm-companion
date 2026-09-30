# -*- coding: utf-8 -*-
"""把模型 ID 解析为提交包中的本地模型；缺失时才尝试下载。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
CACHE = ROOT / "hf_cache"


def resolve_model(model_id: str) -> str:
    direct = Path(model_id).expanduser()
    if direct.exists() and (direct / "config.json").exists():
        return str(direct)

    name = model_id.rstrip("/").split("/")[-1]
    bundled = PROJECT_ROOT / "models" / name
    if bundled.exists() and (bundled / "config.json").exists():
        print("bundled model:", bundled)
        return str(bundled)

    for cfg in CACHE.glob("**/config.json"):
        parent = cfg.parent
        if name in str(parent) and any(parent.glob("*.safetensors")):
            print("local cache:", parent)
            return str(parent)

    last_err = None
    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_download

        path = ms_download(model_id, cache_dir=str(CACHE / "modelscope"))
        print("ModelScope:", path)
        return path
    except Exception as exc:
        last_err = exc
        print("ModelScope 失败：", exc)

    try:
        from huggingface_hub import snapshot_download

        path = snapshot_download(model_id, cache_dir=str(CACHE / "huggingface"))
        print("Hugging Face:", path)
        return path
    except Exception as exc:
        last_err = exc

    raise SystemExit("找不到基础模型 %s：%s" % (model_id, last_err))
