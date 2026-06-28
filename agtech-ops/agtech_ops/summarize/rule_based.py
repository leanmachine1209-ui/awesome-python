"""Deterministic, offline summarizer.

It is intentionally simple but useful: it scans event text for ops-relevant
triggers (health, equipment, supplies, etc.), assigns priority, infers an owner
from the message author, and rolls everything up into points + action items.
This is the default backend and the one the tests assert against.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter

from ..models import Event, Priority
from ..schemas import ActionItemOut, SummaryResult
from .base import render_events

# trigger keyword -> (action verb template, priority, default lead-time days)
_TRIGGERS: list[tuple[tuple[str, ...], str, Priority, int]] = [
    (("sick", "lame", "ill", "injured", "limping", "down", "mastitis", "fever"),
     "Have vet assess", Priority.high, 1),
    (("dead", "death", "died", "mortality"),
     "Investigate and log mortality", Priority.high, 1),
    (("vet", "veterinarian"),
     "Schedule vet visit", Priority.high, 2),
    (("broken", "broke", "repair", "fix", "leak", "leaking", "fault", "down"),
     "Arrange repair", Priority.high, 2),
    (("low", "out of", "empty", "running low", "order", "reorder", "restock"),
     "Replenish supplies", Priority.medium, 3),
    (("fence", "gate", "escape", "loose", "out on the road"),
     "Secure fencing/containment", Priority.high, 1),
    (("water", "trough", "irrigation", "dry", "drought"),
     "Check water/irrigation", Priority.medium, 2),
    (("spray", "weed", "pest", "fungus", "disease", "blight"),
     "Plan crop protection treatment", Priority.medium, 3),
    (("harvest", "ready", "ripe"),
     "Plan harvest", Priority.medium, 4),
    (("calv", "lamb", "birth", "pregnan"),
     "Monitor for births", Priority.medium, 3),
]

_PRIORITY_RANK = {Priority.high: 0, Priority.medium: 1, Priority.low: 2}

# Compile each trigger group into one regex. A leading ``\b`` anchors the match
# to a word start (so "ill" does NOT match inside "will") while still allowing
# suffixes (so "calv" matches "calving").
_COMPILED: list[tuple[re.Pattern[str], str, Priority, int]] = [
    (
        re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")", re.I),
        verb,
        priority,
        lead,
    )
    for keywords, verb, priority, lead in _TRIGGERS
]


class RuleBasedSummarizer:
    name = "rule_based"

    def summarize(self, events: list[Event]) -> SummaryResult:
        if not events:
            return SummaryResult(summary="No events to summarize.", points=[], action_items=[])

        today = dt.date.today()
        action_items: list[ActionItemOut] = []
        by_source: Counter[str] = Counter()
        by_asset: Counter[str] = Counter()
        flagged = 0

        for e in events:
            by_source[e.source.value] += 1
            if e.asset:
                by_asset[e.asset.name] += 1

            haystack = " ".join(
                p for p in [e.text, e.category, e.metric] if p
            ).lower()
            if not haystack:
                continue

            for pattern, verb, priority, lead in _COMPILED:
                if not pattern.search(haystack):
                    continue
                asset_name = e.asset.name if e.asset else None
                detail = (e.text or e.category or e.metric or "").strip()
                task = f"{verb} — {asset_name or 'farm'}"
                if detail:
                    task += f": {detail[:160]}"
                action_items.append(
                    ActionItemOut(
                        task=task,
                        owner=e.author,
                        due=today + dt.timedelta(days=lead),
                        priority=priority,
                        asset=asset_name,
                    )
                )
                flagged += 1
                break  # one action per event keeps the list focused

        action_items.sort(key=lambda a: (_PRIORITY_RANK[a.priority], a.due or today))

        points: list[str] = [
            f"{len(events)} events across {len(by_asset)} asset(s) "
            f"from {len(by_source)} source(s)."
        ]
        if by_asset:
            top = ", ".join(f"{n} ({c})" for n, c in by_asset.most_common(5))
            points.append(f"Most active assets: {top}.")
        points.append(f"{flagged} event(s) triggered a suggested action.")
        high = sum(1 for a in action_items if a.priority is Priority.high)
        if high:
            points.append(f"{high} high-priority item(s) need attention first.")

        summary = (
            f"Reviewed {len(events)} events and generated {len(action_items)} "
            f"action item(s)"
            + (f", {high} high priority." if high else ".")
        )

        # Keep a small rendered context excerpt for traceability.
        excerpt = render_events(events)
        if len(excerpt) > 2000:
            excerpt = excerpt[:2000] + "…"

        result = SummaryResult(summary=summary, points=points, action_items=action_items)
        result.__dict__["_context_excerpt"] = excerpt  # not serialized; debugging aid
        return result
