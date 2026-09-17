# -*- coding: utf-8 -*-
"""
Нейросетевой метод определения языка текста.

Признаки: частоты символьных N-грамм (1..3), полученные с помощью
TfidfVectorizer (analyzer='char', ngram_range=(1,3)) — это векторное
представление документа/предложения.

Классификатор: MLPClassifier (многослойный персептрон) из scikit-learn.

Обучающая выборка формируется путём разбиения обучающего корпуса каждого
языка на короткие фрагменты (предложения/окна по ~120 символов), что
даёт достаточное число примеров для обучения сети.
"""

import re
import pickle
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder

from .preprocess import clean_text

WINDOW_CHARS = 120
STEP_CHARS = 60


def split_into_chunks(text: str, window: int = WINDOW_CHARS, step: int = STEP_CHARS) -> list[str]:
    """Разбивает очищенный текст на перекрывающиеся окна фиксированной длины символов."""
    cleaned = clean_text(text)
    chunks = []
    i = 0
    while i < len(cleaned):
        chunk = cleaned[i:i + window]
        if len(chunk.strip()) > 20:
            chunks.append(chunk)
        i += step
    return chunks


@dataclass
class NeuralLanguageModel:
    vectorizer: TfidfVectorizer
    classifier: MLPClassifier
    classes_: list
    label_encoder: LabelEncoder

    def predict_proba_text(self, text: str) -> dict:
        cleaned = clean_text(text)
        if not cleaned:
            return {c: 0.0 for c in self.classes_}
        X = self.vectorizer.transform([cleaned])
        proba = self.classifier.predict_proba(X)[0]
        labels = self.label_encoder.inverse_transform(self.classifier.classes_)
        return {lab: float(p) for lab, p in zip(labels, proba)}

    def predict(self, text: str) -> dict:
        scores = self.predict_proba_text(text)
        best_lang = max(scores, key=scores.get)
        return {"scores": scores, "predicted": best_lang}

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump({"vectorizer": self.vectorizer, "classifier": self.classifier,
                         "classes_": self.classes_, "label_encoder": self.label_encoder}, f)

    @classmethod
    def load(cls, path: str) -> "NeuralLanguageModel":
        with open(path, "rb") as f:
            d = pickle.load(f)
        return cls(vectorizer=d["vectorizer"], classifier=d["classifier"],
                    classes_=d["classes_"], label_encoder=d["label_encoder"])


def train_neural_model(corpora: dict[str, str], random_state: int = 42) -> NeuralLanguageModel:
    """
    corpora: {"ru": ru_text, "en": en_text, ...}
    Строит обучающую выборку из фрагментов текста и обучает MLPClassifier.
    """
    X_texts, y_labels = [], []
    for lang, text in corpora.items():
        for chunk in split_into_chunks(text):
            X_texts.append(chunk)
            y_labels.append(lang)

    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), min_df=1, max_features=3000)
    X = vectorizer.fit_transform(X_texts)

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_labels)

    clf = MLPClassifier(
        hidden_layer_sizes=(64,),
        activation="relu",
        max_iter=800,
        random_state=random_state,
    )
    clf.fit(X, y)

    return NeuralLanguageModel(vectorizer=vectorizer, classifier=clf,
                                classes_=sorted(set(y_labels)), label_encoder=label_encoder)
