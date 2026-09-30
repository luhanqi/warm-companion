# -*- coding: utf-8 -*-
"""对照 seed_eval.jsonl 做规则检查。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chat import generate, load_pipe
from settings import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(Path(load_config()["sft_output"]) / "adapter"))
    args = parser.parse_args()
    cases = []
    for line in (ROOT / "data" / "prepared" / "eval.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    tok, model = load_pipe(Path(args.adapter))
    hit = 0
    for case in cases:
        reply = generate(tok, model, case["user"])
        ok = True
        for w in case.get("must") or []:
            if w not in reply:
                ok = False
        for w in case.get("must_not") or []:
            if w in reply:
                ok = False
        hit += int(ok)
        print("[%s] %s" % ("OK" if ok else "FAIL", case["id"]))
        print("  Q:", case["user"])
        print("  A:", reply)
    print("pass %s/%s" % (hit, len(cases)))


if __name__ == "__main__":
    main()
