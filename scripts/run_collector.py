"""Run the VBB realtime collector on a fixed schedule."""

import argparse
import json
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from routepulse.collector import (
    CollectionResult,
    DuplicateSnapshotError,
    NotModifiedError,
    collect_once,
)
from routepulse.config import load_config
from routepulse.storage import atomic_write_bytes

OUTPUT_DIRECTORY = Path("data/raw/gtfs_realtime")
MANIFEST_PATH = Path("logs/collection_manifest.jsonl")
MAX_RETRIES = 3


def append_manifest(record: dict[str, Any]) -> None:
    """Append one durable JSON record to the collection manifest."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    with MANIFEST_PATH.open("a", encoding="utf-8") as manifest_file:
        manifest_file.write(json.dumps(record, sort_keys=True) + "\n")
        manifest_file.flush()
        os.fsync(manifest_file.fileno())


def result_to_record(result: CollectionResult) -> dict[str, Any]:
    """Convert successful collection metadata to JSON-compatible values."""
    record = asdict(result)

    for field_name in (
        "request_started_at",
        "request_finished_at",
        "feed_timestamp",
    ):
        value = record[field_name]

        if isinstance(value, datetime):
            record[field_name] = value.isoformat()

    record["snapshot_path"] = str(record["snapshot_path"])
    return record


def write_snapshot_metadata(
    result: CollectionResult,
    record: dict[str, Any],
) -> None:
    """Write JSON metadata beside a saved Protocol Buffer snapshot."""
    metadata_path = result.snapshot_path.with_suffix(".json")
    metadata_bytes = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    atomic_write_bytes(metadata_path, metadata_bytes)


def load_existing_state() -> tuple[set[str], str | None]:
    """Load known checksums and the newest ETag from saved metadata."""
    checksums: set[str] = set()
    latest_etag: str | None = None

    for metadata_path in sorted(OUTPUT_DIRECTORY.glob("*.json")):
        try:
            record = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        checksum = record.get("checksum_sha256")
        etag = record.get("etag")

        if isinstance(checksum, str):
            checksums.add(checksum)

        if isinstance(etag, str):
            latest_etag = etag

    if MANIFEST_PATH.exists():
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            checksum = record.get("checksum_sha256")
            etag = record.get("etag")

            if isinstance(checksum, str):
                checksums.add(checksum)

            if isinstance(etag, str):
                latest_etag = etag

    return checksums, latest_etag


def parse_arguments() -> argparse.Namespace:
    """Read optional trial-run overrides."""
    parser = argparse.ArgumentParser(
        description="Run the RoutePulse realtime collector.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        help="Stop after this many scheduled attempts.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        help="Override the configured interval for a controlled trial.",
    )
    return parser.parse_args()


def make_event_record(
    *,
    attempt_number: int,
    status: str,
    retry_count: int,
    error: Exception | None = None,
) -> dict[str, Any]:
    """Create a manifest record for a non-saved outcome."""
    return {
        "attempt_number": attempt_number,
        "recorded_at": datetime.now(UTC).isoformat(),
        "status": status,
        "retry_count": retry_count,
        "error_type": type(error).__name__ if error else None,
        "error_message": str(error) if error else None,
    }


def run() -> int:
    """Run scheduled collection attempts and return a process exit code."""
    arguments = parse_arguments()
    config = load_config()

    interval_seconds = arguments.interval_seconds or config.interval_seconds
    max_attempts = arguments.max_attempts or config.expected_attempts

    if interval_seconds <= 0:
        raise ValueError("The interval must be greater than zero")

    if max_attempts <= 0:
        raise ValueError("The maximum attempts must be greater than zero")

    known_checksums, previous_etag = load_existing_state()

    print(
        f"Starting collector: attempts={max_attempts}, "
        f"interval_seconds={interval_seconds}",
        flush=True,
    )

    next_attempt_time = time.monotonic()
    successful_snapshots = 0
    unchanged_responses = 0
    duplicate_responses = 0
    failed_attempts = 0

    with httpx.Client(
        timeout=config.request_timeout_seconds,
        follow_redirects=True,
    ) as client:
        try:
            for attempt_number in range(1, max_attempts + 1):
                if attempt_number > 1:
                    sleep_seconds = max(
                        0.0,
                        next_attempt_time - time.monotonic(),
                    )
                    time.sleep(sleep_seconds)

                next_attempt_time += interval_seconds

                for retry_count in range(MAX_RETRIES):
                    try:
                        result = collect_once(
                            config=config,
                            output_directory=OUTPUT_DIRECTORY,
                            client=client,
                            previous_etag=previous_etag,
                            known_checksums=known_checksums,
                        )

                        record = result_to_record(result)
                        record.update(
                            {
                                "attempt_number": attempt_number,
                                "status": "saved",
                                "retry_count": retry_count,
                                "error_type": None,
                                "error_message": None,
                            },
                        )
                        write_snapshot_metadata(result, record)
                        append_manifest(record)

                        known_checksums.add(result.checksum_sha256)

                        if result.etag is not None:
                            previous_etag = result.etag

                        successful_snapshots += 1
                        print(
                            f"Attempt {attempt_number}: saved "
                            f"{result.snapshot_path.name}",
                            flush=True,
                        )
                        break

                    except NotModifiedError as error:
                        append_manifest(
                            make_event_record(
                                attempt_number=attempt_number,
                                status="not_modified",
                                retry_count=retry_count,
                                error=error,
                            ),
                        )
                        unchanged_responses += 1
                        print(
                            f"Attempt {attempt_number}: not modified",
                            flush=True,
                        )
                        break

                    except DuplicateSnapshotError as error:
                        append_manifest(
                            make_event_record(
                                attempt_number=attempt_number,
                                status="duplicate",
                                retry_count=retry_count,
                                error=error,
                            ),
                        )
                        duplicate_responses += 1
                        print(
                            f"Attempt {attempt_number}: duplicate",
                            flush=True,
                        )
                        break

                    except OSError as error:
                        append_manifest(
                            make_event_record(
                                attempt_number=attempt_number,
                                status="failed",
                                retry_count=retry_count,
                                error=error,
                            ),
                        )
                        print(f"Fatal storage error: {error}", flush=True)
                        return 1

                    except (
                        httpx.RequestError,
                        httpx.HTTPStatusError,
                        ValueError,
                    ) as error:
                        if retry_count + 1 < MAX_RETRIES:
                            backoff_seconds = 2**retry_count
                            print(
                                f"Attempt {attempt_number}: retrying after {error}",
                                flush=True,
                            )
                            time.sleep(backoff_seconds)
                            continue

                        append_manifest(
                            make_event_record(
                                attempt_number=attempt_number,
                                status="failed",
                                retry_count=retry_count,
                                error=error,
                            ),
                        )
                        failed_attempts += 1
                        print(
                            f"Attempt {attempt_number}: failed: {error}",
                            flush=True,
                        )

        except KeyboardInterrupt:
            print("Collector interrupted gracefully.", flush=True)

    summary = {
        "finished_at": datetime.now(UTC).isoformat(),
        "scheduled_attempts": max_attempts,
        "saved_snapshots": successful_snapshots,
        "not_modified_responses": unchanged_responses,
        "duplicate_responses": duplicate_responses,
        "failed_attempts": failed_attempts,
    }
    append_manifest({"status": "run_summary", **summary})
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
