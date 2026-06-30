import json
from pathlib import Path

from agtech_ops.agent import build_action_log
from agtech_ops.ingest import ingest_file, looks_like_alibi, parse_alibi_vigilant_events
from agtech_ops.models import Source
from agtech_ops.service import aggregate, ingest_files

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "alibi_vigilant_events.json"


def _wrapped(events: list[dict]) -> bytes:
    return json.dumps([{"EventNotificationAlert": e} for e in events]).encode()


def test_parse_wrapped_event_notification_alerts():
    data = _wrapped(
        [
            {
                "channelID": "2",
                "channelName": "South Field Gate",
                "dateTime": "2026-06-29T02:14:07+00:00",
                "eventType": "linedetection",
                "eventDescription": "Line crossing on perimeter",
            }
        ]
    )
    events, errors = parse_alibi_vigilant_events(
        data, farm="Green Acres", known_assets=["South Field"]
    )
    assert errors == []
    assert len(events) == 1
    e = events[0]
    assert e.source is Source.media
    assert e.category == "media"
    assert e.asset == "South Field"  # inferred from channel name
    assert e.author == "South Field Gate"  # channel -> author
    assert "fence" in e.tags and "linedetection" in e.tags  # perimeter -> fence signal
    assert e.text == "Line crossing on perimeter"
    # tz-aware ISAPI timestamp is normalized to naive datetime
    assert e.occurred_at.tzinfo is None


def test_parse_bare_events_without_wrapper():
    data = json.dumps(
        [
            {
                "channelName": "North Herd Barn",
                "dateTime": "2026-06-29T05:05:10",
                "eventType": "VMD",
            }
        ]
    ).encode()
    events, errors = parse_alibi_vigilant_events(data, farm="Green Acres")
    assert errors == []
    assert events[0].asset == "General"  # no known asset match -> default
    assert "motion" in events[0].tags
    assert events[0].text == "North Herd Barn: VMD detected"  # synthesized text


def test_parse_single_object_and_unparseable_date():
    data = json.dumps(
        {
            "EventNotificationAlert": {
                "channelName": "Feed Store Dock",
                "dateTime": "not-a-date",
                "eventType": "tamperdetection",
            }
        }
    ).encode()
    events, errors = parse_alibi_vigilant_events(data, farm="Green Acres")
    assert events == []
    assert any("dateTime" in e for e in errors)  # one bad event reported, not raised


def test_looks_like_alibi_detection():
    assert looks_like_alibi(_wrapped([{"channelName": "c", "dateTime": "2026-06-29", "eventType": "VMD"}]))
    # A partner clip table (farm/asset/tags) must NOT be mistaken for Alibi.
    clips = json.dumps([{"farm": "F", "asset": "A", "date": "2026-06-29", "tags": "cow"}]).encode()
    assert not looks_like_alibi(clips)


def test_registry_autoroutes_alibi_json_and_requires_farm():
    data = SAMPLE.read_bytes()
    events, errors = ingest_file("alibi_vigilant_events.json", data, farm="Green Acres")
    assert errors == []
    assert len(events) == 5
    assert all(e.source is Source.media for e in events)

    # Without a farm, the camera feed cannot be contextualized.
    no_farm_events, no_farm_errors = ingest_file("alibi_vigilant_events.json", data)
    assert no_farm_events == []
    assert any("farm name is required" in e for e in no_farm_errors)


def test_partner_clip_json_still_routes_to_tabular():
    clips = json.dumps(
        [{"farm": "F", "asset": "A", "date": "2026-06-29", "camera": "cam1", "tags": "cow, lame"}]
    ).encode()
    events, errors = ingest_file("clips.json", clips)
    assert errors == []
    assert events[0].source is Source.media
    assert events[0].asset == "A"  # tabular path keeps its own asset column


def test_perimeter_event_drives_containment_action_offline():
    data = _wrapped(
        [
            {
                "channelName": "South Field Gate",
                "dateTime": "2026-06-29T02:14:07+00:00",
                "eventType": "linedetection",
                "eventDescription": "Line crossing detected on perimeter",
            }
        ]
    )
    ingest_files([("alibi_vigilant_events.json", data)], farm="Green Acres")

    report = aggregate()
    assert report.media_clips == 1
    tags = {t.tag for t in report.top_tags}
    assert "fence" in tags

    result = build_action_log()
    assert any("Secure fencing/containment" in ai.task for ai in result.action_items)
