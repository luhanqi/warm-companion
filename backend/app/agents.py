from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List

from .blackboard import Blackboard, daypart_cn, weekday_cn
from .content import EVENTS, SONGS, find_song, match_song
from .extract import extract_memory
from .embeddings import (
    cosine,
    embed_texts,
    embedding_enabled,
    embedding_is_local,
    embedding_model,
    hashed_vector,
    rerank_documents,
    reranker_is_local,
)
from .life import Life
from .llm import (
    cloud_processing_allowed,
    complete_json,
    deepseek_enabled,
    llm_enabled,
    stream_chat,
    stream_deepseek_messages,
)


@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    goal: str
    user_text: str
    memory_refs: List[str] = field(default_factory=list)
    tool_calls: List[str] = field(default_factory=list)
    blackboard_writes: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""


class MemorySteward:
    name = "memory"

    def retrieve(self, board: Blackboard, query: str = "") -> Dict[str, Any]:
        profile = board.get_profile()
        people = board.list_people()
        facts = board.list_facts(24)
        speech_style = board.speech_style_profile()
        documents = board.list_memory_documents()
        query_units = set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", query.lower()))
        retrieval_mode = "database-hashed-vector"
        vectors = None
        external_allowed = bool(board.consent_scopes().get("external_memory_ai"))
        if query and documents and (embedding_is_local() or external_allowed) and embedding_enabled():
            try:
                model_key = "remote:" + embedding_model()
                query_vectors = embed_texts([query])
                if query_vectors:
                    document_vectors = self._document_vectors(board, documents, model_key, None)
                    missing = [item for item, vector in zip(documents, document_vectors) if vector is None]
                    if missing:
                        created = embed_texts([item.get("text") or "" for item in missing]) or []
                        for item, vector in zip(missing, created):
                            self._save_document_vector(board, item, model_key, vector)
                        document_vectors = self._document_vectors(board, documents, model_key, None)
                    if all(document_vectors):
                        vectors = query_vectors + document_vectors
                        retrieval_mode = "database-semantic-embedding"
            except Exception as exc:
                print("语义向量服务失败，改用数据库私密检索：", exc)
        if not vectors:
            model_key = "local-hashed-v1"
            document_vectors = self._document_vectors(board, documents, model_key, hashed_vector)
            vectors = [hashed_vector(query)] + document_vectors
        query_vector = vectors[0]
        document_vectors = {id(item): vector for item, vector in zip(documents, vectors[1:])}

        def score(item: Dict[str, Any]) -> float:
            text = (item.get("text") or "").lower()
            units = set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text))
            overlap = len(query_units & units)
            phrase_bonus = sum(2 for token in query_units if len(token) > 1 and token in text)
            semantic = cosine(query_vector, document_vectors.get(id(item), []))
            time_bonus = 0.5 if re.search(r"(?:19|20)\d{2}", query) and re.search(r"(?:19|20)\d{2}", text) else 0
            return semantic * 8 + overlap * 0.35 + phrase_bonus + time_bonus

        ranked = sorted(documents, key=score, reverse=True)
        candidates = [item for item in ranked if score(item) > 0][:12]
        reranked = None
        if query and candidates and (reranker_is_local() or external_allowed):
            try:
                reranked = rerank_documents(query, candidates)
            except Exception as exc:
                print("记忆重排服务失败，继续使用本地排序：", exc)
        retrieved = (reranked or candidates)[:5]
        if reranked:
            retrieval_mode += "+reranker"
        if not retrieved:
            retrieved = ranked[:3]
        refs = []
        if profile.get("courtesy"):
            refs.append("称呼=%s" % profile["courtesy"])
        for person in people[:4]:
            refs.append("%s%s" % (person["relation"], person["name"]))
        for item in retrieved:
            refs.append("%s：%s" % (item.get("source") or "个人记忆", item.get("text") or ""))
        return {
            "profile": profile,
            "people": people,
            "facts": facts,
            "speech_style": speech_style,
            "retrieved": retrieved,
            "retrieval": retrieval_mode,
            "refs": refs,
        }

    @staticmethod
    def _text_hash(item: Dict[str, Any]) -> str:
        return hashlib.sha256((item.get("text") or "").encode("utf-8")).hexdigest()

    def _save_document_vector(
        self, board: Blackboard, item: Dict[str, Any], model: str, vector: List[float]
    ) -> None:
        if not vector:
            return
        board.set_memory_embedding(
            str(item.get("kind") or "memory"),
            str(item.get("id") or ""),
            self._text_hash(item),
            model,
            vector,
        )

    def _document_vectors(
        self,
        board: Blackboard,
        documents: List[Dict[str, Any]],
        model: str,
        factory: Any,
    ) -> List[Any]:
        vectors: List[Any] = []
        for item in documents:
            vector = board.get_memory_embedding(
                str(item.get("kind") or "memory"),
                str(item.get("id") or ""),
                self._text_hash(item),
                model,
            )
            if vector is None and factory is not None:
                vector = factory(item.get("text") or "")
                self._save_document_vector(board, item, model, vector)
            vectors.append(vector)
        return vectors

    def write_from_text(self, board: Blackboard, text: str) -> List[Dict[str, Any]]:
        people, facts = extract_memory(text)
        extra = self._llm_extract(text)
        people.extend(extra.get("people") or [])
        facts.extend(extra.get("facts") or [])
        writes: List[Dict[str, Any]] = []
        for person in people:
            name = (person.get("name") or "").strip()
            relation = (person.get("relation") or "").strip()
            if not name or not relation:
                continue
            saved = board.add_person(relation, name, person.get("note") or "")
            if saved:
                writes.append(
                    {"type": "people", "relation": relation, "name": name}
                )
        for fact in facts:
            value = (fact.get("value") or "").strip()
            key = (fact.get("key") or "其他").strip()
            if not value:
                continue
            saved = board.add_fact(key, value, fact.get("source") or "steward")
            if saved:
                writes.append({"type": "facts", "key": key, "value": value})
        return writes

    def handle(
        self, board: Blackboard, text: str, memory: Dict[str, Any]
    ) -> Dict[str, Any]:
        writes = self.write_from_text(board, text)
        courtesy = ((memory.get("profile") or {}).get("courtesy")) or "您"
        bits: List[str] = []
        for item in writes:
            if item.get("type") == "people":
                bits.append("%s%s" % (item.get("relation") or "", item.get("name") or ""))
            elif item.get("type") == "facts":
                bits.append(item.get("value") or "")
        what = "、".join(bit for bit in bits if bit)
        if what:
            speak = "%s，我帮您记在心里了。我记得%s。" % (courtesy, what)
        else:
            speak = "%s，您再说具体一点，比如儿子叫什么、喜欢听什么，我帮您记着。" % courtesy
        return {
            "speak": speak,
            "writes": writes,
            "tool": "write_memory",
            "action": "write_memory",
        }

    def _llm_extract(self, text: str) -> Dict[str, Any]:
        data = complete_json(
            "从老人这句话里提取新的家人或事实。没有就返回空数组。\n"
            '格式：{"people":[{"relation":"儿子","name":"小明","note":""}],'
            '"facts":[{"key":"爱好","value":"喜欢听茉莉花"}]}\n'
            "原话：%s" % text
        )
        return data or {}


class Companion:
    name = "companion"

    def greeting(self, memory: Dict[str, Any]) -> str:
        profile = memory.get("profile") or {}
        people = memory.get("people") or []
        facts = memory.get("facts") or []
        courtesy = profile.get("courtesy") or profile.get("display_name") or "您"
        parts = ["%s，%s好。" % (courtesy, daypart_cn())]
        if people:
            person = people[0]
            parts.append(
                "%s%s最近还好吗？" % (person.get("relation", ""), person.get("name", ""))
            )
        if facts:
            parts.append("我还记得您%s。" % facts[0]["value"].lstrip("曾"))
        parts.append("今天想跟我聊点什么？")
        return "".join(parts)

    def compose(self, courtesy: str, lines: List[str]) -> str:
        kept = []
        for line in lines:
            text = (line or "").strip()
            if not text:
                continue
            if not text.endswith("。"):
                text += "。"
            kept.append(text)
        return "%s，%s出门慢一点。" % (courtesy, "".join(kept))

    def local_reply(
        self, user_text: str, memory: Dict[str, Any], hint: str = ""
    ) -> str:
        profile = memory.get("profile") or {}
        people = memory.get("people") or []
        facts = memory.get("facts") or []
        courtesy = profile.get("courtesy") or "您"
        text = user_text.strip()

        if any(word in text for word in ("儿子", "女儿", "孙子", "孙女", "老伴")):
            known = "、".join("%s%s" % (p["relation"], p["name"]) for p in people[:3])
            if known:
                reply = "%s，我记下了。我记得您家里有%s。他们最近有没有来电话呀？" % (
                    courtesy,
                    known,
                )
            else:
                reply = "%s，您家里人都好着吗？想跟我说说他们的名字，我帮您记着。" % courtesy
        elif any(word in text for word in ("喜欢", "想听", "爱听", "爱好")):
            hobby = next((f["value"] for f in facts if f["key"] == "爱好"), "")
            if hobby:
                reply = "听您这么说我就高兴。我记得您%s。今天还想再听，还是想聊点别的？" % hobby
            else:
                reply = "您喜欢的东西我都想听。是歌，还是别的呀？"
        elif any(word in text for word in ("厂", "工作", "年轻", "以前")):
            work = next((f["value"] for f in facts if f["key"] == "工作"), "")
            if work:
                reply = "您%s，那时候一定很不容易。厂里有没有特别记得的人？" % work
            else:
                reply = "您年轻时候做什么工作呀？我想好好听。"
        elif any(word in text for word in ("孤单", "闷", "没人", "想孩子")):
            if people:
                person = people[0]
                reply = "有我在这儿听着。要不要跟我说说%s%s最近的事？" % (
                    person["relation"],
                    person["name"],
                )
            else:
                reply = "有我在这儿听着。您想说什么都行，我不急。"
        elif len(text) <= 4:
            reply = "%s，我在听。您再说具体一点，今天过得怎么样？" % courtesy
        else:
            mention = ""
            if people:
                mention = "对了，%s%s还好吗？" % (people[0]["relation"], people[0]["name"])
            elif facts:
                mention = "您刚才说到这些，我都记着。"
            reply = "%s，我听明白了。%s" % (courtesy, mention or "您接着说，我听着。")
        return self._apply_hint(reply, hint)

    def _apply_hint(self, reply: str, hint: str) -> str:
        if not hint:
            return reply
        if any(word in hint for word in ("老歌", "心情偏低")) and "老歌" not in reply:
            if not reply.endswith("。"):
                reply += "。"
            reply += "要是心里闷，我给您放一首老歌。"
        return reply

    def stream_reply(
        self,
        user_text: str,
        memory: Dict[str, Any],
        history: List[Dict[str, str]],
        hint: str = "",
    ) -> Iterator[Dict[str, str]]:
        if llm_enabled() or (deepseek_enabled() and cloud_processing_allowed()):
            context = self._memory_prompt(memory)
            if hint:
                context += "\n" + hint
            messages = [{"role": "system", "content": context}]
            messages.extend(history[-8:])
            messages.append({"role": "user", "content": user_text})
            if deepseek_enabled() and cloud_processing_allowed():
                emitted = False
                try:
                    for token in stream_deepseek_messages(messages):
                        emitted = True
                        yield {"text": token, "model": "deepseek"}
                    return
                except Exception as exc:
                    if emitted:
                        raise
                    print("DeepSeek 主对话不可用，改用原训练模型：", exc)
            if llm_enabled():
                try:
                    for token in stream_chat(messages):
                        yield {"text": token, "model": "nuanban-local"}
                    return
                except Exception as exc:
                    print("对话模型调用失败，改用规则回复：", exc)
        reply = self.local_reply(user_text, memory, hint=hint)
        for i in range(0, len(reply), 2):
            yield {"text": reply[i : i + 2], "model": "rules"}

    def _memory_prompt(self, memory: Dict[str, Any]) -> str:
        profile = memory.get("profile") or {}
        people = memory.get("people") or []
        facts = memory.get("facts") or []
        retrieved = memory.get("retrieved") or []
        speech_style = memory.get("speech_style") or {}
        lines = [
            "今天是%s。" % weekday_cn(),
            "对方称呼：%s。" % (profile.get("courtesy") or "您"),
        ]
        if profile.get("hometown"):
            lines.append("籍贯：%s。" % profile["hometown"])
        if people:
            lines.append(
                "家人："
                + "，".join("%s%s" % (p["relation"], p["name"]) for p in people)
            )
        if facts:
            lines.append("已知事实：" + "；".join(f["value"] for f in facts[:5]))
        if retrieved:
            lines.append(
                "与当前话题最相关的个人记忆："
                + "；".join("[%s] %s" % (item.get("source") or "记忆", item.get("text") or "") for item in retrieved)
            )
        if speech_style.get("status") == "available":
            style_bits = ["表达%s" % speech_style.get("pace", "舒缓")]
            if speech_style.get("preferred_ending"):
                style_bits.append("常用语气字“%s”" % speech_style["preferred_ending"])
            if speech_style.get("common_filler"):
                style_bits.append("偶尔会说“%s”" % speech_style["common_filler"])
            lines.append("对方说话风格：%s。回复节奏可以自然贴近，但不要冒充对方。" % "，".join(style_bits))
        lines.append("只在相关时自然使用这些记忆；不要补写记忆中没有的年代、人物或经历。")
        return "\n".join(lines)


class Healing:
    name = "healing"

    def play(self, song_id: str, memory: Dict[str, Any]) -> Dict[str, Any]:
        song = find_song(song_id) or SONGS[0]
        courtesy = ((memory.get("profile") or {}).get("courtesy")) or "您"
        speak = (
            "%s，我给您放《%s》。%s这首歌让您想起谁，或者想起哪一年？"
            % (courtesy, song["title"], song["story"])
        )
        return {
            "action": "play_song",
            "song": song,
            "speak": speak,
            "chapter": song.get("chapter") or "youth",
        }

    def era(self, year: int, memory: Dict[str, Any]) -> Dict[str, Any]:
        event = next((item for item in EVENTS if item["year"] == year), EVENTS[0])
        courtesy = ((memory.get("profile") or {}).get("courtesy")) or "您"
        speak = (
            "%s，%s年，%s。%s您那一年在做什么？点下面「我经历过」，我帮您写进回忆录。"
            % (courtesy, event["year"], event["title"], event["desc"])
        )
        return {
            "action": "era",
            "event": event,
            "speak": speak,
            "chapter": event.get("chapter") or "youth",
        }

    def remember(
        self, board: Blackboard, text: str, chapter_key: str, source: str
    ) -> Dict[str, Any]:
        paragraph = text.strip()
        if not paragraph:
            return {"speak": "我没听清。您再说一次，我写下来。"}
        chapter = board.append_chapter(chapter_key, paragraph, audio_note=paragraph)
        title = chapter.get("title") or chapter_key
        speak = "我把这段写进回忆录的「%s」了。您以后打开那一页，还能再听。" % title
        return {
            "action": "remember",
            "chapter": chapter,
            "speak": speak,
            "source": source,
        }

    def photo_story(self, board: Blackboard, photo_id: int, text: str) -> Dict[str, Any]:
        story = text.strip()
        photo = board.update_photo_story(photo_id, story)
        if not photo:
            return {"speak": "这张照片我没找到。您再选一张。"}
        board.append_chapter("family", story, audio_note=story)
        return {
            "action": "photo_story",
            "photo": photo,
            "speak": "照片下面我写好了。这段也进了回忆录的「家庭」。",
        }

    def encourage(self, game: str, score: str, memory: Dict[str, Any]) -> str:
        courtesy = ((memory.get("profile") or {}).get("courtesy")) or "您"
        if game == "flip":
            return "%s，这局配对完成了，用了%s。收音机、粮票这些老物件，您认得比谁都清楚。" % (
                courtesy,
                score,
            )
        return "%s，数字都找齐了，用了%s。不着急，明天再来，我会记得今天的成绩。" % (
            courtesy,
            score,
        )

    def handle(
        self, goal: str, board: Blackboard, text: str, memory: Dict[str, Any]
    ) -> Dict[str, Any]:
        if goal == "play_song":
            song = match_song(text) or find_song(board.get_kv("last_song")) or SONGS[0]
            return self.play(song["id"], memory)
        song = find_song(board.get_kv("last_song"))
        chapter = (song or {}).get("chapter") or "youth"
        return self.remember(board, text, chapter, "oral")


LOW_WORDS = ("低落", "难过", "不开心", "心烦", "闷得慌", "不想说话")
SUNNY_WORDS = ("开心", "高兴", "挺好", "愉快", "舒服")
CALM_WORDS = ("还行", "一般", "平平", "还好")


class Guardian:
    name = "guardian"

    def infer_mood(self, text: str) -> str:
        if any(word in text for word in LOW_WORDS):
            return "low"
        if any(word in text for word in SUNNY_WORDS):
            return "sunny"
        if any(word in text for word in CALM_WORDS):
            return "calm"
        return ""

    def observe(self, board: Blackboard, text: str, route: str) -> Dict[str, Any]:
        mood = self.infer_mood(text)
        writes: List[Dict[str, Any]] = []
        today = board.get_today_mood()
        if mood and (not today or today.get("source") != "garden"):
            saved = board.set_mood(mood, "guardian")
            writes.append({"type": "mood", "key": "today", "value": saved.get("mood") or mood})
        if mood == "low":
            board.set_kv("next_priority", "healing_song")
        reason = "会话后由守护记账，不跟老人抢话"
        if mood == "low":
            reason = "心情偏低，建议下次优先老歌，不做诊断"
        trace = board.add_trace("guardian", reason, writes)
        return {
            "mood": mood or (today or {}).get("mood") or "",
            "suggest_song": mood == "low" or board.get_kv("next_priority") == "healing_song",
            "trace": trace,
            "route": route,
        }

    def companion_hint(self, board: Blackboard) -> str:
        if board.get_kv("next_priority") == "healing_song":
            return "对方最近心情偏低。可以轻轻问要不要听一首熟悉的老歌。不要提智能体、调度或模型。"
        return ""

    def weather_label(self, moods: List[Dict[str, Any]]) -> str:
        if not moods:
            return "还没点过"
        score = 0
        for item in moods:
            if item.get("mood") == "sunny":
                score += 1
            elif item.get("mood") == "low":
                score -= 1
        if score >= 2:
            return "偏晴"
        if score <= -2:
            return "偏阴"
        return "多云转晴"

    def sanitize(self, text: str) -> str:
        cleaned = text.replace("「", "").replace("」", "").replace('"', "").replace("“", "").replace("”", "")
        return cleaned

    def weekly_digest(self, board: Blackboard) -> Dict[str, Any]:
        moods = board.list_moods(board.week_start())
        days = board.talk_days_this_week()
        chapters = board.chapters_updated_this_week()
        song = board.get_kv("last_song")
        song_row = find_song(song) if song else None
        song_title = (song_row or {}).get("title") or ""
        chapter_titles = [item["title"] for item in chapters if item.get("title")]
        profile = board.get_profile()
        courtesy = profile.get("courtesy") or "老人"
        parts = ["本周%s开口 %s 天。" % (courtesy, days)]
        weather = self.weather_label(moods)
        if moods:
            parts.append("心情%s。" % weather)
        if song_title:
            parts.append("听过《%s》。" % song_title)
        if chapter_titles:
            parts.append("回忆录写下了%s。" % "、".join(chapter_titles))
        if days == 0 and not moods:
            parts = ["这一周还没有新的摘要。"]
        paraphrase = self.sanitize("".join(parts))
        return {
            "days_talked": days,
            "mood_weather": weather,
            "moods": [{"day": item["day"], "mood": item["mood"]} for item in moods],
            "song_title": song_title,
            "chapters": chapter_titles,
            "paraphrase": paraphrase,
            "contains_transcript": False,
        }

    def family_letter(self, board: Blackboard) -> str:
        digest = self.weekly_digest(board)
        profile = board.get_profile()
        people = board.list_people()
        child = ""
        for person in people:
            if person.get("relation") in ("儿子", "女儿"):
                child = person.get("name") or ""
                break
        who = child or "家里人"
        courtesy = profile.get("courtesy") or "我"
        body = digest["paraphrase"]
        return "%s，我是暖伴，替%s带一句：%s 您们忙，她知道。" % (who, courtesy, body)

    def unused_line(self, board: Blackboard) -> str:
        days = board.unused_days()
        if days >= 2:
            return "有两天没听见您说话了。想聊一句，或听一首老歌，我都在。"
        return ""

    def check_meds(self, board: Blackboard, text: str) -> str:
        reminders = board.list_reminders()
        hit = None
        for item in reminders:
            title = item.get("title") or ""
            if title and title in text:
                hit = item
                break
        if hit is None:
            for item in reminders:
                if item.get("kind") == "medicine":
                    hit = item
                    break
        if hit:
            note = hit.get("note") or ""
            extra = note + "。" if note else ""
            return "药单上写着%s。%s这不是用药指导，只是您或家人记下的提醒。" % (
                hit.get("title") or "药",
                extra,
            )
        return "药单上还没有这一条。您或家人可以先写在生活页的提醒里。"


class Orchestrator:
    def __init__(self, board: Blackboard) -> None:
        self.board = board
        self.companion = Companion()
        self.memory = MemorySteward()
        self.healing = Healing()
        self.guardian = Guardian()
        self.life = Life()

    def classify(self, text: str) -> AgentMessage:
        song = match_song(text)
        last_song = self.board.get_kv("last_song")
        low_today = (self.board.get_today_mood() or {}).get("mood") == "low"
        wants_song = any(word in text for word in ("放一首", "点歌", "听歌", "唱", "想听"))
        if song or wants_song or (
            low_today and any(word in text for word in LOW_WORDS + ("听一首", "来一首"))
        ):
            target = song or find_song(last_song) or SONGS[0]
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="healing",
                goal="play_song",
                user_text=text,
                reason="意图=点歌，交接疗愈智能体"
                + ("；守护建议优先老歌" if low_today else ""),
                tool_calls=["play_song:%s" % target["id"]],
            )
        if self.board.get_kv("next_priority") == "healing_song" and wants_song:
            target = find_song(last_song) or SONGS[0]
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="healing",
                goal="play_song",
                user_text=text,
                reason="守护建议优先老歌，交接疗愈",
                tool_calls=["play_song:%s" % target["id"]],
            )
        if last_song and any(
            word in text for word in ("想起", "那年", "厂", "年轻", "小时候", "妈妈", "同学")
        ):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="healing",
                goal="remember",
                user_text=text,
                reason="点歌之后的讲述，疗愈写入回忆录",
                tool_calls=["remember"],
            )
        if any(word in text for word in ("回忆录", "小时候", "年轻时", "讲讲过去")):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="healing",
                goal="memoir",
                user_text=text,
                reason="意图=回忆讲述，交接疗愈",
                tool_calls=["remember"],
            )
        weatherish = any(word in text for word in ("天气", "下雨", "气温", "出门"))
        medish = any(word in text for word in ("降压药", "带药", "吃药", "提醒我", "复诊"))
        if weatherish and medish:
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="companion",
                goal="parallel",
                user_text=text,
                reason="并行协同：生活查天气，守护读自填药单，陪伴合成一句出口",
                tool_calls=["weather", "check_meds", "compose"],
            )
        if "挂号" in text or "预约" in text:
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_lesson",
                user_text=text,
                reason="数字小课堂：挂号教学，不是真实预约",
                tool_calls=["lesson:register"],
            )
        if "视频" in text:
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_lesson",
                user_text=text,
                reason="数字小课堂：接视频",
                tool_calls=["lesson:video"],
            )
        if "怎么看天气" in text or ("教" in text and "天气" in text):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_lesson",
                user_text=text,
                reason="数字小课堂：怎么问天气",
                tool_calls=["lesson:weather"],
            )
        if any(word in text for word in ("天气", "下雨", "气温", "带伞")):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_weather",
                user_text=text,
                reason="意图=问天气，交接生活智能体",
                tool_calls=["weather"],
            )
        if any(word in text for word in ("新闻", "念一段", "头条")):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_news",
                user_text=text,
                reason="意图=念新闻，交接生活智能体",
                tool_calls=["news"],
            )
        if any(word in text for word in ("提醒", "药单", "复诊", "吃药", "降压药")):
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="life",
                goal="life_remind",
                user_text=text,
                reason="意图=读自填提醒，不是用药指导",
                tool_calls=["reminders"],
            )
        rememberish = any(
            word in text for word in ("帮我记住", "帮我记下", "记一下", "帮我记")
        ) or any(
            "%s叫" % word in text for word in ("儿子", "女儿", "孙子", "孙女", "老伴")
        )
        if rememberish:
            return AgentMessage(
                from_agent="orchestrator",
                to_agent="memory",
                goal="remember_fact",
                user_text=text,
                reason="意图=写入记忆，交接记忆管家",
                tool_calls=["write_memory"],
            )
        return AgentMessage(
            from_agent="orchestrator",
            to_agent="companion",
            goal="chat",
            user_text=text,
            reason="意图=闲聊，单派陪伴智能体",
            tool_calls=["route:companion"],
        )

    def greeting(self) -> Dict[str, Any]:
        memory = self.memory.retrieve(self.board)
        unused = self.guardian.unused_line(self.board)
        if unused:
            text = unused
        else:
            text = self.companion.greeting(memory)
            last = (self.board.get_today_mood() or {}).get("mood") or self.board.get_kv("last_mood")
            if last == "low":
                song = find_song(self.board.get_kv("last_song")) or SONGS[0]
                text += "想听一首《%s》吗？" % song["title"]
        note = self.board.get_family_note()
        if note.get("text") and not note.get("delivered"):
            extra = "%s让我跟您说一句：%s" % (note.get("from_name") or "家里人", note["text"])
            if not extra.endswith("。"):
                extra += "。"
            text += extra
            self.board.mark_family_note_delivered()
            self.board.add_trace("guardian", "家人捎话由暖伴转述，不含聊天原文", [])
        return {"greeting": text, "memory": memory}

    def _guardian_event(self, text: str, route_name: str) -> Dict[str, Any]:
        observed = self.guardian.observe(self.board, text, route_name)
        trace = observed["trace"]
        return {
            "type": "trace",
            "id": trace.get("id"),
            "route": "guardian",
            "reason": trace.get("reason") or "",
            "memory_writes": trace.get("memory_writes") or [],
        }

    def play_song(self, song_id: str) -> Dict[str, Any]:
        memory = self.memory.retrieve(self.board)
        result = self.healing.play(song_id, memory)
        self.board.set_kv("last_song", result["song"]["id"])
        self.board.add_fact("爱好", "喜欢听《%s》" % result["song"]["title"], "healing")
        writes = [{"type": "facts", "key": "爱好", "value": "喜欢听《%s》" % result["song"]["title"]}]
        trace = self.board.add_trace("healing", "点歌后由疗愈讲述并追问", writes)
        self.board.add_message("assistant", result["speak"])
        result["trace"] = trace
        result["route"] = "healing"
        return result

    def remember_text(
        self, text: str, chapter_key: str = "", photo_id: int = 0
    ) -> Dict[str, Any]:
        memory = self.memory.retrieve(self.board, text)
        if photo_id:
            result = self.healing.photo_story(self.board, photo_id, text)
        else:
            song = find_song(self.board.get_kv("last_song"))
            key = chapter_key or (song or {}).get("chapter") or "youth"
            result = self.healing.remember(self.board, text, key, "oral")
        writes = self.memory.write_from_text(self.board, text)
        writes.append({"type": "chapter", "key": chapter_key or "youth", "value": "写入回忆录"})
        trace = self.board.add_trace("healing", "讲述写入回忆录", writes)
        self.board.add_message("user", text)
        self.board.add_message("assistant", result.get("speak") or "")
        result["trace"] = trace
        result["writes"] = writes
        result["route"] = "healing"
        result["memory"] = memory
        return result

    def handle_user(self, user_text: str) -> Iterator[Dict[str, Any]]:
        text = (user_text or "").strip()
        if not text:
            yield {"type": "error", "message": "我没听清，您再说一次。"}
            return

        route = self.classify(text)
        memory = self.memory.retrieve(self.board, text)
        route.memory_refs = memory.get("refs") or []
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in self.board.recent_messages(8)
            if item["role"] in ("user", "assistant")
        ]

        yield {
            "type": "route",
            "from_agent": route.from_agent,
            "to_agent": route.to_agent,
            "reason": route.reason,
            "memory_refs": route.memory_refs,
        }

        if route.goal == "play_song":
            played = self.healing.handle("play_song", self.board, text, memory)
            result = self.play_song((played.get("song") or {}).get("id") or SONGS[0]["id"])
            for token in _chunk(result["speak"]):
                yield {"type": "token", "text": token}
            yield {
                "type": "action",
                "action": "play_song",
                "song": result["song"],
            }
            yield {
                "type": "trace",
                "id": result["trace"].get("id"),
                "route": "healing",
                "reason": route.reason,
                "memory_writes": result["trace"].get("memory_writes") or [],
            }
            self.board.set_kv("next_priority", "")
            self.board.log_observation(
                "handoff",
                text,
                ["healing"],
                route.tool_calls or ["play_song"],
                result["trace"].get("memory_writes") or [],
                result["speak"],
            )
            yield self._guardian_event(text, "healing")
            yield {"type": "done", "reply": result["speak"], "writes": []}
            return

        if route.goal in ("remember", "memoir"):
            song = find_song(self.board.get_kv("last_song"))
            chapter = (song or {}).get("chapter") or "youth"
            result = self.remember_text(text, chapter)
            for token in _chunk(result.get("speak") or ""):
                yield {"type": "token", "text": token}
            yield {
                "type": "action",
                "action": "open_memoir",
                "chapter_key": chapter,
            }
            yield {
                "type": "trace",
                "id": result["trace"].get("id"),
                "route": "healing",
                "reason": route.reason,
                "memory_writes": result.get("writes") or [],
            }
            self.board.log_observation(
                "handoff",
                text,
                ["healing", "memory"],
                ["remember"],
                result.get("writes") or [],
                result.get("speak") or "",
            )
            yield self._guardian_event(text, "healing")
            yield {"type": "done", "reply": result.get("speak") or "", "writes": result.get("writes") or []}
            return

        if route.goal == "parallel":
            yield from self._handle_parallel(text, route, memory)
            return

        if route.to_agent == "life":
            yield from self._handle_life(text, route, memory)
            return

        if route.to_agent == "memory":
            yield from self._handle_memory(text, route, memory)
            return

        self.board.add_message("user", text)
        hint = self.guardian.companion_hint(self.board)
        collected: List[str] = []
        reply_model = "rules"
        for piece in self.companion.stream_reply(text, memory, history, hint=hint):
            token = piece.get("text") or ""
            reply_model = piece.get("model") or reply_model
            collected.append(token)
            yield {"type": "token", "text": token, "model": reply_model}

        reply = "".join(collected).strip()
        if reply:
            self.board.add_message("assistant", reply)

        writes = self.memory.write_from_text(self.board, text)
        route.blackboard_writes = writes
        trace = self.board.add_trace(route.to_agent, route.reason, writes)
        yield {
            "type": "trace",
            "id": trace.get("id"),
            "route": route.to_agent,
            "reason": route.reason,
            "memory_writes": writes,
            "created_at": trace.get("created_at"),
        }
        if writes:
            yield self._trace_event("memory", "记忆管家从这句话写入黑板", writes)
        agents = ["companion", "memory"] if writes else ["companion"]
        self.board.log_observation(
            "single",
            text,
            agents,
            ["route:companion"],
            writes,
            reply,
        )
        yield self._guardian_event(text, route.to_agent)
        yield {"type": "done", "reply": reply, "writes": writes, "model": reply_model}

    def _courtesy_of(self, memory: Dict[str, Any]) -> str:
        profile = memory.get("profile") or {}
        return profile.get("courtesy") or profile.get("display_name") or "您"

    def _trace_event(self, agent: str, reason: str, writes: List[Dict[str, Any]]) -> Dict[str, Any]:
        trace = self.board.add_trace(agent, reason, writes)
        return {
            "type": "trace",
            "id": trace.get("id"),
            "route": agent,
            "reason": reason,
            "memory_writes": writes,
            "created_at": trace.get("created_at"),
        }

    def _handle_parallel(
        self, text: str, route: AgentMessage, memory: Dict[str, Any]
    ) -> Iterator[Dict[str, Any]]:
        weather = self.life.weather(self.board)
        meds = self.guardian.check_meds(self.board, text)
        courtesy = self._courtesy_of(memory)
        speak = self.companion.compose(courtesy, [weather.get("speak") or "", meds])
        yield {
            "type": "tool",
            "agent": "life",
            "tool": "weather",
            "text": weather.get("speak") or "",
        }
        yield {
            "type": "tool",
            "agent": "guardian",
            "tool": "check_meds",
            "text": meds,
        }
        self.board.add_message("user", text)
        for token in _chunk(speak):
            yield {"type": "token", "text": token}
        self.board.add_message("assistant", speak)
        writes = self.memory.write_from_text(self.board, text)
        yield self._trace_event("life", "查询天气", [])
        yield self._trace_event("guardian", "读取自填药单，不作用药指导", [])
        yield self._trace_event("companion", "合成一句出口，不让三个智能体抢话", writes)
        self.board.log_observation(
            "parallel",
            text,
            ["life", "guardian", "companion"],
            ["weather", "check_meds", "compose"],
            writes,
            speak,
        )
        yield {"type": "done", "reply": speak, "writes": writes}

    def _handle_memory(
        self, text: str, route: AgentMessage, memory: Dict[str, Any]
    ) -> Iterator[Dict[str, Any]]:
        result = self.memory.handle(self.board, text, memory)
        speak = result.get("speak") or ""
        writes = result.get("writes") or []
        yield {
            "type": "tool",
            "agent": "memory",
            "tool": result.get("tool") or "write_memory",
            "text": speak,
        }
        self.board.add_message("user", text)
        for token in _chunk(speak):
            yield {"type": "token", "text": token}
        self.board.add_message("assistant", speak)
        yield self._trace_event("memory", route.reason, writes)
        self.board.log_observation(
            "handoff",
            text,
            ["memory"],
            ["write_memory"],
            writes,
            speak,
        )
        yield self._guardian_event(text, "memory")
        yield {"type": "done", "reply": speak, "writes": writes}

    def _handle_life(
        self, text: str, route: AgentMessage, memory: Dict[str, Any]
    ) -> Iterator[Dict[str, Any]]:
        courtesy = self._courtesy_of(memory)
        result = self.life.handle(self.board, route.goal, courtesy, route.tool_calls or [])
        speak = result.get("speak") or ""
        tool = result.get("tool") or (route.tool_calls or ["life"])[0]
        yield {
            "type": "tool",
            "agent": "life",
            "tool": tool,
            "text": speak,
        }
        self.board.add_message("user", text)
        for token in _chunk(speak):
            yield {"type": "token", "text": token}
        self.board.add_message("assistant", speak)
        writes = self.memory.write_from_text(self.board, text)
        yield self._trace_event("life", route.reason, writes)
        self.board.log_observation(
            "life",
            text,
            ["life"],
            [tool],
            writes,
            speak,
        )
        yield {"type": "done", "reply": speak, "writes": writes}


def _chunk(text: str) -> Iterator[str]:
    for i in range(0, len(text), 2):
        yield text[i : i + 2]
