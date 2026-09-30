from __future__ import annotations

import math
import re
from collections import Counter
from collections import defaultdict
from statistics import mean
from typing import Any, Dict, Iterable, List


FILLERS = ("嗯", "呃", "这个", "那个", "然后", "就是", "怎么说", "想不起来")
CONNECTORS = ("后来", "然后", "因为", "所以", "但是", "最后", "当时", "以前", "之后")


def _units(text: str) -> List[str]:
    """Return stable Chinese/latin units without requiring an external tokenizer."""
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text or "")


def analyze_transcript(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    units = _units(cleaned)
    sentences = [part for part in re.split(r"[。！？!?；;]+", cleaned) if part.strip()]
    count = len(units)
    frequencies = Counter(units)
    repeated = sum(value - 1 for value in frequencies.values() if value > 1)
    filler_hits = sum(cleaned.count(item) for item in FILLERS)
    connector_hits = sum(cleaned.count(item) for item in CONNECTORS)

    lexical_diversity = len(frequencies) / count if count else 0.0
    repetition_ratio = repeated / count if count else 0.0
    filler_ratio = filler_hits / max(1, count)
    length_score = min(1.0, count / 36.0)
    connector_score = min(1.0, connector_hits / max(1, len(sentences)))
    coherence = min(1.0, 0.45 * length_score + 0.55 * connector_score)
    completeness = min(1.0, (len(sentences) + connector_hits) / 5.0)
    quality = min(1.0, count / 20.0)
    return {
        "char_count": count,
        "sentence_count": len(sentences),
        "lexical_diversity": round(lexical_diversity, 4),
        "repetition_ratio": round(repetition_ratio, 4),
        "filler_ratio": round(filler_ratio, 4),
        "coherence": round(coherence, 4),
        "completeness": round(completeness, 4),
        "quality": round(quality, 4),
    }


def _average(rows: Iterable[Dict[str, Any]], key: str) -> float:
    values = [float(row.get(key) or 0) for row in rows]
    return round(mean(values), 4) if values else 0.0


def build_trend(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare recent language with the person's own earlier samples.

    This is a wellness trend, not a diagnosis. Short or low-quality samples are
    excluded so silence and speech-recognition failures do not create alarms.
    """
    valid = [row for row in reversed(rows) if float(row.get("quality") or 0) >= 0.6]
    daily_mode = any(row.get("day") for row in valid)
    utterance_count = sum(int(row.get("sample_count") or 1) for row in valid)
    keys = ("lexical_diversity", "repetition_ratio", "filler_ratio", "coherence", "completeness")
    recent = valid[-5:]
    baseline = valid[:-5][-20:]
    current = {key: _average(recent, key) for key in keys}
    base = {key: _average(baseline, key) for key in keys}
    deltas = {key: round(current[key] - base[key], 4) for key in keys}

    if len(valid) < 5:
        level, label = "collecting", "正在建立个人基线"
    elif len(baseline) < 5:
        level, label = "stable", "已有初步记录"
    else:
        decline = (
            max(0.0, -deltas["lexical_diversity"]) * 1.5
            + max(0.0, deltas["repetition_ratio"]) * 1.2
            + max(0.0, deltas["filler_ratio"]) * 1.0
            + max(0.0, -deltas["coherence"]) * 1.2
            + max(0.0, -deltas["completeness"]) * 0.8
        )
        if decline >= 0.32:
            level, label = "attention", "近期语言表现有持续变化"
        elif decline >= 0.16:
            level, label = "watch", "建议继续观察"
        else:
            level, label = "stable", "近期表现平稳"

    score = round(
        100
        * (
            0.28 * current["lexical_diversity"]
            + 0.27 * current["coherence"]
            + 0.2 * current["completeness"]
            + 0.15 * (1 - current["repetition_ratio"])
            + 0.1 * (1 - min(1.0, current["filler_ratio"] * 5))
        )
    ) if recent else 0
    return {
        "sample_count": utterance_count,
        "day_count": len(valid) if daily_mode else 0,
        "recent_count": len(recent),
        "baseline_count": len(baseline),
        "data_sufficiency": min(100, round(len(valid) / (21 if daily_mode else 15) * 100)),
        "level": level,
        "label": label,
        "wellness_score": max(0, min(100, score)),
        "current": current,
        "baseline": base,
        "delta": deltas,
        "disclaimer": "仅反映日常语言趋势，不用于诊断；如持续担忧，请咨询专业医务人员。",
    }


def build_series(rows: List[Dict[str, Any]], days: int = 30) -> List[Dict[str, Any]]:
    """Return transcript-free daily wellness points for the family chart."""
    grouped: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        if float(row.get("quality") or 0) < 0.6:
            continue
        day = str(row.get("day") or row.get("created_at") or "")[:10]
        if not day:
            continue
        lexical = float(row.get("lexical_diversity") or 0)
        coherence = float(row.get("coherence") or 0)
        completeness = float(row.get("completeness") or 0)
        repetition = float(row.get("repetition_ratio") or 0)
        filler = min(1.0, float(row.get("filler_ratio") or 0) * 5)
        score = 100 * (
            0.28 * lexical
            + 0.27 * coherence
            + 0.2 * completeness
            + 0.15 * (1 - repetition)
            + 0.1 * (1 - filler)
        )
        grouped[day].append(max(0, min(100, score)))
    return [
        {"day": day, "score": round(mean(values)), "samples": len(values)}
        for day, values in sorted(grouped.items())[-days:]
    ]
