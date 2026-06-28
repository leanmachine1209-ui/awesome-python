import datetime as dt

from agtech_ops.models import Asset, AssetType, Event, Farm, Priority, Source
from agtech_ops.summarize.rule_based import RuleBasedSummarizer


def _make_event(text: str, asset_name: str = "North Herd") -> Event:
    farm = Farm(id=1, name="Green Acres")
    asset = Asset(id=1, farm_id=1, name=asset_name, type=AssetType.herd, farm=farm)
    return Event(
        id=1,
        asset_id=1,
        source=Source.whatsapp,
        occurred_at=dt.datetime(2026, 6, 26, 7, 30),
        author="Alice",
        text=text,
        asset=asset,
    )


def test_empty_summary():
    result = RuleBasedSummarizer().summarize([])
    assert result.action_items == []
    assert "No events" in result.summary


def test_lame_triggers_high_priority_vet_action():
    e = _make_event("cow #42 is lame, needs vet")
    result = RuleBasedSummarizer().summarize([e])
    assert len(result.action_items) == 1
    ai = result.action_items[0]
    assert ai.priority is Priority.high
    assert ai.owner == "Alice"
    assert ai.asset == "North Herd"
    assert ai.due is not None


def test_supplies_low_triggers_medium_action():
    e = _make_event("feed store running low, please reorder", asset_name="Feed Store")
    result = RuleBasedSummarizer().summarize([e])
    assert len(result.action_items) == 1
    assert result.action_items[0].priority is Priority.medium


def test_actions_sorted_high_first():
    events = [
        _make_event("feed running low", asset_name="Feed Store"),
        _make_event("cow is lame", asset_name="North Herd"),
    ]
    result = RuleBasedSummarizer().summarize(events)
    assert result.action_items[0].priority is Priority.high
