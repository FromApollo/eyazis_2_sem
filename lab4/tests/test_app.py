import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis import analyze
from app import create_app
from models import DictionaryEntry, TranslationRun
from seed_data import seed_rows


class TranslationAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "test.db"
        self.app = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}", "SECRET_KEY": "test-key"})
        self.runner = self.app.test_cli_runner()
        result = self.runner.invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.client = self.app.test_client()
        self.client.get("/")

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp.cleanup()

    def token(self):
        with self.client.session_transaction() as sess:
            return sess["csrf_token"]

    def test_translation_tree_frequency_and_export(self):
        response = self.client.post("/translate", data={
            "csrf_token": self.token(), "domain": "computer_science",
            "text": "A neural network uses data. Data improves accuracy.",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Синтаксическое дерево".encode(), response.data)
        self.assertIn(b'class="syntax-tree"', response.data)
        self.assertIn(b'class="syntax-node syntax-leaf"', response.data)
        self.assertIn("neuronales Netzwerk".encode(), response.data)
        self.assertIn("Частотный словарь".encode(), response.data)
        with Session(self.app.extensions["db_engine"]) as db:
            run = db.scalar(select(TranslationRun).order_by(TranslationRun.id.desc()))
            self.assertEqual(run.word_count, 8)
            self.assertEqual(len(run.result["sentences"]), 2)
            self.assertEqual(run.result["rows"][0]["word"], "data")
            run_id = run.id
        export = self.client.get(f"/runs/{run_id}/export.txt")
        self.assertEqual(export.status_code, 200)
        self.assertTrue(export.data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Частотный словарь".encode(), export.data)
        self.assertEqual(self.client.get(f"/runs/{run_id}/print").status_code, 200)

    def test_unknown_word_is_added_then_corrected(self):
        self.client.post("/translate", data={
            "csrf_token": self.token(), "domain": "literature", "text": "The moonbeam shines."
        })
        engine = self.app.extensions["db_engine"]
        with Session(engine) as db:
            entry = db.scalar(select(DictionaryEntry).where(DictionaryEntry.english == "moonbeam"))
            self.assertIsNotNone(entry)
            self.assertEqual(entry.german, "")
            entry_id = entry.id
        self.client.post(f"/dictionary/{entry_id}/edit", data={"csrf_token": self.token(), "german": "Mondstrahl"})
        response = self.client.post("/translate", data={
            "csrf_token": self.token(), "domain": "literature", "text": "The moonbeam shines."
        }, follow_redirects=True)
        self.assertIn("Mondstrahl".encode(), response.data)

    def test_csrf_blocks_mutation(self):
        self.assertEqual(self.client.post("/dictionary", data={"english": "x", "german": "y"}).status_code, 400)

    def test_morphological_fallback(self):
        dictionary = {(word, pos): german for word, pos, german, _ in seed_rows()}
        result = analyze("Classifiers work.", dictionary)
        self.assertIn("Klassifikator", result["translated_text"])
        self.assertEqual(result["word_count"], 2)

    def test_empty_domain_entry_does_not_hide_general_translation(self):
        with Session(self.app.extensions["db_engine"]) as db:
            db.add(DictionaryEntry(english="simple", pos="JJ", german="", domain="computer_science"))
            db.commit()
        response = self.client.post("/translate", data={
            "csrf_token": self.token(), "domain": "computer_science", "text": "A simple model."
        }, follow_redirects=True)
        self.assertIn("einfach".encode(), response.data)

    def test_both_demo_texts_have_complete_dictionary_coverage(self):
        base = Path(__file__).resolve().parents[1] / "static" / "samples"
        for domain in ("computer_science", "literature"):
            dictionary = {(word, pos): german for word, pos, german, area in seed_rows()
                          if area in ("general", domain)}
            text = (base / f"{domain}.txt").read_text(encoding="utf-8")
            result = analyze(text, dictionary)
            self.assertEqual(result["translated_count"], result["word_count"], domain)


if __name__ == "__main__":
    unittest.main()
