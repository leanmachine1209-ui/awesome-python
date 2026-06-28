# AgTech Ops Hub

A contextualized operations hub for farming businesses. It ingests data from
several messy real-world sources, resolves them onto shared farm entities, and
turns the combined picture into **summaries and action items** for ops teams.

```
INGEST  →  NORMALIZE + STORE  →  CONTEXTUALIZE + SUMMARIZE  →  DELIVER to ops
```

This is **Sprint 1**: a working vertical slice that proves the full loop
end-to-end with zero external services or API keys required.

## What works today (Sprint 1)

- **Ingest**
  - Partner / Dropbox **CSV** uploads, with flexible/aliased column names and
    per-row error reporting (one bad row never aborts the file).
  - **WhatsApp** chat exports (both `[date, time] Name:` and `date, time - Name:`
    formats, multi-line messages supported).
- **Contextualize** — every record is resolved onto a canonical model so data
  from different sources lines up on the same thing:

  ```
  Farm --< Asset (herd | crop | field) --< Event >-- ActionItem
  ```

- **Summarize** — a batch of events becomes a `{summary, points, action_items}`
  result. Two interchangeable backends:
  - `rule_based` (default): deterministic, offline, keyword-triggered action
    items with priority, owner (from the message author) and a suggested due
    date. No keys needed.
  - `llm` (optional): LiteLLM + instructor for structured output from any model,
    used automatically when the `ai` extra is installed **and** an API key is set.
- **Deliver**
  - **FastAPI** JSON API (`/ingest/csv`, `/ingest/whatsapp`, `/summarize`,
    `/action-items`, `/health`).
  - **Streamlit** dashboard for ingesting data and reviewing open action items.

## Quick start

```bash
cd agtech-ops
python3 -m venv .venv && . .venv/bin/activate   # or use your environment
pip install -e ".[dev]"        # core + test deps
# optional: pip install -e ".[ai,dashboard]"

# Run the API
uvicorn agtech_ops.api:app --reload

# Try it with the bundled sample data
curl -F "file=@sample_data/herd.csv" http://localhost:8000/ingest/csv
curl -F "text=$(cat sample_data/whatsapp_export.txt)" -F "farm=Green Acres" \
     http://localhost:8000/ingest/whatsapp
curl -X POST "http://localhost:8000/summarize"
curl http://localhost:8000/action-items

# Or the dashboard (needs the 'dashboard' extra)
streamlit run agtech_ops/dashboard.py
```

## Tests

```bash
pytest        # 15 tests, fully offline (forces the rule-based summarizer)
```

## Configuration

All optional; sensible defaults mean it runs with nothing set.

| Env var | Default | Purpose |
|---|---|---|
| `AGTECH_DATABASE_URL` | `sqlite:///agtech_ops.db` | Any SQLAlchemy URL (e.g. Postgres). |
| `AGTECH_LLM_MODEL` | `gpt-4o-mini` | LiteLLM model id for the AI backend. |
| `AGTECH_FORCE_RULE_BASED` | `false` | Force the offline summarizer. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / … | – | Enables the LLM backend. |

## Architecture (mapped to the awesome-python catalog)

| Layer | Library (from this repo's list) |
|---|---|
| API / webhooks | FastAPI, uvicorn |
| Tabular parsing | pandas |
| Validation | pydantic |
| Storage / entity resolution | SQLAlchemy |
| Summaries (AI) | LiteLLM, instructor |
| Dashboard | Streamlit, Plotly |
| Scheduling (future) | APScheduler / Prefect / Dagster |

## Roadmap

- **Sprint 1 (done):** CSV + WhatsApp ingest → contextualized action items via
  API + dashboard, with offline + LLM summarizers.
- **Sprint 2:** Live **Dropbox** sync and **WhatsApp Business API** webhook;
  scheduled pulls (APScheduler); push action items back to chat/email.
- **Sprint 3:** Smarter entity resolution (fuzzy asset matching, aliases),
  per-farm dashboards, trend charts, action-item status workflow.

## Open questions — where I need more detail

These are the decisions that will most shape Sprints 2–3:

1. **Partner CSV schemas.** What columns do your real partners send? Are they
   stable, or do we need per-partner mappings? Right now I infer common aliases.
2. **Dropbox layout.** Folder structure and file naming for herd/crop/operations
   data, and whether to use a service account or per-user OAuth.
3. **WhatsApp source.** Live (WhatsApp Business API / Twilio / Meta Cloud API)
   or periodic chat-export uploads? Live changes the auth + webhook design.
4. **Entity naming.** How are farms/herds/fields named across sources so we can
   match them reliably? Is there a master list/IDs we should sync from?
5. **Action item destination.** Where do ops want items delivered — dashboard
   only, back into WhatsApp, email, or an existing task tool?
6. **AI provider + data policy.** Which model/provider is acceptable, and any
   constraints on sending farm/staff messages to a third-party LLM.
7. **Deployment + scale.** Single farm vs. multi-tenant ("agrefine network"?),
   expected data volume, and where this should run.
