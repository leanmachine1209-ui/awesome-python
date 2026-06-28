"""Test fixtures. Sets up an isolated SQLite DB and forces offline summarizer.

Environment must be configured *before* any ``agtech_ops`` module is imported,
because config defaults are read at import time.
"""

from __future__ import annotations

import os
import tempfile

# Configure before importing the package.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["AGTECH_DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["AGTECH_FORCE_RULE_BASED"] = "1"

import pytest  # noqa: E402

from agtech_ops.db import get_engine, init_db  # noqa: E402
from agtech_ops.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Recreate all tables before each test for isolation."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    init_db()
    yield
    Base.metadata.drop_all(engine)
