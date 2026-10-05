from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"
    __table_args__ = (UniqueConstraint("english", "pos", "domain", name="uq_dictionary_english_pos_domain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    english: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pos: Mapped[str] = mapped_column(String(20), nullable=False, default="*")
    german: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TranslationRun(Base):
    __tablename__ = "translation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="Без названия")
    domain: Mapped[str] = mapped_column(String(30), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    translated_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
