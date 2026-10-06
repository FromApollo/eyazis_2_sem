"""PostgreSQL storage for user documents and their generated summaries."""

import os

import psycopg
from psycopg.types.json import Json


def load_local_environment():
    """Read a local .env file without adding another runtime dependency."""
    env_file = __import__("pathlib").Path(__file__).with_name(".env")
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


load_local_environment()


class DatabaseUnavailable(RuntimeError):
    """Raised when the PostgreSQL connection has not been configured."""


def connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseUnavailable("Не задана переменная окружения DATABASE_URL.")
    try:
        return psycopg.connect(database_url, connect_timeout=5)
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable("Не удалось подключиться к PostgreSQL.") from error


def initialize_database():
    """Create application tables; safe to call every time the server starts."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id BIGSERIAL PRIMARY KEY,
                original_filename VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                language VARCHAR(2) NOT NULL CHECK (language IN ('en', 'es')),
                domain VARCHAR(100) NOT NULL DEFAULT 'Загруженный текст',
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id BIGSERIAL PRIMARY KEY,
                document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                method VARCHAR(20) NOT NULL CHECK (method IN ('sentence', 'lsa')),
                sentence_count SMALLINT NOT NULL CHECK (sentence_count BETWEEN 1 AND 20),
                classic_summary JSONB NOT NULL,
                keywords JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (document_id, method, sentence_count)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS summary_keywords (
                summary_id BIGINT NOT NULL REFERENCES summaries(id) ON DELETE CASCADE,
                term VARCHAR(100) NOT NULL,
                weight DOUBLE PRECISION NOT NULL,
                position SMALLINT NOT NULL,
                PRIMARY KEY (summary_id, term)
            )
        """)


def create_document(filename, language, content):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents (original_filename, title, language, content)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (filename, filename, language, content))
        return cur.fetchone()[0]


def get_document(document_id):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, original_filename, title, language, domain, content
            FROM documents WHERE id = %s
        """, (document_id,))
        row = cur.fetchone()
    if row is None:
        return None
    keys = ("id", "original_filename", "title", "language", "domain", "content")
    return dict(zip(keys, row))


def save_summary(document_id, method, sentence_count, result):
    """Persist output and prevent duplicate records for identical settings."""
    sentences = result["sentences"]
    keywords = result["keywords"]
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO summaries (document_id, method, sentence_count, classic_summary, keywords)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (document_id, method, sentence_count)
            DO UPDATE SET classic_summary = EXCLUDED.classic_summary,
                          keywords = EXCLUDED.keywords,
                          created_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (document_id, method, sentence_count, Json(sentences), Json(keywords)))
        summary_id = cur.fetchone()[0]
        cur.execute("DELETE FROM summary_keywords WHERE summary_id = %s", (summary_id,))
        cur.executemany("""
            INSERT INTO summary_keywords (summary_id, term, weight, position)
            VALUES (%s, %s, %s, %s)
        """, [(summary_id, keyword["term"], keyword["weight"], position)
              for position, keyword in enumerate(keywords, start=1)])

