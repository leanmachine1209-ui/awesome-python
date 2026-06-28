"""Canonical data model.

The whole point of the hub is that data from very different sources (a partner
CSV, a Dropbox spreadsheet, a WhatsApp thread) gets resolved onto the *same*
entities so it can be reasoned about together:

    Farm --< Asset (a herd, crop block, or field) --< Event >-- ActionItem

An ``Event`` is the normalized unit every ingestor produces. An ``ActionItem``
is what the summarizer produces from a batch of events.
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AssetType(str, enum.Enum):
    herd = "herd"
    crop = "crop"
    field = "field"
    other = "other"


class Source(str, enum.Enum):
    csv_partner = "csv_partner"
    dropbox = "dropbox"
    whatsapp = "whatsapp"
    manual = "manual"


class ActionStatus(str, enum.Enum):
    open = "open"
    done = "done"
    dismissed = "dismissed"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan"
    )


class Asset(Base):
    """A herd, crop block, or field — the thing events are *about*."""

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("farm_id", "name", name="uq_asset_farm_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[AssetType] = mapped_column(
        Enum(AssetType), default=AssetType.other
    )

    farm: Mapped[Farm] = relationship(back_populates="assets")
    events: Mapped[list["Event"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class Event(Base):
    """A normalized record from any source.

    ``metric``/``value`` carry structured CSV data; ``text`` carries free-form
    chatter (WhatsApp). Either or both may be present.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source: Mapped[Source] = mapped_column(Enum(Source), index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="events")


class ActionItem(Base):
    """An ops task distilled from one or more events."""

    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int | None] = mapped_column(
        ForeignKey("farms.id"), index=True, nullable=True
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id"), index=True, nullable=True
    )
    task: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due: Mapped[dt.date | None] = mapped_column(DateTime, nullable=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.medium)
    status: Mapped[ActionStatus] = mapped_column(
        Enum(ActionStatus), default=ActionStatus.open, index=True
    )
    source_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
