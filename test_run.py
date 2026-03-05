# -*- coding: utf-8 -*-
"""
سكربت تجربة المشروع من التيرمينال قبل استخدام البوت في تيليجرام.
يكشف سبب رسالة "أواجه ضغطاً في معالجة البيانات" (فشل Gemini أو عدم وجود مفتاح).
شغّل من مجلد AIBot:  python test_run.py
"""

import os
import sys

# جذر المشروع = مجلد AIBot
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

# تحميل .env من مجلد AIBot أو من المجلد الحالي
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(_script_dir, ".env"))
except ImportError:
    pass


def step_env():
    """التحقق من المتغيرات والمفاتيح."""
    print("\n=== 1) البيئة والمفاتيح ===")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    keys_raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    print(f"  TELEGRAM_BOT_TOKEN: {'✓ معرّف' if token else '✗ غير معرّف'}")
    print(f"  GEMINI_API_KEYS:   {len(keys)} مفتاح")
    print(f"  GEMINI_MODEL:      {model}")
    if not keys:
        print("\n  ❌ لا يوجد مفتاح Gemini. أضف GEMINI_API_KEYS أو GEMINI_API_KEY في .env")
        return False
    return True


def step_db():
    """التحقق من قاعدة البيانات والبحث."""
    print("\n=== 2) قاعدة البيانات وقاعدة المعرفة ===")
    try:
        from database import init_db
        from knowledge_base import search_chunks, list_knowledge_files
        init_db()
        files = list_knowledge_files()
        print(f"  المراجع النشطة: {len(files)} ملف")
        if files:
            chunks = search_chunks("اختبار", top_k=2)
            print(f"  بحث 'اختبار': {len(chunks)} مقطع")
        return True
    except Exception as e:
        print(f"  ❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_gemini_raw():
    """استدعاء Gemini مباشرة (نفس المثال: configure + GenerativeModel)."""
    print("\n=== 3) اتصال Gemini (استدعاء بسيط) ===")
    from config import get_gemini_api_keys, GEMINI_MODEL
    import google.generativeai as genai
    keys = get_gemini_api_keys()
    if not keys:
        print("  ❌ لا توجد مفاتيح. تخطي.")
        return None
    key = keys[0]
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content("قل مرحبا بجملة واحدة.")
        text = (response.text or "").strip()
        print(f"  ✓ الرد: {text[:200]}")
        return True
    except Exception as e:
        print(f"  ❌ خطأ Gemini:")
        print(f"     نوع: {type(e).__name__}")
        print(f"     رسالة: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_rag_full():
    """تشغيل RAG كامل (بحث + Gemini) كما في البوت."""
    print("\n=== 4) RAG كامل (بحث + Gemini) ===")
    try:
        from database import init_db
        from rag import answer_question
        init_db()
        question = "ما هو هذا الموضوع؟"  # سؤال عام لاختبار
        print(f"  السؤال: {question}")
        reply = answer_question(question)
        print(f"  رد البوت: {reply[:300]}..." if len(reply) > 300 else f"  رد البوت: {reply}")
        if "ضغطاً" in reply or "ضغطا" in reply:
            print("\n  ⚠ لا يزال يرد برسالة الضغط → السبب غالباً من Gemini (انظر الخطوة 3).")
        return True
    except Exception as e:
        print(f"  ❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("تشغيل اختبار المشروع (بوت فايز)")
    if not step_env():
        sys.exit(1)
    step_db()
    # الخطوة 3 تكشف سبب فشل Gemini (مفتاح خاطئ، موديل غير متوفر، حصة، إلخ)
    ok = step_gemini_raw()
    if not ok:
        print("\n  💡 راجع الخطأ أعلاه: مفتاح صحيح؟ اسم الموديل متوفر في حسابك؟ (مثلاً gemini-2.0-flash)")
        sys.exit(1)
    step_rag_full()
    print("\n=== انتهى الاختبار ===")


if __name__ == "__main__":
    main()
