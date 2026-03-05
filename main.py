# -*- coding: utf-8 -*-
"""
بوت فايز — أرشفة صامتة + مساعد أكاديمي (RAG)
تشغيل: ضع TELEGRAM_BOT_TOKEN و GEMINI_API_KEYS في .env أو بيئة النظام ثم نفّذ:
  python main.py
"""

import os
import sys

# تحميل .env إن وُجد
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import BOT_TOKEN
from database import init_db
from bot_handlers import register_handlers
import telebot


def main():
    if not BOT_TOKEN:
        print("❌ غيّر TELEGRAM_BOT_TOKEN في ملف .env أو متغير البيئة.")
        sys.exit(1)
    init_db()
    bot = telebot.TeleBot(BOT_TOKEN)
    register_handlers(bot)
    print("✅ البوت يعمل. (تذكير: عطّل وضع الخصوصية من @BotFather لقراءة كل الرسائل)")
    bot.infinity_polling()


if __name__ == "__main__":
    main()
