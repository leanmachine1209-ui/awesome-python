"""Free-text document ingestion: plain text, Markdown, PDF, and Word.

These formats have no tabular structure, so each meaningful chunk (a paragraph)
becomes a text ``Event`` that the summarizer can mine for action items. An
optional leading date in a chunk is used as its timestamp; otherwise the
ingestion time is used. The asset is inferred from known asset names, falling
back to a default so nothing is dropped.
"""

from __future__ import annotations

import datetime as dt
import re

from ..models import Source
from ..schemas import EventIn

# Matches a date at the very start of a chunk, e.g. "2026-06-26", "26/06/2026".
_LEADING_DATE = re.compile(
    r"^\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})\b[\s:,-]*"
)
_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
    "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d.%m.%Y", "%Y.%m.%d",
)


def _parse_leading_date(chunk: str) -> tuple[dt.datetime | None, str]:
    m = _LEADING_DATE.match(chunk)
    if not m:
        return None, chunk
    raw = m.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt), chunk[m.end():]
        except ValueError:
            continue
    return None, chunk


def _infer_asset(text: str, known_assets: list[str]) -> str | None:
    low = text.lower()
    for asset in sorted(known_assets, key=len, reverse=True):
        if asset.lower() in low:
            return asset
    return None


def _split_chunks(text: str) -> list[str]:
    # Prefer blank-line-separated paragraphs; fall back to non-empty lines.
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:
        paras = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return paras


def parse_text_document(
    text: str,
    *,
    farm: str,
    known_assets: list[str] | None = None,
    default_asset: str = "General",
    source: Source = Source.manual,
    doc_name: str | None = None,
) -> tuple[list[EventIn], list[str]]:
    known_assets = known_assets or []
    now = dt.datetime.now()
    events: list[EventIn] = []

    for chunk in _split_chunks(text):
        when, body = _parse_leading_date(chunk)
        body = body.strip() or chunk
        events.append(
            EventIn(
                farm=farm,
                asset=_infer_asset(body, known_assets) or default_asset,
                source=source,
                occurred_at=when or now,
                category="document",
                author=doc_name,
                text=body,
                raw=doc_name,
            )
        )

    if not events:
        return [], ["document contained no readable text"]
    return events, []


def extract_text_from_pdf(data: bytes) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", ["PDF support requires the 'files' extra (pip install -e '.[files]')."]
    import io

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001
        return "", [f"could not read PDF: {exc}"]
    return "\n\n".join(pages), []


def extract_text_from_docx(data: bytes) -> tuple[str, list[str]]:
    try:
        import docx  # python-docx
    except ImportError:
        return "", ["DOCX support requires the 'files' extra (pip install -e '.[files]')."]
    import io

    try:
        document = docx.Document(io.BytesIO(data))
        paras = [p.text for p in document.paragraphs if p.text.strip()]
    except Exception as exc:  # noqa: BLE001
        return "", [f"could not read DOCX: {exc}"]
    return "\n\n".join(paras), []
