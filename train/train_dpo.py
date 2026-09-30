# -*- coding: utf-8 -*-
"""在 SFT 适配器上再做一轮 DPO，压掉诊断、用药、抢话。需先跑完 train_sft.py。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch
from datasets import load_dataset
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig, DPOTrainer

from resolve_model import resolve_model
from settings import load_config

DATA = ROOT / "data" / "prepared"


def load_base_id(adapter: Path, fallback: str) -> str:
    meta = adapter / "nuanban_meta.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))["base_model"]
    txt = adapter.parent / "base_model.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8").strip()
    return fallback


def to_dpo(example, tokenizer):
    prompt = tokenizer.apply_chat_template(
        example["prompt"], tokenize=False, add_generation_prompt=True
    )
    chosen = example["chosen"][0]["content"] if isinstance(example["chosen"], list) else example["chosen"]
    rejected = (
        example["rejected"][0]["content"] if isinstance(example["rejected"], list) else example["rejected"]
    )
    return {"prompt": prompt, "chosen": chosen, "rejected": rejected}


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(Path(cfg["sft_output"]) / "adapter"))
    parser.add_argument("--out", default=cfg["dpo_output"])
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    adapter = Path(args.adapter)
    if not adapter.exists():
        raise SystemExit("找不到 SFT 适配器，请先 python train_sft.py")

    cpu = not torch.cuda.is_available()
    base_id = load_base_id(adapter, "Qwen/Qwen2.5-1.5B-Instruct")
    if "0.5B" in base_id:
        raise SystemExit("当前流程固定 1.5B。不能对 0.5B 的 LoRA 做 DPO，请先 python train_sft.py")
    tok = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    dtype = torch.float32 if cpu else (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    base = AutoModelForCausalLM.from_pretrained(
        resolve_model(base_id),
        trust_remote_code=True,
        torch_dtype=dtype,
        device_map={"": "cpu"} if cpu else "auto",
    )
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=True)
    model.config.use_cache = False

    ds = load_dataset("json", data_files=str(DATA / "dpo.jsonl"), split="train")
    ds = ds.map(lambda x: to_dpo(x, tok), remove_columns=ds.column_names)
    if args.smoke:
        ds = ds.select(range(min(4, len(ds))))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = DPOConfig(
        output_dir=str(out),
        num_train_epochs=1 if args.smoke else args.epochs,
        max_steps=4 if args.smoke else -1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        learning_rate=args.lr,
        logging_steps=1,
        bf16=bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
        fp16=bool(torch.cuda.is_available() and not torch.cuda.is_bf16_supported()),
        report_to="none",
        remove_unused_columns=False,
        max_length=512,
        gradient_checkpointing=True,
        use_cpu=cpu,
        dataloader_pin_memory=False,
        dataloader_num_workers=0,
        warmup_steps=1,
        optim="adamw_torch",
    )
    kwargs = dict(model=model, args=cfg, train_dataset=ds)
    try:
        trainer = DPOTrainer(processing_class=tok, **kwargs)
    except TypeError:
        trainer = DPOTrainer(tokenizer=tok, **kwargs)
    trainer.train()
    dest = out / "adapter"
    trainer.save_model(str(dest))
    tok.save_pretrained(str(dest))
    (dest / "nuanban_meta.json").write_text(
        json.dumps({"base_model": base_id, "kind": "dpo"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("saved", dest)


if __name__ == "__main__":
    main()
