# -*- coding: utf-8 -*-
"""Qwen2.5-1.5B-Instruct LoRA 监督微调。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

from resolve_model import resolve_model
from settings import load_config

DATA = ROOT / "data" / "prepared"
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def load_tok_model(model_id: str, cpu: bool):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"
    dtype = torch.float32 if cpu else (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    kwargs = dict(trust_remote_code=True, dtype=dtype)
    if cpu:
        kwargs["device_map"] = {"": "cpu"}
    else:
        kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.config.use_cache = False
    return tok, model


def tokenize_row(example, tokenizer, max_len: int):
    messages = example["messages"]
    prompt_msgs = messages[:-1]
    prompt = tokenizer.apply_chat_template(
        prompt_msgs, tokenize=False, add_generation_prompt=True
    )
    full = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]
    if len(full_ids) > max_len:
        full_ids = full_ids[:max_len]
    labels = [-100] * min(len(prompt_ids), len(full_ids))
    if len(full_ids) > len(prompt_ids):
        labels = labels + full_ids[len(prompt_ids) :]
    else:
        labels = [-100] * len(full_ids)
    return {
        "input_ids": full_ids,
        "attention_mask": [1] * len(full_ids),
        "labels": labels,
    }


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=cfg["base_model"], help="默认 Qwen2.5-1.5B-Instruct")
    parser.add_argument("--out", default=cfg["sft_output"])
    parser.add_argument("--epochs", type=float, default=float(cfg["epochs"]))
    parser.add_argument("--lr", type=float, default=float(cfg["learning_rate"]))
    parser.add_argument("--max-len", type=int, default=int(cfg["max_len"]))
    parser.add_argument("--batch", type=int, default=int(cfg["batch"]))
    parser.add_argument("--accum", type=int, default=int(cfg["accum"]))
    parser.add_argument("--lora-r", type=int, default=int(cfg["lora_r"]))
    parser.add_argument("--continue-from", default="", help="接着同一 1.5B 的 LoRA 再训，不能接 0.5B")
    parser.add_argument("--smoke", action="store_true", help="只跑几步，用来确认环境")
    args = parser.parse_args()

    train_file = DATA / "sft_train.jsonl"
    val_file = DATA / "sft_val.jsonl"
    if not train_file.exists():
        raise SystemExit("请先运行：python prepare_data.py")

    cpu = not torch.cuda.is_available()
    model_id = args.model or BASE_MODEL
    if "0.5B" in model_id:
        raise SystemExit("当前流程固定训练 1.5B。请把 config.yaml 里的 base_model 改为 Qwen/Qwen2.5-1.5B-Instruct")
    if cpu:
        print("警告：没有 NVIDIA GPU。1.5B 在 CPU 上可以跑，但会非常慢。建议先安装 CUDA 版 PyTorch。")
    print("base model:", model_id, "| cuda:", (not cpu))

    tok, model = load_tok_model(resolve_model(model_id), cpu)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    Path(args.out).joinpath("hf_id.txt").write_text(model_id, encoding="utf-8")
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    if args.continue_from:
        from peft import PeftModel

        meta_path = Path(args.continue_from) / "nuanban_meta.json"
        if meta_path.exists():
            prev = json.loads(meta_path.read_text(encoding="utf-8")).get("base_model") or ""
            if "0.5B" in prev:
                raise SystemExit("不能把 0.5B 的 LoRA 接到 1.5B 上，请从头训练：python train_sft.py")
        print("continue from", args.continue_from)
        model = PeftModel.from_pretrained(model, args.continue_from, is_trainable=True)
    else:
        lora = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_r,
            lora_alpha=args.lora_r * 2,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        )
        model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    ds_train = load_dataset("json", data_files=str(train_file), split="train")
    ds_val = load_dataset("json", data_files=str(val_file), split="train")
    if args.smoke:
        ds_train = ds_train.select(range(min(16, len(ds_train))))
        ds_val = ds_val.select(range(min(4, len(ds_val))))

    ds_train = ds_train.map(lambda x: tokenize_row(x, tok, args.max_len), remove_columns=ds_train.column_names)
    ds_val = ds_val.map(lambda x: tokenize_row(x, tok, args.max_len), remove_columns=ds_val.column_names)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "base_model.txt").write_text(model_id, encoding="utf-8")

    resume_ckpt = None
    if not args.smoke and not args.continue_from:
        ckpts = []
        for p in out.glob("checkpoint-*"):
            try:
                ckpts.append((int(p.name.split("-")[1]), p))
            except ValueError:
                continue
        if ckpts:
            resume_ckpt = str(sorted(ckpts)[-1][1])
            print("resume from", resume_ckpt)

    targs = TrainingArguments(
        output_dir=str(out),
        num_train_epochs=1 if args.smoke else args.epochs,
        max_steps=6 if args.smoke else -1,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=2 if args.smoke else args.accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=1 if args.smoke else 10,
        logging_steps=1 if args.smoke else 5,
        eval_strategy="steps" if not args.smoke else "no",
        eval_steps=20,
        save_strategy="steps" if not args.smoke else "no",
        save_steps=10,
        save_total_limit=4,
        bf16=bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
        fp16=bool(torch.cuda.is_available() and not torch.cuda.is_bf16_supported()),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        use_cpu=cpu,
        optim="adamw_torch",
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=ds_train,
        eval_dataset=None if args.smoke else ds_val,
        data_collator=DataCollatorForSeq2Seq(tok, padding=True, pad_to_multiple_of=8),
    )
    trainer.train(resume_from_checkpoint=resume_ckpt)
    trainer.save_model(str(out / "adapter"))
    tok.save_pretrained(str(out / "adapter"))
    meta = {
        "base_model": model_id,
        "smoke": args.smoke,
        "epochs": args.epochs,
        "continue_from": args.continue_from,
    }
    (out / "adapter" / "nuanban_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("saved", out / "adapter")


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
