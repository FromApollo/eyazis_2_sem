# -*- coding: utf-8 -*-
"""
Загружает образцы документов из папки sample_test_docs/ в тестовую коллекцию
веб-приложения (эквивалент ручной загрузки через форму на главной странице).
Удобно для быстрой демонстрации/проверки работы системы без загрузки
документов вручную через браузер.

Запуск (из корня проекта lab2_web):
    python3 scripts/seed_test_collection.py
"""
import os
import sys
import json
import shutil
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from langid_core import service

SAMPLE_DIR = os.path.join(BASE_DIR, "sample_test_docs")


def main():
    with open(os.path.join(SAMPLE_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = {item["file"]: item["true_language"] for item in json.load(f)}

    if not service.models_ready():
        print("Модели ещё не построены. Сначала запустите scripts/build_profiles.py")
        return

    for filename, true_lang in manifest.items():
        src = os.path.join(SAMPLE_DIR, filename)
        stored_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        dst = os.path.join(service.UPLOAD_DIR, stored_filename)
        shutil.copy(src, dst)
        size_bytes = os.path.getsize(dst)
        record = service.add_document(stored_filename, filename, true_lang, size_bytes)
        print(f"Добавлен: {filename} (id={record['id']}, истинный язык={true_lang})")

    print("Готово. Тестовая коллекция заполнена образцами документов.")


if __name__ == "__main__":
    main()
