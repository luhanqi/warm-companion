"""Resume the official Wan2.2 TI2V-5B download into the D: model store."""
from __future__ import annotations

import os
from pathlib import Path

from modelscope import snapshot_download


MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B"
MODEL_ROOT = Path(os.getenv("NUANBAN_MODEL_ROOT", str(Path(__file__).resolve().parents[1] / "models")))
TARGET = MODEL_ROOT / "Wan2.2-TI2V-5B"


if __name__ == "__main__":
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Downloading/resuming {MODEL_ID} -> {TARGET}", flush=True)
    result = snapshot_download(
        MODEL_ID,
        local_dir=str(TARGET),
        cache_dir=str(MODEL_ROOT / "cache"),
    )
    print(f"DOWNLOAD_COMPLETE={result}", flush=True)
