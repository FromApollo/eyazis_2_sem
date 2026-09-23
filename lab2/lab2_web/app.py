# -*- coding: utf-8 -*-
"""
Веб-приложение «Автоматическое распознавание языка текста» (вариант 10).
Flask + Bootstrap 5. Поддерживает загрузку PDF-документов, их классификацию
тремя методами (частотных слов, коротких слов, нейросетевой), просмотр
активных ссылок на документы, сводную статистику, экспорт результатов
в файл (JSON/CSV/PDF-отчёт) и печать, а также справочный раздел.
"""

import os
import io
import csv
import json
import uuid
import subprocess
import tempfile

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, send_file, abort, jsonify
)
from werkzeug.utils import secure_filename

from langid_core import service

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
STATIC_IMG_DIR = os.path.join(BASE_DIR, "static", "img")

ALLOWED_EXTENSIONS = {"pdf"}

app = Flask(__name__)
app.secret_key = "lab2-variant10-secret-key"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

service.init_db()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.context_processor
def inject_globals():
    return {
        "LANG_NAMES": service.LANG_NAMES,
        "METHOD_NAMES": service.METHOD_NAMES,
        "models_ready": service.models_ready(),
    }


# --------------------------------------------------------------------------
# Главная страница
# --------------------------------------------------------------------------

@app.route("/")
def index():
    docs = service.list_documents()
    recent = docs[:5]
    stats = service.compute_summary()
    return render_template("index.html", recent=recent, stats=stats, total=len(docs))


# --------------------------------------------------------------------------
# Загрузка документа
# --------------------------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():
    if not service.models_ready():
        flash("Модели ещё не построены. Сначала выполните построение ПОЯ (см. раздел «Справка»).", "danger")
        return redirect(url_for("index"))

    file = request.files.get("document")
    if file is None or file.filename == "":
        flash("Файл не выбран.", "warning")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Допускается загрузка только файлов формата PDF.", "danger")
        return redirect(url_for("index"))

    true_language = request.form.get("true_language") or None
    if true_language not in ("ru", "en", None):
        true_language = None

    original_filename = secure_filename(file.filename) or "document.pdf"
    stored_filename = f"{uuid.uuid4().hex[:8]}_{original_filename}"
    save_path = os.path.join(UPLOAD_DIR, stored_filename)
    file.save(save_path)
    size_bytes = os.path.getsize(save_path)

    try:
        record = service.add_document(stored_filename, original_filename, true_language, size_bytes)
    except Exception as exc:
        os.remove(save_path)
        flash(f"Не удалось обработать документ: {exc}", "danger")
        return redirect(url_for("index"))

    flash("Документ успешно загружен и классифицирован.", "success")
    return redirect(url_for("document_detail", doc_id=record["id"]))


# --------------------------------------------------------------------------
# Тестовая коллекция документов
# --------------------------------------------------------------------------

@app.route("/documents")
def documents():
    docs = service.list_documents()
    return render_template("documents.html", docs=docs)


@app.route("/documents/<doc_id>")
def document_detail(doc_id):
    doc = service.get_document(doc_id)
    if doc is None:
        abort(404)
    return render_template("document_detail.html", doc=doc)


@app.route("/documents/<doc_id>/set-true-language", methods=["POST"])
def set_true_language(doc_id):
    true_language = request.form.get("true_language") or None
    if true_language not in ("ru", "en", None):
        true_language = None
    updated = service.update_true_language(doc_id, true_language)
    if updated is None:
        abort(404)
    flash("Истинный язык документа обновлён.", "success")
    return redirect(url_for("document_detail", doc_id=doc_id))


@app.route("/documents/<doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    if service.delete_document(doc_id):
        flash("Документ удалён из тестовой коллекции.", "success")
    else:
        flash("Документ не найден.", "warning")
    return redirect(url_for("documents"))


# Активная ссылка на исходный PDF-документ (просмотр в браузере)
@app.route("/files/<doc_id>")
def serve_file(doc_id):
    doc = service.get_document(doc_id)
    if doc is None:
        abort(404)
    return send_from_directory(UPLOAD_DIR, doc["stored_filename"],
                                as_attachment=False,
                                download_name=doc["original_filename"],
                                mimetype="application/pdf")


# --------------------------------------------------------------------------
# Сводная статистика
# --------------------------------------------------------------------------

def _generate_charts(stats: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(STATIC_IMG_DIR, exist_ok=True)
    methods = ["freq_words", "short_words", "neural"]
    names = ["Частотных\nслов", "Коротких\nслов", "Нейросетевой"]
    summary = stats["summary"]

    if stats["labeled_count"] == 0:
        for fname in ("chart_accuracy.png", "chart_time.png"):
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.text(0.5, 0.5, "Нет данных\n(не указан истинный язык\nни для одного документа)",
                    ha="center", va="center", fontsize=11)
            ax.axis("off")
            plt.tight_layout()
            plt.savefig(os.path.join(STATIC_IMG_DIR, fname), dpi=140)
            plt.close(fig)
        return

    acc = [summary[m]["accuracy_percent"] or 0 for m in methods]
    time_ms = [summary[m]["avg_time_ms"] or 0 for m in methods]
    colors = ["#5dade2", "#58d68d", "#f5b041"]

    fig, ax = plt.subplots(figsize=(5, 3.4))
    bars = ax.bar(names, acc, color=colors)
    ax.set_ylim(0, 110)
    ax.set_title("Точность классификации, %")
    for b, v in zip(bars, acc):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.1f}%", ha="center")
    plt.tight_layout()
    plt.savefig(os.path.join(STATIC_IMG_DIR, "chart_accuracy.png"), dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 3.4))
    bars = ax.bar(names, time_ms, color=colors)
    ax.set_title("Среднее время обработки, мс/документ")
    top = max(time_ms) if max(time_ms) > 0 else 1
    for b, v in zip(bars, time_ms):
        ax.text(b.get_x() + b.get_width() / 2, v + top * 0.02, f"{v:.3f}", ha="center")
    plt.tight_layout()
    plt.savefig(os.path.join(STATIC_IMG_DIR, "chart_time.png"), dpi=140)
    plt.close(fig)


@app.route("/statistics")
def statistics():
    stats = service.compute_summary()
    _generate_charts(stats)
    docs = service.list_documents()
    return render_template("statistics.html", stats=stats, docs=docs)


# --------------------------------------------------------------------------
# Экспорт результатов в файл (JSON / CSV / печатный PDF-отчёт)
# --------------------------------------------------------------------------

@app.route("/export/json")
def export_json():
    docs = service.list_documents()
    stats = service.compute_summary()
    payload = json.dumps({"documents": docs, "summary": stats}, ensure_ascii=False, indent=2)
    buf = io.BytesIO(payload.encode("utf-8"))
    return send_file(buf, mimetype="application/json", as_attachment=True,
                      download_name="language_id_results.json")


@app.route("/export/csv")
def export_csv():
    docs = service.list_documents()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["file", "true_language", "freq_words_predicted", "freq_words_correct",
                      "short_words_predicted", "short_words_correct",
                      "neural_predicted", "neural_correct", "uploaded_at"])
    for r in docs:
        m = r["methods"]
        writer.writerow([
            r["original_filename"], r.get("true_language") or "",
            m["freq_words"]["predicted"], m["freq_words"]["correct"],
            m["short_words"]["predicted"], m["short_words"]["correct"],
            m["neural"]["predicted"], m["neural"]["correct"],
            r["uploaded_at"],
        ])
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                      download_name="language_id_results.csv")


@app.route("/export/pdf-report")
def export_pdf_report():
    docs = service.list_documents()
    stats = service.compute_summary()
    _generate_charts(stats)
    html = render_template("report_print.html", docs=docs, stats=stats, for_pdf=True)

    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "report.html")
        pdf_path = os.path.join(tmp, "report.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        subprocess.run(
            ["wkhtmltopdf", "--enable-local-file-access", "--quiet", html_path, pdf_path],
            check=True, cwd=BASE_DIR,
        )
        with open(pdf_path, "rb") as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=True,
                      download_name="language_id_report.pdf")


@app.route("/print")
def print_report():
    docs = service.list_documents()
    stats = service.compute_summary()
    _generate_charts(stats)
    return render_template("report_print.html", docs=docs, stats=stats, for_pdf=False)


# --------------------------------------------------------------------------
# Справка
# --------------------------------------------------------------------------

@app.route("/help")
def help_page():
    expand_all = request.args.get("expand") == "1"
    return render_template("help.html", expand_all=expand_all)


# --------------------------------------------------------------------------
# Административная функция: пересборка ПОЯ и нейросетевой модели
# --------------------------------------------------------------------------

@app.route("/admin/rebuild-profiles", methods=["POST"])
def rebuild_profiles():
    from scripts.build_profiles import build_all
    try:
        log_lines = build_all()
        service.reload_models()
        flash("Профили языков и нейросетевая модель успешно пересобраны.", "success")
        flash(" / ".join(log_lines), "secondary")
    except Exception as exc:
        flash(f"Ошибка при пересборке профилей: {exc}", "danger")
    return redirect(url_for("help_page"))


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
