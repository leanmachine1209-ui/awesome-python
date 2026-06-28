"""FastAPI surface for the AgTech Ops Hub."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile

from .db import init_db
from .ingest import parse_partner_csv, parse_whatsapp_export
from .models import ActionStatus
from .schemas import IngestResult, SummaryResult
from .service import (
    known_asset_names,
    list_action_items,
    store_events,
    summarize_and_store,
)
from .summarize import get_summarizer

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="AgTech Ops Hub",
    version="0.1.0",
    description=(
        "Ingest partner CSVs, Dropbox exports and WhatsApp chatter, contextualize "
        "them onto shared farm assets, and turn them into action items for ops teams."
    ),
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "summarizer": get_summarizer().name}


@app.post("/ingest/csv", response_model=IngestResult)
async def ingest_csv(file: UploadFile = File(...)) -> IngestResult:
    raw = await file.read()
    events, errors = parse_partner_csv(raw)
    if not events and errors:
        raise HTTPException(status_code=422, detail=errors)
    return store_events(events, errors)


@app.post("/ingest/whatsapp", response_model=IngestResult)
async def ingest_whatsapp(
    text: str = Form(...),
    farm: str = Form(...),
    default_asset: str = Form("General"),
) -> IngestResult:
    events, errors = parse_whatsapp_export(
        text,
        farm=farm,
        known_assets=known_asset_names(farm),
        default_asset=default_asset,
    )
    if not events and errors:
        raise HTTPException(status_code=422, detail=errors)
    return store_events(events, errors)


@app.post("/summarize", response_model=SummaryResult)
def summarize(
    farm: str | None = Query(None),
    since_days: int | None = Query(None, ge=0),
    persist: bool = Query(True),
) -> SummaryResult:
    since = None
    if since_days is not None:
        since = dt.datetime.now() - dt.timedelta(days=since_days)
    return summarize_and_store(farm=farm, since=since, persist=persist)


@app.get("/action-items")
def action_items(status: ActionStatus | None = Query(ActionStatus.open)) -> list[dict]:
    return list_action_items(status=status)
