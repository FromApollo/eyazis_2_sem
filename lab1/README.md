# Vector-Model Information Retrieval System

Lab 1 — "Разработка информационно-поисковой системы. Реализация методов
оценки качества её работы"

**Variant 9**: user interface, deployment scope — local area network,
search strategy — vector model, language — English.
Stack: Python 3 / Flask / SQLAlchemy / PostgreSQL / Jinja2 / Bootstrap 5.

## 1. Architecture

```
lab1/
├── app.py                Flask routes (search UI, document CRUD, crawl, metrics, help)
├── config.py              Configuration (DB connection string, etc.)
├── models.py               SQLAlchemy models: Document, Lemma, DocumentLemma
├── search_engine.py       Indexer, tokenizer/stemmer, Search / SearchResult,
│                           smart snippet builder, autocomplete suggestions
├── document_reader.py     PDF / DOCX / TXT text extraction (uploads + disk paths)
├── crawler.py              Directory crawler ("паук"): os.walk + MD5 dedup
├── metrics.py              Precision, recall, F-measure, AP/MAP, R-precision, 11-point PR curve
├── init_db.py               Creates tables and loads the test collection
├── data/test_collection.json     20 English documents + 5 judged queries
├── templates/              Jinja2 + Bootstrap templates (incl. help.html, crawl.html)
├── static/                 style.css + autocomplete.js
└── requirements.txt
```

### Database schema (PostgreSQL)

| Table            | Purpose                                                |
|-------------------|---------------------------------------------------------|
| `documents`        | title, text, date, time, file_path, file_hash — the raw document collection |
| `lemmas`            | the dictionary (словарь) — one row per unique term      |
| `document_lemmas`   | inverted index: (document, lemma) → tf, TF-IDF weight   |

`file_path` / `file_hash` are populated when a document comes from the
directory crawler (`crawler.py`) and are used to detect unchanged /
changed / new files on repeated crawls (MD5 dedup). They are `NULL` for
documents added by pasting text or via a one-off file upload.

This mirrors the `Document` / `Search` / `SearchResult` class diagrams from
the assignment: `Document` exposes `AddDocumentToBase`,
`DeleteDocumentFromBase`, `GetLemmInverseFrequency`,
`GetWordWeightInDocument`, `GetLemmWeightInDocument`, `GetDocumentVector`;
`Search` builds the query vector and returns ranked `SearchResult` objects.

### Vector-model algorithm

1. **Tokenising** — text is lower-cased, split into words, English stop
   words are removed, and a lightweight suffix-stripping stemmer folds
   inflections (`searching` → `search`) — see `search_engine.tokenize`.
2. **Indexing** — for each document, term frequency `tf` (Ndk) is stored
   per (document, term) pair (`Indexer.index_document` /
   `rebuild_full_index`).
3. **Weighting** — inverse document frequency `Bi = log(N / Pi)` (formula
   1.5) and term weight `Aij = tf * Bi` (formula 1.6) are computed, then
   each document vector is Euclidean-normalised (`Indexer.recompute_weights`),
   matching the normalised TF-IDF formula in the lab text.
4. **Query vector** — binary: `wqj = 1` if the term is present in the
   query, else `0`.
5. **Ranking** — cosine similarity `r(D,Q) = (D·Q) / (‖D‖·‖Q‖)`
   (`Search.GetSearchResult`), sorted descending.

Optional filters: "require all query words" (AND semantics on top of the
vector ranking) and a document date range.

## 2. Setup

### 2.1 PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER ir_user WITH PASSWORD 'ir_password';"
sudo -u postgres psql -c "CREATE DATABASE ir_system OWNER ir_user;"
```

### 2.2 Python environment

```bash
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2.3 Configure connection string (optional — defaults shown)

```bash
export DATABASE_URL="postgresql+psycopg2://ir_user:ir_password@localhost:5432/ir_system"
```

For quick local testing without PostgreSQL installed, SQLite also works:

```bash
export DATABASE_URL="sqlite:///ir_system.db"
```

### 2.4 Initialise the database and load the test collection

```bash
python init_db.py            # first run
python init_db.py --reset    # drop & recreate + reseed
```

### 2.5 Run

```bash
python app.py
```

Open `http://localhost:5000` (or `http://<server-LAN-IP>:5000` from
another machine on the same local network, consistent with variant 9's
LAN deployment scope).

## 3. Using the system

- **Search** (`/`, `/search`) — enter an English query; results are
  ranked by cosine similarity, with title, snippet (first 300 chars),
  the query words actually found in the document, rank score and date.
  Optional "require all query words" (AND filter) and a date range.
- **Documents** (`/documents`) — browse / delete indexed documents,
  trigger a full re-index.
- **Add document** (`/add`) — add a document either by pasting text or by
  **uploading a .pdf, .docx or .txt file** (text is extracted
  automatically via `document_reader.py`). It is tokenised, weighted and
  merged into the index immediately (`AddDocumentToBase`).
- **Quality metrics** (`/metrics`) — runs all 5 test queries from
  `data/test_collection.json` against the current index and reports the
  official ROMIP'2004 search-track metrics (see `2004_romip_metrix.pdf`):
  precision, recall, F-measure, average precision (mean = MAP),
  precision(5), precision(10), R-precision, and an averaged 11-point
  interpolated Precision/Recall curve (TREC methodology), each with a
  chart and per-query breakdown with relevant hits highlighted.
- **Help** (`/help`) — in-app guide: what the system does, how to search,
  how to add/manage documents, crawling folders, search suggestions and
  snippets, what each quality metric means, and troubleshooting tips.
  Inline ⓘ tooltips on the search and metrics pages give short
  explanations next to the relevant controls.
- **Crawl folder** (`/crawl`) — point the crawler ("паук") at a directory
  on the server's filesystem (or a mounted LAN share); it walks every
  subfolder with `os.walk`, extracts text from `.txt`/`.pdf`/`.docx`
  files, and indexes them. Each file is tracked by its path and an MD5
  hash of its contents: unchanged files are skipped, changed files are
  re-indexed, new files are added — safe to re-run on the same folder
  repeatedly (`crawler.py`).
- **Search suggestions** — as you type into the search box, a dropdown
  (`/api/suggest`, `static/autocomplete.js`) suggests matching dictionary
  terms and document titles drawn from the system's own index, not an
  external API — keeping the system self-contained for LAN deployment.
- **Smart snippets** — instead of showing the first 300 characters of a
  document, search results show the excerpt with the highest density of
  query-word matches, with those words shown in **bold**
  (`search_engine.build_snippet`).

## 4. Test collection

`data/test_collection.json` contains 20 short English documents spanning
several topics (Python/Flask/web development, databases/SQL, machine
learning, and information retrieval itself) plus 5 queries with manually
assigned relevance judgments, used as the "etalon" (ground truth) set for
the quality metrics described in section 2004_romip_metrix (precision,
recall, F-measure, average precision / MAP, NDCG).

## 5. Notes on the implementation

- No third-party NLP corpora are downloaded at runtime (stop words and
  the stemmer are self-contained), so the system can run fully offline
  on an isolated LAN, consistent with variant 9.
- `Flask-SQLAlchemy` is used as the ORM/data-access layer over
  PostgreSQL; `psycopg2-binary` is the driver.
- Frontend: Bootstrap 5 (CDN) + Jinja2 server-rendered templates;
  Chart.js (CDN) renders the metrics graphs.
- File upload uses `pypdf` for PDF and `python-docx` for DOCX; scanned
  PDFs without a text layer cannot be read (no OCR is performed).
- The Flask development server (`app.run`) is used for demonstration;
  for real LAN deployment a production WSGI server (e.g. gunicorn +
  nginx) should front the application.
