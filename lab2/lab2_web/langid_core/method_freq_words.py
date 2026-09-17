# -*- coding: utf-8 -*-
"""
Метод частотных слов (Frequent Words Method).

ПОЯ (поисковый образ языка) — набор слов, обладающих наибольшей частотой
встречаемости в обучающем корпусе, с рассчитанными вероятностями.

Классификация входного документа выполняется путём произведения
(в логарифмическом виде — суммы) вероятностей его слов согласно ПОЯ
каждого языка. Слову, отсутствующему в ПОЯ, присваивается минимальная
(штрафная) вероятность. Побеждает язык с максимальной суммарной
логарифмической вероятностью (= минимальным "расстоянием" -log P).
"""

import math
from collections import Counter
from .preprocess import tokenize

TOP_N = 250          # размер словаря частотных слов ПОЯ
MIN_PROB_FACTOR = 0.1  # штрафная вероятность = MIN_PROB_FACTOR * min(prob в словаре)


class FrequentWordsProfile:
    def __init__(self, language: str):
        self.language = language
        self.word_probs: dict[str, float] = {}
        self.min_prob: float = 1e-8

    def build(self, text: str, top_n: int = TOP_N) -> "FrequentWordsProfile":
        words = tokenize(text)
        counts = Counter(words)
        most_common = counts.most_common(top_n)
        total = sum(freq for _, freq in most_common)
        self.word_probs = {w: freq / total for w, freq in most_common}
        self.min_prob = min(self.word_probs.values()) * MIN_PROB_FACTOR if self.word_probs else 1e-8
        return self

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "word_probs": self.word_probs,
            "min_prob": self.min_prob,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrequentWordsProfile":
        obj = cls(d["language"])
        obj.word_probs = d["word_probs"]
        obj.min_prob = d["min_prob"]
        return obj

    def log_likelihood(self, document_text: str) -> float:
        """Сумма логарифмов вероятностей слов документа согласно ПОЯ этого языка."""
        words = tokenize(document_text)
        if not words:
            return -math.inf
        total = 0.0
        for w in words:
            p = self.word_probs.get(w, self.min_prob)
            total += math.log(p)
        return total


def classify(document_text: str, profiles: list[FrequentWordsProfile]) -> dict:
    """
    Возвращает словарь {язык: log_likelihood} и определяет язык-победитель
    (с максимальным log_likelihood, т.е. минимальным расстоянием -log P).
    """
    scores = {p.language: p.log_likelihood(document_text) for p in profiles}
    best_lang = max(scores, key=scores.get)
    return {"scores": scores, "predicted": best_lang}
