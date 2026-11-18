"""Turn an uploaded file into (page_number, text) pairs."""

import io

from pypdf import PdfReader

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}
VIRTUAL_PAGE_CHARS = 3000  # txt/md have no pages; we cut them into numbered sections


class UnsupportedFile(ValueError):
    pass


def _virtual_pages(text: str) -> list[tuple[int, str]]:
    pages: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) > VIRTUAL_PAGE_CHARS:
            pages.append(current)
            current = ""
        current += ("\n\n" if current else "") + para
    if current.strip():
        pages.append(current)
    return [(i + 1, p) for i, p in enumerate(pages)]


def load_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise UnsupportedFile(f"unsupported file type: {suffix or 'none'}")
    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
        except Exception as exc:  # pypdf raises many different errors on corrupt files
            raise UnsupportedFile("could not parse PDF") from exc
    else:
        try:
            pages = _virtual_pages(data.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise UnsupportedFile("text files must be UTF-8") from exc
    # PostgreSQL text cannot contain NUL bytes, which some PDF extractors emit.
    pages = [(n, t.replace("\x00", "")) for n, t in pages]
    pages = [(n, t) for n, t in pages if t.strip()]
    if not pages:
        raise UnsupportedFile("no extractable text (scanned PDF? OCR is out of scope)")
    return pages
