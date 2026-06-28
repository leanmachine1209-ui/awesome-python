from agtech_ops.ingest import parse_whatsapp_export
from agtech_ops.models import Source


def test_parse_bracketed_and_dash_formats():
    text = (
        "[2026-06-26, 7:32 AM] Alice: North Herd cow #42 is limping\n"
        "2026/06/26, 16:10 - Bob: South Field irrigation leaking\n"
    )
    events, errors = parse_whatsapp_export(
        text, farm="Green Acres", known_assets=["North Herd", "South Field"]
    )
    assert errors == []
    assert len(events) == 2
    assert events[0].author == "Alice"
    assert events[0].asset == "North Herd"
    assert events[0].source is Source.whatsapp
    assert events[1].author == "Bob"
    assert events[1].asset == "South Field"


def test_multiline_message_appended():
    text = (
        "[2026-06-26, 7:32 AM] Alice: First line\n"
        "still the same message\n"
        "[2026-06-26, 7:40 AM] Bob: Second message\n"
    )
    events, _ = parse_whatsapp_export(text, farm="Green Acres")
    assert len(events) == 2
    assert "still the same message" in events[0].text


def test_unknown_asset_falls_back_to_default():
    text = "[2026-06-26, 7:32 AM] Alice: something vague happened\n"
    events, _ = parse_whatsapp_export(
        text, farm="Green Acres", known_assets=["North Herd"], default_asset="General"
    )
    assert len(events) == 1
    assert events[0].asset == "General"
