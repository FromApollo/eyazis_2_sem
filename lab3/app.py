"""Flask interface for laboratory work 3, variant 18."""

from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flask import Flask, abort, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from summarizer import summarize


ROOT = Path(__file__).parent
CORPUS_DIR = ROOT / "corpus"
UPLOAD_DIR = ROOT / "uploads"
DOCUMENTS = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
DOCUMENT_BY_FILE = {item["file"]: item for item in DOCUMENTS}
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


def read_document(filename):
    if filename not in DOCUMENT_BY_FILE:
        abort(404)
    return (CORPUS_DIR / filename).read_text(encoding="utf-8")


def corpus_for(language):
    return [read_document(item["file"]) for item in DOCUMENTS if item["language"] == language]


@app.get("/")
def index():
    return render_template("index.html", documents=DOCUMENTS)


@app.get("/help")
def help_page():
    return render_template("help.html")


@app.get("/source/<filename>")
def source(filename):
    text = read_document(filename)
    return send_file(BytesIO(text.encode("utf-8")), mimetype="text/plain; charset=utf-8",
                     download_name=filename, as_attachment=False)


@app.get("/source/upload/<filename>")
def uploaded_source(filename):
    if not filename.endswith(".txt") or len(filename) != 36:
        abort(404)
    path = UPLOAD_DIR / filename
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="text/plain; charset=utf-8", as_attachment=False)


@app.post("/summarize")
def summarize_route():
    filename = request.form.get("document", "")
    method = request.form.get("method", "sentence")
    try:
        count = max(1, min(20, int(request.form.get("count", "10"))))
    except ValueError:
        count = 10
    if filename not in DOCUMENT_BY_FILE or method not in {"sentence", "lsa"}:
        abort(400)
    item = DOCUMENT_BY_FILE[filename]
    text = read_document(filename)
    result = summarize(text, item["language"], corpus_for(item["language"]), method, count)
    return render_template("result.html", item=item, result=result, count=count)


@app.post("/upload")
def upload():
    file = request.files.get("file")
    language = request.form.get("language", "")
    method = request.form.get("method", "sentence")
    if not file or not file.filename or not file.filename.lower().endswith(".txt"):
        return render_template("error.html", message="Выберите текстовый файл .txt в UTF-8."), 400
    if language not in {"en", "es"} or method not in {"sentence", "lsa"}:
        abort(400)
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render_template("error.html", message="Файл должен иметь кодировку UTF-8."), 400
    if len(text.strip()) < 50:
        return render_template("error.html", message="Текст слишком короткий: нужно не менее 50 символов."), 400
    UPLOAD_DIR.mkdir(exist_ok=True)
    stored_name = f"{uuid4().hex}.txt"
    (UPLOAD_DIR / stored_name).write_text(text, encoding="utf-8")
    result = summarize(text, language, corpus_for(language), method)
    item = {"title": secure_filename(file.filename), "language": language, "domain": "Загруженный текст"}
    source_url = url_for("uploaded_source", filename=stored_name, _external=True)
    return render_template("result.html", item=item, result=result, count=10,
                           source_url=source_url, uploaded=True)


@app.post("/download")
def download():
    """Save exactly the information displayed by the previous form."""
    title = request.form.get("title", "Документ")[:200]
    source_url = request.form.get("source_url", "")[:300]
    parsed = urlparse(source_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith("/source/"):
        abort(400)
    sentences = request.form.getlist("sentences")[:20]
    keywords = request.form.getlist("keywords")[:20]
    if not sentences:
        abort(400)
    content = "\n".join([f"Документ: {title}", f"Источник: {source_url}", "",
                         "Классический реферат:", *sentences, "", "Ключевые слова:",
                         ", ".join(keywords), ""])
    return send_file(BytesIO(content.encode("utf-8")), mimetype="text/plain; charset=utf-8",
                     as_attachment=True, download_name="summary.txt")


if __name__ == "__main__":
    app.run(port=5088, debug=True)
