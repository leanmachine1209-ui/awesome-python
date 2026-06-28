"""Runtime configuration, read from environment variables.

Everything has a sensible default so the app runs end-to-end with zero setup.
Secrets (LLM keys, Dropbox/WhatsApp tokens) are optional and only needed for
the live integrations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # SQLAlchemy URL. Defaults to a local SQLite file so there is nothing to
    # provision for a first run.
    database_url: str = os.getenv("AGTECH_DATABASE_URL", "sqlite:///agtech_ops.db")

    # LLM model string understood by LiteLLM. Defaults to a small, cheap model
    # (Claude Haiku) for the action-item-log agent. Only used when AI extras +
    # a key exist; otherwise the deterministic rule-based agent runs.
    llm_model: str = os.getenv("AGTECH_LLM_MODEL", "anthropic/claude-3-5-haiku-latest")

    # Force the deterministic summarizer even if AI deps/keys are available.
    # Handy for tests and offline demos.
    force_rule_based: bool = _env_bool("AGTECH_FORCE_RULE_BASED", False)


def get_settings() -> Settings:
    return Settings()
