from __future__ import annotations

from typing import Any, Dict, List


CASES: List[Dict[str, Any]] = [
    {"id": "chat", "text": "今天中午吃了面", "expect": "companion", "mode": "single"},
    {"id": "song", "text": "给我放茉莉花", "expect": "healing", "mode": "handoff"},
    {"id": "memoir", "text": "讲讲过去", "expect": "healing", "mode": "handoff"},
    {"id": "weather", "text": "今天天气怎么样", "expect": "life", "mode": "single"},
    {"id": "news", "text": "念一段新闻", "expect": "life", "mode": "single"},
    {"id": "class", "text": "教我怎么接视频", "expect": "life", "mode": "single"},
    {
        "id": "register",
        "text": "帮我看看怎么挂号",
        "expect": "life",
        "mode": "single",
        "must_not": ["已经挂上", "预约成功"],
    },
    {
        "id": "parallel",
        "text": "明天要出门看老同事，天气怎么样，提醒我带降压药",
        "expect": "parallel",
        "mode": "parallel",
        "agents": ["life", "guardian", "companion"],
    },
    {
        "id": "memory",
        "text": "我儿子叫小明，帮我记住",
        "expect": "memory",
        "mode": "handoff",
    },
]

FORBIDDEN_VOICE = ("智能体", "大模型", "调度", "人工智能", "GPT", "我是AI")


def run_eval(orchestrator: Any) -> Dict[str, Any]:
    rows = []
    hit = 0
    for case in CASES:
        route = orchestrator.classify(case["text"])
        got = route.goal if route.goal == "parallel" else route.to_agent
        if case["expect"] == "parallel":
            ok = route.goal == "parallel"
        else:
            ok = route.to_agent == case["expect"] or route.goal == case["expect"]
        if ok and case.get("must_not"):
            spoken = orchestrator.life.lesson("register", "王阿姨").get("speak") or ""
            if any(bad in spoken for bad in case["must_not"]):
                ok = False
        if ok:
            hit += 1
        rows.append(
            {
                "id": case["id"],
                "text": case["text"],
                "expect": case["expect"],
                "got": "parallel" if route.goal == "parallel" else route.to_agent,
                "ok": ok,
                "reason": route.reason,
                "mode": case.get("mode"),
            }
        )
    memory = orchestrator.memory.retrieve(orchestrator.board)
    refs = " ".join(memory.get("refs") or [])
    memory_ok = "小明" in refs or "儿子" in refs
    persona_ok = _persona_one_voice(orchestrator, memory)
    return {
        "total": len(CASES),
        "routing_hit": hit,
        "routing_acc": round(100.0 * hit / len(CASES), 1) if CASES else 0,
        "memory_consistent": memory_ok,
        "persona_one_voice": persona_ok,
        "cases": rows,
    }


def _persona_one_voice(orchestrator: Any, memory: Dict[str, Any]) -> bool:
    samples = [
        orchestrator.companion.local_reply("今天中午吃了面", memory),
        orchestrator.companion.compose(
            "王阿姨", ["南通明天多云。", "药单上写着降压药。这不是用药指导。"]
        ),
        (orchestrator.life.lesson("register", "王阿姨").get("speak") or ""),
        (orchestrator.healing.play("molihua", memory).get("speak") or ""),
        orchestrator.guardian.family_letter(orchestrator.board),
    ]
    return all(not any(bad in (text or "") for bad in FORBIDDEN_VOICE) for text in samples)
