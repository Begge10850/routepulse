import json
from datetime import datetime

import pytest

from scripts.audit_collection import (
    find_large_gaps,
    get_attempt_records,
    get_record_time,
    load_manifest,
    select_analysis_attempts,
)


def make_attempt(
    attempt_number: int,
    timestamp: str,
    status: str = "saved",
) -> dict[str, object]:
    """Create a minimal collection-attempt record for testing."""
    return {
        "attempt_number": attempt_number,
        "request_started_at": timestamp,
        "status": status,
    }


def test_load_manifest_reads_json_lines(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    records = [
        {"attempt_number": 1, "status": "saved"},
        {"attempt_number": 2, "status": "duplicate"},
    ]
    manifest_path.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )

    assert load_manifest(manifest_path) == records


def test_get_attempt_records_excludes_summary_and_sorts() -> None:
    records = [
        {"attempt_number": 2, "status": "saved"},
        {"status": "run_summary"},
        {"attempt_number": 1, "status": "saved"},
    ]

    attempts = get_attempt_records(records)

    assert [record["attempt_number"] for record in attempts] == [1, 2]


def test_get_record_time_uses_recorded_at_fallback() -> None:
    record = {
        "attempt_number": 1,
        "recorded_at": "2026-09-25T12:20:00+00:00",
    }

    assert get_record_time(record) == datetime.fromisoformat(
        "2026-09-25T12:20:00+00:00"
    )


def test_find_large_gaps_detects_interruption() -> None:
    attempts = [
        make_attempt(1, "2026-09-25T12:20:00+00:00"),
        make_attempt(2, "2026-09-25T12:23:00+00:00"),
        make_attempt(3, "2026-09-25T13:00:00+00:00"),
    ]

    gaps = find_large_gaps(attempts)

    assert len(gaps) == 1
    previous, current, gap_seconds = gaps[0]
    assert previous["attempt_number"] == 2
    assert current["attempt_number"] == 3
    assert gap_seconds == 2_220


def test_select_analysis_attempts_excludes_cutoff_and_later() -> None:
    attempts = [
        make_attempt(1, "2026-09-25T12:20:00+00:00"),
        make_attempt(2, "2026-09-25T12:23:00+00:00"),
        make_attempt(3, "2026-09-25T12:26:00+00:00"),
    ]
    cutoff = datetime.fromisoformat("2026-09-25T12:26:00+00:00")

    selected = select_analysis_attempts(attempts, cutoff)

    assert [record["attempt_number"] for record in selected] == [1, 2]


def test_get_record_time_rejects_missing_timestamp() -> None:
    record = {"attempt_number": 1, "status": "saved"}

    with pytest.raises(TypeError, match="no usable timestamp"):
        get_record_time(record)