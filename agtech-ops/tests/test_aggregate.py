import io
import json

from agtech_ops.service import aggregate, ingest_files


def _csv() -> bytes:
    return (
        b"farm,asset,asset_type,date,metric,value,notes\n"
        b"Green Acres,North Herd,herd,2026-06-25,milk_yield_l,1820,steady\n"
        b"Green Acres,North Herd,herd,2026-06-26,milk_yield_l,1610,cow lame\n"
        b"Green Acres,South Field,crop,2026-06-26,soil_moisture_pct,18,dry\n"
    )


def test_multi_file_ingest_and_aggregate():
    json_doc = json.dumps(
        [{"farm": "Green Acres", "asset": "Feed Store", "date": "2026-06-27",
          "metric": "feed_tonnes", "value": 2, "notes": "running low"}]
    ).encode()
    text_doc = b"2026-06-27 Fence on north boundary is loose, cattle could escape."

    files = [
        ("herd.csv", _csv()),
        ("partner.json", json_doc),
        ("notes.txt", text_doc),
    ]
    res = ingest_files(files, farm="Green Acres")
    assert res.files_processed == 3
    assert res.events_ingested == 5  # 3 csv + 1 json + 1 text
    assert "Green Acres" in res.farms

    report = aggregate()
    assert report.total_events == 5
    assert report.total_farms == 1
    # North Herd, South Field, Feed Store, plus "General" for the text note
    # whose content matched no known asset name.
    assert report.total_assets == 4
    assert {a.asset for a in report.by_asset} >= {
        "North Herd", "South Field", "Feed Store", "General"
    }
    assert report.by_source  # has at least one source
    # milk yield should be a compiled time series with 2 points
    assert "milk_yield_l" in report.metric_series
    assert len(report.metric_series["milk_yield_l"]) == 2
    # series is sorted ascending by time
    pts = report.metric_series["milk_yield_l"]
    assert pts[0].occurred_at <= pts[1].occurred_at


def test_aggregate_empty():
    report = aggregate()
    assert report.total_events == 0
    assert report.total_assets == 0
