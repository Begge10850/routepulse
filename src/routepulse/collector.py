"""Collect and validate one VBB GTFS-Realtime snapshot."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from routepulse.config import CollectorConfig
from routepulse.storage import (
    atomic_write_bytes,
    ensure_minimum_free_space,
    sha256_bytes,
)


class NotModifiedError(Exception):
    """Indicate that the server returned HTTP 304 Not Modified."""


class DuplicateSnapshotError(Exception):
    """Indicate that the downloaded payload was already collected."""


@dataclass(frozen=True)
class CollectionResult:
    """Metadata produced by one successful collection attempt."""

    request_started_at: datetime
    request_finished_at: datetime
    duration_ms: float
    http_status: int
    content_type: str
    etag: str | None
    last_modified: str | None
    downloaded_bytes: int
    checksum_sha256: str
    snapshot_path: Path
    feed_timestamp: datetime | None
    gtfs_realtime_version: str
    total_entities: int
    trip_updates: int
    vehicle_positions: int
    alerts: int
    deleted_entities: int
    free_disk_gb: float


def collect_once(
    config: CollectorConfig,
    output_directory: Path,
    client: httpx.Client,
    previous_etag: str | None = None,
    known_checksums: set[str] | None = None,
) -> CollectionResult:
    """Download, validate, and save one unique realtime snapshot."""
    output_directory.mkdir(parents=True, exist_ok=True)
    free_disk_gb = ensure_minimum_free_space(
        output_directory,
        config.minimum_free_disk_gb,
    )

    headers = {"User-Agent": config.user_agent}

    if previous_etag is not None:
        headers["If-None-Match"] = previous_etag

    request_started_at = datetime.now(UTC)
    timer_started = perf_counter()

    response = client.get(
        config.realtime_url,
        headers=headers,
    )

    if response.status_code == 304:
        raise NotModifiedError("Realtime feed was not modified")

    response.raise_for_status()

    request_finished_at = datetime.now(UTC)
    duration_ms = (perf_counter() - timer_started) * 1000

    content_type = response.headers.get("content-type", "")

    if not content_type.lower().startswith("application/protobuf"):
        raise ValueError(
            f"Unexpected Content-Type: {content_type or 'missing'}",
        )

    payload = response.content

    if not payload:
        raise ValueError("Realtime response was empty")

    feed = gtfs_realtime_pb2.FeedMessage()

    try:
        feed.ParseFromString(payload)
    except DecodeError as error:
        raise ValueError(
            "Realtime response was not valid Protocol Buffer data",
        ) from error

    checksum = sha256_bytes(payload)

    if known_checksums is not None and checksum in known_checksums:
        raise DuplicateSnapshotError(
            f"Snapshot checksum was already collected: {checksum}",
        )

    timestamp_text = request_started_at.strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"{timestamp_text}_{checksum[:12]}.pb"
    snapshot_path = output_directory / filename

    atomic_write_bytes(snapshot_path, payload)

    trip_updates = 0
    vehicle_positions = 0
    alerts = 0
    deleted_entities = 0

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            trip_updates += 1

        if entity.HasField("vehicle"):
            vehicle_positions += 1

        if entity.HasField("alert"):
            alerts += 1

        if entity.is_deleted:
            deleted_entities += 1

    feed_timestamp: datetime | None = None

    if feed.header.HasField("timestamp"):
        feed_timestamp = datetime.fromtimestamp(
            feed.header.timestamp,
            tz=UTC,
        )

    return CollectionResult(
        request_started_at=request_started_at,
        request_finished_at=request_finished_at,
        duration_ms=duration_ms,
        http_status=response.status_code,
        content_type=content_type,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        downloaded_bytes=len(payload),
        checksum_sha256=checksum,
        snapshot_path=snapshot_path,
        feed_timestamp=feed_timestamp,
        gtfs_realtime_version=feed.header.gtfs_realtime_version,
        total_entities=len(feed.entity),
        trip_updates=trip_updates,
        vehicle_positions=vehicle_positions,
        alerts=alerts,
        deleted_entities=deleted_entities,
        free_disk_gb=free_disk_gb,
    )