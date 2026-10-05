import io
import unittest

from app import DOCUMENTS, app, corpus_for, read_document
from summarizer import sentence_extraction, split_sentences, summarize, terms


class SummarizerTests(unittest.TestCase):
    def test_collection_and_sentence_method(self):
        self.assertEqual(len(DOCUMENTS), 4)
        self.assertEqual({d["language"] for d in DOCUMENTS}, {"en", "es"})
        self.assertEqual({d["domain"] for d in DOCUMENTS}, {"Медицина", "Критика искусства"})
        for item in DOCUMENTS:
            text = read_document(item["file"])
            self.assertEqual(len(split_sentences(text)), 30)
            result = summarize(text, item["language"], corpus_for(item["language"]))
            self.assertEqual(len(result["sentences"]), 10)
            self.assertEqual(len(result["keywords"]), 12)
            self.assertEqual([s["index"] for s in result["sentences"]],
                             sorted(s["index"] for s in result["sentences"]))

    def test_formula_and_exclusions(self):
        docs = ["Heart health. Heart sleep.", "Sleep quality."]
        sentences, scores, weights = sentence_extraction(docs[0], "en", docs)
        self.assertEqual(2, len(sentences))
        self.assertAlmostEqual(0.0, weights["sleep"])
        self.assertGreater(weights["heart"], 0)
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(terms("The heart 2026 corazón y presión", "es"),
                         ["the", "heart", "corazón", "presión"])

    def test_lsa(self):
        for item in DOCUMENTS:
            text = read_document(item["file"])
            result = summarize(text, item["language"], corpus_for(item["language"]), "lsa")
            self.assertEqual(len(result["sentences"]), 10)
            self.assertEqual(len(result["keywords"]), 12)


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_pages_result_download_and_print_control(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/help").status_code, 200)
        for item in DOCUMENTS:
            source = self.client.get("/source/" + item["file"])
            self.assertEqual(source.status_code, 200)
            self.assertIn(read_document(item["file"])[:50].encode(), source.data)
            for method in ("sentence", "lsa"):
                response = self.client.post("/summarize", data={"document": item["file"], "method": method, "count": "10"})
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"window.print()", response.data)
                self.assertIn(b"/source/" + item["file"].encode(), response.data)
                self.assertIn("Ключевые слова".encode(), response.data)
        downloaded = self.client.post("/download", data={"title": "Test", "source_url": "http://localhost/source/en_art.txt",
                                                          "sentences": ["First sentence."], "keywords": ["art", "light"]})
        self.assertEqual(downloaded.status_code, 200)
        self.assertIn(b"First sentence.", downloaded.data)

    def test_upload_and_errors(self):
        response = self.client.post("/upload", data={"language": "en", "method": "sentence",
            "file": (io.BytesIO(b"A clear first sentence. A second sentence describes the topic. "
                                b"A third sentence adds useful detail. A fourth sentence concludes."), "sample.txt")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/source/upload/", response.data)
        self.assertEqual(self.client.get("/source/unknown.txt").status_code, 404)
        self.assertEqual(self.client.post("/summarize", data={"document": "../x.txt"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
