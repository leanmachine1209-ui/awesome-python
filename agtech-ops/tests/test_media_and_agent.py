import io
import json

from agtech_ops.agent import action_log, agent_name, build_action_log
from agtech_ops.ingest import ingest_file, parse_json_records
from agtech_ops.models import Source
from agtech_ops.service import aggregate, ingest_files


def test_clip_json_autoroutes_to_media_with_tags():
    payload = json.dumps(
        [
            {"farm": "Green Acres", "asset": "North Herd", "date": "2026-06-28",
             "camera": "barn-cam-1", "duration_s": 18, "tags": "cow, lame, limping"},
        ]
    )
    events, errors = parse_json_records(payload)
    assert errors == []
    assert len(events) == 1
    e = events[0]
    assert e.source is Source.media          # auto-detected from tags/clip columns
    assert e.tags == ["cow", "lame", "limping"]
    assert e.author == "barn-cam-1"          # camera -> author
    assert e.metric == "clip_duration_s"     # duration -> numeric metric
    assert e.value == 18.0


def test_csv_with_tags_column_is_media():
    csv = b"farm,asset,date,tags\nGreen Acres,South Field,2026-06-28,\"fence, open\"\n"
    events, errors = ingest_file("clips.csv", csv)
    assert errors == []
    assert events[0].source is Source.media
    assert events[0].tags == ["fence", "open"]


def test_aggregate_counts_clips_and_top_tags():
    clips = json.dumps([
        {"farm": "F", "asset": "A", "date": "2026-06-28", "tags": "cow, lame"},
        {"farm": "F", "asset": "A", "date": "2026-06-28", "tags": "cow, feeding"},
    ]).encode()
    ingest_files([("clips.json", clips)], farm="F")
    report = aggregate()
    assert report.media_clips == 2
    tags = {t.tag: t.count for t in report.top_tags}
    assert tags["cow"] == 2
    assert tags["lame"] == 1


def test_agent_builds_log_from_tags_offline():
    # A clip tagged "lame" should drive a high-priority action via tags alone.
    clips = json.dumps([
        {"farm": "F", "asset": "North Herd", "date": "2026-06-28",
         "camera": "cam1", "tags": "cow, lame"},
    ]).encode()
    ingest_files([("clips.json", clips)], farm="F")

    assert agent_name() == "rule_based"  # offline default in tests
    result = build_action_log()
    assert len(result.action_items) >= 1

    log = action_log()
    assert log
    item = log[0]
    assert item["created_by"] == "rule_based"
    assert item["rationale"]  # rationale recorded
    assert "lame" in item["rationale"]
