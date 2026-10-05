"""Reproducible precision@10 and timing for the four sample documents."""

import json
from pathlib import Path
from time import perf_counter

from app import DOCUMENTS, corpus_for, read_document
from summarizer import summarize


# Eight central statements per source, selected manually by reading the documents.
REFERENCE = {
    "en_medicine.txt": {2, 6, 9, 11, 16, 21, 25, 26},
    "es_medicine.txt": {2, 6, 9, 11, 16, 21, 25, 26},
    "en_art.txt": {3, 7, 12, 16, 19, 25, 26, 30},
    "es_art.txt": {3, 7, 12, 16, 19, 25, 26, 30},
}


def evaluate(repetitions=30):
    rows = []
    for item in DOCUMENTS:
        text = read_document(item["file"])
        corpus = corpus_for(item["language"])
        for method in ("sentence", "lsa"):
            durations = []
            result = None
            for _ in range(repetitions):
                started = perf_counter()
                result = summarize(text, item["language"], corpus, method)
                durations.append((perf_counter() - started) * 1000)
            selected = {s["index"] for s in result["sentences"]}
            overlap = len(selected & REFERENCE[item["file"]])
            rows.append({"file": item["file"], "domain": item["domain"],
                         "language": item["language"], "method": method,
                         "selected": sorted(selected), "reference": sorted(REFERENCE[item["file"]]),
                         "precision_at_10": round(overlap / 10, 2),
                         "recall_at_8": round(overlap / 8, 2),
                         "mean_ms": round(sum(durations) / len(durations), 2)})
    return rows


if __name__ == "__main__":
    output = Path("evaluation.json")
    output.write_text(json.dumps(evaluate(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
