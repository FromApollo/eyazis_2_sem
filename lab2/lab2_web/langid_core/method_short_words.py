# -*- coding: utf-8 -*-
"""
Метод коротких слов (Short Words Method).

ПОЯ строится из лексем длиной не более MAX_LEN символов, встретившихся
в обучающем корпусе более MIN_COUNT раз. Вероятность появления
i-й лексемы = её частота / сумма частот всех лексем набора.

Вероятность принадлежности предложения языку рассчитывается как
произведение вероятностей его коротких лексем (в лог-виде — сумма).
Лексемам, отсутствующим в ПОЯ, назначается минимальная частота.
"""

import math
from collections import Counter
from .preprocess import tokenize

MAX_LEN = 5
MIN_COUNT = 3
MIN_PROB_FACTOR = 0.1


class ShortWordsProfile:
    def __init__(self, language: str):
        self.language = language
        self.word_probs: dict[str, float] = {}
        self.min_prob: float = 1e-8

    def build(self, text: str, max_len: int = MAX_LEN, min_count: int = MIN_COUNT) -> "ShortWordsProfile":
        words = tokenize(text)
        short_words = [w for w in words if len(w) <= max_len]
        counts = Counter(short_words)
        filtered = {w: c for w, c in counts.items() if c > min_count}
        total = sum(filtered.values())
        if total == 0:
            # fallback: если ни одно слово не превысило порог, берём все короткие слова
            filtered = dict(counts)
            total = sum(filtered.values()) or 1
        self.word_probs = {w: c / total for w, c in filtered.items()}
        self.min_prob = min(self.word_probs.values()) * MIN_PROB_FACTOR if self.word_probs else 1e-8
        return self

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "word_probs": self.word_probs,
            "min_prob": self.min_prob,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ShortWordsProfile":
        obj = cls(d["language"])
        obj.word_probs = d["word_probs"]
        obj.min_prob = d["min_prob"]
        return obj

    def log_likelihood(self, document_text: str, max_len: int = MAX_LEN) -> float:
        words = tokenize(document_text)
        short_words = [w for w in words if len(w) <= max_len]
        if not short_words:
            return -math.inf
        total = 0.0
        for w in short_words:
            p = self.word_probs.get(w, self.min_prob)
            total += math.log(p)
        return total


def classify(document_text: str, profiles: list[ShortWordsProfile]) -> dict:
    scores = {p.language: p.log_likelihood(document_text) for p in profiles}
    best_lang = max(scores, key=scores.get)
    return {"scores": scores, "predicted": best_lang}
