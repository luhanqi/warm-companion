from __future__ import annotations

import json
import secrets
import sqlite3
from collections import Counter
from contextvars import ContextVar, Token
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .db import connect, row_to_dict, rows_to_dicts

_ACTIVE_USER_ID: ContextVar[str] = ContextVar("warm_companion_user_id", default="default")


class _CurrentUser:
    @property
    def value(self) -> str:
        return _ACTIVE_USER_ID.get()


USER_ID = _CurrentUser()
sqlite3.register_adapter(_CurrentUser, lambda item: item.value)


class Blackboard:
    def __init__(self) -> None:
        self.conn = connect()

    @property
    def user_id(self) -> str:
        return _ACTIVE_USER_ID.get()

    def bind_user(self, user_id: str) -> Token:
        return _ACTIVE_USER_ID.set((user_id or "default").strip() or "default")

    def reset_user(self, token: Token) -> None:
        _ACTIVE_USER_ID.reset(token)

    def ensure_user(self, user_id: str, display_name: str = "") -> None:
        user_id = (user_id or "").strip()
        if not user_id:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO profile (user_id, display_name, courtesy) VALUES (?, ?, ?)",
            (user_id, display_name, display_name),
        )
        from .content import CHAPTERS

        for item in CHAPTERS:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO chapters (user_id, chapter_key, title, body, audio_note)
                VALUES (?, ?, ?, '', '')
                """,
                (user_id, item["key"], item["title"]),
            )
        self.conn.commit()

    def get_profile(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM profile WHERE user_id = ?", (USER_ID,)
        ).fetchone()
        return row_to_dict(row) or {}

    def update_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_profile()
        fields = ["display_name", "courtesy", "hometown", "birth_decade", "speech_rate", "photo"]
        values = [payload.get(name, current.get(name, "")) for name in fields]
        self.conn.execute(
            """
            UPDATE profile
            SET display_name=?, courtesy=?, hometown=?, birth_decade=?, speech_rate=?, photo=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?
            """,
            values + [USER_ID],
        )
        self.conn.commit()
        return self.get_profile()

    def list_people(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM people WHERE user_id = ? ORDER BY id", (USER_ID,)
        ).fetchall()
        return rows_to_dicts(rows)

    def add_person(self, relation: str, name: str, note: str = "") -> Dict[str, Any]:
        existing = self.conn.execute(
            "SELECT * FROM people WHERE user_id=? AND relation=? AND name=?",
            (USER_ID, relation, name),
        ).fetchone()
        if existing:
            return row_to_dict(existing) or {}
        cur = self.conn.execute(
            "INSERT INTO people (user_id, relation, name, note) VALUES (?, ?, ?, ?)",
            (USER_ID, relation, name, note),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM people WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row) or {}

    def delete_person(self, person_id: int) -> None:
        self.conn.execute(
            "DELETE FROM people WHERE id = ? AND user_id = ?", (person_id, USER_ID)
        )
        self.conn.commit()

    def set_profile_photo(self, filename: str) -> Dict[str, Any]:
        self.conn.execute(
            "UPDATE profile SET photo=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (filename, USER_ID),
        )
        self.conn.commit()
        return self.get_profile()

    def set_person_photo(self, person_id: int, filename: str) -> Optional[Dict[str, Any]]:
        self.conn.execute(
            "UPDATE people SET photo=? WHERE id=? AND user_id=?",
            (filename, person_id, USER_ID),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM people WHERE id=? AND user_id=?", (person_id, USER_ID)
        ).fetchone()
        return row_to_dict(row)

    def list_facts(self, limit: int = 12) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM facts WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def add_fact(self, key: str, value: str, source: str = "steward") -> Optional[Dict[str, Any]]:
        existed = self.conn.execute(
            "SELECT * FROM facts WHERE user_id=? AND key=? AND value=?",
            (USER_ID, key, value),
        ).fetchone()
        if existed:
            return None
        cur = self.conn.execute(
            "INSERT INTO facts (user_id, key, value, source) VALUES (?, ?, ?, ?)",
            (USER_ID, key, value, source),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM facts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row)

    def update_fact(self, fact_id: int, key: str, value: str) -> Optional[Dict[str, Any]]:
        self.conn.execute(
            "UPDATE facts SET key=?, value=? WHERE id=? AND user_id=?",
            (key.strip(), value.strip(), fact_id, USER_ID),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM facts WHERE id=? AND user_id=?", (fact_id, USER_ID)
        ).fetchone()
        return row_to_dict(row)

    def delete_fact(self, fact_id: int) -> None:
        self.conn.execute("DELETE FROM facts WHERE id=? AND user_id=?", (fact_id, USER_ID))
        self.conn.commit()

    def recent_messages(self, limit: int = 8) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?
            ) t ORDER BY id
            """,
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def speech_style_profile(self, limit: int = 60) -> Dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT content FROM messages
            WHERE user_id=? AND role='user'
            ORDER BY id DESC LIMIT ?
            """,
            (USER_ID, limit),
        ).fetchall()
        texts = [(row["content"] or "").strip() for row in rows if (row["content"] or "").strip()]
        if len(texts) < 5:
            return {"status": "collecting", "sample_count": len(texts)}
        average_length = round(sum(len(text) for text in texts) / len(texts), 1)
        endings = Counter(text[-1] for text in texts if text[-1] in "呀呢啊吧嘛啦哦")
        fillers = Counter()
        for text in texts:
            for word in ("嗯", "这个", "那个", "然后", "就是", "怎么说"):
                fillers[word] += text.count(word)
        return {
            "status": "available",
            "sample_count": len(texts),
            "pace": "简短" if average_length < 16 else ("舒缓" if average_length < 36 else "细致"),
            "average_length": average_length,
            "preferred_ending": endings.most_common(1)[0][0] if endings else "",
            "common_filler": fillers.most_common(1)[0][0] if fillers and fillers.most_common(1)[0][1] else "",
        }

    def add_message(self, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (USER_ID, role, content),
        )
        self.conn.commit()

    def add_trace(self, route: str, reason: str, memory_writes: List[Any]) -> Dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO traces (user_id, route, reason, memory_writes) VALUES (?, ?, ?, ?)",
            (USER_ID, route, reason, json.dumps(memory_writes, ensure_ascii=False)),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM traces WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return self._parse_trace(row_to_dict(row) or {})

    def recent_traces(self, limit: int = 8) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM traces WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return [self._parse_trace(item) for item in rows_to_dicts(rows)]

    def _parse_trace(self, item: Dict[str, Any]) -> Dict[str, Any]:
        raw = item.get("memory_writes") or "[]"
        if isinstance(raw, str):
            try:
                item["memory_writes"] = json.loads(raw)
            except json.JSONDecodeError:
                item["memory_writes"] = []
        return item

    def snapshot(self) -> Dict[str, Any]:
        return {
            "profile": self.get_profile(),
            "people": self.list_people(),
            "facts": self.list_facts(),
            "messages": self.recent_messages(16),
            "speech_style": self.speech_style_profile(),
            "traces": self.recent_traces(6),
            "photos": self.list_photos(),
            "chapters": self.list_chapters(),
            "last_song": self.get_kv("last_song"),
            "reminders": self.list_reminders(),
        }

    def get_kv(self, key: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM kv WHERE user_id=? AND key=?", (USER_ID, key)
        ).fetchone()
        return row["value"] if row else ""

    def set_kv(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO kv (user_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value
            """,
            (USER_ID, key, value),
        )
        self.conn.commit()

    def get_memory_embedding(
        self, kind: str, document_id: str, text_hash: str, model: str
    ) -> Optional[List[float]]:
        row = self.conn.execute(
            """
            SELECT vector FROM memory_embeddings
            WHERE user_id=? AND kind=? AND document_id=? AND text_hash=? AND model=?
            """,
            (USER_ID, kind, str(document_id), text_hash, model),
        ).fetchone()
        if not row:
            return None
        try:
            return [float(value) for value in json.loads(row["vector"])]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def set_memory_embedding(
        self,
        kind: str,
        document_id: str,
        text_hash: str,
        model: str,
        vector: List[float],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_embeddings
                (user_id, kind, document_id, text_hash, model, vector, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, kind, document_id, model) DO UPDATE SET
                text_hash=excluded.text_hash,
                vector=excluded.vector,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                USER_ID,
                kind,
                str(document_id),
                text_hash,
                model,
                json.dumps(vector, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def list_photos(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM photos WHERE user_id=? ORDER BY id DESC", (USER_ID,)
        ).fetchall()
        return rows_to_dicts(rows)

    def add_photo(self, filename: str, caption: str = "") -> Dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO photos (user_id, filename, caption) VALUES (?, ?, ?)",
            (USER_ID, filename, caption),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM photos WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row) or {}

    def set_photo_analysis(self, photo_id: int, description: str, provider: str) -> Dict[str, Any]:
        self.conn.execute(
            "UPDATE photos SET ai_description=?, ai_provider=? WHERE id=? AND user_id=?",
            (description.strip(), provider.strip(), photo_id, USER_ID),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM photos WHERE id=? AND user_id=?", (photo_id, USER_ID)
        ).fetchone()
        return row_to_dict(row) or {}

    def update_photo_story(self, photo_id: int, story: str) -> Optional[Dict[str, Any]]:
        self.conn.execute(
            "UPDATE photos SET story=? WHERE id=? AND user_id=?",
            (story, photo_id, USER_ID),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM photos WHERE id=? AND user_id=?", (photo_id, USER_ID)
        ).fetchone()
        return row_to_dict(row)

    def list_chapters(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM chapters WHERE user_id=? ORDER BY rowid", (USER_ID,)
        ).fetchall()
        return rows_to_dicts(rows)

    def append_chapter(self, chapter_key: str, paragraph: str, audio_note: str = "") -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM chapters WHERE user_id=? AND chapter_key=?",
            (USER_ID, chapter_key),
        ).fetchone()
        current = (row["body"] if row else "").strip()
        body = (current + "\n\n" + paragraph).strip() if current else paragraph.strip()
        note = audio_note or (row["audio_note"] if row else "")
        title = row["title"] if row else chapter_key
        self.conn.execute(
            """
            INSERT INTO chapters (user_id, chapter_key, title, body, audio_note, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chapter_key) DO UPDATE SET
                body=excluded.body,
                audio_note=excluded.audio_note,
                updated_at=CURRENT_TIMESTAMP
            """,
            (USER_ID, chapter_key, title, body, note),
        )
        self.conn.commit()
        saved = self.conn.execute(
            "SELECT * FROM chapters WHERE user_id=? AND chapter_key=?",
            (USER_ID, chapter_key),
        ).fetchone()
        return row_to_dict(saved) or {}

    def clear_chapter(self, chapter_key: str) -> Dict[str, Any]:
        self.conn.execute(
            """
            UPDATE chapters SET body='', audio_note='', updated_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND chapter_key=?
            """,
            (USER_ID, chapter_key),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM chapters WHERE user_id=? AND chapter_key=?",
            (USER_ID, chapter_key),
        ).fetchone()
        return row_to_dict(row) or {}

    def find_account(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE username=?", (username.strip(),)
        ).fetchone()
        return row_to_dict(row)

    def create_account(
        self,
        username: str,
        password_hash: str,
        role: str,
        display_name: str,
        linked_user_id: str = "default",
    ) -> Dict[str, Any]:
        family_link_code = "%06d" % secrets.randbelow(1000000) if role == "elder" else ""
        cur = self.conn.execute(
            """
            INSERT INTO accounts (
                username, password_hash, role, display_name, linked_user_id, family_link_code
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username.strip(), password_hash, role, display_name.strip(),
                linked_user_id, family_link_code,
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row) or {}

    def create_session(self, account_id: int, token: str) -> None:
        from .auth import token_digest

        self.conn.execute(
            """
            INSERT INTO sessions (token, account_id, expires_at)
            VALUES (?, ?, datetime('now', '+30 days'))
            """,
            (token_digest(token), account_id),
        )
        self.conn.commit()

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        from .auth import token_digest

        self.conn.execute(
            "DELETE FROM sessions WHERE expires_at<>'' AND expires_at<=CURRENT_TIMESTAMP"
        )
        row = self.conn.execute(
            """
            SELECT accounts.id, accounts.username, accounts.role, accounts.display_name,
                   accounts.linked_user_id, sessions.token
            FROM sessions JOIN accounts ON accounts.id = sessions.account_id
            WHERE sessions.token=?
              AND (sessions.expires_at='' OR sessions.expires_at>CURRENT_TIMESTAMP)
            """,
            (token_digest(token),),
        ).fetchone()
        self.conn.commit()
        return row_to_dict(row)

    def delete_session(self, token: str) -> None:
        from .auth import token_digest

        self.conn.execute("DELETE FROM sessions WHERE token=?", (token_digest(token),))
        self.conn.commit()

    def update_password_hash(self, account_id: int, password_hash: str) -> None:
        self.conn.execute(
            "UPDATE accounts SET password_hash=? WHERE id=?", (password_hash, account_id)
        )
        self.conn.commit()

    def family_link_code(self, account_id: int) -> str:
        row = self.conn.execute(
            "SELECT family_link_code FROM accounts WHERE id=? AND role='elder'", (account_id,)
        ).fetchone()
        return str(row["family_link_code"] or "") if row else ""

    def rotate_family_link_code(self, account_id: int) -> str:
        code = "%06d" % secrets.randbelow(1000000)
        self.conn.execute(
            "UPDATE accounts SET family_link_code=? WHERE id=? AND role='elder'",
            (code, account_id),
        )
        self.conn.commit()
        return code

    def owns_photo_file(self, filename: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM photos WHERE user_id=? AND filename=? LIMIT 1",
            (USER_ID, filename),
        ).fetchone()
        return bool(row)

    def owns_avatar_file(self, filename: str) -> bool:
        profile = self.conn.execute(
            "SELECT 1 FROM profile WHERE user_id=? AND photo=? LIMIT 1",
            (USER_ID, filename),
        ).fetchone()
        if profile:
            return True
        person = self.conn.execute(
            "SELECT 1 FROM people WHERE user_id=? AND photo=? LIMIT 1",
            (USER_ID, filename),
        ).fetchone()
        return bool(person)

    def owns_painting_file(self, filename: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM paintings WHERE user_id=? AND filename=? LIMIT 1",
            (USER_ID, filename),
        ).fetchone()
        return bool(row)

    def share_digest(self) -> bool:
        return self.get_kv("share_digest") == "1"

    def set_share_digest(self, allowed: bool) -> None:
        self.set_kv("share_digest", "1" if allowed else "0")

    def consent_scopes(self) -> Dict[str, bool]:
        defaults = {
            "family_digest": self.share_digest(),
            "transcript_analysis": False,
            "audio_storage": False,
            "family_cognition": False,
            "family_care_view": False,
            "family_care_edit": False,
            "family_reminders": False,
            "voice_personalization": False,
            "voice_analysis": False,
            "photo_analysis": False,
            "memory_video": False,
            "external_memory_ai": False,
            "cloud_conversation": False,
            "cloud_image_processing": False,
            "cloud_voice_processing": False,
            "cloud_video_processing": False,
            "research_cognition_model": False,
        }
        rows = self.conn.execute(
            "SELECT scope, allowed FROM consent_scopes WHERE user_id=?", (USER_ID,)
        ).fetchall()
        for row in rows:
            defaults[row["scope"]] = bool(row["allowed"])
        return defaults

    def set_consent_scope(self, scope: str, allowed: bool) -> Dict[str, bool]:
        scopes = self.consent_scopes()
        if scope not in scopes:
            raise ValueError("unknown consent scope")
        self.conn.execute(
            """
            INSERT INTO consent_scopes (user_id, scope, allowed, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, scope) DO UPDATE SET
                allowed=excluded.allowed, updated_at=CURRENT_TIMESTAMP
            """,
            (USER_ID, scope, 1 if allowed else 0),
        )
        if scope == "family_digest":
            self.set_share_digest(allowed)
        self.conn.commit()
        return self.consent_scopes()

    def add_language_sample(self, transcript: str, features: Dict[str, Any], source: str = "talk") -> Dict[str, Any]:
        cur = self.conn.execute(
            """
            INSERT INTO language_samples (
                user_id, source, transcript, char_count, sentence_count,
                lexical_diversity, repetition_ratio, filler_ratio,
                coherence, completeness, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                USER_ID,
                source,
                transcript.strip(),
                int(features.get("char_count") or 0),
                int(features.get("sentence_count") or 0),
                float(features.get("lexical_diversity") or 0),
                float(features.get("repetition_ratio") or 0),
                float(features.get("filler_ratio") or 0),
                float(features.get("coherence") or 0),
                float(features.get("completeness") or 0),
                float(features.get("quality") or 0),
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM language_samples WHERE id=?", (cur.lastrowid,)).fetchone()
        self._refresh_cognitive_day(self.today())
        return row_to_dict(row) or {}

    def _refresh_cognitive_day(self, day: str) -> None:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS sample_count,
                   AVG(lexical_diversity) AS lexical_diversity,
                   AVG(repetition_ratio) AS repetition_ratio,
                   AVG(filler_ratio) AS filler_ratio,
                   AVG(coherence) AS coherence,
                   AVG(completeness) AS completeness,
                   AVG(quality) AS quality
            FROM language_samples
            WHERE user_id=? AND substr(created_at, 1, 10)=? AND quality>=0.6
            """,
            (USER_ID, day),
        ).fetchone()
        count = int((row or {})["sample_count"] or 0)
        if not count:
            self.conn.execute(
                "DELETE FROM cognitive_daily_metrics WHERE user_id=? AND day=?",
                (USER_ID, day),
            )
            self.conn.commit()
            return
        self.conn.execute(
            """
            INSERT INTO cognitive_daily_metrics (
                user_id, day, sample_count, lexical_diversity, repetition_ratio,
                filler_ratio, coherence, completeness, quality, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, day) DO UPDATE SET
                sample_count=excluded.sample_count,
                lexical_diversity=excluded.lexical_diversity,
                repetition_ratio=excluded.repetition_ratio,
                filler_ratio=excluded.filler_ratio,
                coherence=excluded.coherence,
                completeness=excluded.completeness,
                quality=excluded.quality,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                USER_ID,
                day,
                count,
                float(row["lexical_diversity"] or 0),
                float(row["repetition_ratio"] or 0),
                float(row["filler_ratio"] or 0),
                float(row["coherence"] or 0),
                float(row["completeness"] or 0),
                float(row["quality"] or 0),
            ),
        )
        self.conn.commit()

    def list_cognitive_daily_metrics(self, limit: int = 90) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *, day AS created_at
            FROM cognitive_daily_metrics
            WHERE user_id=? ORDER BY day DESC LIMIT ?
            """,
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def list_language_samples(self, limit: int = 90) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM language_samples WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def add_voice_session(
        self,
        filename: str,
        transcript: str,
        duration_ms: int,
        mime_type: str,
        silence_ratio: float = 0,
        pause_count: int = 0,
        rms: float = 0,
        peak: float = 0,
        longest_pause_ms: int = 0,
        speech_segments: int = 0,
        zero_crossing_rate: float = 0,
        response_latency_ms: int = 0,
        asr_provider: str = "",
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cur = self.conn.execute(
            """
            INSERT INTO voice_sessions (
                user_id, filename, transcript, duration_ms, mime_type,
                silence_ratio, pause_count, rms, peak
                , longest_pause_ms, speech_segments, zero_crossing_rate, response_latency_ms
                , asr_provider, analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                USER_ID, filename, transcript.strip(), max(0, duration_ms), mime_type,
                max(0, min(1, silence_ratio)), max(0, pause_count), max(0, rms), max(0, peak),
                max(0, longest_pause_ms), max(0, speech_segments),
                max(0, zero_crossing_rate), max(0, response_latency_ms),
                asr_provider.strip(), json.dumps(analysis or {}, ensure_ascii=False),
            ),
        )
        self.conn.execute(
            """
            UPDATE memory_projects SET voice_session_id=?, status='ready'
            WHERE user_id=? AND voice_session_id=0 AND narration=?
              AND created_at >= datetime('now', '-5 minutes')
            """,
            (cur.lastrowid, USER_ID, transcript.strip()),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM voice_sessions WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row) or {}

    def latest_voice_prompt(self) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT * FROM voice_sessions
            WHERE user_id=? AND transcript<>'' AND duration_ms>=1500
            ORDER BY id DESC LIMIT 1
            """,
            (USER_ID,),
        ).fetchone()
        return row_to_dict(row)

    def voice_summary(self, limit: int = 30) -> Dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT transcript, duration_ms, silence_ratio, pause_count, rms, peak,
                   longest_pause_ms, speech_segments, zero_crossing_rate, response_latency_ms
            FROM voice_sessions
            WHERE user_id=? AND duration_ms >= 1000 ORDER BY id DESC LIMIT ?
            """,
            (USER_ID, limit),
        ).fetchall()
        rates = []
        silence_values = []
        pause_values = []
        rms_values = []
        longest_pauses = []
        response_latencies = []
        zero_crossings = []
        for row in rows:
            count = len([char for char in (row["transcript"] or "") if not char.isspace()])
            minutes = float(row["duration_ms"]) / 60000.0
            if count and minutes:
                rates.append(count / minutes)
            silence_values.append(float(row["silence_ratio"] or 0))
            pause_values.append(int(row["pause_count"] or 0))
            rms_values.append(float(row["rms"] or 0))
            longest_pauses.append(int(row["longest_pause_ms"] or 0))
            response_latencies.append(int(row["response_latency_ms"] or 0))
            zero_crossings.append(float(row["zero_crossing_rate"] or 0))
        return {
            "sample_count": len(rates),
            "average_chars_per_minute": round(sum(rates) / len(rates), 1) if rates else 0,
            "average_silence_ratio": round(sum(silence_values) / len(silence_values), 3) if silence_values else 0,
            "average_pause_count": round(sum(pause_values) / len(pause_values), 1) if pause_values else 0,
            "average_rms": round(sum(rms_values) / len(rms_values), 4) if rms_values else 0,
            "average_longest_pause_ms": round(sum(longest_pauses) / len(longest_pauses)) if longest_pauses else 0,
            "average_response_latency_ms": round(sum(response_latencies) / len(response_latencies)) if response_latencies else 0,
            "average_zero_crossing_rate": round(sum(zero_crossings) / len(zero_crossings), 4) if zero_crossings else 0,
            "status": "available" if len(rates) >= 3 else "collecting",
        }

    def get_voice_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM voice_sessions WHERE id=? AND user_id=?", (session_id, USER_ID)
        ).fetchone()
        return row_to_dict(row)

    def ensure_cognitive_alert(self, level: str, title: str, detail: str) -> Optional[Dict[str, Any]]:
        existing = self.conn.execute(
            """
            SELECT * FROM cognitive_alerts
            WHERE user_id=? AND acknowledged=0 AND created_at >= datetime('now', '-7 days')
            ORDER BY id DESC LIMIT 1
            """,
            (USER_ID,),
        ).fetchone()
        if existing:
            return row_to_dict(existing)
        cur = self.conn.execute(
            "INSERT INTO cognitive_alerts (user_id, level, title, detail) VALUES (?, ?, ?, ?)",
            (USER_ID, level, title, detail),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM cognitive_alerts WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)

    def list_cognitive_alerts(self, limit: int = 12) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM cognitive_alerts WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def acknowledge_cognitive_alert(self, alert_id: int) -> None:
        self.conn.execute(
            "UPDATE cognitive_alerts SET acknowledged=1 WHERE id=? AND user_id=?",
            (alert_id, USER_ID),
        )
        self.conn.commit()

    def list_memory_documents(self, limit: int = 120) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        for fact in self.list_facts(limit):
            documents.append({"kind": "fact", "id": fact["id"], "text": fact["value"], "source": fact.get("source") or "记忆"})
        for chapter in self.list_chapters():
            body = (chapter.get("body") or "").strip()
            if body:
                paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
                for index, paragraph in enumerate(paragraphs):
                    for offset in range(0, len(paragraph), 280):
                        chunk = paragraph[offset : offset + 320].strip()
                        if chunk:
                            documents.append({
                                "kind": "chapter",
                                "id": "%s:%s:%s" % (chapter["chapter_key"], index, offset),
                                "text": chunk,
                                "source": "回忆录·" + chapter["title"],
                            })
        for photo in self.list_photos():
            text = " ".join(
                part for part in (photo.get("caption"), photo.get("story"), photo.get("ai_description")) if part
            )
            if text:
                documents.append({"kind": "photo", "id": photo["id"], "text": text, "source": "老照片"})
        return documents

    def add_memory_project(self, photo_id: int, song_id: str, narration: str, title: str = "") -> Dict[str, Any]:
        if photo_id:
            owned = self.conn.execute(
                "SELECT id FROM photos WHERE id=? AND user_id=?", (photo_id, USER_ID)
            ).fetchone()
            if not owned:
                raise ValueError("photo not found")
        voice = self.conn.execute(
            """
            SELECT id FROM voice_sessions
            WHERE user_id=? AND transcript=? AND created_at >= datetime('now', '-5 minutes')
            ORDER BY id DESC LIMIT 1
            """,
            (USER_ID, narration.strip()),
        ).fetchone()
        voice_session_id = int(voice["id"]) if voice else 0
        cur = self.conn.execute(
            """
            INSERT INTO memory_projects (user_id, photo_id, song_id, narration, title, voice_session_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                USER_ID,
                photo_id,
                song_id.strip(),
                narration.strip(),
                title.strip(),
                voice_session_id,
                "ready" if voice_session_id else "storyboard",
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM memory_projects WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row) or {}

    def list_memory_projects(self, limit: int = 24) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT memory_projects.*, photos.filename AS photo_filename,
                   photos.caption AS photo_caption
            FROM memory_projects
            LEFT JOIN photos ON photos.id=memory_projects.photo_id AND photos.user_id=memory_projects.user_id
            WHERE memory_projects.user_id=? ORDER BY memory_projects.id DESC LIMIT ?
            """,
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def get_memory_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT memory_projects.*, photos.filename AS photo_filename,
                   photos.caption AS photo_caption
            FROM memory_projects
            LEFT JOIN photos ON photos.id=memory_projects.photo_id AND photos.user_id=memory_projects.user_id
            WHERE memory_projects.id=? AND memory_projects.user_id=?
            """,
            (project_id, USER_ID),
        ).fetchone()
        return row_to_dict(row)

    def set_memory_project_video(self, project_id: int, result: Dict[str, Any]) -> Dict[str, Any]:
        self.conn.execute(
            """
            UPDATE memory_projects
            SET video_job_id=?, video_url=?, video_provider=?, status=?
            WHERE id=? AND user_id=?
            """,
            (
                str(result.get("job_id") or ""),
                str(result.get("video_url") or ""),
                str(result.get("provider") or ""),
                str(result.get("status") or "submitted"),
                project_id,
                USER_ID,
            ),
        )
        self.conn.commit()
        return self.get_memory_project(project_id) or {}

    def owns_memory_video(self, relative_url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM memory_projects WHERE user_id=? AND video_url=? LIMIT 1",
            (USER_ID, relative_url),
        ).fetchone()
        return bool(row)

    def today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def week_start(self) -> str:
        now = datetime.now()
        start = now - timedelta(days=now.weekday())
        return start.strftime("%Y-%m-%d")

    def set_mood(self, mood: str, source: str = "garden") -> Dict[str, Any]:
        day = self.today()
        self.conn.execute(
            """
            INSERT INTO moods (user_id, day, mood, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                mood=excluded.mood,
                source=excluded.source,
                created_at=CURRENT_TIMESTAMP
            """,
            (USER_ID, day, mood, source),
        )
        self.conn.commit()
        self.set_kv("last_mood", mood)
        row = self.conn.execute(
            "SELECT * FROM moods WHERE user_id=? AND day=?", (USER_ID, day)
        ).fetchone()
        return row_to_dict(row) or {}

    def get_today_mood(self) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM moods WHERE user_id=? AND day=?", (USER_ID, self.today())
        ).fetchone()
        return row_to_dict(row)

    def list_moods(self, since: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM moods WHERE user_id=? AND day>=? ORDER BY day
            """,
            (USER_ID, since),
        ).fetchall()
        return rows_to_dicts(rows)

    def unused_days(self) -> int:
        row = self.conn.execute(
            "SELECT created_at FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (USER_ID,),
        ).fetchone()
        if not row:
            return 0
        raw = str(row["created_at"] or "")[:10]
        try:
            last = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return 0
        delta = datetime.now().date() - last.date()
        return max(0, delta.days)

    def talk_days_this_week(self) -> int:
        rows = self.conn.execute(
            """
            SELECT DISTINCT substr(created_at, 1, 10) AS day
            FROM messages
            WHERE user_id=? AND role='user' AND created_at >= ?
            """,
            (USER_ID, self.week_start()),
        ).fetchall()
        return len(rows)

    def chapters_updated_this_week(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM chapters
            WHERE user_id=? AND body != '' AND updated_at >= ?
            ORDER BY rowid
            """,
            (USER_ID, self.week_start()),
        ).fetchall()
        return rows_to_dicts(rows)

    def list_reminders(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM reminders WHERE user_id=? ORDER BY id", (USER_ID,)
        ).fetchall()
        return rows_to_dicts(rows)

    def add_reminder(self, kind: str, title: str, note: str = "") -> Dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO reminders (user_id, kind, title, note) VALUES (?, ?, ?, ?)",
            (USER_ID, kind, title.strip(), note.strip()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM reminders WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row) or {}

    def delete_reminder(self, reminder_id: int) -> None:
        self.conn.execute(
            "DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, USER_ID)
        )
        self.conn.commit()

    def log_observation(
        self,
        mode: str,
        user_text: str,
        agents: List[str],
        tools: List[str],
        writes: List[Any],
        final_text: str,
    ) -> Dict[str, Any]:
        cur = self.conn.execute(
            """
            INSERT INTO observations (user_id, mode, user_text, agents, tools, writes, final_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                USER_ID,
                mode,
                user_text[:80],
                json.dumps(agents, ensure_ascii=False),
                json.dumps(tools, ensure_ascii=False),
                json.dumps(writes, ensure_ascii=False),
                final_text[:160],
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM observations WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return self._parse_observation(row_to_dict(row) or {})

    def list_observations(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM observations WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return [self._parse_observation(item) for item in rows_to_dicts(rows)]

    def list_paintings(self, limit: int = 24) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM paintings WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def get_family_note(self) -> Dict[str, Any]:
        raw = self.get_kv("family_note")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def set_family_note(self, text: str, from_name: str) -> Dict[str, Any]:
        note = {
            "text": (text or "").strip()[:80],
            "from_name": (from_name or "").strip() or "家里人",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "delivered": False,
        }
        if not note["text"]:
            self.set_kv("family_note", "")
            return {}
        self.set_kv("family_note", json.dumps(note, ensure_ascii=False))
        return note

    def mark_family_note_delivered(self) -> None:
        note = self.get_family_note()
        if not note.get("text"):
            return
        note["delivered"] = True
        self.set_kv("family_note", json.dumps(note, ensure_ascii=False))

    def add_painting(
        self,
        filename: str,
        prompt: str,
        style: str,
        provider: str,
        from_name: str = "",
        dedication: str = "",
    ) -> Dict[str, Any]:
        cur = self.conn.execute(
            """
            INSERT INTO paintings (user_id, filename, prompt, style, provider, from_name, dedication)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (USER_ID, filename, prompt, style, provider, from_name, dedication),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM paintings WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return row_to_dict(row) or {}

    def _parse_observation(self, item: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("agents", "tools", "writes"):
            raw = item.get(key) or "[]"
            if isinstance(raw, str):
                try:
                    item[key] = json.loads(raw)
                except json.JSONDecodeError:
                    item[key] = []
        return item


def weekday_cn() -> str:
    names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return names[datetime.now().weekday()]


def daypart_cn() -> str:
    hour = datetime.now().hour
    if hour < 11:
        return "早上"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    return "晚上"
