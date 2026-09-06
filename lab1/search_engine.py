"""
Vector-model search engine (variant 9: English, vector search strategy).

Implements, in line with the lab's theoretical section:
  - tokenisation / normalisation of English text into terms (lemmas)
  - inverse document frequency Bi = log(N / Pi)                     (1.5)
  - term weight   Aij = Qij * Bi                                    (1.6)
  - normalised TF-IDF document vectors (Euclidean-normalised)
  - binary query vector wqj in {0, 1}
  - cosine similarity  r(D,Q) = (D,Q) / (||D|| * ||Q||)
"""
import html
import math
import re
from collections import Counter

from models import db, Document, Lemma, DocumentLemma

# --------------------------------------------------------------------------
# A compact, self-contained English stop-word list (no external corpus
# download is required -- keeps the system deployable on an isolated LAN,
# consistent with variant 9's "Локальная вычислительная сеть" scope).
# --------------------------------------------------------------------------
STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further had hadn't has hasn't have haven't having he he'd he'll he's
her here here's hers herself him himself his how how's i i'd i'll i'm i've
if in into is isn't it it's its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves
out over own same shan't she she'd she'll she's should shouldn't so some
such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under
until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's
with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves
""".split())

_TOKEN_RE = re.compile(r"[a-zA-Z]+")


def _simple_stem(word):
    """
    A lightweight Porter-style suffix-stripping stemmer. Not a full Porter
    implementation, but sufficient to fold common English inflections
    (plurals, -ing, -ed, -ly, -ness, -ion) into a shared root so that e.g.
    "search", "searches", "searching" index to one term.
    """
    for suffix, min_len in [
        ("ational", 8), ("ization", 8), ("iveness", 8), ("fulness", 8),
        ("ousness", 8), ("ing", 4), ("edly", 5), ("ed", 3), ("ies", 4),
        ("es", 3), ("s", 2), ("ly", 3), ("ness", 4), ("ion", 4), ("ment", 5),
    ]:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_len - len(suffix) + 1:
            if len(word) > len(suffix) + 1:
                return word[: -len(suffix)]
    return word


def tokenize(text):
    """Lower-case, strip punctuation, drop stop-words, stem."""
    tokens = _TOKEN_RE.findall(text.lower())
    return [_simple_stem(t) for t in tokens if t not in STOPWORDS and len(t) > 1]


# --------------------------------------------------------------------------
# "AI element" #1: relevance-dense snippet extraction with bolded matches,
# instead of a naive first-300-characters slice. Finds the window of the
# document that contains the most query-term hits and bolds them.
# --------------------------------------------------------------------------
def build_snippet(text, query_terms, window_tokens=28, max_chars=320):
    """
    text: the full document text
    query_terms: set of stemmed query terms to highlight
    Returns an HTML-safe string (non-matched text escaped, matches wrapped
    in <strong>) with the densest window of query-term hits, or a plain
    leading excerpt if the document contains no words at all.
    """
    tokens = [(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)]
    if not tokens:
        return html.escape(text[:max_chars])

    stems = [_simple_stem(w.lower()) for (_s, _e, w) in tokens]
    match_flags = [1 if s in query_terms else 0 for s in stems]

    n = len(tokens)
    w = min(window_tokens, n)

    # sliding window: find the w-token window with the most query-term hits
    current = sum(match_flags[:w])
    best_score, best_start = current, 0
    for i in range(1, n - w + 1):
        current += match_flags[i + w - 1] - match_flags[i - 1]
        if current > best_score:
            best_score, best_start = current, i

    window = tokens[best_start:best_start + w]
    window_flags = match_flags[best_start:best_start + w]
    start_char, end_char = window[0][0], window[-1][1]

    # Trim an overly long window down toward max_chars, keeping it centred
    # on the highest local match density if it had to be shortened.
    if end_char - start_char > max_chars:
        end_char = start_char + max_chars

    pieces = []
    cursor = start_char
    for (s, e, word), is_match in zip(window, window_flags):
        if e > end_char:
            break
        if s > cursor:
            pieces.append(html.escape(text[cursor:s]))
        display_word = html.escape(text[s:e])
        pieces.append(f"<strong>{display_word}</strong>" if is_match else display_word)
        cursor = e

    prefix = "…" if start_char > 0 else ""
    suffix = "…" if end_char < len(text) else ""
    return prefix + "".join(pieces) + suffix


# --------------------------------------------------------------------------
# "AI element" #2: search-box autocomplete, driven by the system's own
# index (dictionary terms + document titles) rather than an external API --
# keeps the system fully self-contained for LAN deployment.
# --------------------------------------------------------------------------
def suggest_terms(prefix, limit=8):
    prefix = (prefix or "").strip().lower()
    if len(prefix) < 2:
        return []

    term_rows = (
        db.session.query(Lemma.term)
        .filter(Lemma.term.ilike(f"{prefix}%"))
        .order_by(Lemma.term)
        .limit(limit)
        .all()
    )
    title_rows = (
        db.session.query(Document.title)
        .filter(Document.title.ilike(f"%{prefix}%"))
        .order_by(Document.title)
        .limit(limit)
        .all()
    )

    seen = set()
    suggestions = []
    for (value,) in list(term_rows) + list(title_rows):
        key = value.lower()
        if key not in seen:
            seen.add(key)
            suggestions.append(value)
        if len(suggestions) >= limit:
            break
    return suggestions


# --------------------------------------------------------------------------
# Indexing
# --------------------------------------------------------------------------
class Indexer:
    """Builds/refreshes the inverted index and TF-IDF weights."""

    @staticmethod
    def index_document(document, recompute=True):
        """Tokenise a single document and (re)write its DocumentLemma rows.

        recompute=False skips the (collection-wide) weight recomputation --
        useful when indexing many documents in a batch (e.g. the directory
        crawler), where callers should call recompute_weights() once at the
        end instead of after every single document.
        """
        DocumentLemma.query.filter_by(document_id=document.documentID).delete()

        terms = tokenize(document.text + " " + document.title)
        counts = Counter(terms)

        for term, tf in counts.items():
            lemma = Lemma.query.filter_by(term=term).first()
            if lemma is None:
                lemma = Lemma(term=term)
                db.session.add(lemma)
                db.session.flush()  # get lemma.id
            link = DocumentLemma(
                document_id=document.documentID,
                lemma_id=lemma.id,
                tf=tf,
                weight=0.0,  # filled in by recompute_weights()
            )
            db.session.add(link)
        db.session.commit()
        if recompute:
            Indexer.recompute_weights()

    @staticmethod
    def rebuild_full_index():
        """Re-tokenise every document from scratch (used after bulk loads)."""
        DocumentLemma.query.delete()
        Lemma.query.delete()
        db.session.commit()

        lemma_cache = {}
        for document in Document.query.all():
            terms = tokenize(document.text + " " + document.title)
            counts = Counter(terms)
            for term, tf in counts.items():
                lemma_id = lemma_cache.get(term)
                if lemma_id is None:
                    lemma = Lemma(term=term)
                    db.session.add(lemma)
                    db.session.flush()
                    lemma_id = lemma.id
                    lemma_cache[term] = lemma_id
                db.session.add(DocumentLemma(
                    document_id=document.documentID,
                    lemma_id=lemma_id,
                    tf=tf,
                    weight=0.0,
                ))
        db.session.commit()
        Indexer.recompute_weights()

    @staticmethod
    def recompute_weights():
        """
        Recompute Bi (idf) for every lemma and Aij (tf*idf) for every
        document-lemma pair, then Euclidean-normalise each document's
        vector (the normalised TF-IDF formula shown in the lab text).
        """
        N = Document.query.count()
        if N == 0:
            return

        # Pi per lemma: number of documents containing the term
        doc_freq = dict(
            db.session.query(DocumentLemma.lemma_id, db.func.count(DocumentLemma.document_id))
            .group_by(DocumentLemma.lemma_id)
            .all()
        )
        idf = {
            lemma_id: math.log(N / Pi) if Pi > 0 else 0.0
            for lemma_id, Pi in doc_freq.items()
        }

        # raw weight = tf * idf, grouped by document for normalisation
        links_by_doc = {}
        for link in DocumentLemma.query.all():
            raw = link.tf * idf.get(link.lemma_id, 0.0)
            link.weight = raw
            links_by_doc.setdefault(link.document_id, []).append(link)

        for doc_id, links in links_by_doc.items():
            norm = math.sqrt(sum(l.weight ** 2 for l in links))
            if norm > 0:
                for l in links:
                    l.weight = l.weight / norm
        db.session.commit()


# --------------------------------------------------------------------------
# Search / SearchResult (per class diagrams)
# --------------------------------------------------------------------------
class SearchResult:
    def __init__(self, documentId, title, snippet, rank, date, matchedTerms=None):
        self.documentId = documentId
        self.title = title
        self.snippet = snippet
        self.rank = rank
        self.date = date
        # Query words (stemmed lemmas) found in this document -- required
        # by the assignment: "список слов запроса присутствующих в документе".
        self.matchedTerms = sorted(matchedTerms) if matchedTerms else []


class Search:
    """
    Vector-model search: builds a poisk obraz zaprosa (binary query vector),
    scores it against every document vector by cosine similarity, and
    returns results ordered by descending relevance.
    """

    def __init__(self, searchQuery, allWordsTogether=False,
                 dateStartString=None, dateEndString=None):
        self.searchQuery = searchQuery or ""
        self.allWordsTogether = allWordsTogether
        self.dateStartString = dateStartString
        self.dateEndString = dateEndString

    # -- private helpers (per class diagram) --------------------------------
    def _GetSearchQueryVector(self):
        """Binary query vector: wqj = 1 if term j is present in the query."""
        terms = set(tokenize(self.searchQuery))
        lemma_ids = {}
        for term in terms:
            lemma = Lemma.query.filter_by(term=term).first()
            if lemma is not None:
                lemma_ids[lemma.id] = 1.0
        return lemma_ids, terms

    @staticmethod
    def _ScalarProduct(a, b):
        common = set(a.keys()) & set(b.keys())
        return sum(a[k] * b[k] for k in common)

    @staticmethod
    def _EuclideanNorm(a):
        return math.sqrt(sum(v * v for v in a.values()))

    # -- public API -----------------------------------------------------
    def GetSearchResult(self, limit=50):
        query_vector, query_terms = self._GetSearchQueryVector()
        if not query_vector:
            return []

        q_norm = self._EuclideanNorm(query_vector)
        candidate_doc_ids = set(
            r[0] for r in db.session.query(DocumentLemma.document_id)
            .filter(DocumentLemma.lemma_id.in_(query_vector.keys()))
            .distinct().all()
        )

        results = []
        for doc_id in candidate_doc_ids:
            document = Document.query.get(doc_id)
            if document is None:
                continue
            if not self._passes_date_filter(document):
                continue

            doc_vector = Document.GetDocumentVector(doc_id)
            matched_terms = set()
            for lemma_id in query_vector:
                if lemma_id in doc_vector:
                    lemma = Lemma.query.get(lemma_id)
                    if lemma:
                        matched_terms.add(lemma.term)

            if self.allWordsTogether and len(matched_terms) < len(query_terms):
                continue  # require every query term to be present

            d_norm = self._EuclideanNorm(doc_vector)
            numerator = self._ScalarProduct(doc_vector, query_vector)
            rank = numerator / (d_norm * q_norm) if d_norm > 0 and q_norm > 0 else 0.0

            if rank <= 0:
                continue

            results.append(SearchResult(
                documentId=document.documentID,
                title=document.title,
                snippet=build_snippet(document.text, query_terms),
                rank=rank,
                date=document.date,
                matchedTerms=matched_terms,
            ))

        results.sort(key=lambda r: r.rank, reverse=True)
        return results[:limit]

    def _passes_date_filter(self, document):
        if self.dateStartString and document.date < self.dateStartString:
            return False
        if self.dateEndString and document.date > self.dateEndString:
            return False
        return True
