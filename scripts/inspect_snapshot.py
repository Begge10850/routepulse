"""Inspect one GTFS-Realtime Protocol Buffer snapshot."""

import argparse
import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2


def inspect_snapshot(snapshot_path: Path) -> None:
    """Decode one snapshot and print a structural summary."""
    payload = snapshot_path.read_bytes()

    feed = gtfs_realtime_pb2.FeedMessage()

    try:
        feed.ParseFromString(payload)
    except DecodeError as error:
        raise SystemExit(f"Could not decode {snapshot_path}: {error}") from error

    entity_counts: Counter[str] = Counter()

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            entity_counts["trip_updates"] += 1

        if entity.HasField("vehicle"):
            entity_counts["vehicle_positions"] += 1

        if entity.HasField("alert"):
            entity_counts["alerts"] += 1

        if entity.is_deleted:
            entity_counts["deleted_entities"] += 1

    checksum = hashlib.sha256(payload).hexdigest()

    print(f"Snapshot path: {snapshot_path}")
    print(f"File size: {len(payload):,} bytes")
    print(f"SHA-256: {checksum}")
    print(f"GTFS-Realtime version: {feed.header.gtfs_realtime_version}")
    print(f"Total entities: {len(feed.entity):,}")
    print(f"Trip updates: {entity_counts['trip_updates']:,}")
    print(f"Vehicle positions: {entity_counts['vehicle_positions']:,}")
    print(f"Alerts: {entity_counts['alerts']:,}")
    print(f"Deleted entities: {entity_counts['deleted_entities']:,}")

    if feed.header.HasField("timestamp"):
        feed_time = datetime.fromtimestamp(
            feed.header.timestamp,
            tz=UTC,
        )
        print(f"Feed timestamp: {feed_time.isoformat()}")
    else:
        print("Feed timestamp: missing")


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Inspect one GTFS-Realtime snapshot.",
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Path to a saved GTFS-Realtime .pb file.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the snapshot inspection command."""
    arguments = parse_arguments()
    inspect_snapshot(arguments.snapshot)


if __name__ == "__main__":
    main()