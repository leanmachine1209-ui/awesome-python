"""Operator-facing Streamlit dashboard.

Run with:  streamlit run agtech_ops/dashboard.py
Requires the 'dashboard' extra (streamlit, plotly).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

# Absolute imports so the file works when launched directly via
# `streamlit run agtech_ops/dashboard.py` (Streamlit runs it as a script, not
# as part of the package, so relative imports would fail).
from agtech_ops.db import init_db
from agtech_ops.ingest import SUPPORTED_EXTENSIONS, parse_whatsapp_export
from agtech_ops.models import ActionStatus
from agtech_ops.service import (
    aggregate,
    ingest_files,
    known_asset_names,
    list_action_items,
    store_events,
    summarize_and_store,
)
from agtech_ops.summarize import get_summarizer


def main() -> None:
    init_db()
    st.set_page_config(page_title="AgTech Ops Hub", layout="wide")
    st.title("AgTech Ops Hub")
    st.caption(
        f"Compile & aggregate multi-source farm data · summarizer: "
        f"**{get_summarizer().name}**"
    )

    farm_default = "Green Acres"
    exts = ", ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS))

    with st.sidebar:
        st.header("Intake")
        farm = st.text_input("Farm (for text documents)", value=farm_default)
        st.caption(f"Accepted: {exts}")
        uploads = st.file_uploader(
            "Drop a range of files",
            type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
            accept_multiple_files=True,
        )
        if uploads and st.button("Ingest files", type="primary"):
            payload = [(u.name, u.getvalue()) for u in uploads]
            res = ingest_files(payload, farm=farm)
            st.success(
                f"Ingested {res.events_ingested} records from "
                f"{res.files_processed} file(s)."
            )
            with st.expander("Per-file detail"):
                st.dataframe(res.per_file, use_container_width=True)
            if res.errors:
                st.warning("\n".join(res.errors[:20]))

        st.divider()
        wa_text = st.text_area("Or paste WhatsApp / notes text")
        if wa_text and st.button("Ingest pasted text"):
            events, errors = parse_whatsapp_export(
                wa_text, farm=farm, known_assets=known_asset_names(farm)
            )
            res = store_events(events, errors)
            st.success(f"Ingested {res.events_ingested} messages.")
            if res.errors:
                st.warning("\n".join(res.errors))

    report = aggregate()

    # --- Compiled overview ---
    st.subheader("Compiled overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Events", report.total_events)
    c2.metric("Assets", report.total_assets)
    c3.metric("Farms", report.total_farms)
    c4.metric("Open actions", report.open_action_items)

    if report.by_source:
        src_df = pd.DataFrame(
            {"source": list(report.by_source), "events": list(report.by_source.values())}
        )
        st.bar_chart(src_df.set_index("source"))

    # --- Aggregated metric trends ---
    if report.metric_series:
        st.subheader("Aggregated metrics over time")
        metric = st.selectbox("Metric", sorted(report.metric_series))
        pts = report.metric_series[metric]
        mdf = pd.DataFrame(
            [{"date": p.occurred_at, "value": p.value, "asset": p.asset} for p in pts]
        )
        fig = px.line(mdf, x="date", y="value", color="asset", markers=True)
        st.plotly_chart(fig, use_container_width=True)

    # --- Assets table ---
    if report.by_asset:
        with st.expander("Assets compiled across sources"):
            st.dataframe(
                [a.model_dump() for a in report.by_asset], use_container_width=True
            )

    st.divider()
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Summary")
        if st.button("Generate summary + action items"):
            result = summarize_and_store()
            st.write(result.summary)
            for p in result.points:
                st.markdown(f"- {p}")

    with col2:
        st.subheader("Open action items")
        items = list_action_items(status=ActionStatus.open)
        if items:
            st.dataframe(items, use_container_width=True)
        else:
            st.info("No open action items yet. Ingest data and generate a summary.")


if __name__ == "__main__":
    main()
