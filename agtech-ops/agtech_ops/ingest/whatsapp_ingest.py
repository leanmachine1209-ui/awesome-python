"""Parse a WhatsApp chat export into normalized events.

WhatsApp "Export chat" produces lines like::

    [2026-06-28, 8:56:01 PM] Alice: North Herd cow #42 looks lame, call vet
    2026/06/28, 20:56 - Bob: Ordered more feed for Field 3

Both bracketed and dash formats are supported. Multi-line messages (a line
without a new timestamp header) are appended to the previous message.

Because a chat does not name the farm/asset in a structured way, the caller
supplies a default ``farm``; the asset is inferred from the message text when a
known asset name is provided, otherwise it falls back to a "General" asset so
nothing is dropped.
"""

from __future__ import annotations

import datetime as dt
import re

from ..models import Source
from ..schemas import EventIn

# [2026-06-28, 8:56:01 PM] Name: message    OR
# 2026/06/28, 20:56 - Name: message
_LINE_RE = re.compile(
    r"^\[?\s*"
    r"(?P<date>\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})"
    r"[,]?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?)"
    r"\s*\]?\s*[-]?\s*"
    r"(?P<author>[^:]{1,80}?):\s"
    r"(?P<text>.*)$"
)

_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
    "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d.%m.%Y", "%Y.%m.%d",
)
_TIME_FORMATS = ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M")


def _parse_dt(date_s: str, time_s: str) -> dt.datetime | None:
    time_s = time_s.strip().upper().replace("\u202f", " ")
    for df in _DATE_FORMATS:
        for tf in _TIME_FORMATS:
            try:
                return dt.datetime.strptime(f"{date_s} {time_s}", f"{df} {tf}")
            except ValueError:
                continue
    return None


def _infer_asset(text: str, known_assets: list[str]) -> str | None:
    low = text.lower()
    # Longest match first so "North Herd" beats "Herd".
    for asset in sorted(known_assets, key=len, reverse=True):
        if asset.lower() in low:
            return asset
    return None


def parse_whatsapp_export(
    data: str,
    *,
    farm: str,
    known_assets: list[str] | None = None,
    default_asset: str = "General",
) -> tuple[list[EventIn], list[str]]:
    """Return ``(events, errors)`` from a WhatsApp export string."""

    known_assets = known_assets or []
    errors: list[str] = []
    events: list[EventIn] = []

    current: dict | None = None

    def flush(cur: dict) -> None:
        text = cur["text"].strip()
        if not text:
            return
        asset = _infer_asset(text, known_assets) or default_asset
        events.append(
            EventIn(
                farm=farm,
                asset=asset,
                source=Source.whatsapp,
                occurred_at=cur["dt"],
                author=cur["author"],
                text=text,
                raw=cur["raw"],
            )
        )

    for raw_line in data.splitlines():
        line = raw_line.rstrip("\n")
        m = _LINE_RE.match(line.strip())
        if m:
            if current is not None:
                flush(current)
            parsed = _parse_dt(m.group("date"), m.group("time"))
            if parsed is None:
                errors.append(f"unparseable timestamp: {line[:60]!r}")
                current = None
                continue
            current = {
                "dt": parsed,
                "author": m.group("author").strip(),
                "text": m.group("text"),
                "raw": line,
            }
        elif current is not None and line.strip():
            current["text"] += "\n" + line.strip()
        # blank lines / system messages without a header are ignored

    if current is not None:
        flush(current)

    return events, errors
