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
    db.execute("PRAGMA journal_mode=WAL")  # 并发读写友好
    return db


def init():
    """建表（首次运行）。"""
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
    db.commit()
    db.close()


def insert(screen_summary: str, comment: str, category: str):
    """写入一条对话记录。"""
    now = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    db = _connect()
    db.execute(
        "INSERT INTO conversations (date, screen_summary, comment, category, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (today, screen_summary, comment, category, now),
    )
    db.commit()
    db.close()


def get_today() -> list[Conversation]:
    """查询今天的对话记录。"""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    db = _connect()
    rows = db.execute(
        "SELECT date, screen_summary, comment, category, created_at "
        "FROM conversations WHERE date = ? ORDER BY created_at",
        (today,),
    ).fetchall()
    db.close()
    return [Conversation(*r) for r in rows]
