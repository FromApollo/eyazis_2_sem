"""English analysis and inspectable direct English-to-German translation."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import nltk
from nltk import RegexpParser, pos_tag
from nltk.tree import Tree


nltk.data.path.insert(0, str(Path(__file__).parent / ".nltk_data"))


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")
GRAMMAR = r"""
    NP: {<DT|PRP\$>?<JJ.*>*<NN.*|PRP>+}
    PP: {<IN><NP>}
    VP: {<MD>?<VB.*><NP|PP|RB.*>*}
    CLAUSE: {<NP><VP>}
"""

POS_NAMES = {
    "CC": "сочинительный союз", "CD": "числительное", "DT": "определитель",
    "EX": "оборот there is", "FW": "иностранное слово", "IN": "предлог / подчинительный союз",
    "JJ": "прилагательное", "JJR": "прилагательное, сравнительная степень",
    "JJS": "прилагательное, превосходная степень", "LS": "маркер списка",
    "MD": "модальный глагол", "NN": "существительное, ед. ч.",
    "NNS": "существительное, мн. ч.", "NNP": "имя собственное, ед. ч.",
    "NNPS": "имя собственное, мн. ч.", "PDT": "предопределитель",
    "POS": "притяжательное окончание", "PRP": "личное местоимение",
    "PRP$": "притяжательное местоимение", "RB": "наречие",
    "RBR": "наречие, сравнительная степень", "RBS": "наречие, превосходная степень",
    "RP": "частица", "TO": "частица to", "UH": "междометие",
    "VB": "глагол, начальная форма", "VBD": "глагол, прошедшее время",
    "VBG": "глагол, причастие наст. вр.", "VBN": "глагол, причастие прош. вр.",
    "VBP": "глагол, наст. вр. (не 3-е лицо)", "VBZ": "глагол, наст. вр. (3-е лицо)",
    "WDT": "вопросительный определитель", "WP": "вопросительное местоимение",
    "WP$": "притяжательное вопросительное местоимение", "WRB": "вопросительное наречие",
}

TREE_NAMES = {
    "S": "предложение", "CLAUSE": "основа предложения",
    "NP": "именная группа", "VP": "глагольная группа", "PP": "предложная группа",
}


def tree_to_dict(tree_text: str) -> dict:
    """Convert a saved NLTK tree to nodes for the visual tree, including old runs."""
    def convert(node):
        if isinstance(node, str):
            word, pos = node.rsplit("/", 1)
            return {"leaf": True, "word": word, "pos": pos,
                    "meaning": POS_NAMES.get(pos, "другая часть речи")}
        return {"leaf": False, "label": node.label(),
                "meaning": TREE_NAMES.get(node.label(), "группа"),
                "children": [convert(child) for child in node]}

    return convert(Tree.fromstring(tree_text))


def ensure_nltk_model():
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    except LookupError as exc:
        raise RuntimeError(
            "Не найдена модель NLTK. Выполните: python -m nltk.downloader averaged_perceptron_tagger_eng"
        ) from exc


def sentence_spans(text: str):
    """Yield nonempty sentence spans without losing original offsets."""
    for match in SENTENCE_RE.finditer(text):
        if WORD_RE.search(match.group()):
            yield match.start(), match.end(), match.group().strip()


def candidates(word: str):
    word = word.lower()
    yield word
    if word.endswith("ies") and len(word) > 4:
        yield word[:-3] + "y"
    if word.endswith("ing") and len(word) > 5:
        yield word[:-3]
        yield word[:-3] + "e"
    if word.endswith("ed") and len(word) > 4:
        yield word[:-2]
        yield word[:-1]
    if word.endswith("es") and len(word) > 4:
        yield word[:-2]
    if word.endswith("s") and len(word) > 3:
        yield word[:-1]


def lookup(word: str, tag: str, dictionary: dict):
    """Prefer matching POS; recover a known word if NLTK assigned another tag."""
    fallback_tags = {
        "NNS": ("NN",), "NNPS": ("NNP", "NN"),
        "VBZ": ("VB",), "VBP": ("VB",), "VBD": ("VB",),
        "VBN": ("VB",), "VBG": ("VB",),
        "JJR": ("JJ",), "JJS": ("JJ",),
        "RBR": ("RB",), "RBS": ("RB",),
    }
    for form in dict.fromkeys(candidates(word)):
        for key in ((form, tag), (form, "*"), *((form, other) for other in fallback_tags.get(tag, ()))):
            value = dictionary.get(key, "")
            if value:
                return value
    for form in dict.fromkeys(candidates(word)):
        for (english, _), value in dictionary.items():
            if english == form and value:
                return value
    return ""


def _phrase(tokens, index, dictionary):
    for size in range(min(4, len(tokens) - index), 1, -1):
        group = tokens[index:index + size]
        if any(not tokens[j + 1][3].isspace() for j in range(index, index + size - 1)):
            continue
        phrase = " ".join(item[2].lower() for item in group)
        german = dictionary.get((phrase, "*"), "")
        if german:
            return size, german
    return 0, ""


def analyze(text: str, dictionary: dict) -> dict:
    ensure_nltk_model()
    parser = RegexpParser(GRAMMAR)
    sentences = []
    frequencies = Counter()
    tag_frequencies = {}
    translated_count = 0
    output = []
    cursor = 0
    seen_unknown = set()
    seen_words = set()

    for start, end, sentence in sentence_spans(text):
        raw = text[start:end]
        matches = list(WORD_RE.finditer(raw))
        words = [match.group() for match in matches]
        tags = pos_tag(words, lang="eng")
        tokens = []
        for i, match in enumerate(matches):
            gap = raw[matches[i - 1].end():match.start()] if i else ""
            tokens.append((start + match.start(), start + match.end(), words[i], gap, tags[i][1]))
        tree = parser.parse(tags)
        sentences.append({
            "text": sentence,
            "tree": tree.pformat(margin=100),
            "tokens": [{"word": word, "tag": tag, "meaning": POS_NAMES.get(tag, "другая часть речи")}
                       for word, tag in tags],
        })

        i = 0
        while i < len(tokens):
            token = tokens[i]
            size, german = _phrase(tokens, i, dictionary)
            if size:
                last = tokens[i + size - 1]
                output.extend((text[cursor:token[0]], german))
                cursor = last[1]
                translated_count += size
                for part in tokens[i:i + size]:
                    word = part[2].lower()
                    frequencies[word] += 1
                    tag_frequencies.setdefault(word, Counter())[part[4]] += 1
                    seen_words.add((word, part[4]))
                i += size
                continue

            source, tag = token[2], token[4]
            german = lookup(source, tag, dictionary)
            word = source.lower()
            frequencies[word] += 1
            tag_frequencies.setdefault(word, Counter())[tag] += 1
            seen_words.add((word, tag))
            if german:
                translated_count += 1
                if tag.startswith("NN"):
                    german = german[0].upper() + german[1:]
                if source[0].isupper() and (i == 0 or tag.startswith("NNP")):
                    german = german[0].upper() + german[1:]
            else:
                german = source
                seen_unknown.add((source.lower(), tag))
            output.extend((text[cursor:token[0]], german))
            cursor = token[1]
            i += 1

    output.append(text[cursor:])
    rows = []
    for word, count in sorted(frequencies.items(), key=lambda x: (-x[1], x[0])):
        tags = [tag for tag, _ in tag_frequencies[word].most_common()]
        translation = next((lookup(word, tag, dictionary) for tag in tags if lookup(word, tag, dictionary)), "")
        rows.append({
            "word": word, "translation": translation, "tag": ", ".join(tags),
            "meaning": "; ".join(dict.fromkeys(POS_NAMES.get(tag, "другая часть речи") for tag in tags)),
            "frequency": count,
        })
    return {
        "translated_text": "".join(output),
        "word_count": sum(frequencies.values()),
        "translated_count": translated_count,
        "rows": rows,
        "sentences": sentences,
        "unknown": sorted(seen_unknown),
        "seen_words": sorted(seen_words),
    }
