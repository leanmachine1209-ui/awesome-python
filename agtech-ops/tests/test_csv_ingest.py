from agtech_ops.ingest import parse_partner_csv
from agtech_ops.models import AssetType, Source


def test_parse_basic_csv():
    csv = (
        "farm,asset,asset_type,date,metric,value,notes\n"
        "Green Acres,North Herd,herd,2026-06-26,milk_yield_l,1610,Cow lame\n"
    )
    events, errors = parse_partner_csv(csv)
    assert errors == []
    assert len(events) == 1
    e = events[0]
    assert e.farm == "Green Acres"
    assert e.asset == "North Herd"
    assert e.asset_type is AssetType.herd
    assert e.source is Source.csv_partner
    assert e.metric == "milk_yield_l"
    assert e.value == 1610.0
    assert e.text == "Cow lame"


def test_header_aliases_and_extra_columns_in_raw():
    csv = (
        "site,paddock,timestamp,reading,comment,partner_id\n"
        "Green Acres,South Field,2026-06-27 10:00,15,Dry,PX-9\n"
    )
    events, errors = parse_partner_csv(csv)
    assert errors == []
    assert len(events) == 1
    e = events[0]
    assert e.farm == "Green Acres"
    assert e.asset == "South Field"
    assert e.value == 15.0
    assert e.text == "Dry"
    assert e.raw is not None and "PX-9" in e.raw


def test_missing_required_column():
    events, errors = parse_partner_csv("foo,bar\n1,2\n")
    assert events == []
    assert any("missing required column" in err for err in errors)


def test_bad_row_is_reported_not_fatal():
    csv = (
        "farm,asset,date,value\n"
        "Green Acres,North Herd,not-a-date,5\n"
        "Green Acres,North Herd,2026-06-27,7\n"
    )
    events, errors = parse_partner_csv(csv)
    assert len(events) == 1
    assert any("unparseable date" in err for err in errors)
