# -*- coding: utf-8 -*-
"""إعدادات المشروع - بوت فايز (الأرشفة والمساعد الأكاديمي)."""

import os
from pathlib import Path

# المسارات
BASE_DIR = Path(__file__).resolve().parent
ARCHIVE_ROOT = BASE_DIR / "archive"
KNOWLEDGE_RAW = BASE_DIR / "knowledge_base" / "raw"
DB_PATH = BASE_DIR / "fayez_bot.db"

# تيليجرام
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_USER_ID = 5049749756  # المدير الوحيد لإدارة المراجع
# المجموعة الوحيدة التي يعمل فيها البوت (أرشفة + أوامر). غيّر عبر ALLOWED_CHAT_ID في .env أو اتركه للافتراضي.
_raw_chat = os.environ.get("ALLOWED_CHAT_ID", "-1003457683038")
ALLOWED_CHAT_ID = int(_raw_chat.strip()) if _raw_chat and str(_raw_chat).strip() else -1003457683038

# حدود الملفات (تيليجرام للبوتات)
TELEGRAM_FILE_SIZE_LIMIT_MB = 20
TELEGRAM_FILE_SIZE_LIMIT_BYTES = TELEGRAM_FILE_SIZE_LIMIT_MB * 1024 * 1024

# مفاتيح API - من متغير بيئة مفصولة بفاصلة (للتدوير)
# مثال: GEMINI_API_KEYS=key1,key2,key3
def get_gemini_api_keys():
    raw = os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY", ""))
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]

# RAG
CHUNK_SIZE_WORDS = 500
CHUNK_OVERLAP_WORDS = 50
TOP_K_RESULTS = 5

# صيغ الملفات المقبولة لقاعدة المعرفة
ALLOWED_KB_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_KB_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".gif"}

# موديل Gemini (من قائمة الحساب)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
