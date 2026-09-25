"""Collect one live VBB GTFS-Realtime snapshot."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from routepulse.collector import CollectionResult, collect_once
from routepulse.config import load_config
from routepulse.storage import atomic_write_bytes

OUTPUT_DIRECTORY = Path("data/raw/gtfs_realtime")


def make_json_record(result: CollectionResult) -> dict[str, Any]:
    """Convert collection metadata into JSON-compatible values."""
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


def main() -> None:
    """Collect one validated snapshot and save its metadata."""
    config = load_config()

    with httpx.Client(
        timeout=config.request_timeout_seconds,
        follow_redirects=True,
    ) as client:
        result = collect_once(
            config=config,
            output_directory=OUTPUT_DIRECTORY,
            client=client,
        )

    record = make_json_record(result)
    metadata_path = result.snapshot_path.with_suffix(".json")
    metadata_bytes = (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    atomic_write_bytes(metadata_path, metadata_bytes)

    print(json.dumps(record, indent=2, sort_keys=True))
    print(f"Metadata path: {metadata_path}")


if __name__ == "__main__":
    main()