# -*- coding: utf-8 -*-
"""RAG: بحث FTS5 + تجميع السياق + استدعاء Gemini وتنسيق الرد."""

import re
from typing import Optional

from config import TOP_K_RESULTS
from knowledge_base import search_chunks
from gemini_client import generate_rag_answer

NO_ANSWER_MSG = "عذراً، لا تتوفر معلومات حول هذا السؤال في الملفات المرجعية لدي."
BUSY_MSG = "عذراً، أواجه ضغطاً في معالجة البيانات حالياً. يرجى المحاولة بعد قليل."


def _keywords(query: str) -> str:
    """تنظيف السؤال واستخراج كلمات للبحث (إزالة علامات ترقيم زائدة)."""
    q = re.sub(r"[^\w\s\u0600-\u06FF]", " ", query)
    return " ".join(q.split())


def answer_question(question: str) -> str:
    """
    تنفيذ RAG: بحث → سياق → Gemini → تنسيق رسالة تيليجرام.
    يُرجع النص الجاهز للإرسال للمستخدم.
    """
    question = (question or "").strip()
    if not question:
        return NO_ANSWER_MSG
    keywords = _keywords(question)
    if not keywords:
        return NO_ANSWER_MSG
    chunks = search_chunks(keywords, top_k=TOP_K_RESULTS)
    if not chunks:
        return NO_ANSWER_MSG
    context_parts = []
    for c in chunks:
        context_parts.append(
            f"[{c['file_name']} - {c['page_number']}]\n{c['chunk_text']}"
        )
    context = "\n\n---\n\n".join(context_parts)
    result = generate_rag_answer(context, question)
    if result is None:
        return BUSY_MSG
    if not result.get("found"):
        return NO_ANSWER_MSG
    answer = (result.get("answer") or "").strip()
    citations = result.get("citations") or []
    if not answer:
        return NO_ANSWER_MSG
    lines = [answer]
    if citations:
        lines.append("")
        lines.append("📎 المصادر:")
        for i, cit in enumerate(citations, 1):
            fname = cit.get("file_name", "?")
            page = cit.get("page_or_section", "?")
            quote = (cit.get("exact_quote") or "")[:100]
            if quote:
                lines.append(f"{i}. {fname} ({page}): «{quote}...»")
            else:
                lines.append(f"{i}. {fname} ({page})")
    return "\n".join(lines)
