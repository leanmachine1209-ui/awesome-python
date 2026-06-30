"""Ingest Alibi Vigilant (ISAPI / Hikvision-OEM) camera event feeds.

Alibi Vigilant NVRs and IP cameras speak the **ISAPI** protocol and emit event
notifications as ``EventNotificationAlert`` JSON objects — the same shape the
device pushes on its live ``/ISAPI/Event/notification/alertStream`` arming
endpoint and writes to exported event logs::

    {
      "EventNotificationAlert": {
        "channelID": "2",
        "channelName": "South Field Gate",
        "dateTime": "2026-06-29T02:14:07+00:00",
        "eventType": "linedetection",
        "eventState": "active",
        "eventDescription": "Line crossing detected on perimeter"
      }
    }

Unlike the partner clip tables (which carry their own ``farm``/``asset``
columns), these alerts are device-centric: they identify a *camera channel*, not
a farm asset. So a ``farm`` is supplied for context and the asset is inferred
from the channel name (falling back to a default), mirroring the free-text
ingest path.

Each alert becomes a ``media`` event so camera feeds flow through the exact same
aggregate -> tag -> action-item pipeline as upstream vision-model clips. The
ISAPI ``eventType`` is mapped to workflow tags; perimeter detections
(line-crossing, intrusion, region entry/exit) map to a ``fence`` signal so the
rule-based agent raises a containment task — the most plausible ops meaning of a
perimeter breach on a farm camera.
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from ..models import Source
from ..schemas import EventIn
from .text_ingest import _infer_asset

# Container keys an export might wrap the alert list in.
_LIST_KEYS = ("EventNotificationAlertList", "events", "alerts", "records", "data", "items")

# ISAPI/Hikvision ``eventType`` -> workflow tags. Perimeter detections become a
# ``fence`` signal (the rule-based agent's "Secure fencing/containment" trigger);
# the raw event type is always preserved as a tag for traceability.
_EVENT_TYPE_TAGS: dict[str, list[str]] = {
    "vmd": ["motion"],
    "motion": ["motion"],
    "motiondetection": ["motion"],
    "linedetection": ["intrusion", "fence"],
    "fielddetection": ["intrusion", "fence"],
    "regionentrance": ["intrusion", "fence"],
    "regionexiting": ["intrusion", "fence"],
    "intrusion": ["intrusion", "fence"],
    "perimeter": ["intrusion", "fence"],
    "tamperdetection": ["tamper"],
    "shelteralarm": ["tamper"],
    "videoloss": ["video-loss"],
    "videomismatch": ["video-loss"],
    "diskfull": ["storage"],
    "diskerror": ["storage"],
    "recordingexception": ["storage"],
    "io": ["alarm"],
    "facedetection": ["person"],
}


def _norm_type(event_type: str) -> str:
    return event_type.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _event_tags(event_type: str) -> list[str]:
    tags = list(_EVENT_TYPE_TAGS.get(_norm_type(event_type), []))
    raw = event_type.strip().lower()
    if raw and raw not in tags:
        tags.append(raw)
    return tags


def _get(alert: dict, *names: str) -> object | None:
    """Case-insensitive lookup that skips blank values."""
    lowered = {str(k).lower(): v for k, v in alert.items()}
    for name in names:
        if name.lower() in lowered:
            value = lowered[name.lower()]
            if value is not None and str(value).strip() != "":
                return value
    return None


def _unwrap(alert: dict) -> dict:
    inner = alert.get("EventNotificationAlert")
    return inner if isinstance(inner, dict) else alert


def _iter_alerts(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        for key in _LIST_KEYS:
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        return []
    return [_unwrap(item) for item in payload if isinstance(item, dict)]


def _payload_looks_like_alibi(payload: object) -> bool:
    if isinstance(payload, dict) and (
        "EventNotificationAlert" in payload or "EventNotificationAlertList" in payload
    ):
        return True
    for alert in _iter_alerts(payload)[:5]:
        keys = {str(k).lower() for k in alert}
        if "eventtype" in keys and ({"channelname", "channelid", "channel"} & keys):
            return True
    return False


def looks_like_alibi(data: str | bytes) -> bool:
    """True if ``data`` is JSON in the Alibi Vigilant / ISAPI event shape."""
    try:
        payload = json.loads(data)
    except Exception:  # noqa: BLE001 - not our format if it isn't valid JSON
        return False
    return _payload_looks_like_alibi(payload)


def parse_alibi_vigilant_events(
    data: str | bytes,
    *,
    farm: str,
    known_assets: list[str] | None = None,
    default_asset: str = "General",
) -> tuple[list[EventIn], list[str]]:
    """Parse an Alibi Vigilant / ISAPI event feed into ``media`` events."""
    known_assets = known_assets or []
    try:
        payload = json.loads(data)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller
        return [], [f"could not parse Alibi Vigilant JSON: {exc}"]

    alerts = _iter_alerts(payload)
    if not alerts:
        return [], ["no Alibi Vigilant events found"]

    events: list[EventIn] = []
    errors: list[str] = []
    for i, alert in enumerate(alerts, start=1):
        try:
            raw_dt = _get(alert, "dateTime", "datetime", "time", "triggerTime", "startTime")
            occurred_at = pd.to_datetime(raw_dt, errors="coerce")
            if raw_dt is None or pd.isna(occurred_at):
                errors.append(f"event {i}: missing/unparseable dateTime {raw_dt!r}")
                continue
            occurred = occurred_at.to_pydatetime() if hasattr(occurred_at, "to_pydatetime") else occurred_at
            if isinstance(occurred, dt.datetime) and occurred.tzinfo is not None:
                # Keep naive datetimes consistent with the rest of the app.
                occurred = occurred.replace(tzinfo=None)

            event_type = str(_get(alert, "eventType", "type") or "event")
            camera = _get(alert, "channelName", "channelID", "channel", "deviceName", "ipAddress")
            description = _get(alert, "eventDescription", "description", "eventStateDescription")

            cam_label = str(camera) if camera else "camera"
            asset = _infer_asset(cam_label, known_assets) or default_asset
            text = str(description) if description else f"{cam_label}: {event_type} detected"

            events.append(
                EventIn(
                    farm=farm,
                    asset=asset,
                    source=Source.media,
                    occurred_at=occurred,
                    category="media",
                    author=cam_label,
                    text=text,
                    tags=_event_tags(event_type),
                    raw=json.dumps(alert, default=str),
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-event resilience
            errors.append(f"event {i}: {exc}")

    return events, errors
