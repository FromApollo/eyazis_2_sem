# -*- coding: utf-8 -*-
"""
Построение поисковых образов языка (ПОЯ) и обучение нейросетевой модели
для веб-приложения. Запускается один раз перед первым стартом Flask-сервера
(или повторно через админ-функцию "Пересобрать модели" в веб-интерфейсе).
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from langid_core.method_freq_words import FrequentWordsProfile
from langid_core.method_short_words import ShortWordsProfile
from langid_core.method_neural import train_neural_model

CORPUS_DIR = os.path.join(BASE_DIR, "corpus")
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")

LANGUAGES = {
    "ru": os.path.join(CORPUS_DIR, "ru_train.txt"),
    "en": os.path.join(CORPUS_DIR, "en_train.txt"),
}


def build_all():
    os.makedirs(PROFILES_DIR, exist_ok=True)
    corpora = {}
    log = []
    for lang, path in LANGUAGES.items():
        with open(path, "r", encoding="utf-8") as f:
            corpora[lang] = f.read()
        size_kb = os.path.getsize(path) / 1024
        log.append(f"[{lang}] Загружен обучающий корпус: {size_kb:.1f} КБ")

    for lang, text in corpora.items():
        profile = FrequentWordsProfile(lang).build(text)
        with open(os.path.join(PROFILES_DIR, f"freq_words_{lang}.json"), "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        log.append(f"[{lang}] Метод частотных слов: ПОЯ из {len(profile.word_probs)} слов")

    for lang, text in corpora.items():
        profile = ShortWordsProfile(lang).build(text)
        with open(os.path.join(PROFILES_DIR, f"short_words_{lang}.json"), "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        log.append(f"[{lang}] Метод коротких слов: ПОЯ из {len(profile.word_probs)} лексем")

    log.append("Обучение нейросетевой модели (MLPClassifier)...")
    model = train_neural_model(corpora)
    model.save(os.path.join(PROFILES_DIR, "neural_model.pkl"))
    log.append("Нейросетевая модель обучена и сохранена.")
    return log


if __name__ == "__main__":
    for line in build_all():
        print(line)
