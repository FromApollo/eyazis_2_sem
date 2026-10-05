"""Two small, inspectable extractive summarizers for English and Spanish."""

from collections import Counter
from dataclasses import dataclass
import math
import re

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer


STOPWORDS = {
    "en": set("a about an and are as at be been but by can could did do does during for from had has have he her hers him his how i if in into is it its may more most my no nor not of on or our ours she should so some such than that the their them there these they this those through to too under was were what when where which while who will with would you your".split()),
    "es": set("a al algo algunas algunos ante antes como con contra cual cuales cuando de del desde donde dos el ella ellas ellos en entre era eran es esa esas ese esos esta están estaban este esto estos fue fueron ha han hasta hay la las le les lo los mas más me mi mis mucha muchos muy ni no nos o para pero por porque que quien se ser si sin sobre son su sus tambien también te tiene tienen todo todos tu un una unas unos y ya".split()),
}

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.UNICODE)


@dataclass
class Sentence:
    text: str
    document_offset: int
    paragraph_offset: int
    paragraph_length: int
    index: int


def terms(text, language):
    """Exclude numbers and stopwords; retain words in the selected Latin-script language."""
    return [word.lower() for word in WORD_RE.findall(text)
            if len(word) > 1 and word.lower() not in STOPWORDS[language]]


def split_sentences(text):
    sentences = []
    for paragraph_match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        paragraph = paragraph_match.group()
        for match in SENTENCE_RE.finditer(paragraph):
            raw = match.group()
            cleaned = raw.strip()
            if cleaned:
                leading = len(raw) - len(raw.lstrip())
                offset = match.start() + leading
                sentences.append(Sentence(cleaned, paragraph_match.start() + offset,
                                          offset, len(paragraph), len(sentences)))
    return sentences


def document_frequency(documents, language):
    counts = Counter()
    for document in documents:
        counts.update(set(terms(document, language)))
    return counts


def sentence_extraction(text, language, corpus):
    """The position product and modified TF-IDF on page 2 of the assignment."""
    sentences = split_sentences(text)
    docs = list(corpus)
    if text not in docs:
        docs.append(text)
    df = document_frequency(docs, language)
    frequency = Counter(terms(text, language))
    maximum = max(frequency.values(), default=1)
    # Exact assignment formula: 0.5(1 + tf(t,D)/tf_max(D)) * log(|DB|/df(t)).
    weights = {term: 0.5 * (1 + count / maximum) * math.log(len(docs) / df[term])
               for term, count in frequency.items()}
    scores = []
    for sentence in sentences:
        score = sum(count * weights.get(term, 0.0)
                    for term, count in Counter(terms(sentence.text, language)).items())
        position_document = 1 - sentence.document_offset / max(len(text), 1)
        position_paragraph = 1 - sentence.paragraph_offset / max(sentence.paragraph_length, 1)
        scores.append(score * position_document * position_paragraph)
    return sentences, scores, weights


def lsa_scores(sentences, language):
    """Sentence-term TF-IDF, truncated SVD and cosine to the document centroid."""
    if len(sentences) < 3:
        return [1.0] * len(sentences)
    vectorizer = TfidfVectorizer(tokenizer=lambda s: terms(s, language),
                                 token_pattern=None, lowercase=False)
    try:
        matrix = vectorizer.fit_transform(s.text for s in sentences)
    except ValueError:  # No usable terms.
        return [0.0] * len(sentences)
    components = min(3, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if components < 1:
        return [float(v) for v in np.asarray(matrix.sum(axis=1)).ravel()]
    latent = TruncatedSVD(n_components=components, random_state=0).fit_transform(matrix)
    centroid = latent.mean(axis=0)
    denominator = np.linalg.norm(latent, axis=1) * np.linalg.norm(centroid)
    return list(np.divide(latent @ centroid, denominator,
                          out=np.zeros(len(sentences)), where=denominator > 0))


def summarize(text, language, corpus, method="sentence", count=10, keyword_count=12):
    if language not in STOPWORDS:
        raise ValueError("Unsupported language")
    sentences, base_scores, weights = sentence_extraction(text, language, corpus)
    if not sentences:
        raise ValueError("The document has no sentences")
    if method == "lsa":
        scores = lsa_scores(sentences, language)
    elif method == "sentence":
        scores = base_scores
    else:
        raise ValueError("Unsupported method")
    selected = set(sorted(range(len(sentences)), key=lambda i: (-scores[i], i))[:count])
    # The highest scoring sentences are returned in their source order.
    extract = [{"text": sentence.text, "score": round(float(scores[i]), 4),
                "index": i + 1} for i, sentence in enumerate(sentences) if i in selected]
    keywords = [{"term": term, "weight": round(weight, 4)}
                for term, weight in sorted(weights.items(), key=lambda pair: (-pair[1], pair[0]))
                if weight > 0][:keyword_count]
    return {"sentences": extract, "keywords": keywords, "total_sentences": len(sentences),
            "method": method, "language": language}
