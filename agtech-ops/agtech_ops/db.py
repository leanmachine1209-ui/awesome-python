"""Database engine/session helpers and entity-resolution upserts."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Asset, AssetType, Base, Farm

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
    return _engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_or_create_farm(session: Session, name: str) -> Farm:
    name = name.strip()
    farm = session.query(Farm).filter(Farm.name == name).one_or_none()
    if farm is None:
        farm = Farm(name=name)
        session.add(farm)
        session.flush()
    return farm


def get_or_create_asset(
    session: Session,
    farm: Farm,
    name: str,
    asset_type: AssetType = AssetType.other,
) -> Asset:
    """Resolve an asset by (farm, name), the core of cross-source context."""
    name = name.strip()
    asset = (
        session.query(Asset)
        .filter(Asset.farm_id == farm.id, Asset.name == name)
        .one_or_none()
    )
    if asset is None:
        asset = Asset(farm_id=farm.id, name=name, type=asset_type)
        session.add(asset)
        session.flush()
    elif asset_type is not AssetType.other and asset.type is AssetType.other:
        # Upgrade a placeholder type once we learn what the asset really is.
        asset.type = asset_type
        session.flush()
    return asset
