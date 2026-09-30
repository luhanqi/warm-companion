# -*- coding: utf-8 -*-
"""把种子数据写成训练文件；可选再混入少量公开中文闲聊（需外网）。"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_seed import main as build_seed
from prompt import BASE_SYSTEM

DATA = ROOT / "data"
PREPARED = DATA / "prepared"


def read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
        encoding="utf-8",
    )


def split_sft(rows, seed=42, val_ratio=0.1):
    random.Random(seed).shuffle(rows)
    n_val = max(8, int(len(rows) * val_ratio))
    return rows[n_val:], rows[:n_val]


def try_public(limit: int):
    """抽样公开中文指令数据，改写成短口语。失败则跳过。"""
    extra = []
    try:
        from datasets import load_dataset
    except ImportError:
        print("datasets 未安装，跳过公开集")
        return extra

    try:
        ds = load_dataset("shibing624/alpaca-zh", split="train", streaming=True)
    except Exception as exc:
        print("公开集下载失败（可只用种子）：", exc)
        return extra

    bad = ("代码", "python", "函数", "翻译成", "英文", "JSON", "论文")
    count = 0
    for item in ds:
        if count >= limit:
            break
        instr = (item.get("instruction") or item.get("input") or "").strip()
        out = (item.get("output") or "").strip()
        if not instr or not out:
            continue
        if any(w in instr.lower() or w in out.lower() for w in bad):
            continue
        if len(out) > 80 or len(instr) > 40:
            continue
        extra.append(
            {
                "messages": [
                    {"role": "system", "content": BASE_SYSTEM},
                    {"role": "user", "content": instr},
                    {
                        "role": "assistant",
                        "content": "我在听。%s您慢慢说就行。" % (out[:40] + "。"),
                    },
                ]
            }
        )
        count += 1
    print("公开集纳入 %s 条（已截短，仅作风格辅料）" % len(extra))
    return extra


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=int, default=0, help="额外公开闲聊条数，0 表示只用种子")
    args = parser.parse_args()

    build_seed()
    sft = read_jsonl(DATA / "seed_sft.jsonl")
    keys = (
        "今天中午吃了面",
        "小明最近怎么样",
        "降压药吃几片",
        "我是不是抑郁了",
        "帮我预约",
        "有点低落",
        "我想听茉莉花",
        "提醒我带降压药",
    )
    extra = []
    for row in sft:
        user = row["messages"][-2]["content"]
        if any(k in user for k in keys):
            extra.extend([json.loads(json.dumps(row)) for _ in range(2)])
    sft = sft + extra
    if args.public:
        sft.extend(try_public(args.public))
    train, val = split_sft(sft)
    PREPARED.mkdir(parents=True, exist_ok=True)
    write_jsonl(PREPARED / "sft_train.jsonl", train)
    write_jsonl(PREPARED / "sft_val.jsonl", val)
    write_jsonl(PREPARED / "dpo.jsonl", read_jsonl(DATA / "seed_dpo.jsonl"))
    write_jsonl(PREPARED / "eval.jsonl", read_jsonl(DATA / "seed_eval.jsonl"))
    print("train %s  val %s" % (len(train), len(val)))
    print("prepared ->", PREPARED)


if __name__ == "__main__":
    main()
