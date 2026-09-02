"""
Creates database tables and loads the test document collection.

Usage:
    python init_db.py            # create tables + seed test collection
    python init_db.py --reset    # drop all tables first, then recreate/seed
"""
import json
import sys
import os

from app import create_app
from models import db, Document
from search_engine import Indexer

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "test_collection.json")


def seed():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    if Document.query.count() > 0:
        print("Documents already present -- skipping seed (use --reset to reload).")
        return

    for doc in data["documents"]:
        d = Document(
            title=doc["title"],
            text=doc["text"],
            date=doc["date"],
            time=doc["time"],
        )
        db.session.add(d)
    db.session.commit()
    print(f"Inserted {len(data['documents'])} documents.")

    Indexer.rebuild_full_index()
    print("Index built (lemmas + TF-IDF weights).")


def main():
    app = create_app()
    with app.app_context():
        if "--reset" in sys.argv:
            db.drop_all()
            print("Dropped all tables.")
        db.create_all()
        print("Tables created.")
        seed()


if __name__ == "__main__":
    main()
