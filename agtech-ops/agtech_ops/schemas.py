"""Pydantic schemas: validate messy inbound data and shape AI output."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator

from .models import AssetType, Priority, Source


class EventIn(BaseModel):
    """A validated, source-agnostic event ready to persist."""

    farm: str
    asset: str
    asset_type: AssetType = AssetType.other
    source: Source
    occurred_at: dt.datetime
    category: str | None = None
    metric: str | None = None
    value: float | None = None
    author: str | None = None
    text: str | None = None
    raw: str | None = None

    @field_validator("farm", "asset")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ActionItemOut(BaseModel):
    task: str = Field(..., description="Concrete, actionable instruction.")
    owner: str | None = Field(None, description="Person/team responsible.")
    due: dt.date | None = Field(None, description="Suggested due date if implied.")
    priority: Priority = Priority.medium
    asset: str | None = Field(None, description="Asset name this relates to.")


class SummaryResult(BaseModel):
    """The structured output the summarizer must produce."""

    summary: str = Field(..., description="Short narrative of the situation.")
    points: list[str] = Field(default_factory=list, description="Key bullet points.")
    action_items: list[ActionItemOut] = Field(default_factory=list)


class IngestResult(BaseModel):
    source: Source
    events_ingested: int
    farms: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FileIngestResult(BaseModel):
    """Per-file outcome plus an aggregate roll-up for a multi-file upload."""

    files_processed: int
    events_ingested: int
    per_file: list[dict] = Field(default_factory=list)
    farms: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AssetSummary(BaseModel):
    farm: str
    asset: str
    asset_type: str
    events: int
    last_seen: dt.datetime | None = None


class MetricPoint(BaseModel):
    asset: str
    occurred_at: dt.datetime
    value: float


class AggregateReport(BaseModel):
    """Compiled, cross-source view of everything ingested."""

    total_events: int
    total_farms: int
    total_assets: int
    open_action_items: int
    by_source: dict[str, int] = Field(default_factory=dict)
    by_asset: list[AssetSummary] = Field(default_factory=list)
    metric_series: dict[str, list[MetricPoint]] = Field(default_factory=dict)
    date_range: list[dt.datetime | None] = Field(default_factory=list)
