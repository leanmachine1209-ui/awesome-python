"""Optional LLM summarizer using LiteLLM + instructor for structured output.

Only imported when AI extras are installed and an API key is configured (see
``summarize.get_summarizer``). It returns the exact same ``SummaryResult``
schema as the rule-based backend, so callers never branch on which one ran.
"""

from __future__ import annotations

from ..models import Event
from ..schemas import SummaryResult
from .base import render_events

_SYSTEM = (
    "You are an operations analyst for a farming business. You receive a log of "
    "events drawn from partner CSV uploads, shared Dropbox spreadsheets, and "
    "WhatsApp messages between farm staff. Produce a concise situational summary, "
    "key bullet points, and concrete action items for the ops team. Each action "
    "item must be specific, name an owner when one is implied by the message "
    "author, set a sensible priority, and reference the relevant asset. Only use "
    "information present in the events."
)


class LLMSummarizer:
    name = "llm"

    def __init__(self, model: str):
        import instructor
        import litellm

        self.model = model
        self._litellm = litellm
        self._client = instructor.from_litellm(litellm.completion)

    def summarize(self, events: list[Event]) -> SummaryResult:
        if not events:
            return SummaryResult(summary="No events to summarize.")

        context = render_events(events)
        return self._client.chat.completions.create(
            model=self.model,
            response_model=SummaryResult,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Events:\n{context}"},
            ],
        )
