# -*- coding: utf-8 -*-
"""تهيئة SQLite وجداول الأرشفة وقاعدة المعرفة و FTS5."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from config import DB_PATH, KNOWLEDGE_RAW, ARCHIVE_ROOT

SCHEMA_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    message_id INTEGER,
    user_id INTEGER,
    username TEXT,
    content_type TEXT,
    text_content TEXT,
    file_id TEXT,
    file_unique_id TEXT,
    file_name TEXT,
    mime_type TEXT,
    file_size INTEGER,
    local_path TEXT,
    download_status TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_chat_timestamp ON messages(chat_id, timestamp);
"""

SCHEMA_KNOWLEDGE_FILES = """
CREATE TABLE IF NOT EXISTS knowledge_base_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    local_path TEXT,
    mime_type TEXT,
    file_size INTEGER,
    sha256_hash TEXT UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);
"""

# FTS5 virtual table - يجب أن لا يكون لها IF NOT EXISTS بنفس الصيغة، نتحقق يدوياً
SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
    file_id UNINDEXED,
    page_number UNINDEXED,
    chunk_text,
    tokenize='unicode61'
);
"""


def ensure_dirs():
    """إنشاء مجلدات الأرشيف وقاعدة المعرفة."""
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_RAW.mkdir(parents=True, exist_ok=True)


def init_db():
    """إنشاء/تهيئة قاعدة البيانات والجداول."""
    ensure_dirs()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_MESSAGES)
    conn.executescript(SCHEMA_KNOWLEDGE_FILES)
    conn.execute(SCHEMA_FTS)
    conn.commit()
    conn.close()


@contextmanager
def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cursor():
    """للاستخدام مع with get_connection() as conn ثم conn.cursor()."""
    return get_connection()
