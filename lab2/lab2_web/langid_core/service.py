# -*- coding: utf-8 -*-
"""
Сервисный слой веб-приложения:
 - хранение базы данных документов тестовой коллекции (PostgreSQL);
 - извлечение текста из PDF;
 - прогон документа через три метода классификации;
 - подсчёт сводной статистики (точность, среднее время) по коллекции.
"""

import os
import json
import time
import math
import uuid
from datetime import datetime

import pdfplumber
import psycopg2
import psycopg2.extras

from .method_freq_words import FrequentWordsProfile, classify as classify_freq
from .method_short_words import ShortWordsProfile, classify as classify_short
from .method_neural import NeuralLanguageModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://languser:langpass@localhost:5432/langdb",
)

LANGUAGES = ["ru", "en"]
LANG_NAMES = {"ru": "Русский", "en": "Английский", None: "Не указан", "": "Не указан"}
METHOD_NAMES = {
    "freq_words": "Метод частотных слов",
    "short_words": "Метод коротких слов",
    "neural": "Нейросетевой метод",
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --------------------------------------------------------------------------
# Загрузка моделей (один раз при старте процесса)
# --------------------------------------------------------------------------

_freq_profiles = None
_short_profiles = None
_neural_model = None


def _ensure_models_loaded():
    global _freq_profiles, _short_profiles, _neural_model
    if _freq_profiles is not None:
        return
    _freq_profiles = []
    _short_profiles = []
    for lang in LANGUAGES:
        with open(os.path.join(PROFILES_DIR, f"freq_words_{lang}.json"), encoding="utf-8") as f:
            _freq_profiles.append(FrequentWordsProfile.from_dict(json.load(f)))
        with open(os.path.join(PROFILES_DIR, f"short_words_{lang}.json"), encoding="utf-8") as f:
            _short_profiles.append(ShortWordsProfile.from_dict(json.load(f)))
    _neural_model = NeuralLanguageModel.load(os.path.join(PROFILES_DIR, "neural_model.pkl"))


def reload_models():
    """Принудительно перечитать модели с диска (после пересборки профилей)."""
    global _freq_profiles, _short_profiles, _neural_model
    _freq_profiles = None
    _short_profiles = None
    _neural_model = None
    _ensure_models_loaded()


def models_ready() -> bool:
    return os.path.exists(os.path.join(PROFILES_DIR, "neural_model.pkl"))


# --------------------------------------------------------------------------
# База данных документов (PostgreSQL)
# --------------------------------------------------------------------------

def _conn():
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    """Создаёт таблицу documents, если она ещё не существует."""
    with _conn() as con, con.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                stored_filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                file_size_kb DOUBLE PRECISION,
                true_language TEXT,
                text_preview TEXT,
                text_length_chars INTEGER,
                methods JSONB NOT NULL
            )
        """)


def _row_to_record(row: dict) -> dict:
    rec = dict(row)
    if isinstance(rec.get("methods"), str):
        rec["methods"] = json.loads(rec["methods"])
    return rec


def _load_db() -> list:
    with _conn() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM documents")
        return [_row_to_record(r) for r in cur.fetchall()]


def _save_db(records: list) -> None:
    """Полностью перезаписывает таблицу documents (сохранён интерфейс JSON-версии)."""
    with _conn() as con, con.cursor() as cur:
        cur.execute("DELETE FROM documents")
        for r in records:
            cur.execute(
                """INSERT INTO documents
                   (id, stored_filename, original_filename, uploaded_at,
                    file_size_kb, true_language, text_preview,
                    text_length_chars, methods)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                (r["id"], r["stored_filename"], r["original_filename"], r["uploaded_at"],
                 r["file_size_kb"], r.get("true_language"), r["text_preview"],
                 r["text_length_chars"], json.dumps(r["methods"], ensure_ascii=False)),
            )


def _sanitize_float(v):
    if isinstance(v, float):
        if math.isinf(v):
            return -1e9 if v < 0 else 1e9
        if math.isnan(v):
            return 0.0
    return v


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return _sanitize_float(obj)


def extract_pdf_text(path: str) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def classify_text(text: str) -> dict:
    """Прогоняет текст через три метода и возвращает структуру с результатами и временем."""
    _ensure_models_loaded()

    t0 = time.perf_counter()
    res_freq = classify_freq(text, _freq_profiles)
    t_freq = time.perf_counter() - t0

    t0 = time.perf_counter()
    res_short = classify_short(text, _short_profiles)
    t_short = time.perf_counter() - t0

    t0 = time.perf_counter()
    res_neural = _neural_model.predict(text)
    t_neural = time.perf_counter() - t0

    return {
        "freq_words": {"predicted": res_freq["predicted"], "scores": res_freq["scores"], "time_sec": t_freq},
        "short_words": {"predicted": res_short["predicted"], "scores": res_short["scores"], "time_sec": t_short},
        "neural": {"predicted": res_neural["predicted"], "scores": res_neural["scores"], "time_sec": t_neural},
    }


def add_document(stored_filename: str, original_filename: str, true_language: str | None,
                  file_size_bytes: int) -> dict:
    """Обрабатывает новый документ: извлекает текст, классифицирует, сохраняет запись в БД."""
    path = os.path.join(UPLOAD_DIR, stored_filename)
    text = extract_pdf_text(path)
    methods = classify_text(text)

    for m in methods.values():
        m["correct"] = (true_language is not None and m["predicted"] == true_language)

    record = {
        "id": uuid.uuid4().hex[:10],
        "stored_filename": stored_filename,
        "original_filename": original_filename,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_size_kb": round(file_size_bytes / 1024, 1),
        "true_language": true_language,
        "text_preview": text[:600],
        "text_length_chars": len(text),
        "methods": methods,
    }
    record = _sanitize(record)

    records = _load_db()
    records.append(record)
    _save_db(records)
    return record


def get_document(doc_id: str) -> dict | None:
    for r in _load_db():
        if r["id"] == doc_id:
            return r
    return None


def list_documents() -> list:
    return sorted(_load_db(), key=lambda r: r["uploaded_at"], reverse=True)


def update_true_language(doc_id: str, true_language: str | None) -> dict | None:
    records = _load_db()
    updated = None
    for r in records:
        if r["id"] == doc_id:
            r["true_language"] = true_language
            for m in r["methods"].values():
                m["correct"] = (true_language is not None and m["predicted"] == true_language)
            updated = r
    _save_db(records)
    return updated


def delete_document(doc_id: str) -> bool:
    records = _load_db()
    new_records = [r for r in records if r["id"] != doc_id]
    if len(new_records) == len(records):
        return False
    removed = [r for r in records if r["id"] == doc_id]
    _save_db(new_records)
    for r in removed:
        try:
            os.remove(os.path.join(UPLOAD_DIR, r["stored_filename"]))
        except OSError:
            pass
    return True


def compute_summary() -> dict:
    """Считает точность и среднее время по документам, для которых указан истинный язык."""
    records = [r for r in _load_db() if r.get("true_language")]
    n = len(records)
    summary = {}
    for method in ["freq_words", "short_words", "neural"]:
        if n == 0:
            summary[method] = {"accuracy_percent": None, "correct": 0, "total": 0, "avg_time_ms": None}
            continue
        correct = sum(1 for r in records if r["methods"][method]["correct"])
        avg_time = sum(r["methods"][method]["time_sec"] for r in records) / n * 1000
        summary[method] = {
            "accuracy_percent": round(correct / n * 100, 2),
            "correct": correct,
            "total": n,
            "avg_time_ms": round(avg_time, 4),
        }
    return {
        "summary": summary,
        "labeled_count": n,
        "total_count": len(_load_db()),
    }
