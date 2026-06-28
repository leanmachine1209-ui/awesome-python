"""Operator-facing Streamlit dashboard.

Run with:  streamlit run agtech_ops/dashboard.py
Requires the 'dashboard' extra (streamlit, plotly).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Absolute imports so the file works when launched directly via
# `streamlit run agtech_ops/dashboard.py` (Streamlit runs it as a script, not
# as part of the package, so relative imports would fail).
from agtech_ops.agent import action_log, agent_name, build_action_log
from agtech_ops.db import init_db
from agtech_ops.ingest import SUPPORTED_EXTENSIONS, parse_whatsapp_export
from agtech_ops.service import (
    aggregate,
    ingest_files,
    known_asset_names,
    store_events,
)


def main() -> None:
    init_db()
    st.set_page_config(page_title="AgTech Ops Hub", layout="wide")
    st.title("AgTech Ops Hub")
    st.caption(
        f"Compile & aggregate multi-source farm data · action-item agent: "
        f"**{agent_name()}**"
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
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Events", report.total_events)
    c2.metric("Assets", report.total_assets)
    c3.metric("Clips", report.media_clips)
    c4.metric("Farms", report.total_farms)
    c5.metric("Open actions", report.open_action_items)

    if report.by_source:
        src_df = pd.DataFrame(
            {"source": list(report.by_source), "events": list(report.by_source.values())}
        )
        st.bar_chart(src_df.set_index("source"))

    # --- Media metadata & tags (workflow signals) ---
    if report.top_tags:
        st.subheader("Media metadata & tags (workflow signals)")
        st.caption(
            "Tags extracted from video/camera clips — the most frequent tags "
            "indicate where the workflow needs attention."
        )
        tdf = pd.DataFrame(
            [{"tag": t.tag, "count": t.count} for t in report.top_tags]
        ).set_index("tag")
        st.bar_chart(tdf)

    st.divider()
    st.subheader(f"Action-item log · built by {agent_name()}")
    st.caption(
        "An AI agent (Claude Haiku when a key is set, deterministic rules "
        "otherwise) turns incoming bridge data into a logged, prioritized "
        "action list with a rationale for each item."
    )
    if st.button("Run agent on incoming data", type="primary"):
        result = build_action_log()
        st.write(result.summary)
        for p in result.points:
            st.markdown(f"- {p}")

    log = action_log()
    if log:
        st.dataframe(
            [
                {
                    "priority": a["priority"],
                    "task": a["task"],
                    "owner": a["owner"],
                    "due": a["due"],
                    "rationale": a["rationale"],
                    "by": a["created_by"],
                    "logged": a["logged_at"],
                }
                for a in log
            ],
            use_container_width=True,
        )
    else:
        st.info("Log is empty. Ingest data, then run the agent.")

    # --- Aggregated metric trends (native charts; one per metric) ---
    if report.metric_series:
        st.divider()
        st.subheader("Aggregated metrics over time")
        for metric in sorted(report.metric_series):
            pts = report.metric_series[metric]
            mdf = pd.DataFrame(
                [{"date": p.occurred_at, "value": p.value, "asset": p.asset} for p in pts]
            )
            # Pivot so each asset is its own line; native chart avoids heavy deps.
            wide = mdf.pivot_table(
                index="date", columns="asset", values="value", aggfunc="mean"
            )
            st.caption(metric)
            st.line_chart(wide)


if __name__ == "__main__":
    main()
