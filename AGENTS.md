# AGENTS.md

## Repository Overview

An opinionated list of Python frameworks, libraries, tools, and resources. Published at [awesome-python.com](https://awesome-python.com/).

## Entry Guidelines

**Refer to [CONTRIBUTING.md](CONTRIBUTING.md)** for acceptance criteria, quality requirements, rejection rules, and entry format. Apply these rules whenever adding or removing an entry, whether reviewing a PR or committing directly.

## Structure

- **README.md**: Source of truth for catalog entries and README sponsor placements. Hierarchical categories with alphabetically ordered entries.
- **CONTRIBUTING.md**: Submission guidelines and review criteria.
- **SPONSORSHIP.md**: Sponsor tiers, placement rules, and the editorial-independence policy. `website/templates/sponsorship.html` separately defines which sponsorship content appears on the published website page.
- **website/**: Static site generator that builds awesome-python.com from README.md.
  - `build.py`: Parses README.md and renders HTML via Jinja2 templates.
  - `fetch_github_stars.py`: Fetches star counts into `website/data/`.
  - `readme_parser.py`: Markdown-to-structured-data parser.
  - `templates/`, `static/`: Jinja2 templates and CSS/JS assets.
  - `tests/`: Pytest tests for the build pipeline.
- **Makefile**: `make install`, `make build`, `make preview`, `make test`, `make lint`, `make format`, `make typecheck`, `make fetch_github_stars`.
- **pyproject.toml**: Uses `uv` for dependency management. Python >=3.13.

## Key Rules

- Alphabetical ordering within categories is mandatory.
- Quality over quantity. Only "awesome" projects.
- One project per PR.
- One entry per commit when adding or deleting entries. Format, wording, or categorization changes across multiple entries may be bundled in a single commit.
- README.md is the source of truth for catalog entries and README sponsor placements; treat `SPONSORSHIP.md` and `website/templates/sponsorship.html` as separate sponsorship content surfaces.

## Cursor Cloud specific instructions

This repo holds two independent Python products:

- **awesome-python website** (root `pyproject.toml`, `website/`): static-site generator, managed by `uv` (Python 3.13, fetched automatically by `uv`). Commands are in the `Makefile`: `make build`, `make test`, `make lint`, `make typecheck`. The update script runs `uv sync --locked`; `uv` lives at `$HOME/.local/bin/uv` (not on `PATH` by default — prefix it or add it to `PATH`).
- **agtech-ops** (`agtech-ops/`): FastAPI ingest API + Streamlit dashboard, Python 3.10+. Standard run/test commands are in `agtech-ops/README.md`.

Non-obvious caveats:

- The base image's `python3.12` lacks `ensurepip`, so `python3 -m venv` fails. The update script creates `agtech-ops/.venv` with `uv venv` instead. Run agtech-ops commands via `agtech-ops/.venv/bin/<tool>` (or activate the venv); do not rely on `python3 -m venv`.
- agtech-ops runs fully offline by default. Set `AGTECH_FORCE_RULE_BASED=1` to force the deterministic summarizer/agent (no API keys needed); the test suite already forces this. An LLM agent is used only when `AGTECH_FORCE_RULE_BASED` is unset/false AND an `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` is present.
- API and dashboard share state through `AGTECH_DATABASE_URL` (defaults to a SQLite file in the cwd). Point both at the same URL (e.g. `sqlite:////tmp/agtech_demo.db`) to see API-ingested data in the dashboard.
- `make lint` (root) runs `ruff check .` over the whole repo, so it also flags pre-existing lint issues in `agtech-ops/tests/`. Website (`website/`) code itself is clean.
