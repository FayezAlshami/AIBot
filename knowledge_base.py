# -*- coding: utf-8 -*-
"""قاعدة المعرفة: استخراج النص، تقطيع، فهرسة FTS5."""

import hashlib
import sqlite3
import re
from pathlib import Path
from typing import List, Tuple, Optional

from database import get_connection
from config import (
    KNOWLEDGE_RAW,
    CHUNK_SIZE_WORDS,
    CHUNK_OVERLAP_WORDS,
    ALLOWED_KB_MIMES,
    ALLOWED_KB_EXTENSIONS,
)
from gemini_client import extract_text_from_image

# ربط امتداد الملف بـ MIME للرفع المباشر من المشروع
EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def sha256_file(path: Path) -> str:
    """حساب SHA256 للملف."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text_pdf(path: Path) -> Optional[str]:
    """استخراج النص من PDF بـ pdfplumber."""
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n\n".join(parts) if parts else None
    except Exception:
        return None


def extract_text_docx(path: Path) -> Optional[str]:
    """استخراج النص من Word بـ python-docx."""
    try:
        from docx import Document
        doc = Document(path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception:
        return None


def extract_text_image(path: Path) -> Optional[str]:
    """استخراج النص من صورة عبر Gemini Vision."""
    return extract_text_from_image(str(path))


def extract_text(local_path: str, mime_type: str) -> Optional[str]:
    """استخراج النص حسب نوع الملف."""
    path = Path(local_path)
    if not path.exists():
        return None
    mime = (mime_type or "").lower()
    ext = path.suffix.lower()
    if "pdf" in mime or ext == ".pdf":
        return extract_text_pdf(path)
    if "wordprocessingml" in mime or "document" in mime or ext == ".docx":
        return extract_text_docx(path)
    if mime.startswith("image/") or ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return extract_text_image(path)
    return None


def word_tokenize_ar_simple(text: str) -> List[str]:
    """تقسيم تقريبي للكلمات (يدعم العربية والفراغات)."""
    if not text:
        return []
    return re.findall(r'\S+', text)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> List[Tuple[str, str]]:
    """
    تقطيع النص إلى أجزاء بالكلمات مع تداخل.
    يُرجع قائمة (نص_الجزء, رقم_الصفحة_أو_المقطع).
    """
    words = word_tokenize_ar_simple(text)
    if not words:
        return []
    step = max(1, chunk_size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        block = words[i : i + chunk_size]
        if not block:
            break
        chunk_str = " ".join(block)
        page_label = f"مقطع {len(chunks) + 1}"
        chunks.append((chunk_str, page_label))
    return chunks


def index_file(file_id: int, full_text: str, file_name: str):
    """إدراج مقاطع النص في FTS5."""
    chunks = chunk_text(full_text)
    with get_connection() as conn:
        for chunk_text_val, page_label in chunks:
            conn.execute(
                """
                INSERT INTO knowledge_chunks_fts (file_id, page_number, chunk_text)
                VALUES (?, ?, ?)
                """,
                (file_id, page_label, chunk_text_val),
            )


def delete_file_chunks(file_id: int):
    """حذف كل مقاطع ملف من FTS5 (حذف السجلات التي تحتوي file_id)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge_chunks_fts WHERE file_id = ?", (file_id,))


def add_knowledge_file(
    file_name: str,
    local_path: str,
    mime_type: str,
    file_size: int,
) -> Tuple[Optional[int], Optional[str]]:
    """
    إضافة ملف لقاعدة المعرفة: استخراج، تقطيع، فهرسة.
    يُرجع (file_id, None) عند النجاح أو (None, "رسالة خطأ").
    عند فشل الاستخراج: يُحفظ السجل بـ is_active=0 ويُرجع (id, "فشل الاستخراج").
    """
    path = Path(local_path)
    if not path.exists():
        return None, "الملف غير موجود."
    raw_sha = sha256_file(path)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM knowledge_base_files WHERE sha256_hash = ?",
            (raw_sha,),
        ).fetchone()
        if existing:
            return None, "تم رفع هذا الملف مسبقاً (نفس المحتوى)."
        conn.execute(
            """
            INSERT INTO knowledge_base_files (file_name, local_path, mime_type, file_size, sha256_hash, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (file_name, local_path, mime_type, file_size, raw_sha),
        )
        file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    text = extract_text(local_path, mime_type)
    if not text or not text.strip():
        with get_connection() as conn:
            conn.execute("UPDATE knowledge_base_files SET is_active = 0 WHERE id = ?", (file_id,))
        return file_id, "فشل استخراج النص من الملف."
    index_file(file_id, text, file_name)
    return file_id, None


def list_knowledge_files() -> List[dict]:
    """قائمة المراجع النشطة (id, file_name, file_size)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, file_name, file_size FROM knowledge_base_files WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        return [{"id": r[0], "file_name": r[1], "file_size": r[2]} for r in rows]


def ingest_local_folder(folder_path: Optional[str] = None) -> Tuple[int, int, List[str]]:
    """
    فهرسة الملفات الموضوعة مباشرة في مجلد المشروع.
    يمسح المجلد المحدد (أو knowledge_base/raw افتراضياً) ويضيف أي ملف جديد
    (PDF، Word، صور) غير موجود في القاعدة (حسب المسار أو الـ hash).
    يُرجع (عدد_المضاف, عدد_المتخطى, قائمة_أخطاء).
    """
    folder = Path(folder_path) if folder_path else KNOWLEDGE_RAW
    if not folder.exists() or not folder.is_dir():
        return 0, 0, [f"المجلد غير موجود: {folder}"]
    added = 0
    skipped = 0
    errors: List[str] = []
    with get_connection() as conn:
        existing_paths = set(
            row[0] for row in conn.execute("SELECT local_path FROM knowledge_base_files").fetchall()
        )
        existing_hashes = set(
            row[0] for row in conn.execute("SELECT sha256_hash FROM knowledge_base_files").fetchall()
        )
    for path in folder.iterdir():
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_KB_EXTENSIONS:
            continue
        local_path = str(path.resolve())
        if local_path in existing_paths:
            skipped += 1
            continue
        try:
            raw_sha = sha256_file(path)
            if raw_sha in existing_hashes:
                skipped += 1
                continue
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            continue
        mime = EXT_TO_MIME.get(ext, "application/octet-stream")
        size = path.stat().st_size
        fid, err = add_knowledge_file(path.name, local_path, mime, size)
        if err:
            errors.append(f"{path.name}: {err}")
        else:
            added += 1
            with get_connection() as conn:
                row = conn.execute("SELECT sha256_hash FROM knowledge_base_files WHERE id = ?", (fid,)).fetchone()
                if row:
                    existing_hashes.add(row[0])
            existing_paths.add(local_path)
    return added, skipped, errors


def remove_knowledge_file(file_id: int) -> bool:
    """حذف ملف من القاعدة (السجل، المقاطع، الملف الفيزيائي)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT local_path FROM knowledge_base_files WHERE id = ?",
            (file_id,),
        ).fetchone()
        if not row:
            return False
        local_path = row[0]
    delete_file_chunks(file_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge_base_files WHERE id = ?", (file_id,))
    p = Path(local_path)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
    return True


def _chunks_rows_to_result(rows: list) -> List[dict]:
    """تحويل صفوف (file_id, page_number, chunk_text) إلى قائمة قاموس مع file_name."""
    if not rows:
        return []
    with get_connection() as conn:
        file_ids = list({r[0] for r in rows})
        names = {}
        for fid in file_ids:
            r = conn.execute(
                "SELECT file_name FROM knowledge_base_files WHERE id = ? AND is_active = 1",
                (fid,),
            ).fetchone()
            if r:
                names[fid] = r[0]
        return [
            {"file_id": r[0], "page_number": r[1], "chunk_text": r[2], "file_name": names.get(r[0], "?")}
            for r in rows
        ]


def search_chunks(query: str, top_k: int = 5) -> List[dict]:
    """
    بحث FTS5 عن المقاطع الأقرب للسؤال.
    إذا لم يُعثر على نتائج من MATCH، يُجرى بحث بـ OR ثم نسخة احتياطية: جلب مقاطع عشوائية لتمكين Gemini من الإجابة.
    يُرجع قائمة {file_id, page_number, chunk_text, file_name}.
    """
    query_clean = (query or "").strip()
    rows = []

    def run_match(q: str):
        with get_connection() as conn:
            try:
                return conn.execute(
                    """
                    SELECT file_id, page_number, chunk_text
                    FROM knowledge_chunks_fts
                    WHERE knowledge_chunks_fts MATCH ?
                    ORDER BY bm25(knowledge_chunks_fts)
                    LIMIT ?
                    """,
                    (q, top_k),
                ).fetchall()
            except sqlite3.OperationalError:
                return []

    # 1) محاولة أولى: السؤال كما هو (أو عبارة بين علامتي تنصيص)
    if query_clean:
        safe_query = query_clean.replace('"', '""')
        rows = run_match(safe_query)

    # 2) إذا لم توجد نتائج: تجربة بحث بأي كلمة (OR) لتحسين المطابقة مع العربية
    if not rows and query_clean:
        words = [w.strip() for w in re.findall(r"[\w\u0600-\u06FF]+", query_clean) if w.strip()]
        if words:
            or_parts = []
            for w in words[:8]:  # حد معقول للكلمات
                or_parts.append('"' + w.replace('"', '""') + '"')
            or_query = " OR ".join(or_parts)
            rows = run_match(or_query)

    # 3) نسخة احتياطية: إذا لا زال لا توجد نتائج، جلب مقاطع من القاعدة لتمريرها لـ Gemini
    if not rows:
        with get_connection() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT file_id, page_number, chunk_text
                    FROM knowledge_chunks_fts
                    LIMIT ?
                    """,
                    (top_k,),
                ).fetchall()
            except sqlite3.OperationalError:
                pass

    if not rows:
        return []
    return _chunks_rows_to_result(rows)
