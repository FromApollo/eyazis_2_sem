"""
Text extraction for uploaded documents (PDF / DOCX / TXT), so the
information source ("множество естественно-языковых текстов") can be fed
into the system without manual copy-pasting -- required for the "приём
информации и её предварительная обработка" task from the assignment.
"""
import os
from io import BytesIO

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}


def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def extract_text(file_storage):
    """
    file_storage: a Werkzeug FileStorage object (from request.files).
    Returns extracted plain text, or raises ValueError on failure.
    """
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    data = file_storage.read()

    if ext == "txt":
        for encoding in ("utf-8", "cp1251", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode text file (unknown encoding).")

    if ext == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("PDF support requires the 'pypdf' package.")
        reader = PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError(
                "No extractable text found in this PDF (it may be a scanned "
                "image without OCR)."
            )
        return text

    if ext == "docx":
        try:
            import docx
        except ImportError:
            raise ValueError("DOCX support requires the 'python-docx' package.")
        document = docx.Document(BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        if not text:
            raise ValueError("No text found in this DOCX file.")
        return text

    raise ValueError(f"Unsupported file type: .{ext}")
