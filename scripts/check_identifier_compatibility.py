"""Check whether realtime identifiers exist in a static GTFS archive."""

import argparse
import csv
from collections.abc import Iterable
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

from google.transit import gtfs_realtime_pb2


def load_static_ids(
    archive_path: Path,
    filename: str,
    column_name: str,
) -> set[str]:
    """Load one identifier column from a CSV file inside a GTFS ZIP archive."""
    identifiers: set[str] = set()

    with (
        ZipFile(archive_path) as archive,
        archive.open(filename) as binary_file,
        TextIOWrapper(
            binary_file,
            encoding="utf-8-sig",
            newline="",
        ) as text_file,
    ):
        reader = csv.DictReader(text_file)

        if column_name not in (reader.fieldnames or []):
            raise ValueError(
                f"{column_name!r} was not found in {filename!r}",
            )

        for row in reader:
            identifier = row[column_name].strip()

            if identifier:
                identifiers.add(identifier)

    return identifiers


def load_realtime_ids(
    snapshot_path: Path,
) -> tuple[set[str], set[str], set[str]]:
    """Load trip, route, and stop identifiers from one realtime snapshot."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(snapshot_path.read_bytes())

    trip_ids: set[str] = set()
    route_ids: set[str] = set()
    stop_ids: set[str] = set()

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        trip_update = entity.trip_update
        trip = trip_update.trip

        if trip.trip_id:
            trip_ids.add(trip.trip_id)

        if trip.route_id:
            route_ids.add(trip.route_id)

        for stop_time_update in trip_update.stop_time_update:
            if stop_time_update.stop_id:
                stop_ids.add(stop_time_update.stop_id)

    return trip_ids, route_ids, stop_ids


def report_matches(
    label: str,
    realtime_ids: set[str],
    static_ids: set[str],
) -> None:
    """Print match statistics for one identifier type."""
    matched_ids = realtime_ids & static_ids
    unmatched_ids = realtime_ids - static_ids

    print(f"{label} realtime unique IDs: {len(realtime_ids):,}")
    print(f"{label} matched unique IDs: {len(matched_ids):,}")
    print(f"{label} unmatched unique IDs: {len(unmatched_ids):,}")

    if realtime_ids:
        match_rate = len(matched_ids) / len(realtime_ids)
        print(f"{label} unique-ID match rate: {match_rate:.2%}")
    else:
        print(f"{label} unique-ID match rate: not applicable")

    print(f"{label} unmatched examples: {sorted(unmatched_ids)[:5]}")
    print()


def describe_counts(values: Iterable[str], label: str) -> None:
    """Print the number of unique identifiers loaded from a static table."""
    print(f"Static {label} IDs: {len(set(values)):,}")


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare realtime IDs with a static GTFS ZIP archive.",
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Path to a GTFS-Realtime .pb snapshot.",
    )
    parser.add_argument(
        "static_archive",
        type=Path,
        help="Path to a static GTFS ZIP archive.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the identifier compatibility check."""
    arguments = parse_arguments()

    static_trip_ids = load_static_ids(
        arguments.static_archive,
        "trips.txt",
        "trip_id",
    )
    static_route_ids = load_static_ids(
        arguments.static_archive,
        "routes.txt",
        "route_id",
    )
    static_stop_ids = load_static_ids(
        arguments.static_archive,
        "stops.txt",
        "stop_id",
    )

    realtime_trip_ids, realtime_route_ids, realtime_stop_ids = load_realtime_ids(
        arguments.snapshot,
    )

    describe_counts(static_trip_ids, "trip")
    describe_counts(static_route_ids, "route")
    describe_counts(static_stop_ids, "stop")
    print()

    report_matches("Trip", realtime_trip_ids, static_trip_ids)
    report_matches("Route", realtime_route_ids, static_route_ids)
    report_matches("Stop", realtime_stop_ids, static_stop_ids)


if __name__ == "__main__":
    main()