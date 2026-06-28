"""Excel and JSON ingestion, reusing the shared tabular -> events core."""

from __future__ import annotations

import io
import json as jsonlib

import pandas as pd

from ..models import Source
from ..schemas import EventIn
from .csv_ingest import dataframe_to_events


def parse_excel(
    data: bytes,
    *,
    source: Source = Source.csv_partner,
) -> tuple[list[EventIn], list[str]]:
    """Parse every sheet of an .xlsx/.xls workbook into events."""
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    except ImportError:
        return [], [
            "Excel support requires the 'files' extra (pip install -e '.[files]')."
        ]
    except Exception as exc:  # noqa: BLE001
        return [], [f"could not read Excel file: {exc}"]

    all_events: list[EventIn] = []
    all_errors: list[str] = []
    for sheet_name, df in sheets.items():
        events, errors = dataframe_to_events(df, source=source)
        all_events.extend(events)
        all_errors.extend(f"[sheet {sheet_name}] {e}" for e in errors)
    if not all_events and not all_errors:
        all_errors.append("workbook contained no rows")
    return all_events, all_errors


def parse_json_records(
    data: str | bytes,
    *,
    source: Source = Source.csv_partner,
) -> tuple[list[EventIn], list[str]]:
    """Parse a JSON array (or {records|data|items: [...]}) of record objects."""
    try:
        payload = jsonlib.loads(data)
    except Exception as exc:  # noqa: BLE001
        return [], [f"could not parse JSON: {exc}"]

    if isinstance(payload, dict):
        for key in ("records", "data", "items", "rows"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]

    if not isinstance(payload, list) or not payload:
        return [], ["JSON did not contain a list of records"]

    try:
        df = pd.DataFrame(payload)
    except Exception as exc:  # noqa: BLE001
        return [], [f"could not tabulate JSON records: {exc}"]

    return dataframe_to_events(df, source=source)
