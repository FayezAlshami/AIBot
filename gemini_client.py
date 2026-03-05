# -*- coding: utf-8 -*-
"""عميل Gemini مع تدوير المفاتيح (Key Rotation) ومعالجة 429/5xx."""

import json
import time
import re
from typing import List, Optional, Any

from google import genai
from google.genai import types

from config import get_gemini_api_keys, GEMINI_MODEL

# تدوير المفاتيح
_keys: List[str] = []
_current_index = 0
_cooldown_until: float = 0
COOLDOWN_SECONDS = 60


def _ensure_keys():
    global _keys
    if not _keys:
        _keys = get_gemini_api_keys()


def _current_key() -> Optional[str]:
    _ensure_keys()
    if not _keys:
        return None
    return _keys[_current_index % len(_keys)]


def _rotate_key():
    global _current_index
    _current_index = (_current_index + 1) % len(_keys)
    global _cooldown_until
    _cooldown_until = time.time() + COOLDOWN_SECONDS


def _in_cooldown() -> bool:
    return time.time() < _cooldown_until


def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "resource exhausted" in msg or "quota" in msg


def _is_server_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "500" in msg or "502" in msg or "503" in msg


def generate_rag_answer(context: str, question: str) -> Optional[dict]:
    """
    استدعاء Gemini مع الـ Context والسؤال وإرجاع JSON.
    إذا فشلت كل المفاتيح أو لم يوجد مفتاح: نرجع None.
    """
    _ensure_keys()
    if not _keys:
        return None

    system_instruction = """أنت "فايز"، مساعد أكاديمي لطلاب الجامعة في مجموعة تيليجرام.
قواعد إلزامية صارمة:
1. ستتلقى "مقتطفات مرجعية" (Context) وسؤالاً من الطالب.
2. يجب أن تبني إجابتك *حصراً* وبشكل مطلق على المقتطفات المقدمة.
3. يُمنع منعاً باتاً إضافة أي معلومات من خارج المقتطفات (لا تهلوس).
4. إذا لم تحتوي المقتطفات على إجابة كافية، يجب أن تكون قيمة 'found' في الـ JSON هي false، واترك حقل الإجابة فارغاً.
5. الإجابة يجب أن تكون دقيقة، مختصرة، ومباشرة.
أرجع JSON فقط بالشكل:
{"found": true أو false, "answer": "الإجابة هنا أو فارغ", "citations": [{"file_name": "...", "page_or_section": "...", "exact_quote": "..."}]}"""

    user_content = f"""المقتطفات المرجعية:
---
{context}
---

سؤال الطالب: {question}

أرجع JSON فقط بدون markdown أو شرح إضافي."""

    json_schema = {
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_name": {"type": "string"},
                        "page_or_section": {"type": "string"},
                        "exact_quote": {"type": "string"},
                    },
                },
            },
        },
        "required": ["found", "answer", "citations"],
    }

    last_error = None
    attempt = 0
    max_attempts = len(_keys) * 2 + 3  # عدة محاولات مع تدوير

    while attempt < max_attempts:
        key = _current_key()
        if not key:
            break
        if _in_cooldown() and _current_index > 0:
            time.sleep(min(5, COOLDOWN_SECONDS - (time.time() - _cooldown_until)))
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=json_schema,
                    temperature=0.2,
                    max_output_tokens=1024,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                return {"found": False, "answer": "", "citations": []}
            # إزالة markdown code block إن وجد
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```\s*$", "", text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            # محاولة استخراج كائن JSON من النص
            try:
                m = re.search(r"\{[\s\S]*\}", text)
                if m:
                    return json.loads(m.group())
            except Exception:
                pass
            attempt += 1
            continue
        except Exception as e:
            last_error = e
            if _is_rate_limit(e):
                _rotate_key()
                attempt += 1
                continue
            if _is_server_error(e):
                time.sleep(2 ** min(attempt, 5))  # exponential backoff
                attempt += 1
                continue
            raise
        attempt += 1

    return None


def extract_text_from_image(image_path: str) -> Optional[str]:
    """استخراج النص من صورة باستخدام Gemini Vision (مرة واحدة عند الرفع)."""
    _ensure_keys()
    if not _keys:
        return None
    key = _current_key()
    try:
        from pathlib import Path
        import base64
        path = Path(image_path)
        if not path.exists():
            return None
        # رفع الصورة كـ inline data
        with open(path, "rb") as f:
            data = f.read()
        b64 = base64.standard_b64encode(data).decode("utf-8")
        mime = "image/jpeg"
        if path.suffix.lower() in (".png",):
            mime = "image/png"
        elif path.suffix.lower() in (".webp",):
            mime = "image/webp"
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=data, mime_type=mime),
                types.Part.from_text("استخرج كل النص الظاهر في هذه الصورة. أرجع النص فقط بدون تعليق."),
            ],
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=4096),
        )
        return (response.text or "").strip()
    except Exception as e:
        if _is_rate_limit(e):
            _rotate_key()
        return None
