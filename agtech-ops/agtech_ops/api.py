"""FastAPI surface for the AgTech Ops Hub."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile

from .agent import action_log, agent_name, build_action_log
from .db import init_db
from .ingest import SUPPORTED_EXTENSIONS, parse_partner_csv, parse_whatsapp_export
from .models import ActionStatus
from .schemas import AggregateReport, FileIngestResult, IngestResult, SummaryResult
from .service import (
    aggregate,
    ingest_files,
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
    return {
        "status": "ok",
        "summarizer": get_summarizer().name,
        "supported_files": sorted(SUPPORTED_EXTENSIONS),
    }


@app.post("/ingest/files", response_model=FileIngestResult)
async def ingest_files_endpoint(
    files: list[UploadFile] = File(...),
    farm: str | None = Form(None),
    default_asset: str = Form("General"),
) -> FileIngestResult:
    """Ingest a range of files (CSV/TSV/Excel/JSON/TXT/MD/LOG/PDF/DOCX).

    Tabular files carry their own farm/asset columns; free-text files use the
    optional ``farm`` for context resolution.
    """
    payload = [(f.filename or "upload", await f.read()) for f in files]
    result = ingest_files(payload, farm=farm, default_asset=default_asset)
    if result.events_ingested == 0 and result.errors:
        raise HTTPException(status_code=422, detail=result.errors)
    return result


@app.get("/report", response_model=AggregateReport)
def report(farm: str | None = Query(None)) -> AggregateReport:
    """Compiled, aggregated view across all ingested sources."""
    return aggregate(farm=farm)


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


@app.get("/agent")
def agent_info() -> dict:
    """Which action-item-log agent is active (haiku-agent or rule_based)."""
    return {"agent": agent_name()}


@app.post("/agent/run", response_model=SummaryResult)
def agent_run(
    farm: str | None = Query(None),
    since_days: int | None = Query(None, ge=0),
) -> SummaryResult:
    """Run the agent over incoming data and append to the action-item log."""
    return build_action_log(farm=farm, since_days=since_days)


@app.get("/agent/log")
def agent_log(limit: int | None = Query(None, ge=1)) -> list[dict]:
    """Read the current action-item log (newest first)."""
    return action_log(limit=limit)
