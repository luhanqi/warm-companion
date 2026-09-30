from __future__ import annotations

import re
from typing import Any, Dict, List


def subtitle_timeline(text: str, duration_ms: int) -> List[Dict[str, Any]]:
    parts = [item.strip() for item in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text or "") if item.strip()]
    if not parts:
        return []
    duration_ms = max(duration_ms, len(parts) * 1200)
    weights = [max(2, len(re.sub(r"\s", "", item))) for item in parts]
    total = sum(weights)
    cursor = 0
    cues = []
    for index, (part, weight) in enumerate(zip(parts, weights)):
        span = round(duration_ms * weight / total)
        end = duration_ms if index == len(parts) - 1 else min(duration_ms, cursor + max(900, span))
        cues.append({"start_ms": cursor, "end_ms": end, "text": part})
        cursor = end
    return cues


def _stamp(milliseconds: int) -> str:
    seconds, ms = divmod(max(0, milliseconds), 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return "%02d:%02d:%02d.%03d" % (hours, minute, sec, ms)


def to_webvtt(cues: List[Dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for index, cue in enumerate(cues, 1):
        lines.extend(
            [
                str(index),
                "%s --> %s" % (_stamp(int(cue["start_ms"])), _stamp(int(cue["end_ms"]))),
                str(cue["text"]),
                "",
            ]
        )
    return "\n".join(lines)

