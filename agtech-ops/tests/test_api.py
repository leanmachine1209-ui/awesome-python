import io

from fastapi.testclient import TestClient

from agtech_ops.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["summarizer"] == "rule_based"


def test_end_to_end_csv_then_summarize():
    csv = (
        "farm,asset,asset_type,date,metric,value,notes\n"
        "Green Acres,North Herd,herd,2026-06-26,milk_yield_l,1610,Cow #42 looks lame\n"
        "Green Acres,Feed Store,other,2026-06-27,feed_tonnes,2,Running low on feed\n"
    )
    files = {"file": ("herd.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = client.post("/ingest/csv", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["events_ingested"] == 2
    assert "Green Acres" in body["farms"]

    r = client.post("/summarize", params={"persist": True})
    assert r.status_code == 200, r.text
    result = r.json()
    assert len(result["action_items"]) >= 1

    r = client.get("/action-items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["priority"] == "high"  # lame cow sorts first


def test_whatsapp_ingest_endpoint():
    data = {
        "text": "[2026-06-26, 7:32 AM] Alice: North Herd cow is lame, call vet\n",
        "farm": "Green Acres",
    }
    r = client.post("/ingest/whatsapp", data=data)
    assert r.status_code == 200, r.text
    assert r.json()["events_ingested"] == 1


def test_csv_with_no_valid_columns_returns_422():
    files = {"file": ("bad.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}
    r = client.post("/ingest/csv", files=files)
    assert r.status_code == 422


def test_ingest_files_multi_then_report():
    csv = b"farm,asset,date,metric,value\nGreen Acres,North Herd,2026-06-26,milk_yield_l,1610\n"
    notes = b"2026-06-27 South Field irrigation is leaking, needs repair."
    files = [
        ("files", ("herd.csv", io.BytesIO(csv), "text/csv")),
        ("files", ("notes.txt", io.BytesIO(notes), "text/plain")),
    ]
    r = client.post("/ingest/files", files=files, data={"farm": "Green Acres"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files_processed"] == 2
    assert body["events_ingested"] == 2

    r = client.get("/report")
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["total_events"] == 2
    assert "milk_yield_l" in report["metric_series"]


def test_health_lists_supported_files():
    r = client.get("/health")
    assert r.status_code == 200
    assert ".pdf" in r.json()["supported_files"]
