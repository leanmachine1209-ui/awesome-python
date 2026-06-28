"""Application service layer: persist events, run summaries, store action items.

Keeps the FastAPI layer and the Streamlit layer thin by centralizing all
database + summarizer orchestration here.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .db import get_or_create_asset, get_or_create_farm, session_scope
from .ingest import ingest_file
from .models import ActionItem, ActionStatus, Asset, Event, Farm, Priority, Source
from .schemas import (
    ActionItemOut,
    AggregateReport,
    AssetSummary,
    EventIn,
    FileIngestResult,
    IngestResult,
    MetricPoint,
    SummaryResult,
    TagCount,
)
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
                    tags=",".join(ev.tags) if ev.tags else None,
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


def ingest_files(
    files: list[tuple[str, bytes]],
    *,
    farm: str | None = None,
    default_asset: str = "General",
) -> FileIngestResult:
    """Ingest a batch of heterogeneous files and compile the results.

    ``files`` is a list of ``(filename, bytes)``. Tabular files self-describe
    their farm/asset; free-text files use the supplied ``farm`` for context.
    """
    per_file: list[dict] = []
    all_errors: list[str] = []
    farms: set[str] = set()
    assets: set[str] = set()
    total = 0

    for filename, data in files:
        known = known_asset_names(farm)
        events, errors = ingest_file(
            filename, data, farm=farm, known_assets=known, default_asset=default_asset
        )
        if events:
            res = store_events(events)
            farms.update(res.farms)
            assets.update(res.assets)
            total += res.events_ingested
            per_file.append(
                {"file": filename, "events": res.events_ingested, "errors": errors}
            )
        else:
            per_file.append({"file": filename, "events": 0, "errors": errors})
        all_errors.extend(f"{filename}: {e}" for e in errors)

    return FileIngestResult(
        files_processed=len(files),
        events_ingested=total,
        per_file=per_file,
        farms=sorted(farms),
        assets=sorted(assets),
        errors=all_errors,
    )


def aggregate(farm: str | None = None) -> AggregateReport:
    """Compile a cross-source roll-up of everything ingested."""
    with session_scope() as session:
        base = (
            session.query(Event)
            .join(Asset)
            .join(Farm)
        )
        if farm:
            base = base.filter(Farm.name == farm)

        events = base.options(
            joinedload(Event.asset).joinedload(Asset.farm)
        ).all()

        total_events = len(events)
        farms = {e.asset.farm.name for e in events if e.asset and e.asset.farm}
        assets = {(e.asset.farm.name, e.asset.name) for e in events if e.asset}

        by_source: dict[str, int] = {}
        per_asset: dict[tuple[str, str], dict] = {}
        metric_series: dict[str, list[MetricPoint]] = {}
        tag_counts: dict[str, int] = {}
        media_clips = 0
        min_dt = max_dt = None

        for e in events:
            by_source[e.source.value] = by_source.get(e.source.value, 0) + 1
            min_dt = e.occurred_at if min_dt is None else min(min_dt, e.occurred_at)
            max_dt = e.occurred_at if max_dt is None else max(max_dt, e.occurred_at)

            if e.source is Source.media:
                media_clips += 1
            if e.tags:
                for tag in (t.strip() for t in e.tags.split(",") if t.strip()):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            if e.asset:
                key = (e.asset.farm.name, e.asset.name)
                slot = per_asset.setdefault(
                    key,
                    {
                        "farm": e.asset.farm.name,
                        "asset": e.asset.name,
                        "asset_type": e.asset.type.value,
                        "events": 0,
                        "last_seen": None,
                    },
                )
                slot["events"] += 1
                if slot["last_seen"] is None or e.occurred_at > slot["last_seen"]:
                    slot["last_seen"] = e.occurred_at

            if e.metric and e.value is not None:
                metric_series.setdefault(e.metric, []).append(
                    MetricPoint(
                        asset=e.asset.name if e.asset else "?",
                        occurred_at=e.occurred_at,
                        value=e.value,
                    )
                )

        for series in metric_series.values():
            series.sort(key=lambda p: p.occurred_at)

        open_items = (
            session.query(func.count(ActionItem.id))
            .filter(ActionItem.status == ActionStatus.open)
            .scalar()
        )

        by_asset = sorted(
            (AssetSummary(**v) for v in per_asset.values()),
            key=lambda a: a.events,
            reverse=True,
        )
        top_tags = [
            TagCount(tag=t, count=c)
            for t, c in sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

        return AggregateReport(
            total_events=total_events,
            total_farms=len(farms),
            total_assets=len(assets),
            open_action_items=int(open_items or 0),
            media_clips=media_clips,
            by_source=by_source,
            by_asset=by_asset,
            metric_series=metric_series,
            top_tags=top_tags,
            date_range=[min_dt, max_dt],
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
                        created_by=summarizer.name,
                        rationale=ai.rationale,
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
                "created_by": a.created_by,
                "rationale": a.rationale,
                "logged_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ]
