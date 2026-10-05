from __future__ import annotations

import io
import os
import secrets
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import case, create_engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from analysis import analyze, lookup, tree_to_dict
from models import Base, DictionaryEntry, TranslationRun
from seed_data import seed_rows


DOMAINS = {"computer_science": "Computer science", "literature": "Литература"}
MAX_TEXT = 30000


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(24),
        DATABASE_URL=os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/lab4"),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    engine = create_engine(app.config["DATABASE_URL"], pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    app.extensions["db_engine"] = engine

    @app.context_processor
    def common():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)
        return {"domains": DOMAINS, "csrf_token": session["csrf_token"]}

    def check_csrf():
        if not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf_token", "")):
            abort(400, "Неверный токен формы. Обновите страницу и повторите действие.")

    @app.cli.command("init-db")
    def init_db():
        """Create PostgreSQL tables and seed editable dictionary entries."""
        Base.metadata.create_all(engine)
        with SessionLocal.begin() as db:
            existing = {(row.english, row.pos, row.domain): row for row in db.scalars(select(DictionaryEntry))}
            for english, pos, german, domain in seed_rows():
                entry = existing.get((english, pos, domain))
                if entry is None:
                    db.add(DictionaryEntry(english=english, pos=pos, german=german, domain=domain))
                elif not entry.german:
                    entry.german = german
        print("Таблицы и начальный словарь готовы.")

    @app.get("/")
    def index():
        with SessionLocal() as db:
            recent = db.scalars(select(TranslationRun).order_by(TranslationRun.id.desc()).limit(10)).all()
        return render_template("index.html", recent=recent)

    @app.post("/translate")
    def translate():
        check_csrf()
        domain = request.form.get("domain", "computer_science")
        if domain not in DOMAINS:
            abort(400, "Неизвестная предметная область")
        text = request.form.get("text", "").strip()
        upload = request.files.get("file")
        if upload and upload.filename:
            if not upload.filename.lower().endswith(".txt"):
                flash("Поддерживается загрузка только .txt в UTF-8.", "danger")
                return redirect(url_for("index"))
            try:
                text = upload.read().decode("utf-8-sig").strip()
            except UnicodeDecodeError:
                flash("Файл должен быть в кодировке UTF-8.", "danger")
                return redirect(url_for("index"))
        if not text or len(text) > MAX_TEXT:
            flash(f"Введите английский текст длиной от 1 до {MAX_TEXT} символов.", "danger")
            return redirect(url_for("index"))
        title = (request.form.get("title", "").strip() or text[:80])[:160]
        with SessionLocal.begin() as db:
            entries = db.scalars(
                select(DictionaryEntry)
                .where(DictionaryEntry.domain.in_(("general", domain)))
                .order_by(case((DictionaryEntry.domain == "general", 0), else_=1))
            ).all()
            dictionary = {}
            for entry in entries:
                key = (entry.english, entry.pos)
                if entry.german or key not in dictionary:
                    dictionary[key] = entry.german
            try:
                result = analyze(text, dictionary)
            except RuntimeError as exc:
                flash(str(exc), "danger")
                return redirect(url_for("index"))
            if result["word_count"] == 0:
                flash("В тексте не найдены английские слова.", "danger")
                return redirect(url_for("index"))
            known = {(e.english, e.pos) for e in entries}
            for word, tag in result["seen_words"]:
                if (word, tag) not in known:
                    db.add(DictionaryEntry(english=word, pos=tag, german=lookup(word, tag, dictionary), domain=domain))
            run = TranslationRun(
                title=title, domain=domain, source_text=text,
                translated_text=result["translated_text"],
                word_count=result["word_count"], translated_count=result["translated_count"],
                result={"rows": result["rows"], "sentences": result["sentences"]},
            )
            db.add(run)
            db.flush()
            run_id = run.id
        flash("Перевод сохранен. Новые слова добавлены в словарь; пустые переводы можно заполнить вручную.", "success")
        return redirect(url_for("run_detail", run_id=run_id))

    @app.get("/runs/<int:run_id>")
    def run_detail(run_id):
        with SessionLocal() as db:
            run = db.get(TranslationRun, run_id)
            if run is None:
                abort(404)
        chosen = request.args.get("sentence", "0")
        try:
            index = int(chosen)
        except ValueError:
            index = 0
        sentences = run.result["sentences"]
        index = max(0, min(index, len(sentences) - 1))
        trees = [tree_to_dict(sentence["tree"]) for sentence in sentences]
        return render_template("result.html", run=run, selected=index, trees=trees)

    def format_report(run):
        lines = [
            "Лабораторная работа 4. Вариант 3: англо-немецкий перевод",
            f"Название: {run.title}",
            f"Предметная область: {DOMAINS[run.domain]}",
            f"Дата: {run.created_at:%Y-%m-%d %H:%M}",
            f"Слов во входном тексте: {run.word_count}",
            f"Переведено слов: {run.translated_count}",
            "", "Исходный текст:", run.source_text, "", "Перевод:", run.translated_text,
            "", "Частотный словарь (по убыванию частоты):",
            "Частота\tСлово\tПеревод\tPOS\tРасшифровка",
        ]
        for row in run.result["rows"]:
            lines.append(f"{row['frequency']}\t{row['word']}\t{row['translation'] or '—'}\t{row['tag']}\t{row['meaning']}")
        return "\n".join(lines) + "\n"

    @app.get("/runs/<int:run_id>/export.txt")
    def export_run(run_id):
        with SessionLocal() as db:
            run = db.get(TranslationRun, run_id)
            if run is None:
                abort(404)
        data = format_report(run).encode("utf-8-sig")
        return send_file(io.BytesIO(data), as_attachment=True, download_name=f"translation_{run.id}.txt", mimetype="text/plain; charset=utf-8")

    @app.get("/runs/<int:run_id>/print")
    def print_run(run_id):
        with SessionLocal() as db:
            run = db.get(TranslationRun, run_id)
            if run is None:
                abort(404)
        return render_template("print.html", run=run)

    @app.get("/dictionary")
    def dictionary_view():
        query = request.args.get("q", "").strip()[:120]
        status = request.args.get("status", "all")
        page = max(1, request.args.get("page", 1, type=int))
        with SessionLocal() as db:
            stmt = select(DictionaryEntry)
            if query:
                like = f"%{query}%"
                stmt = stmt.where(or_(DictionaryEntry.english.ilike(like), DictionaryEntry.german.ilike(like)))
            if status == "missing":
                stmt = stmt.where(DictionaryEntry.german == "")
            total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            entries = db.scalars(stmt.order_by(DictionaryEntry.english, DictionaryEntry.pos).offset((page - 1) * 50).limit(50)).all()
        return render_template("dictionary.html", entries=entries, query=query, status=status, page=page, total=total)

    @app.post("/dictionary")
    def dictionary_add():
        check_csrf()
        english = request.form.get("english", "").strip().lower()
        pos = request.form.get("pos", "*").strip().upper() or "*"
        german = request.form.get("german", "").strip()
        domain = request.form.get("domain", "general")
        if not (english and german and len(english) <= 120 and len(german) <= 240 and len(pos) <= 20):
            flash("Заполните английское слово и немецкий перевод.", "danger")
            return redirect(url_for("dictionary_view"))
        if domain not in {"general", *DOMAINS}:
            abort(400)
        with SessionLocal.begin() as db:
            existing = db.scalar(select(DictionaryEntry).where(DictionaryEntry.english == english, DictionaryEntry.pos == pos, DictionaryEntry.domain == domain))
            if existing:
                flash("Такая пара слово/POS уже есть. Используйте изменение записи.", "warning")
            else:
                db.add(DictionaryEntry(english=english, pos=pos, german=german, domain=domain))
                flash("Запись добавлена.", "success")
        return redirect(url_for("dictionary_view"))

    @app.post("/dictionary/<int:entry_id>/edit")
    def dictionary_edit(entry_id):
        check_csrf()
        german = request.form.get("german", "").strip()
        if len(german) > 240:
            abort(400)
        with SessionLocal.begin() as db:
            entry = db.get(DictionaryEntry, entry_id)
            if entry is None:
                abort(404)
            entry.german = german
        flash("Перевод обновлен. Для применения к старому тексту выполните перевод повторно.", "success")
        return redirect(request.referrer or url_for("dictionary_view"))

    @app.post("/dictionary/<int:entry_id>/delete")
    def dictionary_delete(entry_id):
        check_csrf()
        with SessionLocal.begin() as db:
            entry = db.get(DictionaryEntry, entry_id)
            if entry is None:
                abort(404)
            db.delete(entry)
        flash("Запись удалена.", "success")
        return redirect(url_for("dictionary_view"))

    @app.errorhandler(413)
    def too_large(_):
        flash("Файл слишком большой (максимум 1 МБ).", "danger")
        return redirect(url_for("index"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False)
