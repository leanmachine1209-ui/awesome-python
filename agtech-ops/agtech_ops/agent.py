"""Action-item-log agent.

This is the "Haiku agent" entry point: as data flows in from the bridge
(WhatsApp, Dropbox, partner files, video/clip tags), it distills an append-only
**action-item log** with provenance — what to do, who owns it, why it was
raised, and which agent produced it.

It delegates to the configured summarizer backend:
  - ``llm``  — Claude Haiku (or any LiteLLM model) when the AI extra + an API
    key are present. Cheap, fast, good at turning chatter + tags into tasks.
  - ``rule_based`` — deterministic offline fallback, so the log always builds.

Each run appends to the ``action_items`` table (the log); existing entries are
preserved so the log is a running history, not a snapshot.
"""

from __future__ import annotations

import datetime as dt

from .schemas import SummaryResult
from .service import list_action_items, summarize_and_store
from .summarize import get_summarizer


def agent_name() -> str:
    """Human-readable name of the active agent backend."""
    return get_summarizer().name


def build_action_log(
    farm: str | None = None,
    since_days: int | None = None,
) -> SummaryResult:
    """Process incoming data and append to the action-item log."""
    since = None
    if since_days is not None:
        since = dt.datetime.now() - dt.timedelta(days=since_days)
    return summarize_and_store(farm=farm, since=since, persist=True)


def action_log(limit: int | None = None) -> list[dict]:
    """Return the current open action-item log (newest first)."""
    items = list_action_items()
    items.sort(key=lambda a: (a.get("logged_at") or ""), reverse=True)
    return items[:limit] if limit else items
