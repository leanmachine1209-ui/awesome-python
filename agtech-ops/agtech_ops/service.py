"""Application service layer: persist events, run summaries, store action items.

Keeps the FastAPI layer and the Streamlit layer thin by centralizing all
database + summarizer orchestration here.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session, joinedload

from .db import get_or_create_asset, get_or_create_farm, session_scope
from .models import ActionItem, ActionStatus, Asset, Event, Farm, Priority, Source
from .schemas import ActionItemOut, EventIn, IngestResult, SummaryResult
from .summarize import get_summarizer


def store_events(events: list[EventIn], errors: list[str] | None = None) -> IngestResult:
    """Resolve farms/assets and persist a batch of validated events."""
    errors = list(errors or [])
    farms: set[str] = set()
    assets: set[str] = set()
    count = 0

    with session_scope() as session:
        for ev in events:
            farm = get_or_create_farm(session, ev.farm)
            asset = get_or_create_asset(session, farm, ev.asset, ev.asset_type)
            session.add(
                Event(
                    asset_id=asset.id,
                    source=ev.source,
                    occurred_at=ev.occurred_at,
                    category=ev.category,
                    metric=ev.metric,
                    value=ev.value,
                    author=ev.author,
                    text=ev.text,
                    raw=ev.raw,
                )
            )
            farms.add(farm.name)
            assets.add(asset.name)
            count += 1

    source = events[0].source if events else Source.manual
    return IngestResult(
        source=source,
        events_ingested=count,
        farms=sorted(farms),
        assets=sorted(assets),
        errors=errors,
    )


def known_asset_names(farm: str | None = None) -> list[str]:
    with session_scope() as session:
        q = session.query(Asset.name)
        if farm:
            q = q.join(Farm).filter(Farm.name == farm)
        return [name for (name,) in q.distinct().all()]


def _load_events(
    session: Session,
    farm: str | None,
    since: dt.datetime | None,
) -> list[Event]:
    q = (
        session.query(Event)
        .options(joinedload(Event.asset).joinedload(Asset.farm))
        .join(Asset)
        .join(Farm)
    )
    if farm:
        q = q.filter(Farm.name == farm)
    if since:
        q = q.filter(Event.occurred_at >= since)
    return q.order_by(Event.occurred_at).all()


def summarize_and_store(
    farm: str | None = None,
    since: dt.datetime | None = None,
    persist: bool = True,
) -> SummaryResult:
    """Summarize stored events and (optionally) persist the action items."""
    summarizer = get_summarizer()
    with session_scope() as session:
        events = _load_events(session, farm, since)
        result = summarizer.summarize(events)

        if persist and result.action_items:
            farm_id = None
            if farm:
                f = session.query(Farm).filter(Farm.name == farm).one_or_none()
                farm_id = f.id if f else None
            for ai in result.action_items:
                asset_id = None
                if ai.asset:
                    a = (
                        session.query(Asset)
                        .filter(Asset.name == ai.asset)
                        .first()
                    )
                    asset_id = a.id if a else None
                session.add(
                    ActionItem(
                        farm_id=farm_id,
                        asset_id=asset_id,
                        task=ai.task,
                        owner=ai.owner,
                        due=dt.datetime.combine(ai.due, dt.time()) if ai.due else None,
                        priority=ai.priority,
                        source_summary=result.summary,
                    )
                )
    return result


def list_action_items(
    status: ActionStatus | None = ActionStatus.open,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(ActionItem)
        if status is not None:
            q = q.filter(ActionItem.status == status)
        rank = {Priority.high: 0, Priority.medium: 1, Priority.low: 2}
        items = q.all()
        items.sort(key=lambda a: (rank[a.priority], a.due or dt.datetime.max))
        return [
            {
                "id": a.id,
                "task": a.task,
                "owner": a.owner,
                "due": a.due.date().isoformat() if a.due else None,
                "priority": a.priority.value,
                "status": a.status.value,
            }
            for a in items
        ]
