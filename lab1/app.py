import json
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

from config import Config
from models import db, Document
from search_engine import Search, Indexer
from document_reader import extract_text, allowed_file
import metrics as metrics_module

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "test_collection.json")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    register_routes(app)
    return app


def register_routes(app):

    @app.route("/", methods=["GET"])
    def index():
        doc_count = Document.query.count()
        return render_template("index.html", doc_count=doc_count)

    @app.route("/search", methods=["GET"])
    def search():
        query = request.args.get("q", "").strip()
        all_words = request.args.get("all_words") == "on"
        date_start = request.args.get("date_start") or None
        date_end = request.args.get("date_end") or None

        results = []
        if query:
            searcher = Search(
                searchQuery=query,
                allWordsTogether=all_words,
                dateStartString=date_start,
                dateEndString=date_end,
            )
            results = searcher.GetSearchResult()

        return render_template(
            "results.html",
            query=query,
            results=results,
            all_words=all_words,
            date_start=date_start or "",
            date_end=date_end or "",
        )

    @app.route("/document/<int:doc_id>")
    def document_detail(doc_id):
        document = Document.query.get_or_404(doc_id)
        vector = Document.GetDocumentVector(doc_id)
        # top weighted terms for display
        from models import Lemma
        top_terms = []
        for lemma_id, w in sorted(vector.items(), key=lambda kv: kv[1], reverse=True)[:15]:
            lemma = Lemma.query.get(lemma_id)
            if lemma:
                top_terms.append((lemma.term, round(w, 4)))
        return render_template("document.html", document=document, top_terms=top_terms)

    @app.route("/documents")
    def document_list():
        documents = Document.query.order_by(Document.documentID.desc()).all()
        return render_template("documents.html", documents=documents)

    @app.route("/add", methods=["GET", "POST"])
    def add_document():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            text = request.form.get("text", "").strip()

            uploaded = request.files.get("file")
            if uploaded and uploaded.filename:
                if not allowed_file(uploaded.filename):
                    flash("Only .pdf, .docx and .txt files are supported.", "danger")
                    return redirect(url_for("add_document"))
                try:
                    extracted = extract_text(uploaded)
                except ValueError as e:
                    flash(f"Could not read file: {e}", "danger")
                    return redirect(url_for("add_document"))
                # File content is authoritative when provided; a manually
                # typed title/text still takes precedence if the person
                # filled it in themselves.
                if not text:
                    text = extracted.strip()
                if not title:
                    title = os.path.splitext(uploaded.filename)[0]

            if not title or not text:
                flash("Provide a title and either text or a file to upload.", "danger")
                return redirect(url_for("add_document"))

            now = datetime.now()
            document = Document(
                title=title,
                text=text,
                date=now.strftime("%Y-%m-%d"),
                time=now.strftime("%H:%M"),
            )
            document.AddDocumentToBase()
            flash(f'Document "{title}" added and indexed.', "success")
            return redirect(url_for("document_list"))

        return render_template("add_document.html")

    @app.route("/document/<int:doc_id>/delete", methods=["POST"])
    def delete_document(doc_id):
        ok = Document.DeleteDocumentFromBase(doc_id)
        if ok:
            Indexer.recompute_weights()
            flash("Document deleted.", "success")
        else:
            flash("Document not found.", "danger")
        return redirect(url_for("document_list"))

    # ---------------------------------------------------------------
    # Quality evaluation (metrics) against the built-in test collection
    # ---------------------------------------------------------------
    @app.route("/metrics")
    def metrics_page():
        if not os.path.exists(DATA_FILE):
            flash("Test collection file not found.", "danger")
            return redirect(url_for("index"))

        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)

        title_to_id = {d.title: d.documentID for d in Document.query.all()}

        per_query_results = []

        for q in data["queries"]:
            relevant_ids = {
                title_to_id[t] for t in q["relevant_titles"] if t in title_to_id
            }
            searcher = Search(searchQuery=q["query"])
            search_results = searcher.GetSearchResult(limit=len(title_to_id) or 20)
            ranked_ids = [r.documentId for r in search_results]

            m = metrics_module.evaluate_query(ranked_ids, relevant_ids)
            per_query_results.append({
                "query": q["query"],
                "num_relevant": len(relevant_ids),
                "num_retrieved": len(ranked_ids),
                "metrics": m,
                "top_results": [
                    {"title": r.title, "rank": round(r.rank, 4),
                     "relevant": r.documentId in relevant_ids,
                     "matched_terms": r.matchedTerms}
                    for r in search_results[:10]
                ],
            })

        # ROMIP search-track convention: microaverage each metric across
        # queries (queries with an empty relevant set are excluded inside
        # microaverage() via the None sentinel).
        summary = {
            "avg_precision": round(metrics_module.microaverage(
                [r["metrics"]["precision"] for r in per_query_results]), 4),
            "avg_recall": round(metrics_module.microaverage(
                [r["metrics"]["recall"] for r in per_query_results]), 4),
            "map": round(metrics_module.microaverage(
                [r["metrics"]["average_precision"] for r in per_query_results]), 4),
            "avg_precision@5": round(metrics_module.microaverage(
                [r["metrics"]["precision@5"] for r in per_query_results]), 4),
            "avg_precision@10": round(metrics_module.microaverage(
                [r["metrics"]["precision@10"] for r in per_query_results]), 4),
            "avg_r_precision": round(metrics_module.microaverage(
                [r["metrics"]["r_precision"] for r in per_query_results]), 4),
            "avg_f_measure": round(metrics_module.microaverage(
                [r["metrics"]["f_measure"] for r in per_query_results]), 4),
        }

        # averaged 11-point interpolated precision-recall curve across queries
        avg_curve = []
        n_points = len(per_query_results[0]["metrics"]["pr_curve"])
        for i in range(n_points):
            level = per_query_results[0]["metrics"]["pr_curve"][i][0]
            avg_p = sum(r["metrics"]["pr_curve"][i][1] for r in per_query_results) / len(per_query_results)
            avg_curve.append((level, round(avg_p, 4)))

        return render_template(
            "metrics.html",
            per_query_results=per_query_results,
            summary=summary,
            avg_curve=avg_curve,
        )

    @app.route("/help")
    def help_page():
        return render_template("help.html")

    @app.route("/reindex", methods=["POST"])
    def reindex():
        Indexer.rebuild_full_index()
        flash("Index rebuilt for all documents.", "success")
        return redirect(url_for("document_list"))


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
