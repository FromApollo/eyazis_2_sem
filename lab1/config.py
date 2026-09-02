import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """
    Application configuration.

    The system is designed to work with PostgreSQL (per the assignment,
    variant 9: LAN-scoped IR system with a PostgreSQL back-end). For local
    development / testing without a running PostgreSQL server, the
    DATABASE_URL environment variable can be pointed at SQLite instead --
    the SQLAlchemy layer is agnostic to the concrete engine.

    Example PostgreSQL connection string:
        postgresql+psycopg2://ir_user:ir_password@localhost:5432/ir_system

    Example SQLite (dev/test) connection string:
        sqlite:///ir_system.db
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "lab1-vector-ir-secret-key")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://ir_user:ir_password@localhost:5432/ir_system",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # A word must appear in at least this fraction of documents to be
    # considered "too common" and dropped as a stop-word candidate on top
    # of the static stop-word list (keeps the index compact).
    MAX_DOC_FREQUENCY_RATIO = 0.9
