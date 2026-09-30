# -*- coding: utf-8 -*-
"""把 LoRA 合成完整权重，方便拷到别的机器。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from resolve_model import resolve_model
from settings import load_config

ROOT = Path(__file__).resolve().parent


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(Path(cfg["sft_output"]) / "adapter"))
    parser.add_argument("--out", default=cfg["merged_output"])
    args = parser.parse_args()
    adapter = Path(args.adapter)
    base_id = json.loads((adapter / "nuanban_meta.json").read_text(encoding="utf-8"))["base_model"]
    tok = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=True)
    cpu = not torch.cuda.is_available()
    base = AutoModelForCausalLM.from_pretrained(
        resolve_model(base_id),
        trust_remote_code=True,
        torch_dtype=torch.float32 if cpu else torch.float16,
        device_map={"": "cpu"} if cpu else "auto",
    )
    model = PeftModel.from_pretrained(base, str(adapter))
    merged = model.merge_and_unload()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out), safe_serialization=True)
    tok.save_pretrained(str(out))
    print("merged ->", out)


if __name__ == "__main__":
    main()
