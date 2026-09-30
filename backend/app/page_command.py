from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .content import SONGS
from .llm import complete_deepseek_json, deepseek_enabled

PAGES: Dict[str, Dict[str, Any]] = {
    "garden": {
        "title": "心情花园",
        "actions": ["set_mood", "set_consent", "read_letter", "chat"],
        "hint": "set_mood(mood=sunny|calm|low), set_consent(share=true|false), read_letter, chat",
    },
    "games": {
        "title": "健脑小游戏",
        "actions": ["start_flip", "start_schulte", "go_menu", "chat"],
        "hint": "start_flip, start_schulte, go_menu, chat",
    },
    "profile": {
        "title": "我的资料",
        "actions": ["set_courtesy", "add_person", "set_hometown", "chat"],
        "hint": "set_courtesy(courtesy), add_person(relation,name), set_hometown(hometown), chat",
    },
    "memory": {
        "title": "暖伴记得这些",
        "actions": ["ask_people", "ask_facts", "chat"],
        "hint": "ask_people, ask_facts, chat",
    },
    "nostalgia": {
        "title": "怀旧时光",
        "actions": ["play_song", "set_tab", "remember", "chat"],
        "hint": "play_song(title或song_id), set_tab(tab=songs|era|photos), remember, chat",
    },
    "memoir": {
        "title": "回忆录",
        "actions": ["prev_chapter", "next_chapter", "read_chapter", "remember", "chat"],
        "hint": "prev_chapter, next_chapter, read_chapter, remember, chat",
    },
    "paint": {
        "title": "作画",
        "actions": ["paint", "chat"],
        "hint": "paint(prompt, style=ink|water|oil|story), chat",
    },
    "gift": {
        "title": "寄画",
        "actions": ["paint", "chat"],
        "hint": "paint(prompt, style=ink|water|oil|story), chat",
    },
    "family": {
        "title": "家人周报",
        "actions": ["add_reminder", "copy_letter", "read_digest", "chat"],
        "hint": "add_reminder(title), copy_letter, read_digest, chat",
    },
    "care": {
        "title": "照料",
        "actions": ["set_courtesy", "save_note", "clear_note", "chat"],
        "hint": "set_courtesy(courtesy), save_note, clear_note, chat",
    },
    "observe": {
        "title": "观察台",
        "actions": ["run_eval", "refresh", "chat"],
        "hint": "run_eval, refresh, chat",
    },
    "life": {
        "title": "生活",
        "actions": ["add_reminder", "chat"],
        "hint": "add_reminder(title), chat",
    },
}


def _song_hit(text: str) -> Optional[Dict[str, str]]:
    for song in SONGS:
        title = str(song.get("title") or "")
        if title and title in text:
            return {"song_id": str(song["id"]), "title": title}
    return None


def _keyword(page: str, text: str) -> Optional[Dict[str, Any]]:
    if page == "garden":
        mood_cmd = bool(re.search(r"记|点成|点个|改成|设成|写成", text))
        if mood_cmd and re.search(r"不开心|不太开心|阴|闷|难过|低落", text):
            return {"action": "set_mood", "args": {"mood": "low"}}
        if mood_cmd and re.search(r"晴|开心|高兴|挺好", text):
            return {"action": "set_mood", "args": {"mood": "sunny"}}
        if mood_cmd and re.search(r"平|还行|一般|还好", text):
            return {"action": "set_mood", "args": {"mood": "calm"}}
        if re.search(r"允许|给家人看|打开周报", text):
            return {"action": "set_consent", "args": {"share": True}}
        if re.search(r"不给|关上周报|先不给", text):
            return {"action": "set_consent", "args": {"share": False}}
        if re.search(r"短信|念给", text):
            return {"action": "read_letter", "args": {}}
    elif page == "games":
        if re.search(r"翻牌|配对|老物件", text):
            return {"action": "start_flip", "args": {}}
        if re.search(r"数字|舒尔特|找数", text):
            return {"action": "start_schulte", "args": {}}
        if re.search(r"返回|菜单|重来选", text):
            return {"action": "go_menu", "args": {}}
    elif page == "profile":
        courtesy = re.search(r"叫我(.{1,8})", text)
        if courtesy:
            return {"action": "set_courtesy", "args": {"courtesy": re.sub(r"[。！？\s]", "", courtesy.group(1))}}
        person = re.search(r"(儿子|女儿|孙子|孙女|老伴)叫(.{1,8})", text)
        if person:
            return {
                "action": "add_person",
                "args": {"relation": person.group(1), "name": re.sub(r"[。！？\s]", "", person.group(2))},
            }
        home = re.search(r"(?:老家在|籍贯|我是)(.{2,12}?)(?:人|$)", text)
        if home:
            return {"action": "set_hometown", "args": {"hometown": re.sub(r"[。！？\s]", "", home.group(1))}}
    elif page == "memory":
        if re.search(r"家人|儿子|女儿|谁", text):
            return {"action": "ask_people", "args": {}}
        if re.search(r"爱好|喜欢|记得", text):
            return {"action": "ask_facts", "args": {}}
    elif page == "nostalgia":
        play_cmd = bool(re.search(r"点唱|唱歌|放歌|听歌|放一首|再唱", text))
        hit = _song_hit(text)
        if play_cmd or hit:
            chosen = hit or {"song_id": str(SONGS[0]["id"]), "title": str(SONGS[0]["title"])}
            leftover = text.replace(chosen.get("title") or "", "")
            leftover = re.sub(r"[《》。！？\s]|点唱|唱歌|放歌|听歌|放一首|再唱", "", leftover)
            if play_cmd or len(leftover) < 3:
                return {"action": "play_song", "args": chosen}
        if re.search(r"年代|时光机|经历", text):
            return {"action": "set_tab", "args": {"tab": "era"}}
        if re.search(r"照片|老照片", text):
            return {"action": "set_tab", "args": {"tab": "photos"}}
        if len(text) >= 4:
            return {"action": "remember", "args": {"text": text}}
    elif page == "memoir":
        if re.search(r"上一章|上一页|前面一章", text):
            return {"action": "prev_chapter", "args": {}}
        if re.search(r"下一章|下一页|后面一章", text):
            return {"action": "next_chapter", "args": {}}
        if re.search(r"念给我|读给我|听这一章|念这一章", text):
            return {"action": "read_chapter", "args": {}}
        if len(text) >= 4:
            return {"action": "remember", "args": {"text": text}}
    elif page in ("paint", "gift"):
        style = ""
        if re.search(r"国画|水墨", text):
            style = "ink"
        elif re.search(r"水彩", text):
            style = "water"
        elif re.search(r"油画", text):
            style = "oil"
        elif re.search(r"故事", text):
            style = "story"
        scene = re.sub(r"用?(国画|水墨|水彩|油画|故事画?)", "", text)
        scene = re.sub(r"[，,。]", " ", scene).strip()
        if scene:
            return {"action": "paint", "args": {"prompt": scene, "style": style}}
        if style:
            return {"action": "paint", "args": {"prompt": "", "style": style}}
    elif page == "family":
        if re.search(r"复制|短信稿", text):
            return {"action": "copy_letter", "args": {}}
        remind = re.search(r"(?:记下提醒|提醒她|提醒)(.+)", text)
        if remind:
            return {"action": "add_reminder", "args": {"title": re.sub(r"[。！？\s]", "", remind.group(1))}}
        if re.search(r"周报|摘要|念给", text):
            return {"action": "read_digest", "args": {}}
    elif page == "care":
        courtesy = re.search(r"叫她(.{1,8})", text)
        if courtesy:
            return {"action": "set_courtesy", "args": {"courtesy": re.sub(r"[。！？\s]", "", courtesy.group(1))}}
        if re.search(r"撤掉|删掉捎|不要捎", text):
            return {"action": "clear_note", "args": {}}
        if len(text) >= 2:
            return {"action": "save_note", "args": {"text": text}}
    elif page == "observe":
        if re.search(r"评测|跑一遍|测试", text):
            return {"action": "run_eval", "args": {}}
        if re.search(r"刷新|更新观察台", text):
            return {"action": "refresh", "args": {}}
    elif page == "life":
        remind = re.search(r"(?:记下提醒|提醒)(.+)", text)
        if remind:
            return {"action": "add_reminder", "args": {"title": re.sub(r"[。！？\s]", "", remind.group(1))}}
    return None


GREEDY = {
    ("nostalgia", "remember"),
    ("memoir", "remember"),
    ("care", "save_note"),
    ("paint", "paint"),
    ("gift", "paint"),
}


def _pack(kind: str, action: str, args: Optional[Dict[str, Any]] = None, reply: str = "", source: str = "") -> Dict[str, Any]:
    return {
        "kind": kind,
        "action": action or "chat",
        "args": args or {},
        "reply": reply or "",
        "source": source,
    }


def _llm_route(page: str, text: str) -> Optional[Dict[str, Any]]:
    if not deepseek_enabled() or page not in PAGES:
        return None
    meta = PAGES[page]
    prompt = (
        "你是暖伴。当前页面：「%s」。用户说：「%s」。\n"
        "先判断这句话是命令还是普通对话。只选一个 kind：command 或 chat。\n"
        "- command：这句话的目的就是让这一页立刻办事。例如「记成晴天」「开始翻牌」「用水墨画荷花」「叫我王阿姨」「放茉莉花」「写进回忆录」「记下提醒买菜」。\n"
        "- chat：问好、闲聊、诉苦、问你是谁、讲心情但不要求记下、提到画/歌/家人但没有让你去办。例如「你好啊」「今天过得怎么样」「有点闷，陪我说说话」。\n"
        "拿不准时选 chat，不要把闲聊当成命令。\n"
        "本页可用动作：%s\n"
        "只输出 JSON：{\"kind\":\"command\",\"action\":\"set_mood\",\"args\":{\"mood\":\"sunny\"},\"reply\":\"记下了，今天晴着。\"}\n"
        "command 时 action 必须是上面的动作之一（不能是 chat），reply 用暖伴口吻、不超过 40 字，告诉老人已经办了。\n"
        "chat 时 action 必须是 chat，args 为空对象，reply 必须是空字符串。\n"
        "不要诊断、不要用药指导、不要提自己是模型。"
        % (meta["title"], text, meta["hint"])
    )
    data = complete_deepseek_json(prompt)
    if not isinstance(data, dict):
        return None
    kind = str(data.get("kind") or "").strip().lower()
    action = str(data.get("action") or "chat").strip()
    allowed = set(meta["actions"])
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    reply = str(data.get("reply") or "").strip()
    if kind not in ("command", "chat"):
        kind = "command" if action in allowed and action != "chat" else "chat"
    if kind == "command":
        if action not in allowed or action == "chat":
            return _pack("chat", "chat", {}, "", "deepseek")
        print("DeepSeek 路由: command/%s" % action)
        return _pack("command", action, args, reply, "deepseek")
    print("DeepSeek 路由: chat")
    return _pack("chat", "chat", {}, "", "deepseek")


def resolve(page: str, text: str) -> Dict[str, Any]:
    page = (page or "").strip()
    text = (text or "").strip()
    if page not in PAGES or not text:
        return _pack("chat", "chat", {}, "", "none")
    llm = _llm_route(page, text)
    if llm:
        return llm
    hit = _keyword(page, text)
    if hit and (page, hit.get("action")) not in GREEDY:
        return _pack("command", str(hit["action"]), hit.get("args") or {}, "", "keyword")
    return _pack("chat", "chat", {}, "", "keyword-chat" if hit else "none")
