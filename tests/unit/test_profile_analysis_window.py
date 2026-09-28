import json
from collections import Counter
from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2

import scripts.profile_analysis_window as profiler


def build_test_feed() -> gtfs_realtime_pb2.FeedMessage:
    """Create a small GTFS-Realtime feed with known contents."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"

    first_trip = feed.entity.add()
    first_trip.id = "trip-update-1"
    first_trip.trip_update.trip.trip_id = "trip-1"
    first_trip.trip_update.trip.route_id = "route-7"
    first_trip.trip_update.trip.direction_id = 0
    first_trip.trip_update.trip.start_date = "20260925"
    first_trip.trip_update.trip.start_time = "12:00:00"
    first_trip.trip_update.trip.schedule_relationship = (
        gtfs_realtime_pb2.TripDescriptor.SCHEDULED
    )
    first_trip.trip_update.timestamp = 1_000
    first_trip.trip_update.delay = 120
    first_trip.trip_update.vehicle.id = "vehicle-7"

    first_stop = first_trip.trip_update.stop_time_update.add()
    first_stop.stop_sequence = 1
    first_stop.stop_id = "stop-A"
    first_stop.schedule_relationship = (
        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SCHEDULED
    )
    first_stop.arrival.delay = 120
    first_stop.arrival.time = 1_100
    first_stop.arrival.uncertainty = 30
    first_stop.departure.delay = 150
    first_stop.departure.time = 1_130
    first_stop.departure.uncertainty = 20

    second_stop = first_trip.trip_update.stop_time_update.add()
    second_stop.stop_sequence = 2
    second_stop.stop_id = "stop-B"
    second_stop.schedule_relationship = (
        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED
    )

    second_trip = feed.entity.add()
    second_trip.id = "trip-update-2"
    second_trip.trip_update.trip.trip_id = "trip-2"
    second_trip.trip_update.trip.route_id = "route-12"
    second_trip.trip_update.trip.schedule_relationship = (
        gtfs_realtime_pb2.TripDescriptor.CANCELED
    )

    third_stop = second_trip.trip_update.stop_time_update.add()
    third_stop.stop_sequence = 3
    third_stop.stop_id = "stop-C"
    third_stop.schedule_relationship = (
        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SCHEDULED
    )
    third_stop.arrival.time = 1_200
    third_stop.departure.time = 1_230

    vehicle = feed.entity.add()
    vehicle.id = "vehicle-1"
    vehicle.vehicle.trip.trip_id = "trip-1"

    alert = feed.entity.add()
    alert.id = "alert-1"
    alert.alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION

    deleted = feed.entity.add()
    deleted.id = "deleted-1"
    deleted.is_deleted = True

    return feed


def test_profile_feed_counts_known_entities() -> None:
    feed = build_test_feed()

    result = profiler.profile_feed(feed)

    assert result == {
        "total_entities": 5,
        "trip_updates": 2,
        "vehicle_positions": 1,
        "alerts": 1,
        "deleted_entities": 1,
        "stop_time_updates": 3,
        "field_presence": {
            "arrival.delay": 1,
            "arrival.time": 2,
            "arrival.uncertainty": 1,
            "departure.delay": 1,
            "departure.time": 2,
            "departure.uncertainty": 1,
            "stop_time_update.arrival": 2,
            "stop_time_update.departure": 2,
            "stop_time_update.schedule_relationship": 3,
            "stop_time_update.stop_id": 3,
            "stop_time_update.stop_sequence": 3,
            "trip.direction_id": 1,
            "trip.route_id": 2,
            "trip.schedule_relationship": 2,
            "trip.start_date": 1,
            "trip.start_time": 1,
            "trip.trip_id": 2,
            "trip_update.delay": 1,
            "trip_update.timestamp": 1,
            "trip_update.vehicle": 1,
            "trip_update.vehicle_id": 1,
        },
        "schedule_relationships": {
            "stop_time_update.SCHEDULED": 2,
            "stop_time_update.SKIPPED": 1,
            "trip.CANCELED": 1,
            "trip.SCHEDULED": 1,
        },
    }


def test_decode_and_profile_parses_serialized_feed() -> None:
    feed = build_test_feed()
    payload = feed.SerializeToString()

    result = profiler.decode_and_profile(payload)

    assert result["total_entities"] == 5
    assert result["trip_updates"] == 2
    assert result["stop_time_updates"] == 3

def test_load_inventory_reads_json_lines(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.jsonl"
    records = [
        {"attempt_number": 1, "snapshot_path": "first.pb"},
        {"attempt_number": 2, "snapshot_path": "second.pb"},
    ]
    inventory_path.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )

    result = profiler.load_inventory(inventory_path)

    assert result == records


def test_load_inventory_rejects_invalid_json(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.jsonl"
    inventory_path.write_text(
        '{"attempt_number": 1}\nnot-json\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="inventory line 2"):
        profiler.load_inventory(inventory_path)


def test_merge_and_availability_use_correct_denominators() -> None:
    totals: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    relationship_counts: Counter[str] = Counter()

    snapshot_profile = {
        "total_entities": 10,
        "trip_updates": 4,
        "vehicle_positions": 1,
        "alerts": 0,
        "deleted_entities": 0,
        "stop_time_updates": 5,
        "field_presence": {
            "trip.route_id": 3,
            "arrival.delay": 2,
        },
        "schedule_relationships": {
            "trip.SCHEDULED": 4,
        },
    }

    profiler.merge_profile(
        totals,
        field_counts,
        relationship_counts,
        snapshot_profile,
    )
    availability = profiler.build_field_availability(
        field_counts,
        totals,
    )

    assert totals["total_entities"] == 10
    assert totals["trip_updates"] == 4
    assert totals["stop_time_updates"] == 5
    assert relationship_counts["trip.SCHEDULED"] == 4

    assert availability["trip.route_id"] == {
        "present": 3,
        "denominator": 4,
        "percentage": 75.0,
    }
    assert availability["arrival.delay"] == {
        "present": 2,
        "denominator": 5,
        "percentage": 40.0,
    }
    

def test_profile_inventory_records_reads_snapshot_files(
    tmp_path: Path,
) -> None:
    feed = build_test_feed()
    payload = feed.SerializeToString()

    first_path = tmp_path / "first.pb"
    second_path = tmp_path / "second.pb"
    first_path.write_bytes(payload)
    second_path.write_bytes(payload)

    records = [
        {
            "attempt_number": 1,
            "snapshot_path": str(first_path),
        },
        {
            "attempt_number": 2,
            "snapshot_path": str(second_path),
        },
    ]

    result = profiler.profile_inventory_records(records)

    assert result["snapshots_listed"] == 2
    assert result["snapshots_profiled"] == 2
    assert result["snapshots_failed"] == 0
    assert result["totals"]["total_entities"] == 10
    assert result["totals"]["trip_updates"] == 4
    assert result["totals"]["stop_time_updates"] == 6
    assert result["field_availability"]["trip.route_id"] == {
        "present": 4,
        "denominator": 4,
        "percentage": 100.0,
    }
    assert result["failures"] == []