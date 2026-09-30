from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .cognition import build_trend


def evaluate_cases(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate alert behavior without treating the result as clinical validity."""
    tp = fp = tn = fn = 0
    details = []
    for case in cases:
        predicted = build_trend(case.get("samples") or []).get("level") == "attention"
        expected = bool(case.get("expected_attention"))
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1
        details.append({"name": case.get("name") or "case", "expected": expected, "predicted": predicted})
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "cases": len(cases),
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "sensitivity": round(sensitivity, 4),
        "specificity": round(specificity, 4),
        "details": details,
        "warning": "该结果只验证程序行为；只有使用真实、合规标注数据才能评估临床有效性。",
    }


def evaluate_file(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return evaluate_cases(payload.get("cases") or [])

