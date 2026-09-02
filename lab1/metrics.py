"""
Quality-of-retrieval metrics, implemented per the official ROMIP'2004
metric set described in 2004_romip_metrix.pdf (M. Ageev, I. Kuralenok),
"search track" metrics:

    1. recall (полнота)
    2. precision (точность)
    3. average precision (средняя точность)
    4. precision(5)  -- precision at rank 5
    5. precision(10) -- precision at rank 10
    6. R-precision   -- precision at rank R = |relevant set|
    7. 11-point interpolated precision/recall curve, TREC methodology

F-measure (from the classification-track list, but broadly useful) is
also provided as a bonus combined metric.

Convention, per the document: queries with an empty relevant set are
undefined (0/0) and must be excluded before averaging -- callers should
filter such queries out before calling the *_mean_over_queries helpers.

All functions take:
    ranked_ids : list[int]   -- document ids returned by the system, in
                                 rank order (best first)
    relevant   : set[int]    -- ids of documents judged relevant for the
                                 query (the "ground truth" / etalon set)
"""


# --------------------------------------------------------------------------
# 1. Metrics on the (unordered) result set -- classification matrix
#    a = found & relevant, b = found & not relevant,
#    c = relevant & not found, d = not found & not relevant
# --------------------------------------------------------------------------
def recall(ranked_ids, relevant):
    """r = a / (a + c) -- fraction of relevant documents that were found."""
    if not relevant:
        return None  # undefined, per ROMIP convention (0/0)
    a = len(set(ranked_ids) & relevant)
    return a / len(relevant)


def precision(ranked_ids, relevant):
    """p = a / (a + b) -- fraction of found documents that are relevant."""
    if not ranked_ids:
        return None
    a = len(set(ranked_ids) & relevant)
    return a / len(ranked_ids)


def f_measure(p, r, beta=1.0):
    """F = (1+b^2) / (b^2/p + 1/r), the harmonic mean of precision/recall."""
    if p is None or r is None or (p == 0 and r == 0):
        return 0.0
    b2 = beta ** 2
    return (1 + b2) * p * r / (b2 * p + r)


# --------------------------------------------------------------------------
# 2. Metrics on the ranked sequence of documents
# --------------------------------------------------------------------------
def precision_at_n(ranked_ids, relevant, n):
    """precision(n): relevant docs among the first n results, divided by n."""
    if n <= 0:
        return 0.0
    top_n = ranked_ids[:n]
    hits = sum(1 for d in top_n if d in relevant)
    return hits / n


def r_precision(ranked_ids, relevant):
    """R-precision: precision(n) with n = number of relevant documents."""
    if not relevant:
        return None
    return precision_at_n(ranked_ids, relevant, len(relevant))


def average_precision(ranked_ids, relevant):
    """
    AvgPrec = (1/k) * sum_i prec_rel(i), where prec_rel(i) is the
    precision(pos(i)) at the rank of the i-th relevant document found
    (0 if that relevant document was not retrieved at all), for i = 1..k
    relevant documents.
    """
    if not relevant:
        return None
    k = len(relevant)
    hits = 0
    sum_prec_rel = 0.0
    for i, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in relevant:
            hits += 1
            sum_prec_rel += hits / i
    return sum_prec_rel / k


# --------------------------------------------------------------------------
# 3. 11-point interpolated precision/recall curve (TREC methodology)
# --------------------------------------------------------------------------
def eleven_point_curve(ranked_ids, relevant):
    """
    For each fixed recall level r_i in {0.0, 0.1, ..., 1.0}:
        p(r_i) = 0                                    if r_i > recall achieved
        p(r_i) = max( precision(n) for n >= pos(r_i) ) otherwise
    where pos(r_i) is the minimal result-list length at which recall r_i
    is first reached. Equivalently: the interpolated precision at level
    r_i is the maximum precision observed at any rank whose cumulative
    recall is >= r_i.
    """
    levels = [round(i / 10, 1) for i in range(11)]
    if not relevant:
        return [(lvl, 0.0) for lvl in levels]

    n_relevant = len(relevant)
    running = []  # (recall, precision) achieved after each retrieved doc
    hits = 0
    for i, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in relevant:
            hits += 1
        running.append((hits / n_relevant, hits / i))

    curve = []
    for level in levels:
        candidates = [p for r, p in running if r >= level]
        curve.append((level, max(candidates) if candidates else 0.0))
    return curve


# --------------------------------------------------------------------------
# 4. Per-query bundle + microaveraging across queries
#    (ROMIP uses microaveraging -- compute per query, then average --
#    for the search track)
# --------------------------------------------------------------------------
def evaluate_query(ranked_ids, relevant):
    """All ROMIP search-track metrics for a single query."""
    p = precision(ranked_ids, relevant)
    r = recall(ranked_ids, relevant)
    return {
        "precision": p,
        "recall": r,
        "f_measure": f_measure(p, r),
        "average_precision": average_precision(ranked_ids, relevant),
        "precision@5": precision_at_n(ranked_ids, relevant, 5),
        "precision@10": precision_at_n(ranked_ids, relevant, 10),
        "r_precision": r_precision(ranked_ids, relevant),
        "pr_curve": eleven_point_curve(ranked_ids, relevant),
    }


def microaverage(values):
    """Mean over a list of per-query metric values, skipping None (queries
    with no relevant documents are excluded, per ROMIP convention)."""
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0
