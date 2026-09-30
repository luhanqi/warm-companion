# -*- coding: utf-8 -*-
"""读取 train/config.yaml。"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
    "sft_output": "outputs/sft-1.5b",
    "dpo_output": "outputs/dpo-1.5b",
    "merged_output": "outputs/merged-1.5b",
    "epochs": 3,
    "learning_rate": 1e-4,
    "lora_r": 16,
    "max_len": 512,
    "batch": 1,
    "accum": 8,
}


def load_config() -> dict:
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        data.update({k: v for k, v in raw.items() if v is not None})
    data["sft_output"] = str(ROOT / data["sft_output"])
    data["dpo_output"] = str(ROOT / data["dpo_output"])
    data["merged_output"] = str(ROOT / data["merged_output"])
    return data
