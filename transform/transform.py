"""
transform.py

Transform step of the ETL pipeline (Extract -> Transform -> Load).

Takes raw traffic-flow records coming out of the Extract step (e.g. from a
HERE-Traffic-like API, buffered through Kafka) and produces clean, enriched
records ready to be written to the Load step (DynamoDB / PostgreSQL).

Design goals:
- Pure functions, no I/O -> easy to unit test with pytest.
- One bad record must not kill the whole batch (see transform_batch).
- Explicit, typed errors (TransformError) instead of silent failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class TransformError(Exception):
    """Raised when a single raw record cannot be transformed."""


@dataclass(frozen=True)
class TrafficRecord:
    """A cleaned, enriched traffic record ready for the Load step."""

    segment_id: str
    timestamp: datetime
    speed_kmh: float
    free_flow_speed_kmh: float
    congestion_ratio: float
    jam_factor: float


REQUIRED_FIELDS = ("segmentId", "timestamp", "speedKmh", "freeFlowSpeedKmh")


def parse_raw_record(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validate that a raw record has all required fields (non-None).

    Raises:
        TransformError: if any required field is missing or None.
    """
    missing = [f for f in REQUIRED_FIELDS if raw.get(f) is None]
    if missing:
        raise TransformError(f"Missing required fields: {missing}")
    return raw


def compute_speed_kmh(raw_speed: float, unit: str = "kmh") -> float:
    """
    Normalize a raw speed value to km/h.

    The upstream API sometimes reports speed in m/s, so callers can pass
    unit="ms" to convert.

    Raises:
        TransformError: for negative speeds or an unrecognized unit.
    """
    if raw_speed is None:
        raise TransformError("speed value is None")
    if raw_speed < 0:
        raise TransformError(f"negative speed is not valid: {raw_speed}")

    if unit == "ms":
        return round(raw_speed * 3.6, 2)
    if unit == "kmh":
        return round(raw_speed, 2)

    raise TransformError(f"unknown speed unit: {unit!r}")


def compute_congestion_ratio(speed_kmh: float, free_flow_speed_kmh: float) -> float:
    """
    Ratio of current speed to free-flow speed for the same segment.

    1.0  -> no congestion (moving at free-flow speed or faster, capped at 1.0)
    ~0.0 -> heavy congestion

    Raises:
        TransformError: if free_flow_speed_kmh is not strictly positive.
    """
    if free_flow_speed_kmh <= 0:
        raise TransformError("free_flow_speed_kmh must be > 0")

    ratio = speed_kmh / free_flow_speed_kmh
    return round(min(ratio, 1.0), 4)


def compute_jam_factor(congestion_ratio: float) -> float:
    """
    Map a congestion ratio to a 0-10 jam factor (inspired by HERE's JamFactor).

    0  -> free flow
    10 -> fully jammed
    """
    return round((1 - congestion_ratio) * 10, 2)


def _parse_timestamp(ts: Any) -> datetime:
    """Parse an ISO-8601 string or pass through a datetime, always tz-aware (UTC)."""
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as e:
            raise TransformError(f"invalid timestamp format: {ts!r}") from e
    if not isinstance(ts, datetime):
        raise TransformError(f"timestamp must be str or datetime, got {type(ts)}")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def enrich_record(raw: dict[str, Any]) -> TrafficRecord:
    """
    Validate + enrich a single raw record into a TrafficRecord.

    Raises:
        TransformError: on any validation/parsing failure.
    """
    raw = parse_raw_record(raw)
    unit = raw.get("speedUnit", "kmh")

    speed_kmh = compute_speed_kmh(raw["speedKmh"], unit=unit)
    free_flow_kmh = compute_speed_kmh(raw["freeFlowSpeedKmh"], unit=unit)

    congestion_ratio = compute_congestion_ratio(speed_kmh, free_flow_kmh)
    jam_factor = compute_jam_factor(congestion_ratio)
    timestamp = _parse_timestamp(raw["timestamp"])

    return TrafficRecord(
        segment_id=str(raw["segmentId"]),
        timestamp=timestamp,
        speed_kmh=speed_kmh,
        free_flow_speed_kmh=free_flow_kmh,
        congestion_ratio=congestion_ratio,
        jam_factor=jam_factor,
    )


def deduplicate_batch(records: list[TrafficRecord]) -> list[TrafficRecord]:
    """
    Keep only the most recent record per segment_id within a batch.

    This simulates the upsert semantics used by the Load step, so the
    Transform step never hands the Load step two conflicting rows for the
    same segment in the same batch.
    """
    latest: dict[str, TrafficRecord] = {}
    for record in records:
        existing = latest.get(record.segment_id)
        if existing is None or record.timestamp > existing.timestamp:
            latest[record.segment_id] = record
    return list(latest.values())


def transform_batch(
    raw_records: list[dict[str, Any]],
) -> tuple[list[TrafficRecord], list[dict[str, Any]]]:
    """
    Transform a batch of raw records pulled from Kafka.

    A record that fails validation is collected in `failed` (with its error)
    instead of raising, so one malformed message doesn't drop the whole batch.

    Returns:
        (clean_records, failed_records)
    """
    clean: list[TrafficRecord] = []
    failed: list[dict[str, Any]] = []

    for raw in raw_records:
        try:
            clean.append(enrich_record(raw))
        except TransformError as e:
            failed.append({"raw": raw, "error": str(e)})

    return deduplicate_batch(clean), failed
