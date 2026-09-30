from __future__ import annotations

from typing import Any, Dict, List, Optional


NEWS = [
    "生活提示（非实时）：天气合适时可以在家人陪同下短距离散步。",
    "生活提示（非实时）：高温天少在正午晒太阳，外出前请查看实时天气。",
    "生活提示（非实时）：可向所在社区确认近期是否有戏曲或文娱活动。",
]

LESSONS = {
    "video": {
        "title": "怎么接视频",
        "steps": [
            "电话响了，先看屏幕上是不是熟人的名字。",
            "绿的是接，红的是挂。点绿色那一个。",
            "接上以后，把声音开大，脸对着上面的小圆点。",
            "说完了，再点红色挂掉。",
        ],
        "encourage": "您跟着做就行，不着急。",
    },
    "weather": {
        "title": "怎么问天气",
        "steps": [
            "不用自己翻软件。",
            "按住说话，跟我说「明天天气怎么样」。",
            "我念给您听，要不要带伞，我会说到。",
        ],
        "encourage": "问一次就会了。",
    },
    "register": {
        "title": "挂号怎么看（教学，不是真挂号）",
        "steps": [
            "这是教您认屏幕，暖伴不会替您挂上号，也不会付钱。",
            "医院软件里，先找「预约挂号」四个字。",
            "再选科室和日期。选完会弹出确认，那一步请家人帮您点。",
            "如果看不清，把手机给旁边的人，您只说要看哪一科。",
        ],
        "encourage": "学会看，不等于号已经约上。需要挂号时，让家人帮您点确认。",
    },
}


def weather_line(hometown: str = "") -> str:
    place = hometown or "南通"
    return "演示天气（非实时）：%s的真实天气尚未接入，外出前请查看当地气象服务。" % place


def news_lines() -> List[str]:
    return list(NEWS)


def lesson(topic: str) -> Optional[Dict[str, Any]]:
    return LESSONS.get(topic)


def speak_lesson(topic: str, courtesy: str) -> str:
    item = LESSONS.get(topic)
    if not item:
        return "%s，这一课我还没备好。您可以说接视频，或问天气。" % courtesy
    parts = ["%s，我教您「%s」。" % (courtesy, item["title"])]
    if topic == "register":
        parts.append("先说清楚：这不是真的挂号。")
    for index, step in enumerate(item["steps"], 1):
        parts.append("%s，%s" % (index, step))
    parts.append(item["encourage"])
    return "".join(parts)


class Life:
    name = "life"

    def weather(self, board: Any) -> Dict[str, str]:
        hometown = (board.get_profile() or {}).get("hometown") or "南通"
        return {"speak": weather_line(hometown), "tool": "weather"}

    def news(self) -> Dict[str, str]:
        return {"speak": "我给您念三句。%s" % "。".join(news_lines()), "tool": "news"}

    def reminders(self, board: Any) -> Dict[str, str]:
        items = board.list_reminders()
        if not items:
            return {"speak": "还没有提醒。您或家人可以先写在生活页上。", "tool": "reminders"}
        bits = ["您记下的提醒有："]
        for item in items:
            bits.append("%s%s。" % (item["title"], "，" + item["note"] if item.get("note") else ""))
        bits.append("这些是自己写的，不是医嘱。")
        return {"speak": "".join(bits), "tool": "reminders"}

    def lesson(self, topic: str, courtesy: str) -> Dict[str, str]:
        return {"speak": speak_lesson(topic, courtesy), "tool": "lesson:%s" % topic}

    def handle(self, board: Any, goal: str, courtesy: str, tool_calls: List[str]) -> Dict[str, str]:
        if goal == "life_weather":
            result = self.weather(board)
            return {
                "speak": "%s，%s" % (courtesy, result.get("speak") or ""),
                "tool": result.get("tool") or "weather",
            }
        if goal == "life_news":
            result = self.news()
            return {
                "speak": "%s，%s" % (courtesy, result.get("speak") or ""),
                "tool": result.get("tool") or "news",
            }
        if goal == "life_remind":
            result = self.reminders(board)
            return {
                "speak": "%s，%s" % (courtesy, result.get("speak") or ""),
                "tool": result.get("tool") or "reminders",
            }
        topic = "video"
        for call in tool_calls or []:
            if call.startswith("lesson:"):
                topic = call.split(":", 1)[-1]
                break
        result = self.lesson(topic, courtesy)
        return {
            "speak": result.get("speak") or "",
            "tool": result.get("tool") or "lesson:%s" % topic,
        }
