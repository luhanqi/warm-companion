from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.getenv("NUANBAN_DATA_DIR") or DEFAULT_DATA_DIR).resolve()
DB_PATH = DATA_DIR / "warm_companion.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS profile (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            courtesy TEXT NOT NULL DEFAULT '',
            hometown TEXT NOT NULL DEFAULT '',
            birth_decade TEXT NOT NULL DEFAULT '',
            speech_rate REAL NOT NULL DEFAULT 0.82,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            name TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'steward',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            route TEXT NOT NULL,
            reason TEXT NOT NULL,
            memory_writes TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS kv (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (user_id, key)
        );

        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            story TEXT NOT NULL DEFAULT '',
            ai_description TEXT NOT NULL DEFAULT '',
            ai_provider TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chapters (
            user_id TEXT NOT NULL,
            chapter_key TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            audio_note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chapter_key)
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            linked_user_id TEXT NOT NULL DEFAULT 'default',
            family_link_code TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            day TEXT NOT NULL,
            mood TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'garden',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, day)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'medicine',
            title TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            user_text TEXT NOT NULL DEFAULT '',
            agents TEXT NOT NULL DEFAULT '[]',
            tools TEXT NOT NULL DEFAULT '[]',
            writes TEXT NOT NULL DEFAULT '[]',
            final_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS paintings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            prompt TEXT NOT NULL DEFAULT '',
            style TEXT NOT NULL DEFAULT 'water',
            provider TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS consent_scopes (
            user_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, scope)
        );

        CREATE TABLE IF NOT EXISTS language_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'talk',
            transcript TEXT NOT NULL DEFAULT '',
            char_count INTEGER NOT NULL DEFAULT 0,
            sentence_count INTEGER NOT NULL DEFAULT 0,
            lexical_diversity REAL NOT NULL DEFAULT 0,
            repetition_ratio REAL NOT NULL DEFAULT 0,
            filler_ratio REAL NOT NULL DEFAULT 0,
            coherence REAL NOT NULL DEFAULT 0,
            completeness REAL NOT NULL DEFAULT 0,
            quality REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            mime_type TEXT NOT NULL DEFAULT '',
            silence_ratio REAL NOT NULL DEFAULT 0,
            pause_count INTEGER NOT NULL DEFAULT 0,
            rms REAL NOT NULL DEFAULT 0,
            peak REAL NOT NULL DEFAULT 0,
            longest_pause_ms INTEGER NOT NULL DEFAULT 0,
            speech_segments INTEGER NOT NULL DEFAULT 0,
            zero_crossing_rate REAL NOT NULL DEFAULT 0,
            response_latency_ms INTEGER NOT NULL DEFAULT 0,
            asr_provider TEXT NOT NULL DEFAULT '',
            analysis_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cognitive_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'watch',
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            acknowledged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cognitive_daily_metrics (
            user_id TEXT NOT NULL,
            day TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            lexical_diversity REAL NOT NULL DEFAULT 0,
            repetition_ratio REAL NOT NULL DEFAULT 0,
            filler_ratio REAL NOT NULL DEFAULT 0,
            coherence REAL NOT NULL DEFAULT 0,
            completeness REAL NOT NULL DEFAULT 0,
            quality REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, day)
        );

        CREATE TABLE IF NOT EXISTS memory_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            photo_id INTEGER NOT NULL DEFAULT 0,
            song_id TEXT NOT NULL DEFAULT '',
            narration TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            voice_session_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'storyboard',
            video_job_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            video_provider TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS memory_embeddings (
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            document_id TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            vector TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, kind, document_id, model)
        );

        CREATE INDEX IF NOT EXISTS idx_language_samples_user_time
        ON language_samples(user_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_cognitive_daily_user_day
        ON cognitive_daily_metrics(user_id, day);

        CREATE INDEX IF NOT EXISTS idx_facts_user_key
        ON facts(user_id, key);
        """
    )
    conn.commit()
    _ensure_columns(conn)
    _seed_if_empty(conn)
    _seed_chapters(conn)
    _seed_accounts(conn)
    _seed_reminders(conn)
    _seed_consent(conn)
    _backfill_cognitive_daily(conn)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    account_cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if "family_link_code" not in account_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN family_link_code TEXT NOT NULL DEFAULT ''")
    session_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "expires_at" not in session_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")
    # Tokens from older releases were stored in plaintext.  They cannot be
    # migrated safely to the new digest format, so invalidate them once.
    conn.execute("DELETE FROM sessions WHERE expires_at='' ")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(paintings)")}
    if "from_name" not in cols:
        conn.execute("ALTER TABLE paintings ADD COLUMN from_name TEXT NOT NULL DEFAULT ''")
    if "dedication" not in cols:
        conn.execute("ALTER TABLE paintings ADD COLUMN dedication TEXT NOT NULL DEFAULT ''")
    voice_cols = {row[1] for row in conn.execute("PRAGMA table_info(voice_sessions)")}
    for name, sql_type in (
        ("silence_ratio", "REAL NOT NULL DEFAULT 0"),
        ("pause_count", "INTEGER NOT NULL DEFAULT 0"),
        ("rms", "REAL NOT NULL DEFAULT 0"),
        ("peak", "REAL NOT NULL DEFAULT 0"),
        ("longest_pause_ms", "INTEGER NOT NULL DEFAULT 0"),
        ("speech_segments", "INTEGER NOT NULL DEFAULT 0"),
        ("zero_crossing_rate", "REAL NOT NULL DEFAULT 0"),
        ("response_latency_ms", "INTEGER NOT NULL DEFAULT 0"),
        ("asr_provider", "TEXT NOT NULL DEFAULT ''"),
        ("analysis_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in voice_cols:
            conn.execute("ALTER TABLE voice_sessions ADD COLUMN %s %s" % (name, sql_type))
    project_cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_projects)")}
    if "voice_session_id" not in project_cols:
        conn.execute("ALTER TABLE memory_projects ADD COLUMN voice_session_id INTEGER NOT NULL DEFAULT 0")
    for name, sql_type in (
        ("video_job_id", "TEXT NOT NULL DEFAULT ''"),
        ("video_url", "TEXT NOT NULL DEFAULT ''"),
        ("video_provider", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in project_cols:
            conn.execute("ALTER TABLE memory_projects ADD COLUMN %s %s" % (name, sql_type))
    photo_cols = {row[1] for row in conn.execute("PRAGMA table_info(photos)")}
    for name in ("ai_description", "ai_provider"):
        if name not in photo_cols:
            conn.execute("ALTER TABLE photos ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % name)
    profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(profile)")}
    if "photo" not in profile_cols:
        conn.execute("ALTER TABLE profile ADD COLUMN photo TEXT NOT NULL DEFAULT ''")
    people_cols = {row[1] for row in conn.execute("PRAGMA table_info(people)")}
    if "photo" not in people_cols:
        conn.execute("ALTER TABLE people ADD COLUMN photo TEXT NOT NULL DEFAULT ''")
    conn.commit()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT user_id FROM profile WHERE user_id = 'default'").fetchone()
    if row:
        return
    conn.execute(
        """
        INSERT INTO profile (user_id, display_name, courtesy, hometown, birth_decade, speech_rate)
        VALUES ('default', '王秀兰', '王阿姨', '江苏南通', '1950年代', 0.82)
        """
    )
    conn.executemany(
        "INSERT INTO people (user_id, relation, name, note) VALUES (?, ?, ?, ?)",
        [
            ("default", "儿子", "小明", "在外地工作"),
            ("default", "孙女", "甜甜", ""),
        ],
    )
    conn.executemany(
        "INSERT INTO facts (user_id, key, value, source) VALUES (?, ?, ?, ?)",
        [
            ("default", "工作", "曾在纺织厂工作二十年", "seed"),
            ("default", "爱好", "喜欢听《茉莉花》", "seed"),
            ("default", "作息", "早上喜欢打太极", "seed"),
        ],
    )
    conn.commit()


def _seed_chapters(conn: sqlite3.Connection) -> None:
    from .content import CHAPTERS

    for item in CHAPTERS:
        conn.execute(
            """
            INSERT OR IGNORE INTO chapters (user_id, chapter_key, title, body, audio_note)
            VALUES ('default', ?, ?, '', '')
            """,
            (item["key"], item["title"]),
        )
    conn.commit()


def _seed_accounts(conn: sqlite3.Connection) -> None:
    if os.getenv("NUANBAN_SEED_DEMO_ACCOUNTS", "").strip() != "1":
        return
    from .auth import hash_password

    row = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()
    if row:
        return
    conn.executemany(
        """
        INSERT INTO accounts (username, password_hash, role, display_name, linked_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("wang", hash_password("1950"), "elder", "王秀兰", "default"),
            ("ming", hash_password("1234"), "family", "小明", "default"),
        ],
    )
    conn.commit()


def _seed_reminders(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM reminders LIMIT 1").fetchone()
    if row:
        return
    conn.executemany(
        "INSERT INTO reminders (user_id, kind, title, note) VALUES (?, ?, ?, ?)",
        [
            ("default", "medicine", "降压药", "早饭后带上，这是自己记下的提醒"),
            ("default", "visit", "下周二复诊", "带病历本，请家人陪着"),
        ],
    )
    conn.commit()


def _seed_consent(conn: sqlite3.Connection) -> None:
    """Keep the original demo usable while making each sensitive scope explicit."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO consent_scopes (user_id, scope, allowed)
        VALUES ('default', ?, ?)
        """,
        [
            ("family_digest", 0),
            ("transcript_analysis", 1),
            ("audio_storage", 0),
            ("family_cognition", 0),
            ("family_care_view", 0),
            ("family_care_edit", 0),
            ("family_reminders", 0),
            ("voice_personalization", 0),
            ("voice_analysis", 0),
            ("photo_analysis", 0),
            ("memory_video", 1),
            ("external_memory_ai", 0),
            ("cloud_conversation", 0),
            ("cloud_image_processing", 0),
            ("cloud_voice_processing", 0),
            ("cloud_video_processing", 0),
            ("research_cognition_model", 0),
        ],
    )
    conn.commit()


def _backfill_cognitive_daily(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO cognitive_daily_metrics (
            user_id, day, sample_count, lexical_diversity, repetition_ratio,
            filler_ratio, coherence, completeness, quality, updated_at
        )
        SELECT user_id, substr(created_at, 1, 10), COUNT(*),
               AVG(lexical_diversity), AVG(repetition_ratio), AVG(filler_ratio),
               AVG(coherence), AVG(completeness), AVG(quality), CURRENT_TIMESTAMP
        FROM language_samples
        WHERE quality>=0.6
        GROUP BY user_id, substr(created_at, 1, 10)
        """
    )
    conn.commit()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in rows]
