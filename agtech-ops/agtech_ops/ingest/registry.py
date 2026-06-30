"""Single entry point that ingests *any* supported file by dispatching on type.

Supported today:
  - Tabular:   .csv, .tsv, .xlsx, .xls, .json
  - Free text: .txt, .md, .log, .pdf, .docx
WhatsApp exports (.txt) are auto-detected and routed to the chat parser.
Alibi Vigilant / ISAPI camera event feeds (.json) are auto-detected and routed
to the camera-event parser.

Tabular files carry their own farm/asset columns. Free-text files do not, so a
``farm`` (and optional known asset list) is supplied for context resolution.
"""

from __future__ import annotations

import os

from ..models import Source
from ..schemas import EventIn
from .alibi_ingest import looks_like_alibi, parse_alibi_vigilant_events
from .csv_ingest import parse_partner_csv
from .tabular_ingest import parse_excel, parse_json_records
from .text_ingest import (
    extract_text_from_docx,
    extract_text_from_pdf,
    parse_text_document,
)
from .whatsapp_ingest import _LINE_RE, parse_whatsapp_export

SUPPORTED_EXTENSIONS = {
    ".csv", ".tsv", ".xlsx", ".xls", ".json",
    ".txt", ".md", ".log", ".pdf", ".docx",
}


def _looks_like_whatsapp(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()][:30]
    if not lines:
        return False
    hits = sum(1 for ln in lines if _LINE_RE.match(ln.strip()))
    return hits >= max(2, len(lines) // 3)


def ingest_file(
    filename: str,
    data: bytes,
    *,
    farm: str | None = None,
    known_assets: list[str] | None = None,
    default_asset: str = "General",
) -> tuple[list[EventIn], list[str]]:
    """Return ``(events, errors)`` for a single uploaded file."""
    ext = os.path.splitext(filename)[1].lower()
    known_assets = known_assets or []

    # --- Tabular (self-describing: farm/asset in columns) ---
    if ext == ".csv":
        return parse_partner_csv(data)
    if ext == ".tsv":
        return parse_partner_csv(data, sep="\t")
    if ext in {".xlsx", ".xls"}:
        return parse_excel(data)
    if ext == ".json":
        # Alibi Vigilant / ISAPI camera event feeds are device-centric (no
        # farm/asset columns), so detect them and route to the dedicated parser.
        if looks_like_alibi(data):
            if not farm:
                return [], [f"{filename}: a farm name is required for Alibi Vigilant event feeds"]
            return parse_alibi_vigilant_events(
                data, farm=farm, known_assets=known_assets, default_asset=default_asset
            )
        return parse_json_records(data)

    # --- Free text (needs a farm for context) ---
    if ext in {".txt", ".md", ".log", ".pdf", ".docx"}:
        if not farm:
            return [], [f"{filename}: a farm name is required for text documents"]

        if ext == ".pdf":
            text, errors = extract_text_from_pdf(data)
        elif ext == ".docx":
            text, errors = extract_text_from_docx(data)
        else:
            errors = []
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                return [], [f"{filename}: could not decode text ({exc})"]

        if errors:
            return [], [f"{filename}: {e}" for e in errors]

        if ext in {".txt", ".log"} and _looks_like_whatsapp(text):
            return parse_whatsapp_export(
                text, farm=farm, known_assets=known_assets, default_asset=default_asset
            )

        return parse_text_document(
            text,
            farm=farm,
            known_assets=known_assets,
            default_asset=default_asset,
            source=Source.manual,
            doc_name=filename,
        )

    return [], [f"{filename}: unsupported file type '{ext}'"]
