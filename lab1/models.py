"""
Database schema for the Information Retrieval System (vector model).

Corresponds to the class diagram "Document" from the lab specification,
plus two supporting index tables (Lemma, DocumentLemma) that realise the
inverted index used by the vector search model.

Tables
------
documents        -- one row per indexed document (poisk obraz dokumenta
                     is derived from this + document_lemmas)
lemmas           -- the dictionary (slovar'), one row per unique term
document_lemmas  -- the inverted index: (document, lemma) -> tf / weight
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Document(db.Model):
    __tablename__ = "documents"

    documentID = db.Column("document_id", db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    text = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)

    # Populated when the document came from the directory crawler; used to
    # detect the same file across repeated crawls and to decide whether it
    # needs re-indexing (see crawler.py).
    file_path = db.Column(db.String(1000), nullable=True, index=True)
    file_hash = db.Column(db.String(32), nullable=True)  # MD5 hex digest

    lemma_links = db.relationship(
        "DocumentLemma", backref="document", cascade="all, delete-orphan"
    )

    # ---- instance methods -------------------------------------------------
    def AddDocumentToBase(self):
        """Persist this document and (re)build its index entries."""
        db.session.add(self)
        db.session.commit()
        from search_engine import Indexer

        Indexer.index_document(self)
        return True

    # ---- static/class methods (per Document class diagram) ---------------
    @staticmethod
    def DeleteDocumentFromBase(documentID):
        doc = Document.query.get(documentID)
        if doc is None:
            return False
        db.session.delete(doc)
        db.session.commit()
        return True

    @staticmethod
    def GetLemmInverseFrequency(lemmId=None, lemmStr=None):
        """
        Bi = log(N / Pi)   (formula 1.5)
        Returns (ok: bool, value: float)
        """
        import math

        lemma = None
        if lemmId is not None:
            lemma = Lemma.query.get(lemmId)
        elif lemmStr is not None:
            lemma = Lemma.query.filter_by(term=lemmStr.lower()).first()
        if lemma is None:
            return False, 0.0

        N = db.session.query(Document).count()
        Pi = db.session.query(DocumentLemma).filter_by(lemma_id=lemma.id).count()
        if N == 0 or Pi == 0:
            return False, 0.0
        return True, math.log(N / Pi)

    @staticmethod
    def GetWordWeightInDocument(lemmStr, documentId):
        lemma = Lemma.query.filter_by(term=lemmStr.lower()).first()
        if lemma is None:
            return False, 0.0
        return Document.GetLemmWeightInDocument(lemma.id, documentId)

    @staticmethod
    def GetLemmWeightInDocument(lemmId, documentId):
        link = DocumentLemma.query.filter_by(
            lemma_id=lemmId, document_id=documentId
        ).first()
        if link is None:
            return False, 0.0
        return True, link.weight

    @staticmethod
    def GetDocumentVector(documentId):
        """Returns {lemma_id: weight} for the given document."""
        links = DocumentLemma.query.filter_by(document_id=documentId).all()
        return {l.lemma_id: l.weight for l in links}


class Lemma(db.Model):
    __tablename__ = "lemmas"

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(200), unique=True, nullable=False, index=True)

    doc_links = db.relationship(
        "DocumentLemma", backref="lemma", cascade="all, delete-orphan"
    )


class DocumentLemma(db.Model):
    __tablename__ = "document_lemmas"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.document_id"), nullable=False
    )
    lemma_id = db.Column(db.Integer, db.ForeignKey("lemmas.id"), nullable=False)
    tf = db.Column(db.Integer, nullable=False, default=0)  # Ndk, raw term count
    weight = db.Column(db.Float, nullable=False, default=0.0)  # normalised TF-IDF

    __table_args__ = (
        db.UniqueConstraint("document_id", "lemma_id", name="uq_doc_lemma"),
    )
