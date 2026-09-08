"""
Directory crawler ("паук") for the information retrieval system.

Per variant 9's LAN deployment scope, this walks a folder tree on the
local filesystem (or a mounted network share) with os.walk, finds
supported files (.txt, .pdf, .docx), and indexes them -- this is the
"агент (паук, кроулер)" component described in the assignment's theory
section ("поисковые системы обычно состоят из трёх компонентов:
агент... база данных... поисковый механизм").

Deduplication: each crawled file is tracked by its filesystem path and
an MD5 hash of its contents.
    - path not seen before          -> extract text, add as a new document
    - path seen, hash unchanged     -> skip (nothing to do)
    - path seen, hash changed       -> re-extract text, update the
                                        existing document and re-index it
"""
import hashlib
import os
from datetime import datetime

from models import db, Document
from search_engine import Indexer
from document_reader import extract_text_from_path, allowed_file

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB safety cap per file


def compute_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class CrawlResult:
    """Accumulates what happened during one crawl, for reporting in the UI."""

    def __init__(self, root_path):
        self.root_path = root_path
        self.added = []              # list[str] file paths
        self.updated = []            # list[str] file paths
        self.skipped_unchanged = []  # list[str] file paths (hash matched)
        self.skipped_unsupported = []  # list[str] file paths (wrong extension)
        self.errors = []             # list[(path, message)]

    @property
    def total_scanned(self):
        return (len(self.added) + len(self.updated) +
                len(self.skipped_unchanged) + len(self.skipped_unsupported) +
                len(self.errors))


def crawl_directory(root_path):
    """
    Walks root_path recursively looking for .txt / .pdf / .docx files and
    indexes new/changed ones. Returns a CrawlResult summarising the run.
    """
    result = CrawlResult(root_path)

    if not root_path or not os.path.isdir(root_path):
        result.errors.append((root_path or "", "Path does not exist or is not a directory."))
        return result

    for dirpath, _dirnames, filenames in os.walk(root_path, followlinks=False):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)

            if not allowed_file(filename):
                result.skipped_unsupported.append(full_path)
                continue

            try:
                size = os.path.getsize(full_path)
                if size > MAX_FILE_SIZE:
                    result.errors.append(
                        (full_path, f"File too large ({size // 1024} KB) -- skipped.")
                    )
                    continue

                file_hash = compute_md5(full_path)
                existing = Document.query.filter_by(file_path=full_path).first()

                if existing and existing.file_hash == file_hash:
                    result.skipped_unchanged.append(full_path)
                    continue

                text = extract_text_from_path(full_path)
                now = datetime.now()

                if existing:
                    existing.text = text
                    existing.file_hash = file_hash
                    existing.date = now.strftime("%Y-%m-%d")
                    existing.time = now.strftime("%H:%M")
                    db.session.commit()
                    Indexer.index_document(existing, recompute=False)
                    result.updated.append(full_path)
                else:
                    title = os.path.splitext(filename)[0]
                    doc = Document(
                        title=title,
                        text=text,
                        date=now.strftime("%Y-%m-%d"),
                        time=now.strftime("%H:%M"),
                        file_path=full_path,
                        file_hash=file_hash,
                    )
                    db.session.add(doc)
                    db.session.commit()
                    Indexer.index_document(doc, recompute=False)
                    result.added.append(full_path)

            except ValueError as e:
                # extraction failures (e.g. scanned PDF with no text layer)
                result.errors.append((full_path, str(e)))
            except Exception as e:  # pragma: no cover -- defensive
                db.session.rollback()
                result.errors.append((full_path, f"Unexpected error: {e}"))

    if result.added or result.updated:
        Indexer.recompute_weights()

    return result
