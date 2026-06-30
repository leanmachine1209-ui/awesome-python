"""Ingestors that turn raw source data into validated ``EventIn`` records."""

from .alibi_ingest import looks_like_alibi, parse_alibi_vigilant_events
from .csv_ingest import dataframe_to_events, parse_partner_csv
from .registry import SUPPORTED_EXTENSIONS, ingest_file
from .tabular_ingest import parse_excel, parse_json_records
from .text_ingest import parse_text_document
from .whatsapp_ingest import parse_whatsapp_export

__all__ = [
    "parse_partner_csv",
    "dataframe_to_events",
    "parse_excel",
    "parse_json_records",
    "parse_alibi_vigilant_events",
    "looks_like_alibi",
    "parse_whatsapp_export",
    "parse_text_document",
    "ingest_file",
    "SUPPORTED_EXTENSIONS",
]
