from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
from google.transit import gtfs_realtime_pb2

import scripts.convert_realtime_to_parquet as converter


def build_test_feed() -> gtfs_realtime_pb2.FeedMessage:
    """Create a known feed for testing row extraction."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_700_000_000

    entity = feed.entity.add()
    entity.id = "entity-1"

    trip_update = entity.trip_update
    trip_update.trip.trip_id = "trip-1"
    trip_update.trip.route_id = "route-7"
    trip_update.trip.direction_id = 0
    trip_update.trip.start_date = "20260925"
    trip_update.trip.schedule_relationship = (
        gtfs_realtime_pb2.TripDescriptor.SCHEDULED
    )
    trip_update.timestamp = 1_700_000_010

    first_stop = trip_update.stop_time_update.add()
    first_stop.stop_id = "stop-A"
    first_stop.stop_sequence = 1
    first_stop.schedule_relationship = (
        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SCHEDULED
    )
    first_stop.arrival.delay = 0
    first_stop.arrival.time = 1_700_000_100

    second_stop = trip_update.stop_time_update.add()
    second_stop.stop_id = "stop-B"
    second_stop.stop_sequence = 2
    second_stop.schedule_relationship = (
        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED
    )

    return feed


def build_inventory_record() -> dict[str, object]:
    """Create matching audit metadata for the test feed."""
    return {
        "attempt_number": 42,
        "request_started_at": "2026-09-25T12:20:16+00:00",
        "snapshot_path": "data/raw/gtfs_realtime/snapshot.pb",
        "checksum_sha256": "known-checksum",
    }


def test_extract_snapshot_rows_preserves_values_and_nulls() -> None:
    feed = build_test_feed()
    record = build_inventory_record()

    feed_row, trip_rows, stop_rows = (
        converter.extract_snapshot_rows(
            record,
            feed.SerializeToString(),
        )
    )

    assert feed_row["snapshot_id"] == "snapshot"
    assert feed_row["attempt_number"] == 42
    assert feed_row["request_started_at"] == datetime(
        2026,
        9,
        25,
        12,
        20,
        16,
        tzinfo=UTC,
    )
    assert feed_row["feed_timestamp"] == datetime.fromtimestamp(
        1_700_000_000,
        tz=UTC,
    )
    assert feed_row["entity_count"] == 1
    assert feed_row["trip_update_count"] == 1
    assert feed_row["stop_time_update_count"] == 2

    assert len(trip_rows) == 1
    assert trip_rows[0]["trip_id"] == "trip-1"
    assert trip_rows[0]["route_id"] == "route-7"
    assert trip_rows[0]["direction_id"] == 0
    assert (
        trip_rows[0]["trip_schedule_relationship"]
        == "SCHEDULED"
    )
    assert trip_rows[0]["vehicle_id"] is None
    assert trip_rows[0]["trip_delay_seconds"] is None
    assert trip_rows[0]["stop_time_update_count"] == 2

    assert len(stop_rows) == 2
    assert stop_rows[0]["stop_id"] == "stop-A"
    assert stop_rows[0]["arrival_delay_seconds"] == 0
    assert stop_rows[0]["arrival_timestamp"] == (
        datetime.fromtimestamp(1_700_000_100, tz=UTC)
    )
    assert stop_rows[0]["departure_timestamp"] is None

    assert stop_rows[1]["stop_id"] == "stop-B"
    assert (
        stop_rows[1]["stop_schedule_relationship"]
        == "SKIPPED"
    )
    assert stop_rows[1]["arrival_delay_seconds"] is None
    assert stop_rows[1]["arrival_timestamp"] is None

def test_rows_to_table_applies_explicit_schemas() -> None:
    feed = build_test_feed()
    record = build_inventory_record()

    feed_row, trip_rows, stop_rows = (
        converter.extract_snapshot_rows(
            record,
            feed.SerializeToString(),
        )
    )

    feed_table = converter.rows_to_table(
        [feed_row],
        converter.FEED_SCHEMA,
    )
    trip_table = converter.rows_to_table(
        trip_rows,
        converter.TRIP_SCHEMA,
    )
    stop_table = converter.rows_to_table(
        stop_rows,
        converter.STOP_SCHEMA,
    )

    assert feed_table.schema == converter.FEED_SCHEMA
    assert trip_table.schema == converter.TRIP_SCHEMA
    assert stop_table.schema == converter.STOP_SCHEMA

    assert feed_table.num_rows == 1
    assert trip_table.num_rows == 1
    assert stop_table.num_rows == 2

    assert trip_table.column("vehicle_id").null_count == 1
    assert stop_table.column("arrival_delay_seconds")[0].as_py() == 0
    assert stop_table.column("arrival_delay_seconds")[1].as_py() is None

def test_rotating_writer_creates_typed_file_parts(
    tmp_path: Path,
) -> None:
    feed = build_test_feed()
    record = build_inventory_record()
    feed_row, _, _ = converter.extract_snapshot_rows(
        record,
        feed.SerializeToString(),
    )
    table = converter.rows_to_table(
        [feed_row],
        converter.FEED_SCHEMA,
    )

    writer = converter.RotatingParquetWriter(
        output_directory=tmp_path / "feed_snapshots",
        schema=converter.FEED_SCHEMA,
        maximum_rows_per_file=1,
    )

    writer.write_table(table)
    writer.write_table(table)
    writer.close()

    assert writer.total_rows == 2
    assert len(writer.file_paths) == 2
    assert writer.file_paths[0].name == "part-00000.parquet"
    assert writer.file_paths[1].name == "part-00001.parquet"

    first_table = pq.read_table(writer.file_paths[0])
    second_table = pq.read_table(writer.file_paths[1])

    assert first_table.schema == converter.FEED_SCHEMA
    assert second_table.schema == converter.FEED_SCHEMA
    assert first_table.num_rows == 1
    assert second_table.num_rows == 1