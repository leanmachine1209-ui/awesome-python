"""Summarization: turn a batch of events into a structured ``SummaryResult``.

``get_summarizer`` picks the best available backend: the LLM backend when the
AI extras are installed and an API key is present, otherwise the deterministic
rule-based backend. The rule-based backend guarantees the app is useful with
zero configuration and makes tests fully offline.
"""

from __future__ import annotations

import os

from ..config import get_settings
from .base import Summarizer
from .rule_based import RuleBasedSummarizer

__all__ = ["Summarizer", "RuleBasedSummarizer", "get_summarizer"]


def _has_llm_key() -> bool:
    return any(
        os.getenv(k)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_API_KEY", "GEMINI_API_KEY")
    )


def get_summarizer() -> Summarizer:
    settings = get_settings()
    if settings.force_rule_based or not _has_llm_key():
        return RuleBasedSummarizer()
    try:
        from .llm import LLMSummarizer

        return LLMSummarizer(model=settings.llm_model)
    except Exception:
        # Any import/setup failure (missing extras, bad config) degrades safely.
        return RuleBasedSummarizer()
