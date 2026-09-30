# -*- coding: utf-8 -*-
"""加载 LoRA 后本地对话。"""
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

from prompt import build_system
from resolve_model import resolve_model
from settings import load_config


def load_pipe(adapter: Path):
    meta = adapter / "nuanban_meta.json"
    if meta.exists():
        base_id = json.loads(meta.read_text(encoding="utf-8"))["base_model"]
    else:
        base_id = (adapter.parent / "base_model.txt").read_text(encoding="utf-8").strip()
    tok = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=True)
    cpu = not torch.cuda.is_available()
    dtype = torch.float32 if cpu else torch.float16
    base = AutoModelForCausalLM.from_pretrained(
        resolve_model(base_id),
        trust_remote_code=True,
        torch_dtype=dtype,
        device_map={"": "cpu"} if cpu else "auto",
    )
    model = PeftModel.from_pretrained(base, str(adapter))
    model.eval()
    return tok, model


def generate(tok, model, user: str, max_new=120):
    messages = [
        {"role": "system", "content": build_system()},
        {"role": "user", "content": user},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(text, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            eos_token_id=tok.eos_token_id,
            pad_token_id=tok.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1] :]
    return tok.decode(gen, skip_special_tokens=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(Path(load_config()["sft_output"]) / "adapter"))
    parser.add_argument("--text", default="")
    args = parser.parse_args()
    tok, model = load_pipe(Path(args.adapter))
    if args.text:
        print(generate(tok, model, args.text))
        return
    print("本地暖伴已加载。空行退出。")
    while True:
        try:
            user = input("您：").strip()
        except EOFError:
            break
        if not user:
            break
        print("暖伴：", generate(tok, model, user))


if __name__ == "__main__":
    main()
