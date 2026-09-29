"""Convert audited GTFS-Realtime snapshots into analytical rows."""

"""Convert audited GTFS-Realtime snapshots into analytical rows."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from google.transit import gtfs_realtime_pb2

UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")

FEED_SCHEMA = pa.schema(
    [
        ("snapshot_id", pa.string()),
        ("attempt_number", pa.int32()),
        ("request_started_at", UTC_TIMESTAMP),
        ("feed_timestamp", UTC_TIMESTAMP),
        ("gtfs_realtime_version", pa.string()),
        ("entity_count", pa.int32()),
        ("trip_update_count", pa.int32()),
        ("stop_time_update_count", pa.int32()),
        ("vehicle_position_count", pa.int32()),
        ("alert_count", pa.int32()),
        ("deleted_entity_count", pa.int32()),
        ("checksum_sha256", pa.string()),
        ("source_path", pa.string()),
    ]
)

TRIP_SCHEMA = pa.schema(
    [
        ("snapshot_id", pa.string()),
        ("attempt_number", pa.int32()),
        ("entity_id", pa.string()),
        ("trip_id", pa.string()),
        ("route_id", pa.string()),
        ("direction_id", pa.int32()),
        ("start_date", pa.string()),
        ("start_time", pa.string()),
        ("trip_schedule_relationship", pa.string()),
        ("vehicle_id", pa.string()),
        ("trip_update_timestamp", UTC_TIMESTAMP),
        ("trip_delay_seconds", pa.int64()),
        ("stop_time_update_count", pa.int32()),
    ]
)

STOP_SCHEMA = pa.schema(
    [
        ("snapshot_id", pa.string()),
        ("attempt_number", pa.int32()),
        ("entity_id", pa.string()),
        ("trip_id", pa.string()),
        ("route_id", pa.string()),
        ("direction_id", pa.int32()),
        ("start_date", pa.string()),
        ("stop_id", pa.string()),
        ("stop_sequence", pa.int32()),
        ("stop_schedule_relationship", pa.string()),
        ("arrival_delay_seconds", pa.int64()),
        ("arrival_timestamp", UTC_TIMESTAMP),
        ("arrival_uncertainty_seconds", pa.int64()),
        ("departure_delay_seconds", pa.int64()),
        ("departure_timestamp", UTC_TIMESTAMP),
        ("departure_uncertainty_seconds", pa.int64()),
    ]
)

def rows_to_table(
    rows: list[dict[str, Any]],
    schema: pa.Schema,
) -> pa.Table:
    """Convert extracted rows into a table with explicit types."""
    return pa.Table.from_pylist(rows, schema=schema)

def optional_value(message: Any, field_name: str) -> Any | None:
    """Return an explicitly populated protobuf value or null."""
    if message.HasField(field_name):
        return getattr(message, field_name)

    return None


def optional_timestamp(
    message: Any,
    field_name: str,
) -> datetime | None:
    """Convert an optional Unix timestamp to a UTC datetime."""
    value = optional_value(message, field_name)

    if value is None:
        return None

    return datetime.fromtimestamp(value, tz=UTC)

class RotatingParquetWriter:
    """Write typed Parquet parts without retaining the full dataset."""

    def __init__(
        self,
        output_directory: Path,
        schema: pa.Schema,
        maximum_rows_per_file: int,
    ) -> None:
        self.output_directory = output_directory
        self.schema = schema
        self.maximum_rows_per_file = maximum_rows_per_file
        self.writer: pq.ParquetWriter | None = None
        self.file_number = 0
        self.rows_in_current_file = 0
        self.total_rows = 0
        self.file_paths: list[Path] = []

    def _open_next_file(self) -> None:
        """Open the next numbered Parquet part."""
        self.close_current_file()
        self.output_directory.mkdir(parents=True, exist_ok=True)

        output_path = (
            self.output_directory
            / f"part-{self.file_number:05d}.parquet"
        )
        self.file_number += 1

        self.writer = pq.ParquetWriter(
            output_path,
            self.schema,
            compression="zstd",
            use_dictionary=True,
        )
        self.file_paths.append(output_path)
        self.rows_in_current_file = 0

    def write_table(self, table: pa.Table) -> None:
        """Write one table, rotating files at the configured limit."""
        if table.schema != self.schema:
            raise ValueError("Table schema does not match writer schema")

        if table.num_rows == 0:
            return

        would_exceed_limit = (
            self.rows_in_current_file > 0
            and self.rows_in_current_file + table.num_rows
            > self.maximum_rows_per_file
        )

        if self.writer is None or would_exceed_limit:
            self._open_next_file()

        if self.writer is None:
            raise RuntimeError("Parquet writer was not opened")

        self.writer.write_table(
            table,
            row_group_size=100_000,
        )
        self.rows_in_current_file += table.num_rows
        self.total_rows += table.num_rows

    def close_current_file(self) -> None:
        """Close the active Parquet file, if one is open."""
        if self.writer is not None:
            self.writer.close()
            self.writer = None
            self.rows_in_current_file = 0

    def close(self) -> None:
        """Finish writing the dataset."""
        self.close_current_file()


def optional_enum_name(
    message: Any,
    field_name: str,
    enum_type: Any,
) -> str | None:
    """Return an optional protobuf enum as a readable name."""
    value = optional_value(message, field_name)

    if value is None:
        return None

    return enum_type.Name(value)


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and preserve its timezone."""
    return datetime.fromisoformat(value)


def extract_snapshot_rows(
    record: dict[str, Any],
    payload: bytes,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Decode one snapshot into feed, trip, and stop-level rows."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)

    snapshot_path = Path(record["snapshot_path"])
    snapshot_id = snapshot_path.stem

    trip_rows: list[dict[str, Any]] = []
    stop_rows: list[dict[str, Any]] = []

    vehicle_position_count = 0
    alert_count = 0
    deleted_entity_count = 0

    for entity in feed.entity:
        if entity.HasField("vehicle"):
            vehicle_position_count += 1

        if entity.HasField("alert"):
            alert_count += 1

        if entity.is_deleted:
            deleted_entity_count += 1

        if not entity.HasField("trip_update"):
            continue

        trip_update = entity.trip_update
        trip = trip_update.trip

        trip_relationship = optional_enum_name(
            trip,
            "schedule_relationship",
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship,
        )

        vehicle_id = None
        if (
            trip_update.HasField("vehicle")
            and trip_update.vehicle.HasField("id")
        ):
            vehicle_id = trip_update.vehicle.id

        trip_row = {
            "snapshot_id": snapshot_id,
            "attempt_number": record["attempt_number"],
            "entity_id": entity.id,
            "trip_id": optional_value(trip, "trip_id"),
            "route_id": optional_value(trip, "route_id"),
            "direction_id": optional_value(trip, "direction_id"),
            "start_date": optional_value(trip, "start_date"),
            "start_time": optional_value(trip, "start_time"),
            "trip_schedule_relationship": trip_relationship,
            "vehicle_id": vehicle_id,
            "trip_update_timestamp": optional_timestamp(
                trip_update,
                "timestamp",
            ),
            "trip_delay_seconds": optional_value(
                trip_update,
                "delay",
            ),
            "stop_time_update_count": len(
                trip_update.stop_time_update
            ),
        }
        trip_rows.append(trip_row)

        for stop_update in trip_update.stop_time_update:
            arrival = (
                stop_update.arrival
                if stop_update.HasField("arrival")
                else None
            )
            departure = (
                stop_update.departure
                if stop_update.HasField("departure")
                else None
            )

            stop_relationship = optional_enum_name(
                stop_update,
                "schedule_relationship",
                (
                    gtfs_realtime_pb2.TripUpdate.StopTimeUpdate
                    .ScheduleRelationship
                ),
            )

            stop_row = {
                "snapshot_id": snapshot_id,
                "attempt_number": record["attempt_number"],
                "entity_id": entity.id,
                "trip_id": optional_value(trip, "trip_id"),
                "route_id": optional_value(trip, "route_id"),
                "direction_id": optional_value(
                    trip,
                    "direction_id",
                ),
                "start_date": optional_value(trip, "start_date"),
                "stop_id": optional_value(stop_update, "stop_id"),
                "stop_sequence": optional_value(
                    stop_update,
                    "stop_sequence",
                ),
                "stop_schedule_relationship": stop_relationship,
                "arrival_delay_seconds": (
                    optional_value(arrival, "delay")
                    if arrival is not None
                    else None
                ),
                "arrival_timestamp": (
                    optional_timestamp(arrival, "time")
                    if arrival is not None
                    else None
                ),
                "arrival_uncertainty_seconds": (
                    optional_value(arrival, "uncertainty")
                    if arrival is not None
                    else None
                ),
                "departure_delay_seconds": (
                    optional_value(departure, "delay")
                    if departure is not None
                    else None
                ),
                "departure_timestamp": (
                    optional_timestamp(departure, "time")
                    if departure is not None
                    else None
                ),
                "departure_uncertainty_seconds": (
                    optional_value(departure, "uncertainty")
                    if departure is not None
                    else None
                ),
            }
            stop_rows.append(stop_row)

    feed_row = {
        "snapshot_id": snapshot_id,
        "attempt_number": record["attempt_number"],
        "request_started_at": parse_iso_datetime(
            record["request_started_at"]
        ),
        "feed_timestamp": (
            datetime.fromtimestamp(feed.header.timestamp, tz=UTC)
            if feed.header.HasField("timestamp")
            else None
        ),
        "gtfs_realtime_version": (
            feed.header.gtfs_realtime_version
        ),
        "entity_count": len(feed.entity),
        "trip_update_count": len(trip_rows),
        "stop_time_update_count": len(stop_rows),
        "vehicle_position_count": vehicle_position_count,
        "alert_count": alert_count,
        "deleted_entity_count": deleted_entity_count,
        "checksum_sha256": record["checksum_sha256"],
        "source_path": str(snapshot_path),
    }

    return feed_row, trip_rows, stop_rows

EXPECTED_SNAPSHOT_ROWS = 777
EXPECTED_TRIP_ROWS = 4_518_265
EXPECTED_STOP_ROWS = 94_839_920


def calculate_sha256(path: Path) -> str:
    """Calculate a file checksum without loading the full file."""
    digest = hashlib.sha256()

    with path.open("rb") as source_file:
        for chunk in iter(
            lambda: source_file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_inventory(path: Path) -> list[dict[str, Any]]:
    """Load the audited JSON Lines inventory."""
    records: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as inventory_file:
        for line_number, line in enumerate(
            inventory_file,
            start=1,
        ):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on inventory line {line_number}"
                ) from error

            records.append(record)

    return records


def parquet_dataset_row_count(
    file_paths: list[Path],
    expected_schema: pa.Schema,
) -> int:
    """Validate schemas and count rows using Parquet metadata."""
    total_rows = 0

    for file_path in file_paths:
        parquet_file = pq.ParquetFile(file_path)
        actual_schema = parquet_file.schema_arrow

        if actual_schema != expected_schema:
            raise ValueError(
                f"Unexpected schema in {file_path}"
            )

        total_rows += parquet_file.metadata.num_rows

    return total_rows


def convert_inventory(
    inventory_path: Path,
    output_root: Path,
    project_root: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    """Convert audited snapshots into three Parquet datasets."""
    if output_root.exists():
        raise FileExistsError(
            f"Output directory already exists: {output_root}"
        )

    records = load_inventory(inventory_path)

    if limit is not None:
        records = records[:limit]

    feed_writer = RotatingParquetWriter(
        output_directory=output_root / "feed_snapshots",
        schema=FEED_SCHEMA,
        maximum_rows_per_file=10_000,
    )
    trip_writer = RotatingParquetWriter(
        output_directory=output_root / "trip_updates",
        schema=TRIP_SCHEMA,
        maximum_rows_per_file=500_000,
    )
    stop_writer = RotatingParquetWriter(
        output_directory=output_root / "stop_time_updates",
        schema=STOP_SCHEMA,
        maximum_rows_per_file=2_000_000,
    )

    failed_snapshots: list[dict[str, Any]] = []

    try:
        for position, record in enumerate(records, start=1):
            snapshot_path = project_root / record["snapshot_path"]

            try:
                payload = snapshot_path.read_bytes()
                actual_checksum = hashlib.sha256(payload).hexdigest()

                if actual_checksum != record["checksum_sha256"]:
                    raise ValueError("SHA-256 checksum mismatch")

                feed_row, trip_rows, stop_rows = (
                    extract_snapshot_rows(record, payload)
                )

                feed_writer.write_table(
                    rows_to_table([feed_row], FEED_SCHEMA)
                )
                trip_writer.write_table(
                    rows_to_table(trip_rows, TRIP_SCHEMA)
                )
                stop_writer.write_table(
                    rows_to_table(stop_rows, STOP_SCHEMA)
                )
            except (OSError, ValueError) as error:
                failed_snapshots.append(
                    {
                        "attempt_number": record.get(
                            "attempt_number"
                        ),
                        "snapshot_path": str(snapshot_path),
                        "error": str(error),
                    }
                )
                raise

            if position % 25 == 0 or position == len(records):
                print(
                    f"Converted {position} of "
                    f"{len(records)} snapshots"
                )
    finally:
        feed_writer.close()
        trip_writer.close()
        stop_writer.close()

    feed_rows = parquet_dataset_row_count(
        feed_writer.file_paths,
        FEED_SCHEMA,
    )
    trip_rows = parquet_dataset_row_count(
        trip_writer.file_paths,
        TRIP_SCHEMA,
    )
    stop_rows = parquet_dataset_row_count(
        stop_writer.file_paths,
        STOP_SCHEMA,
    )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "inventory_path": str(inventory_path),
        "output_root": str(output_root),
        "snapshots_processed": len(records),
        "snapshots_failed": len(failed_snapshots),
        "feed_snapshot_rows": feed_rows,
        "trip_update_rows": trip_rows,
        "stop_time_update_rows": stop_rows,
        "feed_parquet_files": len(feed_writer.file_paths),
        "trip_parquet_files": len(trip_writer.file_paths),
        "stop_parquet_files": len(stop_writer.file_paths),
        "failures": failed_snapshots,
    }

    if limit is None:
        expected_counts = {
            "feed_snapshot_rows": EXPECTED_SNAPSHOT_ROWS,
            "trip_update_rows": EXPECTED_TRIP_ROWS,
            "stop_time_update_rows": EXPECTED_STOP_ROWS,
        }

        for field_name, expected_value in expected_counts.items():
            if summary[field_name] != expected_value:
                raise ValueError(
                    f"{field_name}: expected {expected_value:,}, "
                    f"found {summary[field_name]:,}"
                )

    summary_path = output_root / "conversion_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    return summary


def parse_arguments() -> argparse.Namespace:
    """Read command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert audited GTFS-Realtime snapshots to Parquet."
        )
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path(
            "evidence/collection/"
            "analysis_window_inventory.jsonl"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/realtime"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Convert only the first N snapshots for testing.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the command-line conversion."""
    arguments = parse_arguments()
    project_root = Path(__file__).resolve().parents[1]

    inventory_path = arguments.inventory
    if not inventory_path.is_absolute():
        inventory_path = project_root / inventory_path

    output_root = arguments.output
    if not output_root.is_absolute():
        output_root = project_root / output_root

    summary = convert_inventory(
        inventory_path=inventory_path,
        output_root=output_root,
        project_root=project_root,
        limit=arguments.limit,
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()