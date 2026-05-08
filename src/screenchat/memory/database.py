import os
import sqlite3
from datetime import datetime, timezone

from screenchat.memory.models import Conversation

DB_PATH = os.path.expanduser("~/.screenchat/history.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _connect():
    _ensure_dir()
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init():
    db = _connect()
    db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            screen_summary  TEXT DEFAULT '',
            comment         TEXT NOT NULL,
            category        TEXT DEFAULT '',
            created_at      TEXT NOT NULL
        )
    """)
    # 新增 role 列（兼容旧表）
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN role TEXT DEFAULT 'assistant'")
    except sqlite3.OperationalError:
        pass  # 列已存在
    for stmt in (
        "ALTER TABLE conversations ADD COLUMN event_type TEXT DEFAULT 'message'",
        "ALTER TABLE conversations ADD COLUMN coaching_state TEXT DEFAULT ''",
        "ALTER TABLE conversations ADD COLUMN target_relevance TEXT DEFAULT ''",
        "ALTER TABLE conversations ADD COLUMN suggested_action TEXT DEFAULT ''",
        "ALTER TABLE conversations ADD COLUMN target_goal TEXT DEFAULT ''",
        "ALTER TABLE conversations ADD COLUMN goal_type TEXT DEFAULT ''",
        "ALTER TABLE conversations ADD COLUMN intensity TEXT DEFAULT ''",
    ):
        try:
            db.execute(stmt)
        except sqlite3.OperationalError:
            pass
    db.commit()
    db.close()


def insert(screen_summary: str, comment: str, category: str, role: str = "assistant"):
    now = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    db = _connect()
    db.execute(
        "INSERT INTO conversations (date, screen_summary, comment, category, created_at, role) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (today, screen_summary, comment, category, now, role),
    )
    db.commit()
    db.close()


def insert_coaching_event(
    event_type: str,
    comment: str,
    *,
    screen_summary: str = "",
    coaching_state: str = "",
    target_relevance: str = "",
    suggested_action: str = "",
    target_goal: str = "",
    goal_type: str = "",
    intensity: str = "",
):
    now = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    db = _connect()
    db.execute(
        "INSERT INTO conversations (date, screen_summary, comment, category, created_at, role, "
        "event_type, coaching_state, target_relevance, suggested_action, target_goal, goal_type, intensity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            today,
            screen_summary,
            comment,
            "coaching",
            now,
            "assistant",
            event_type,
            coaching_state,
            target_relevance,
            suggested_action,
            target_goal,
            goal_type,
            intensity,
        ),
    )
    db.commit()
    db.close()


def get_today() -> list[Conversation]:
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    db = _connect()
    try:
        rows = db.execute(
            "SELECT date, screen_summary, comment, category, created_at, role, "
            "event_type, coaching_state, target_relevance, suggested_action, target_goal, goal_type, intensity "
            "FROM conversations WHERE date = ? ORDER BY created_at",
            (today,),
        ).fetchall()
    except sqlite3.OperationalError:
        try:
            rows = db.execute(
                "SELECT date, screen_summary, comment, category, created_at, role "
                "FROM conversations WHERE date = ? ORDER BY created_at",
                (today,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = db.execute(
                "SELECT date, screen_summary, comment, category, created_at "
                "FROM conversations WHERE date = ? ORDER BY created_at",
                (today,),
            ).fetchall()
    db.close()
    return [Conversation(*r) for r in rows]
