from __future__ import annotations

import json
import sys
from pathlib import Path

from app.cognition_eval import evaluate_file


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：python backend/eval_cognition.py 标注数据.json")
    result = evaluate_file(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))

