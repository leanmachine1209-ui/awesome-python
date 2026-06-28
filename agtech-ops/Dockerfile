FROM python:3.12-slim

WORKDIR /app

# Install the package with file-processing + dashboard extras.
COPY pyproject.toml README.md ./
COPY agtech_ops ./agtech_ops
RUN pip install --no-cache-dir -e ".[files,dashboard]"

ENV AGTECH_FORCE_RULE_BASED=1 \
    AGTECH_DATABASE_URL=sqlite:////data/agtech_ops.db

# SQLite lives on a volume so data survives container restarts.
VOLUME ["/data"]
EXPOSE 8501

# $PORT is honored when present (e.g. on Render), else default to 8501.
CMD ["sh", "-c", "streamlit run agtech_ops/dashboard.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false"]
