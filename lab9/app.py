"""Laboratory work 9, variant 5: spoken commands for literature essays."""

import re
from collections import Counter

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "he", "her", "his", "i", "in", "is", "it", "its", "of", "on",
    "or", "she", "that", "the", "their", "there", "they", "this", "to",
    "was", "were", "with", "you",
}


def analyze_essay(text):
    """Return transparent, rule-based indicators rather than a quality score."""
    words = [word.lower() for word in WORD_RE.findall(text)]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    sentences = [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]
    repeated = Counter(word for word in words if word not in STOP_WORDS and len(word) > 3)
    top_words = [{"word": word, "count": count} for word, count in repeated.most_common(5)]
    lower = text.lower()
    markers = {
        "thesis": any(phrase in lower for phrase in ("i argue", "this essay argues", "my thesis", "i believe")),
        "evidence": any(phrase in lower for phrase in ("for example", "for instance", "the text shows", "the author writes")),
        "conclusion": any(phrase in lower for phrase in ("in conclusion", "to conclude", "overall")),
    }
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "top_words": top_words,
        "markers": markers,
        "notice": "Indicators are based on simple rules; they do not grade literary quality.",
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not isinstance(text, str):
        return jsonify(error="Text must be a string."), 400
    if len(text) > 10000:
        return jsonify(error="The essay must be at most 10,000 characters."), 400
    return jsonify(analyze_essay(text))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5009, debug=True)
