"""Parse partner / Dropbox CSV exports into normalized events.

Expected (case-insensitive, flexible) columns:

    farm, asset, date, [asset_type], [category], [metric], [value], [notes]

Partners are messy, so column names are normalized and unknown extras are kept
in ``raw``. Rows that cannot be salvaged are reported as errors rather than
aborting the whole file.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re

import pandas as pd

from ..models import AssetType, Source
from ..schemas import EventIn

# Map common partner header variants onto our canonical names.
_COLUMN_ALIASES = {
    "farm": "farm",
    "farm_name": "farm",
    "site": "farm",
    "asset": "asset",
    "herd": "asset",
    "crop": "asset",
    "field": "asset",
    "asset_name": "asset",
    "paddock": "asset",
    "asset_type": "asset_type",
    "type": "asset_type",
    "date": "date",
    "timestamp": "date",
    "datetime": "date",
    "recorded_at": "date",
    "category": "category",
    "event": "category",
    "metric": "metric",
    "measure": "metric",
    "value": "value",
    "reading": "value",
    "amount": "value",
    "notes": "notes",
    "note": "notes",
    "comment": "notes",
    "comments": "notes",
    "description": "notes",
    # Video / clip metadata (tags drive workflow).
    "tags": "tags",
    "tag": "tags",
    "labels": "tags",
    "detections": "tags",
    "duration": "duration_s",
    "duration_s": "duration_s",
    "length": "duration_s",
    "camera": "camera",
    "cam": "camera",
    "clip": "clip",
    "clip_id": "clip",
    "video": "clip",
    "filename": "clip",
}

_REQUIRED = {"farm", "asset", "date"}
# Presence of any of these implies the rows are video/clip metadata.
_MEDIA_COLUMNS = {"tags", "duration_s", "camera", "clip"}


def _split_tags(raw: object) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        items = re.split(r"[;,|]", str(raw))
    return [t.strip() for t in items if str(t).strip()]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        renamed[col] = _COLUMN_ALIASES.get(key, key)
    return df.rename(columns=renamed)


def _coerce_asset_type(raw: object) -> AssetType:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return AssetType.other
    try:
        return AssetType(str(raw).strip().lower())
    except ValueError:
        return AssetType.other


def parse_partner_csv(
    data: str | bytes,
    *,
    source: Source = Source.csv_partner,
    sep: str | None = None,
) -> tuple[list[EventIn], list[str]]:
    """Return ``(events, errors)`` parsed from CSV/TSV ``data``."""

    if isinstance(data, bytes):
        buffer: io.StringIO | io.BytesIO = io.BytesIO(data)
    else:
        buffer = io.StringIO(data)

    try:
        read_kwargs = {"sep": sep} if sep is not None else {}
        df = pd.read_csv(buffer, **read_kwargs)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller
        return [], [f"could not read CSV: {exc}"]

    return dataframe_to_events(df, source=source)


def dataframe_to_events(
    df: pd.DataFrame,
    *,
    source: Source = Source.csv_partner,
) -> tuple[list[EventIn], list[str]]:
    """Convert an already-loaded tabular frame into normalized events.

    Shared by the CSV, Excel and JSON ingestors so column aliasing and row
    coercion behave identically regardless of the original file format.
    """

    errors: list[str] = []
    if df is None or df.empty:
        return [], ["no rows found"]

    df = _normalize_columns(df)

    missing = _REQUIRED - set(df.columns)
    if missing:
        return [], [f"missing required column(s): {', '.join(sorted(missing))}"]

    known = {
        "farm", "asset", "asset_type", "date", "category", "metric", "value",
        "notes", "tags", "duration_s", "camera", "clip",
    }
    extra_cols = [c for c in df.columns if c not in known]

    # Clip-metadata tables (tags/duration/camera/clip) are auto-tagged as media
    # unless the caller explicitly asked for a different source.
    is_media = bool(_MEDIA_COLUMNS & set(df.columns))
    if is_media and source is Source.csv_partner:
        source = Source.media

    events: list[EventIn] = []
    for idx, row in df.iterrows():
        rownum = int(idx) + 2  # +1 for header, +1 for 1-based humans
        try:
            occurred_at = pd.to_datetime(row["date"], errors="coerce")
            if pd.isna(occurred_at):
                errors.append(f"row {rownum}: unparseable date {row['date']!r}")
                continue

            value = row.get("value")
            if value is not None and not pd.isna(value):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = None
            else:
                value = None

            tags = _split_tags(row.get("tags"))

            # Clip duration becomes a numeric metric so it aggregates like data.
            metric = _clean(row.get("metric"))
            duration = row.get("duration_s")
            if metric is None and duration is not None and not pd.isna(duration):
                try:
                    value = float(duration)
                    metric = "clip_duration_s"
                except (TypeError, ValueError):
                    pass

            text = _clean(row.get("notes"))
            if text is None and tags:
                text = "Clip tagged: " + ", ".join(tags)

            raw_extra = {c: _jsonable(row.get(c)) for c in extra_cols}

            events.append(
                EventIn(
                    farm=str(row["farm"]),
                    asset=str(row["asset"]),
                    asset_type=_coerce_asset_type(row.get("asset_type")),
                    source=source,
                    occurred_at=occurred_at.to_pydatetime()
                    if hasattr(occurred_at, "to_pydatetime")
                    else dt.datetime.fromisoformat(str(occurred_at)),
                    category=_clean(row.get("category"))
                    or ("media" if is_media else None),
                    metric=metric,
                    value=value,
                    author=_clean(row.get("camera")),
                    text=text,
                    tags=tags,
                    raw=json.dumps(raw_extra) if raw_extra else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-row resilience
            errors.append(f"row {rownum}: {exc}")

    return events, errors


def _clean(v: object) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _jsonable(v: object):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)
