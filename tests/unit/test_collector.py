from pathlib import Path

import httpx
import pytest
from google.transit import gtfs_realtime_pb2

from routepulse.collector import (
    DuplicateSnapshotError,
    NotModifiedError,
    collect_once,
)
from routepulse.config import CollectorConfig
from routepulse.storage import sha256_bytes


def make_config() -> CollectorConfig:
    """Return safe configuration for collector unit tests."""
    return CollectorConfig(
        realtime_url="https://example.com/feed",
        interval_seconds=180,
        duration_hours=48,
        request_timeout_seconds=30,
        minimum_free_disk_gb=1,
        user_agent="RoutePulse-Test/0.1",
    )


def make_valid_feed() -> bytes:
    """Create a small valid GTFS-Realtime payload."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_700_000_000

    entity = feed.entity.add()
    entity.id = "entity-1"
    entity.trip_update.trip.trip_id = "trip-1"

    return feed.SerializeToString()


def test_collect_once_saves_valid_snapshot(tmp_path: Path) -> None:
    payload = make_valid_feed()

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "RoutePulse-Test/0.1"

        return httpx.Response(
            status_code=200,
            headers={
                "Content-Type": "application/protobuf",
                "ETag": '"test-etag"',
                "Last-Modified": "Fri, 25 Sep 2026 09:23:08 GMT",
            },
            content=payload,
        )

    transport = httpx.MockTransport(handle_request)

    with httpx.Client(transport=transport) as client:
        result = collect_once(
            config=make_config(),
            output_directory=tmp_path,
            client=client,
        )

    assert result.snapshot_path.exists()
    assert result.snapshot_path.read_bytes() == payload
    assert result.http_status == 200
    assert result.downloaded_bytes == len(payload)
    assert result.checksum_sha256 == sha256_bytes(payload)
    assert result.total_entities == 1
    assert result.trip_updates == 1
    assert result.vehicle_positions == 0
    assert result.alerts == 0
    assert result.etag == '"test-etag"'
    assert result.feed_timestamp is not None


def test_collect_once_rejects_wrong_content_type(tmp_path: Path) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Error page</html>",
        )

    transport = httpx.MockTransport(handle_request)

    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(ValueError, match="Unexpected Content-Type"),
    ):
        collect_once(
            config=make_config(),
            output_directory=tmp_path,
            client=client,
        )

    assert list(tmp_path.iterdir()) == []


def test_collect_once_rejects_corrupt_protobuf(tmp_path: Path) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/protobuf"},
            content=b"\xff",
        )

    transport = httpx.MockTransport(handle_request)

    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(
            ValueError,
            match="not valid Protocol Buffer data",
        ),
    ):
        collect_once(
            config=make_config(),
            output_directory=tmp_path,
            client=client,
        )

    assert list(tmp_path.iterdir()) == []

def test_collect_once_handles_not_modified_response(tmp_path: Path) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"previous-etag"'
        return httpx.Response(status_code=304)

    transport = httpx.MockTransport(handle_request)

    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(NotModifiedError, match="not modified"),
    ):
        collect_once(
            config=make_config(),
            output_directory=tmp_path,
            client=client,
            previous_etag='"previous-etag"',
        )

    assert list(tmp_path.iterdir()) == []


def test_collect_once_rejects_duplicate_checksum(tmp_path: Path) -> None:
    payload = make_valid_feed()
    checksum = sha256_bytes(payload)

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/protobuf"},
            content=payload,
        )

    transport = httpx.MockTransport(handle_request)

    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(DuplicateSnapshotError, match=checksum),
    ):
        collect_once(
            config=make_config(),
            output_directory=tmp_path,
            client=client,
            known_checksums={checksum},
        )

    assert list(tmp_path.iterdir()) == []