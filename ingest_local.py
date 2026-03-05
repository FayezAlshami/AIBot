# -*- coding: utf-8 -*-
"""
فهرسة الملفات الموضوعة مباشرة في مجلد قاعدة المعرفة.
ضع الملفات (PDF، Word، صور) في مجلد knowledge_base/raw ثم شغّل:
  python ingest_local.py
"""

import sys
import os

# جعل الجذر هو مجلد المشروع
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db
from knowledge_base import ingest_local_folder
from config import KNOWLEDGE_RAW


def main():
    init_db()
    added, skipped, errors = ingest_local_folder(KNOWLEDGE_RAW)
    print(f"✅ تمت الإضافة: {added} ملف")
    print(f"⏭️ متخطى (موجود مسبقاً): {skipped} ملف")
    if errors:
        print("❌ أخطاء:")
        for e in errors:
            print(f"   • {e}")
    if added == 0 and skipped == 0 and not errors:
        print("لا توجد ملفات جديدة في", KNOWLEDGE_RAW)


if __name__ == "__main__":
    main()
