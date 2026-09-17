# -*- coding: utf-8 -*-
"""
Модуль предварительной обработки текста.

Выполняет:
 - приведение текста к нижнему регистру;
 - удаление цифр и знаков препинания;
 - нормализацию пробельных символов;
 - токенизацию текста на слова.
"""

import re

# Буквы русского и английского алфавитов (плюс ё)
_ALLOWED_CHARS = re.compile(r"[^a-zа-яё\s]", re.IGNORECASE)
_MULTI_SPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Приводит текст к нижнему регистру и убирает всё, кроме букв и пробелов."""
    text = text.lower()
    text = _ALLOWED_CHARS.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    """Разбивает предварительно очищенный текст на слова (леммы не строятся)."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return cleaned.split(" ")


def char_ngrams(text: str, n: int = 5) -> list[str]:
    """
    Строит список символьных N-грамм длины от 1 до n (метод Кэнвара-Тренкла
    использует N-граммы длины НЕ БОЛЕЕ N, поэтому включаем все длины 1..n).
    Границы слов помечаются символом '_' (пробел заменяется на '_').
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []
    words = cleaned.split(" ")
    grams: list[str] = []
    for w in words:
        padded = f"_{w}_"
        for size in range(1, n + 1):
            if len(padded) < size:
                continue
            for i in range(len(padded) - size + 1):
                grams.append(padded[i:i + size])
    return grams
