# -*- coding: utf-8 -*-
"""معالجات البوت: أرشفة، أوامر، قاعدة معرفة، RAG."""

import re
from pathlib import Path
from typing import Optional

import telebot
from telebot import types as tb_types

from config import (
    ADMIN_USER_ID,
    ALLOWED_CHAT_ID,
    KNOWLEDGE_RAW,
    ALLOWED_KB_MIMES,
    ALLOWED_KB_EXTENSIONS,
    TELEGRAM_FILE_SIZE_LIMIT_BYTES,
    TELEGRAM_FILE_SIZE_LIMIT_MB,
)
from database import init_db
from archive import (
    archive_text,
    archive_photo,
    archive_document,
    get_archive_stats,
)
from knowledge_base import add_knowledge_file, list_knowledge_files, remove_knowledge_file
from rag import answer_question

# حالة المستخدم: {user_id: "waiting_for_file" | None}
_user_state: dict[int, Optional[str]] = {}


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


def _admin_only_decorator(bot: telebot.TeleBot):
    def decorator(func):
        def wrapper(message: tb_types.Message):
            if not is_admin(message.from_user.id):
                bot.reply_to(message, "هذا الأمر متاح للمدير فقط.")
                return
            return func(message)
        return wrapper
    return decorator


def _allowed_chat_only(bot: telebot.TeleBot):
    """يتجاهل الرسائل من أي دردشة غير المجموعة المحددة؛ للأوامر يرد برسالة توضيحية."""
    def decorator(func):
        def wrapper(message: tb_types.Message):
            if message.chat.id != ALLOWED_CHAT_ID:
                bot.reply_to(message, "هذا البوت يعمل فقط في المجموعة المحددة.")
                return
            return func(message)
        return wrapper
    return decorator


def set_state(user_id: int, state: Optional[str]):
    _user_state[user_id] = state


def get_state(user_id: int) -> Optional[str]:
    return _user_state.get(user_id)


def safe_filename_from_telegram(name: str, file_id: str) -> str:
    if not name or not name.strip():
        return f"{file_id}.bin"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip() or f"{file_id}.bin"


def register_handlers(bot: telebot.TeleBot):
    """تسجيل كل المعالجات."""
    admin_only = _admin_only_decorator(bot)
    allowed_chat = _allowed_chat_only(bot)

    # —— أوامر أولاً (قبل النص العام) ——
    # —— /chat ——
    @bot.message_handler(commands=["chat"])
    @allowed_chat
    def cmd_chat(message: tb_types.Message):
        text = (message.text or "").strip()
        rest = text[len("/chat"):].strip()
        if not rest:
            bot.reply_to(message, "استخدم: /chat ثم اكتب سؤالك.\nمثال: /chat ما هو تعريف X؟")
            return
        reply = answer_question(rest)
        bot.reply_to(message, reply)

    # —— /privacy ——
    @bot.message_handler(commands=["privacy"])
    @allowed_chat
    def cmd_privacy(message: tb_types.Message):
        msg = (
            "🔒 الخصوصية:\n\n"
            "هذا البوت يرشف محادثات المجموعة لغايات أكاديمية بحتة (تحسين المساعد والمراجع). "
            "لا يتم مشاركة المحتوى مع أطراف خارجية. الأرشفة تتم بصمت ولا يرسل البوت أي تأكيد عند التسجيل."
        )
        bot.reply_to(message, msg)

    # —— أدمن: /file ——
    @bot.message_handler(commands=["file"])
    @allowed_chat
    @admin_only
    def cmd_file(message: tb_types.Message):
        set_state(message.from_user.id, "waiting_for_file")
        bot.reply_to(
            message,
            "أرسل الآن الملف (PDF، Word، أو صورة) لإضافته إلى قاعدة المعرفة. "
            "الحد الأقصى 20 ميجابايت. لإلغاء الأمر أرسل /cancel",
        )

    @bot.message_handler(commands=["cancel"])
    @allowed_chat
    def _cmd_cancel(message: tb_types.Message):
        if message.from_user and get_state(message.from_user.id):
            set_state(message.from_user.id, None)
            bot.reply_to(message, "تم الإلغاء.")

    # معالجة الملف المرسل من الآدمن (عند انتظار /file) — تسجيل قبل document/photo العام
    @bot.message_handler(content_types=["document"], func=lambda m: m.chat.id == ALLOWED_CHAT_ID and m.from_user and get_state(m.from_user.id) == "waiting_for_file")
    def on_document_admin(message: tb_types.Message):
        doc = message.document
        if not doc:
            return
        handle_admin_file(
            message, bot,
            doc.file_id,
            doc.file_name or "",
            doc.mime_type or "",
            doc.file_size or 0,
            False,
        )

    @bot.message_handler(content_types=["photo"], func=lambda m: m.chat.id == ALLOWED_CHAT_ID and m.from_user and get_state(m.from_user.id) == "waiting_for_file")
    def on_photo_admin(message: tb_types.Message):
        photo = message.photo[-1] if message.photo else None
        if not photo:
            return
        handle_admin_file(
            message, bot,
            photo.file_id,
            None,
            "image/jpeg",
            photo.file_size or 0,
            True,
        )

    # —— أرشفة صامتة (بدون رد) ——
    @bot.message_handler(func=lambda m: m.chat.id == ALLOWED_CHAT_ID, content_types=["text"])
    def on_text(message: tb_types.Message):
        text = (message.text or "").strip()
        if text.startswith("/"):
            return
        archive_text(
            message.chat.id,
            message.message_id,
            message.from_user.id if message.from_user else 0,
            message.from_user.username if message.from_user else "",
            text,
        )

    @bot.message_handler(content_types=["photo"], func=lambda m: m.chat.id == ALLOWED_CHAT_ID)
    def on_photo(message: tb_types.Message):
        photo = message.photo[-1] if message.photo else None
        if not photo:
            return
        archive_photo(
            message.chat.id,
            message.message_id,
            message.from_user.id if message.from_user else 0,
            message.from_user.username if message.from_user else "",
            photo.file_id,
            photo.file_unique_id,
            message.caption or "",
            photo.file_size,
            bot,
        )

    @bot.message_handler(content_types=["document"], func=lambda m: m.chat.id == ALLOWED_CHAT_ID)
    def on_document(message: tb_types.Message):
        doc = message.document
        if not doc:
            return
        archive_document(
            message.chat.id,
            message.message_id,
            message.from_user.id if message.from_user else 0,
            message.from_user.username if message.from_user else "",
            doc.file_id,
            doc.file_unique_id,
            doc.file_name or "",
            doc.mime_type or "",
            doc.file_size or 0,
            message.caption or "",
            bot,
        )

    def handle_admin_file(message: tb_types.Message, bot_instance: telebot.TeleBot, file_id: str, file_name: str, mime: str, file_size: int, is_photo: bool):
        if not is_admin(message.from_user.id):
            return False
        if get_state(message.from_user.id) != "waiting_for_file":
            return False
        set_state(message.from_user.id, None)
        if file_size > TELEGRAM_FILE_SIZE_LIMIT_BYTES:
            bot_instance.reply_to(
                message,
                f"حجم الملف يتجاوز حد تيليجرام للبوتات ({TELEGRAM_FILE_SIZE_LIMIT_MB}MB).",
            )
            return True
        ext = Path(file_name or "").suffix.lower() if file_name else ""
        if mime and mime not in ALLOWED_KB_MIMES and ext not in ALLOWED_KB_EXTENSIONS:
            bot_instance.reply_to(
                message,
                "صيغة غير مدعومة. المقبولة: PDF، Word (docx)، صور (jpg, png, webp, gif).",
            )
            return True
        try:
            file_info = bot_instance.get_file(file_id)
            safe_name = safe_filename_from_telegram(file_name or "file", file_id)
            local_path = KNOWLEDGE_RAW / safe_name
            data = bot_instance.download_file(file_info.file_path)
            if data:
                local_path.write_bytes(data)
        except Exception as e:
            bot_instance.reply_to(message, f"فشل التنزيل: {e}")
            return True
        fid, err = add_knowledge_file(
            file_name or safe_name,
            str(local_path),
            mime or "application/octet-stream",
            file_size,
        )
        if err:
            bot_instance.reply_to(message, f"تم حفظ الملف لكن: {err}")
        else:
            bot_instance.reply_to(message, f"✅ تمت إضافة الملف إلى قاعدة المعرفة (رقم: {fid}).")
        return True

    # —— /files ——
    @bot.message_handler(commands=["files"])
    @allowed_chat
    @admin_only
    def cmd_files(message: tb_types.Message):
        files = list_knowledge_files()
        if not files:
            bot.reply_to(message, "لا توجد مراجع حالياً.")
            return
        lines = [f"📁 المراجع ({len(files)}):"]
        for f in files:
            size_kb = (f["file_size"] or 0) // 1024
            lines.append(f"  • ID: {f['id']} | {f['file_name']} | {size_kb} KB")
        bot.reply_to(message, "\n".join(lines))

    # —— /remove_file <id> ——
    @bot.message_handler(commands=["remove_file"])
    @allowed_chat
    @admin_only
    def cmd_remove_file(message: tb_types.Message):
        text = (message.text or "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "استخدم: /remove_file <رقم_الملف>")
            return
        try:
            fid = int(parts[1])
        except ValueError:
            bot.reply_to(message, "رقم الملف يجب أن يكون رقماً صحيحاً.")
            return
        if remove_knowledge_file(fid):
            bot.reply_to(message, f"تم حذف الملف رقم {fid}.")
        else:
            bot.reply_to(message, "لم يُعثر على ملف بهذا الرقم.")

    # —— /status ——
    @bot.message_handler(commands=["status"])
    @allowed_chat
    @admin_only
    def cmd_status(message: tb_types.Message):
        msg_count, kb_count, total_bytes = get_archive_stats()
        total_mb = total_bytes / (1024 * 1024)
        bot.reply_to(
            message,
            f"📊 الحالة:\n"
            f"• الرسائل المؤرشفة: {msg_count}\n"
            f"• المراجع النشطة: {kb_count}\n"
            f"• مساحة التخزين: {total_mb:.2f} MB",
        )
