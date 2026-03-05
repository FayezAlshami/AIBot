# -*- coding: utf-8 -*-
"""أرشفة الرسائل بصمت: نص، صورة، مستند مع حد 20MB."""

import os
import re
from datetime import datetime
from pathlib import Path

from database import get_connection
from config import ARCHIVE_ROOT, TELEGRAM_FILE_SIZE_LIMIT_BYTES


def archive_path_for_chat(chat_id: int) -> Path:
    """مسار مجلد أرشيف اليوم للمجموعة."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    folder = ARCHIVE_ROOT / str(chat_id) / today
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_filename(name: str) -> str:
    """تنظيف اسم الملف من أحرف غير آمنة."""
    if not name or not name.strip():
        return "file"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip() or "file"


def insert_message(
    chat_id: int,
    message_id: int,
    user_id: int,
    username: str,
    content_type: str,
    text_content: str = None,
    file_id: str = None,
    file_unique_id: str = None,
    file_name: str = None,
    mime_type: str = None,
    file_size: int = None,
    local_path: str = None,
    download_status: str = None,
):
    """إدراج سجل رسالة في جدول messages."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (
                chat_id, message_id, user_id, username, content_type,
                text_content, file_id, file_unique_id, file_name, mime_type,
                file_size, local_path, download_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                user_id,
                username,
                content_type,
                text_content,
                file_id,
                file_unique_id,
                file_name,
                mime_type,
                file_size,
                local_path,
                download_status,
            ),
        )


def archive_text(chat_id: int, message_id: int, user_id: int, username: str, text: str):
    """أرشفة رسالة نصية فقط."""
    insert_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        username=username or "",
        content_type="text",
        text_content=text or "",
    )


def archive_photo(
    chat_id: int,
    message_id: int,
    user_id: int,
    username: str,
    file_id: str,
    file_unique_id: str,
    caption: str,
    file_size: int,
    bot,
):
    """أرشفة صورة: تنزيل إذا ≤20MB وإلا metadata فقط."""
    status = "skipped_too_large"
    local_path = None
    if file_size is not None and file_size > TELEGRAM_FILE_SIZE_LIMIT_BYTES:
        insert_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username or "",
            content_type="photo",
            text_content=caption or "",
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=None,
            mime_type="image/jpeg",
            file_size=file_size,
            local_path=None,
            download_status=status,
        )
        return
    try:
        folder = archive_path_for_chat(chat_id)
        ext = ".jpg"
        base = file_unique_id or file_id
        path = folder / f"{base}{ext}"
        file_info = bot.get_file(file_id)
        if file_info.file_path:
            data = bot.download_file(file_info.file_path)
            if data:
                path.write_bytes(data)
        if path.exists():
            local_path = str(path)
            status = "ok"
    except Exception:
        status = "failed"
    insert_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        username=username or "",
        content_type="photo",
        text_content=caption or "",
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=None,
        mime_type="image/jpeg",
        file_size=file_size,
        local_path=local_path,
        download_status=status,
    )


def archive_document(
    chat_id: int,
    message_id: int,
    user_id: int,
    username: str,
    file_id: str,
    file_unique_id: str,
    file_name: str,
    mime_type: str,
    file_size: int,
    caption: str,
    bot,
):
    """أرشفة مستند: تنزيل إذا ≤20MB وإلا metadata فقط."""
    status = "skipped_too_large"
    local_path = None
    if file_size is not None and file_size > TELEGRAM_FILE_SIZE_LIMIT_BYTES:
        insert_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username or "",
            content_type="document",
            text_content=caption or "",
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
            mime_type=mime_type or "",
            file_size=file_size,
            local_path=None,
            download_status=status,
        )
        return
    try:
        folder = archive_path_for_chat(chat_id)
        name = safe_filename(file_name) if file_name else f"{file_unique_id or file_id}.bin"
        path = folder / name
        file_info = bot.get_file(file_id)
        if file_info.file_path:
            data = bot.download_file(file_info.file_path)
            if data:
                path.write_bytes(data)
        if path.exists():
            local_path = str(path)
            status = "ok"
    except Exception:
        status = "failed"
    insert_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        username=username or "",
        content_type="document",
        text_content=caption or "",
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        mime_type=mime_type or "",
        file_size=file_size,
        local_path=local_path,
        download_status=status,
    )


def get_archive_stats():
    """عدد الرسائل المؤرشفة وعدد المراجع النشطة ومساحة التخزين (تقريبية)."""
    with get_connection() as conn:
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        kb_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_base_files WHERE is_active = 1"
        ).fetchone()[0]
    total_size = 0
    for root, dirs, files in os.walk(ARCHIVE_ROOT):
        for f in files:
            p = Path(root) / f
            try:
                total_size += p.stat().st_size
            except OSError:
                pass
    kb_root = Path(__file__).resolve().parent / "knowledge_base" / "raw"
    for p in kb_root.rglob("*"):
        if p.is_file():
            try:
                total_size += p.stat().st_size
            except OSError:
                pass
    return msg_count, kb_count, total_size
