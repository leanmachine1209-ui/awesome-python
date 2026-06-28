"""Summarizer interface and shared helpers."""

from __future__ import annotations

from typing import Protocol

from ..models import Event
from ..schemas import SummaryResult


def render_events(events: list[Event]) -> str:
    """Render events into a compact, context-rich text block for a summarizer."""
    lines: list[str] = []
    for e in sorted(events, key=lambda x: x.occurred_at):
        when = e.occurred_at.strftime("%Y-%m-%d %H:%M")
        asset = e.asset.name if e.asset else "?"
        farm = e.asset.farm.name if e.asset and e.asset.farm else "?"
        prefix = f"[{when}] {farm} / {asset} ({e.source.value})"
        if e.text:
            who = f" {e.author}:" if e.author else ""
            lines.append(f"{prefix}{who} {e.text}")
        if e.metric is not None:
            val = "" if e.value is None else f"={e.value}"
            cat = f" {e.category}" if e.category else ""
            lines.append(f"{prefix}{cat} {e.metric}{val}")
    return "\n".join(lines)


class Summarizer(Protocol):
    name: str

    def summarize(self, events: list[Event]) -> SummaryResult: ...
