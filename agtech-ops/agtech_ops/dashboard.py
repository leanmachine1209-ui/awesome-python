"""Operator-facing Streamlit dashboard.

Run with:  streamlit run agtech_ops/dashboard.py
Requires the 'dashboard' extra (streamlit, plotly).
"""

from __future__ import annotations

import streamlit as st

# Absolute imports so the file works when launched directly via
# `streamlit run agtech_ops/dashboard.py` (Streamlit runs it as a script, not
# as part of the package, so relative imports would fail).
from agtech_ops.db import init_db
from agtech_ops.ingest import parse_partner_csv, parse_whatsapp_export
from agtech_ops.models import ActionStatus
from agtech_ops.service import (
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
        f"Contextualized farm operations · summarizer: **{get_summarizer().name}**"
    )

    with st.sidebar:
        st.header("Ingest data")
        csv_file = st.file_uploader("Partner / Dropbox CSV", type=["csv"])
        if csv_file is not None and st.button("Ingest CSV"):
            events, errors = parse_partner_csv(csv_file.getvalue())
            res = store_events(events, errors)
            st.success(f"Ingested {res.events_ingested} events.")
            if res.errors:
                st.warning("\n".join(res.errors))

        st.divider()
        wa_farm = st.text_input("Farm name (for WhatsApp)", value="Green Acres")
        wa_text = st.text_area("Paste WhatsApp export")
        if wa_text and st.button("Ingest WhatsApp"):
            events, errors = parse_whatsapp_export(
                wa_text, farm=wa_farm, known_assets=known_asset_names(wa_farm)
            )
            res = store_events(events, errors)
            st.success(f"Ingested {res.events_ingested} messages.")
            if res.errors:
                st.warning("\n".join(res.errors))

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
