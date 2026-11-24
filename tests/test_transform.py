"""
test_transform.py

Unit tests for transform.py. Run with:

    pytest -v

or, to see a coverage summary:

    pytest --cov=transform -v
"""

from datetime import datetime, timezone

import pytest

from transform.transform import (
    TransformError,
    compute_congestion_ratio,
    compute_jam_factor,
    compute_speed_kmh,
    deduplicate_batch,
    enrich_record,
    parse_raw_record,
    transform_batch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_raw_record() -> dict:
    return {
        "segmentId": "seg-001",
        "timestamp": "2026-09-22T08:00:00Z",
        "speedKmh": 24.0,
        "freeFlowSpeedKmh": 48.0,
        "speedUnit": "kmh",
    }


# ---------------------------------------------------------------------------
# parse_raw_record
# ---------------------------------------------------------------------------


class TestParseRawRecord:
    def test_valid_record_passes_through(self, valid_raw_record):
        assert parse_raw_record(valid_raw_record) == valid_raw_record

    @pytest.mark.parametrize(
        "missing_field", ["segmentId", "timestamp", "speedKmh", "freeFlowSpeedKmh"]
    )
    def test_missing_required_field_raises(self, valid_raw_record, missing_field):
        del valid_raw_record[missing_field]
        with pytest.raises(TransformError, match="Missing required fields"):
            parse_raw_record(valid_raw_record)

    def test_none_value_counts_as_missing(self, valid_raw_record):
        valid_raw_record["speedKmh"] = None
        with pytest.raises(TransformError):
            parse_raw_record(valid_raw_record)


# ---------------------------------------------------------------------------
# compute_speed_kmh
# ---------------------------------------------------------------------------


class TestComputeSpeedKmh:
    def test_kmh_passthrough_rounds_to_2dp(self):
        assert compute_speed_kmh(30.126, unit="kmh") == 30.13

    def test_ms_to_kmh_conversion(self):
        # 10 m/s == 36 km/h
        assert compute_speed_kmh(10, unit="ms") == 36.0

    def test_zero_speed_is_valid(self):
        assert compute_speed_kmh(0, unit="kmh") == 0.0

    def test_negative_speed_raises(self):
        with pytest.raises(TransformError, match="negative speed"):
            compute_speed_kmh(-5, unit="kmh")

    def test_none_speed_raises(self):
        with pytest.raises(TransformError, match="is None"):
            compute_speed_kmh(None)

    def test_unknown_unit_raises(self):
        with pytest.raises(TransformError, match="unknown speed unit"):
            compute_speed_kmh(20, unit="mph")


# ---------------------------------------------------------------------------
# compute_congestion_ratio
# ---------------------------------------------------------------------------


class TestComputeCongestionRatio:
    def test_half_speed_gives_half_ratio(self):
        assert compute_congestion_ratio(24, 48) == 0.5

    def test_free_flow_speed_gives_ratio_one(self):
        assert compute_congestion_ratio(48, 48) == 1.0

    def test_ratio_is_capped_at_one(self):
        # current speed faster than "free flow" baseline shouldn't exceed 1.0
        assert compute_congestion_ratio(60, 48) == 1.0

    def test_zero_free_flow_speed_raises(self):
        with pytest.raises(TransformError, match="must be > 0"):
            compute_congestion_ratio(20, 0)

    def test_negative_free_flow_speed_raises(self):
        with pytest.raises(TransformError):
            compute_congestion_ratio(20, -10)


# ---------------------------------------------------------------------------
# compute_jam_factor
# ---------------------------------------------------------------------------


class TestComputeJamFactor:
    @pytest.mark.parametrize(
        "ratio,expected",
        [
            (1.0, 0.0),   # free flow
            (0.5, 5.0),   # half congested
            (0.0, 10.0),  # fully jammed
        ],
    )
    def test_jam_factor_values(self, ratio, expected):
        assert compute_jam_factor(ratio) == expected


# ---------------------------------------------------------------------------
# enrich_record
# ---------------------------------------------------------------------------


class TestEnrichRecord:
    def test_full_valid_record(self, valid_raw_record):
        record = enrich_record(valid_raw_record)

        assert record.segment_id == "seg-001"
        assert record.speed_kmh == 24.0
        assert record.free_flow_speed_kmh == 48.0
        assert record.congestion_ratio == 0.5
        assert record.jam_factor == 5.0
        assert record.timestamp == datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)

    def test_missing_field_raises(self, valid_raw_record):
        del valid_raw_record["freeFlowSpeedKmh"]
        with pytest.raises(TransformError):
            enrich_record(valid_raw_record)

    def test_ms_unit_is_converted_before_ratio(self, valid_raw_record):
        # 10 m/s (=36 km/h) over 18 m/s (=64.8 km/h) free flow
        valid_raw_record["speedUnit"] = "ms"
        valid_raw_record["speedKmh"] = 10
        valid_raw_record["freeFlowSpeedKmh"] = 18

        record = enrich_record(valid_raw_record)

        assert record.speed_kmh == 36.0
        assert record.free_flow_speed_kmh == 64.8

    def test_naive_datetime_gets_utc_timezone(self, valid_raw_record):
        valid_raw_record["timestamp"] = datetime(2026, 9, 22, 8, 0)  # no tzinfo
        record = enrich_record(valid_raw_record)
        assert record.timestamp.tzinfo == timezone.utc

    def test_invalid_timestamp_string_raises(self, valid_raw_record):
        valid_raw_record["timestamp"] = "not-a-date"
        with pytest.raises(TransformError, match="invalid timestamp"):
            enrich_record(valid_raw_record)


# ---------------------------------------------------------------------------
# deduplicate_batch
# ---------------------------------------------------------------------------


class TestDeduplicateBatch:
    def test_keeps_latest_record_per_segment(self, valid_raw_record):
        older = enrich_record(valid_raw_record)

        newer_raw = dict(valid_raw_record)
        newer_raw["timestamp"] = "2026-09-22T09:00:00Z"
        newer_raw["speedKmh"] = 40.0
        newer = enrich_record(newer_raw)

        result = deduplicate_batch([older, newer])

        assert len(result) == 1
        assert result[0] is newer

    def test_different_segments_are_all_kept(self, valid_raw_record):
        rec_a = enrich_record(valid_raw_record)

        raw_b = dict(valid_raw_record)
        raw_b["segmentId"] = "seg-002"
        rec_b = enrich_record(raw_b)

        result = deduplicate_batch([rec_a, rec_b])
        assert {r.segment_id for r in result} == {"seg-001", "seg-002"}


# ---------------------------------------------------------------------------
# transform_batch (integration of the above)
# ---------------------------------------------------------------------------


class TestTransformBatch:
    def test_all_valid_records_pass(self, valid_raw_record):
        raw_b = dict(valid_raw_record)
        raw_b["segmentId"] = "seg-002"

        clean, failed = transform_batch([valid_raw_record, raw_b])

        assert len(clean) == 2
        assert failed == []

    def test_bad_record_does_not_break_the_batch(self, valid_raw_record):
        bad_record = {"segmentId": "seg-broken"}  # missing required fields

        clean, failed = transform_batch([valid_raw_record, bad_record])

        assert len(clean) == 1
        assert clean[0].segment_id == "seg-001"
        assert len(failed) == 1
        assert failed[0]["raw"] == bad_record
        assert "Missing required fields" in failed[0]["error"]

    def test_duplicate_segment_in_batch_is_deduplicated(self, valid_raw_record):
        newer_raw = dict(valid_raw_record)
        newer_raw["timestamp"] = "2026-09-22T09:00:00Z"

        clean, failed = transform_batch([valid_raw_record, newer_raw])

        assert len(clean) == 1
        assert clean[0].timestamp == datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
        assert failed == []

    def test_empty_batch_returns_empty_results(self):
        clean, failed = transform_batch([])
        assert clean == []
        assert failed == []
