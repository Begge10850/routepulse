"""Audit the timing and outcomes of the GTFS-Realtime collection."""
import hashlib
import json
from collections import Counter
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path("logs/collection_manifest.jsonl")
EXPECTED_INTERVAL_SECONDS = 180
MAX_CONTINUOUS_GAP_SECONDS = EXPECTED_INTERVAL_SECONDS * 2
ANALYSIS_CUTOFF = datetime.fromisoformat(
    "2026-09-27T03:52:43+00:00"
)

INVENTORY_PATH = Path(
    "evidence/collection/analysis_window_inventory.jsonl"
)
SUMMARY_PATH = Path(
    "evidence/collection/analysis_window_summary.json"
)

def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Load individual JSON records from a JSON Lines manifest."""
    records: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as manifest_file:
        for line_number, line in enumerate(manifest_file, start=1):
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                record = json.loads(stripped_line)
            except json.JSONDecodeError as error:
                raise TypeError(
                    f"Invalid JSON on line {line_number}: {error}"
                ) from error

            records.append(record)

    return records

def get_attempt_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return collection-attempt records in attempt-number order."""
    attempts = [
        record
        for record in records
        if isinstance(record.get("attempt_number"), int)
    ]

    return sorted(attempts, key=lambda record: record["attempt_number"])


def get_record_time(record: dict[str, Any]) -> datetime:
    """Return the timestamp representing when an attempt occurred."""
    timestamp_text = record.get("request_started_at") or record.get("recorded_at")

    if not isinstance(timestamp_text, str):
        attempt_number = record.get("attempt_number", "unknown")
        raise TypeError(
            f"Attempt {attempt_number} has no usable timestamp"
        )

    timestamp = datetime.fromisoformat(timestamp_text)

    if timestamp.utcoffset() is None:
        raise TypeError(
            f"Timestamp has no timezone information: {timestamp_text}"
        )

    return timestamp


def find_large_gaps(
    attempts: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    """Find consecutive attempts separated by more than the allowed gap."""
    large_gaps: list[
        tuple[dict[str, Any], dict[str, Any], float]
    ] = []

    for previous, current in pairwise(attempts):
        previous_time = get_record_time(previous)
        current_time = get_record_time(current)
        gap_seconds = (current_time - previous_time).total_seconds()

        if gap_seconds > MAX_CONTINUOUS_GAP_SECONDS:
            large_gaps.append((previous, current, gap_seconds))

    return large_gaps

def select_analysis_attempts(
    attempts: list[dict[str, Any]],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Select attempts occurring before the documented sleep event."""
    return [
        record
        for record in attempts
        if get_record_time(record) < cutoff
    ]

def calculate_file_sha256(path: Path) -> str:
    """Calculate a file's SHA-256 checksum without loading it all at once."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def verify_saved_snapshots(
    saved_records: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str], int]:
    """Verify selected snapshot files, metadata sidecars, and checksums."""
    missing_snapshots: list[str] = []
    missing_sidecars: list[str] = []
    checksum_mismatches: list[str] = []
    total_bytes = 0

    for record in saved_records:
        snapshot_text = record.get("snapshot_path")
        expected_checksum = record.get("checksum_sha256")

        if not isinstance(snapshot_text, str):
            raise TypeError("Saved record has no valid snapshot path")

        if not isinstance(expected_checksum, str):
            raise TypeError(
                f"Snapshot {snapshot_text} has no valid checksum"
            )

        snapshot_path = Path(snapshot_text)
        sidecar_path = snapshot_path.with_suffix(".json")

        if not snapshot_path.is_file():
            missing_snapshots.append(snapshot_text)
            continue

        total_bytes += snapshot_path.stat().st_size

        if not sidecar_path.is_file():
            missing_sidecars.append(str(sidecar_path))

        actual_checksum = calculate_file_sha256(snapshot_path)

        if actual_checksum != expected_checksum:
            checksum_mismatches.append(snapshot_text)

    return (
        missing_snapshots,
        missing_sidecars,
        checksum_mismatches,
        total_bytes,
    )

def build_inventory(
    saved_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the authoritative inventory of selected snapshot files."""
    inventory: list[dict[str, Any]] = []

    for record in saved_records:
        snapshot_path = Path(record["snapshot_path"])

        inventory.append(
            {
                "attempt_number": record["attempt_number"],
                "request_started_at": record["request_started_at"],
                "feed_timestamp": record["feed_timestamp"],
                "snapshot_path": str(snapshot_path),
                "sidecar_path": str(snapshot_path.with_suffix(".json")),
                "checksum_sha256": record["checksum_sha256"],
                "size_bytes": snapshot_path.stat().st_size,
            }
        )

    return inventory


def write_json(path: Path, value: Any) -> None:
    """Write formatted JSON using an atomic temporary-file replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def write_json_lines(
    path: Path,
    records: list[dict[str, Any]],
) -> None:
    """Write records as JSON Lines using atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    contents = "".join(
        json.dumps(record, sort_keys=True) + "\n"
        for record in records
    )
    temporary_path.write_text(contents, encoding="utf-8")
    temporary_path.replace(path)

def main() -> None:
    records = load_manifest(MANIFEST_PATH)
    attempts = get_attempt_records(records)
    status_counts = Counter(record["status"] for record in attempts)
    large_gaps = find_large_gaps(attempts)

    analysis_attempts = select_analysis_attempts(
        attempts,
        ANALYSIS_CUTOFF,
    )
    analysis_status_counts = Counter(
        record["status"] for record in analysis_attempts
    )
    saved_analysis_records = [
        record
        for record in analysis_attempts
        if record["status"] == "saved"
    ]

    (
    missing_snapshots,
    missing_sidecars,
    checksum_mismatches,
    selected_bytes,
    ) = verify_saved_snapshots(saved_analysis_records)

    analysis_start = get_record_time(analysis_attempts[0])
    analysis_end = get_record_time(analysis_attempts[-1])
    analysis_duration = analysis_end - analysis_start

    inventory = build_inventory(saved_analysis_records)

    summary = {
        "analysis_start_utc": analysis_start.isoformat(),
        "analysis_end_utc": analysis_end.isoformat(),
        "duration_hours": analysis_duration.total_seconds() / 3600,
        "first_attempt": analysis_attempts[0]["attempt_number"],
        "last_attempt": analysis_attempts[-1]["attempt_number"],
        "selected_attempts": len(analysis_attempts),
        "selected_saved_snapshots": len(saved_analysis_records),
        "status_counts": dict(analysis_status_counts),
        "selected_bytes": selected_bytes,
        "missing_snapshots": len(missing_snapshots),
        "missing_sidecars": len(missing_sidecars),
        "checksum_mismatches": len(checksum_mismatches),
        "large_gaps_after_window": len(large_gaps),
    }

    write_json_lines(INVENTORY_PATH, inventory)
    write_json(SUMMARY_PATH, summary)

    print(f"Manifest records: {len(records)}")
    print(f"Collection attempts: {len(attempts)}")
    print(f"Status counts: {dict(status_counts)}")
    print(f"Large gaps: {len(large_gaps)}")

    print()
    print("Selected continuous analysis window")
    print(f"First attempt: {analysis_attempts[0]['attempt_number']}")
    print(f"Last attempt: {analysis_attempts[-1]['attempt_number']}")
    print(f"Start UTC: {analysis_start.isoformat()}")
    print(f"End UTC: {analysis_end.isoformat()}")
    print(
        "Duration hours: "
        f"{analysis_duration.total_seconds() / 3600:.2f}"
    )
    print(f"Selected attempts: {len(analysis_attempts)}")
    print(f"Selected status counts: {dict(analysis_status_counts)}")
    print(f"Selected saved snapshots: {len(saved_analysis_records)}")
    print(f"Missing snapshots: {len(missing_snapshots)}")
    print(f"Missing sidecars: {len(missing_sidecars)}")
    print(f"Checksum mismatches: {len(checksum_mismatches)}")
    print(f"Selected size GB: {selected_bytes / 1_000_000_000:.2f}")

    print(f"Inventory path: {INVENTORY_PATH}")
    print(f"Summary path: {SUMMARY_PATH}")

    for previous, current, gap_seconds in large_gaps:
        print()
        print(
            f"Attempt {previous['attempt_number']} "
            f"to attempt {current['attempt_number']}"
        )
        print(f"Previous time: {get_record_time(previous).isoformat()}")
        print(f"Current time: {get_record_time(current).isoformat()}")
        print(f"Gap seconds: {gap_seconds:.1f}")
        print(f"Gap hours: {gap_seconds / 3600:.2f}")

if __name__ == "__main__":
    main()