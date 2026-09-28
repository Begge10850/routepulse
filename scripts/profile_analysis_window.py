"""Profile field availability across audited GTFS-Realtime snapshots."""
import json
from collections import Counter
from pathlib import Path
from typing import Any

from google.protobuf.message import DecodeError, Message
from google.transit import gtfs_realtime_pb2

INVENTORY_PATH = Path(
    "evidence/collection/analysis_window_inventory.jsonl"
)
OUTPUT_PATH = Path(
    "evidence/profiling/realtime_field_profile.json"
)

TRIP_DESCRIPTOR_FIELDS = (
    "trip_id",
    "route_id",
    "direction_id",
    "start_date",
    "start_time",
    "schedule_relationship",
)

TRIP_UPDATE_FIELDS = (
    "timestamp",
    "delay",
)

STOP_TIME_UPDATE_FIELDS = (
    "stop_sequence",
    "stop_id",
    "schedule_relationship",
)

STOP_TIME_EVENT_FIELDS = (
    "delay",
    "time",
    "uncertainty",
)

PROFILED_FIELD_NAMES = (
    *(f"trip.{name}" for name in TRIP_DESCRIPTOR_FIELDS),
    *(f"trip_update.{name}" for name in TRIP_UPDATE_FIELDS),
    "trip_update.vehicle",
    "trip_update.vehicle_id",
    *(f"stop_time_update.{name}" for name in STOP_TIME_UPDATE_FIELDS),
    "stop_time_update.arrival",
    "stop_time_update.departure",
    *(f"arrival.{name}" for name in STOP_TIME_EVENT_FIELDS),
    *(f"departure.{name}" for name in STOP_TIME_EVENT_FIELDS),
)


def count_present_fields(
    message: Message,
    field_names: tuple[str, ...],
    prefix: str,
    counts: Counter[str],
) -> None:
    """Count optional protobuf fields that contain explicit values."""
    for field_name in field_names:
        if message.HasField(field_name):
            counts[f"{prefix}.{field_name}"] += 1


def profile_feed(feed: gtfs_realtime_pb2.FeedMessage) -> dict[str, Any]:
    """Count the structural contents and field availability of one feed."""
    entity_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    relationship_counts: Counter[str] = Counter()
    stop_time_update_count = 0

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            entity_counts["trip_updates"] += 1
            trip_update = entity.trip_update
            trip = trip_update.trip

            count_present_fields(
                trip,
                TRIP_DESCRIPTOR_FIELDS,
                "trip",
                field_counts,
            )
            count_present_fields(
                trip_update,
                TRIP_UPDATE_FIELDS,
                "trip_update",
                field_counts,
            )

            if trip.HasField("schedule_relationship"):
                relationship_name = (
                    gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                        trip.schedule_relationship
                    )
                )
                relationship_counts[
                    f"trip.{relationship_name}"
                ] += 1

            if trip_update.HasField("vehicle"):
                field_counts["trip_update.vehicle"] += 1

                if trip_update.vehicle.HasField("id"):
                    field_counts["trip_update.vehicle_id"] += 1

            for stop_update in trip_update.stop_time_update:
                stop_time_update_count += 1

                count_present_fields(
                    stop_update,
                    STOP_TIME_UPDATE_FIELDS,
                    "stop_time_update",
                    field_counts,
                )

                if stop_update.HasField("schedule_relationship"):
                    relationship_name = (
                        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate
                        .ScheduleRelationship.Name(
                            stop_update.schedule_relationship
                        )
                    )
                    relationship_counts[
                        f"stop_time_update.{relationship_name}"
                    ] += 1

                if stop_update.HasField("arrival"):
                    field_counts["stop_time_update.arrival"] += 1
                    count_present_fields(
                        stop_update.arrival,
                        STOP_TIME_EVENT_FIELDS,
                        "arrival",
                        field_counts,
                    )

                if stop_update.HasField("departure"):
                    field_counts["stop_time_update.departure"] += 1
                    count_present_fields(
                        stop_update.departure,
                        STOP_TIME_EVENT_FIELDS,
                        "departure",
                        field_counts,
                    )

        if entity.HasField("vehicle"):
            entity_counts["vehicle_positions"] += 1

        if entity.HasField("alert"):
            entity_counts["alerts"] += 1

        if entity.is_deleted:
            entity_counts["deleted_entities"] += 1

    return {
        "total_entities": len(feed.entity),
        "trip_updates": entity_counts["trip_updates"],
        "vehicle_positions": entity_counts["vehicle_positions"],
        "alerts": entity_counts["alerts"],
        "deleted_entities": entity_counts["deleted_entities"],
        "stop_time_updates": stop_time_update_count,
        "field_presence": dict(sorted(field_counts.items())),
        "schedule_relationships": dict(
            sorted(relationship_counts.items())
        ),
    }


def decode_and_profile(payload: bytes) -> dict[str, Any]:
    """Decode one protobuf payload and profile its structure."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)

    return profile_feed(feed)

def load_inventory(inventory_path: Path) -> list[dict[str, Any]]:
    """Load audited snapshot records from a JSON-lines inventory."""
    records: list[dict[str, Any]] = []

    with inventory_path.open(encoding="utf-8") as inventory_file:
        for line_number, line in enumerate(inventory_file, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on inventory line {line_number}"
                ) from error

            records.append(record)

    return records


def merge_profile(
    totals: Counter[str],
    field_counts: Counter[str],
    relationship_counts: Counter[str],
    snapshot_profile: dict[str, Any],
) -> None:
    """Merge one snapshot profile into the analysis-window totals."""
    total_names = (
        "total_entities",
        "trip_updates",
        "vehicle_positions",
        "alerts",
        "deleted_entities",
        "stop_time_updates",
    )

    for total_name in total_names:
        totals[total_name] += snapshot_profile[total_name]

    field_counts.update(snapshot_profile["field_presence"])
    relationship_counts.update(
        snapshot_profile["schedule_relationships"]
    )


def field_denominator(
    field_name: str,
    totals: Counter[str],
) -> int:
    """Return the relevant row count for a profiled field."""
    if field_name.startswith("trip."):
        return totals["trip_updates"]

    if field_name.startswith("trip_update."):
        return totals["trip_updates"]

    return totals["stop_time_updates"]


def build_field_availability(
    field_counts: Counter[str],
    totals: Counter[str],
) -> dict[str, dict[str, int | float]]:
    """Calculate field-presence counts and percentages."""
    availability: dict[str, dict[str, int | float]] = {}

    for field_name in PROFILED_FIELD_NAMES:
        present_count = field_counts[field_name]
        denominator = field_denominator(field_name, totals)

        if denominator == 0:
            percentage = 0.0
        else:
            percentage = round(
                present_count / denominator * 100,
                4,
            )

        availability[field_name] = {
            "present": present_count,
            "denominator": denominator,
            "percentage": percentage,
        }

    return availability

def profile_inventory_records(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Profile every snapshot referenced by the audited inventory."""
    totals: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    relationship_counts: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []

    for position, record in enumerate(records, start=1):
        snapshot_path = Path(record["snapshot_path"])

        try:
            payload = snapshot_path.read_bytes()
            snapshot_profile = decode_and_profile(payload)
        except (OSError, DecodeError) as error:
            failures.append(
                {
                    "attempt_number": record.get("attempt_number"),
                    "snapshot_path": str(snapshot_path),
                    "error": str(error),
                }
            )
        else:
            merge_profile(
                totals,
                field_counts,
                relationship_counts,
                snapshot_profile,
            )

        if position % 25 == 0 or position == len(records):
            print(f"Profiled {position:,} of {len(records):,} snapshots")

    return {
        "snapshots_listed": len(records),
        "snapshots_profiled": len(records) - len(failures),
        "snapshots_failed": len(failures),
        "totals": {
            "total_entities": totals["total_entities"],
            "trip_updates": totals["trip_updates"],
            "vehicle_positions": totals["vehicle_positions"],
            "alerts": totals["alerts"],
            "deleted_entities": totals["deleted_entities"],
            "stop_time_updates": totals["stop_time_updates"],
        },
        "field_availability": build_field_availability(
            field_counts,
            totals,
        ),
        "schedule_relationships": dict(
            sorted(relationship_counts.items())
        ),
        "failures": failures,
    }


def main() -> None:
    """Profile the audited analysis window and save its evidence."""
    records = load_inventory(INVENTORY_PATH)
    report = profile_inventory_records(records)
    report["source_inventory"] = str(INVENTORY_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Profile written to {OUTPUT_PATH}")
    print(f"Snapshots profiled: {report['snapshots_profiled']:,}")
    print(f"Snapshots failed: {report['snapshots_failed']:,}")
    print(f"Trip updates: {report['totals']['trip_updates']:,}")
    print(
        "Stop-time updates: "
        f"{report['totals']['stop_time_updates']:,}"
    )

    if report["snapshots_failed"]:
        raise SystemExit(
            "Profiling completed with snapshot failures. "
            "Review the evidence report."
        )


if __name__ == "__main__":
    main()