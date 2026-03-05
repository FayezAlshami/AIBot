# -*- coding: utf-8 -*-
"""عميل Gemini باستخدام google.generativeai (نفس المثال: configure + GenerativeModel + gemini-flash-latest)."""

import json
import time
import re
from typing import List, Optional

import google.generativeai as genai

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


def _get_model(api_key: str):
    """نفس أسلوب المثال: configure ثم GenerativeModel."""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def generate_rag_answer(context: str, question: str) -> Optional[dict]:
    """
    استدعاء Gemini مع Context والسؤال (طلب خفيف: prompt قصير، رد قصير).
    عند 429 ننتظر ~30 ثانية ثم نعيد المحاولة.
    """
    _ensure_keys()
    if not _keys:
        return None

    # prompt قصير جداً لتقليل الرموز
    prompt = f"""أجب من النص فقط. إن لم تجد إجابة أرجع found:false وanswer:"".
النص:
{context}

س: {question}
أرجع JSON فقط: {{"found":true/false,"answer":"...","citations":[]}}"""

    text = ""
    attempt = 0
    # محاولات أكثر مع انتظار عند 429 (حتى 5 محاولات مع انتظار 30s)
    max_attempts = max(len(_keys) * 2 + 2, 5)

    while attempt < max_attempts:
        key = _current_key()
        if not key:
            break
        if _in_cooldown() and _current_index > 0:
            time.sleep(min(10, COOLDOWN_SECONDS - (time.time() - _cooldown_until)))
        try:
            model = _get_model(key)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 512,
                },
            )
            text = (response.text or "").strip()
            if not text:
                return {"found": False, "answer": "", "citations": []}
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```\s*$", "", text)
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                m = re.search(r"\{[\s\S]*\}", text)
                if m:
                    return json.loads(m.group())
            except Exception:
                pass
            attempt += 1
            continue
        except Exception as e:
            if _is_rate_limit(e):
                # انتظار ثم إعادة محاولة (الخطأ يقول retry after ~26s)
                time.sleep(30)
                _rotate_key()
                attempt += 1
                continue
            if _is_server_error(e):
                time.sleep(2 ** min(attempt, 4))
                attempt += 1
                continue
            raise
        attempt += 1

    return None


def extract_text_from_image(image_path: str) -> Optional[str]:
    """استخراج النص من صورة باستخدام Gemini Vision (نفس المثال: GenerativeModel)."""
    _ensure_keys()
    if not _keys:
        return None
    key = _current_key()
    try:
        from pathlib import Path
        from PIL import Image
        path = Path(image_path)
        if not path.exists():
            return None
        img = Image.open(path)
        model = _get_model(key)
        response = model.generate_content(
            [img, "استخرج كل النص الظاهر في هذه الصورة. أرجع النص فقط بدون تعليق."],
            generation_config={"temperature": 0, "max_output_tokens": 4096},
        )
        return (response.text or "").strip()
    except Exception as e:
        if _is_rate_limit(e):
            _rotate_key()
        return None
