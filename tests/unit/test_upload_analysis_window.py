import json
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

import scripts.upload_analysis_window as uploader


def prepare_audited_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Create one temporary audited snapshot and its evidence files."""

    monkeypatch.chdir(tmp_path)

    snapshot_path = Path("data/raw/gtfs_realtime/example.pb")
    sidecar_path = snapshot_path.with_suffix(".json")
    inventory_path = Path("evidence/collection/inventory.jsonl")
    summary_path = Path("evidence/collection/summary.json")

    snapshot_path.parent.mkdir(parents=True)
    inventory_path.parent.mkdir(parents=True)

    snapshot_path.write_bytes(b"protobuf contents")
    sidecar_path.write_text('{"status": "saved"}\n', encoding="utf-8")
    inventory_path.write_text("{}\n", encoding="utf-8")
    summary_path.write_text('{"saved": 1}\n', encoding="utf-8")

    monkeypatch.setattr(uploader, "INVENTORY_PATH", inventory_path)
    monkeypatch.setattr(uploader, "SUMMARY_PATH", summary_path)

    return {
        "snapshot_path": str(snapshot_path),
        "sidecar_path": str(sidecar_path),
        "checksum_sha256": uploader.calculate_file_sha256(snapshot_path),
    }


def test_load_inventory_reads_json_lines(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.jsonl"
    records = [
        {"attempt_number": 1},
        {"attempt_number": 2},
    ]
    inventory_path.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )

    assert uploader.load_inventory(inventory_path) == records


def test_load_inventory_rejects_invalid_json(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.jsonl"
    inventory_path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inventory line 1"):
        uploader.load_inventory(inventory_path)


def test_build_upload_plan_includes_data_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = prepare_audited_record(tmp_path, monkeypatch)

    items = uploader.build_upload_plan([record])

    assert len(items) == 4
    assert items[0].object_key == "raw/gtfs_realtime/example.pb"
    assert items[1].object_key == "raw/gtfs_realtime/example.json"
    assert items[2].object_key == "evidence/collection/inventory.jsonl"
    assert items[3].object_key == "evidence/collection/summary.json"


def test_build_upload_plan_rejects_checksum_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = prepare_audited_record(tmp_path, monkeypatch)
    record["checksum_sha256"] = "incorrect"

    with pytest.raises(ValueError, match="Checksum mismatch"):
        uploader.build_upload_plan([record])


class ExistingObjectClient:
    """Return metadata for an object that already exists."""

    def __init__(self, checksum: str) -> None:
        self.checksum = checksum

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "Metadata": {
                "sha256": self.checksum,
            }
        }


class MissingObjectClient:
    """Pretend that objects are absent and record uploads."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str, dict[str, Any]]] = []

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        raise ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, Any],
    ) -> None:
        self.uploads.append((filename, bucket, key, ExtraArgs))


def test_remote_object_matches_equal_checksum(tmp_path: Path) -> None:
    local_path = tmp_path / "example.pb"
    local_path.write_bytes(b"contents")
    checksum = uploader.calculate_file_sha256(local_path)
    item = uploader.UploadItem(
        local_path=local_path,
        object_key="raw/example.pb",
        checksum_sha256=checksum,
        content_type="application/x-protobuf",
    )
    client = ExistingObjectClient(checksum)

    assert uploader.remote_object_matches(client, item) is True


def test_remote_object_rejects_different_checksum(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "example.pb"
    local_path.write_bytes(b"contents")
    item = uploader.UploadItem(
        local_path=local_path,
        object_key="raw/example.pb",
        checksum_sha256="local-checksum",
        content_type="application/x-protobuf",
    )
    client = ExistingObjectClient("different-checksum")

    with pytest.raises(RuntimeError, match="different checksum"):
        uploader.remote_object_matches(client, item)


def test_upload_plan_uploads_missing_object(tmp_path: Path) -> None:
    local_path = tmp_path / "example.pb"
    local_path.write_bytes(b"contents")
    checksum = uploader.calculate_file_sha256(local_path)
    item = uploader.UploadItem(
        local_path=local_path,
        object_key="raw/example.pb",
        checksum_sha256=checksum,
        content_type="application/x-protobuf",
    )
    client = MissingObjectClient()

    uploader.upload_plan(client, [item])

    assert len(client.uploads) == 1
    _, bucket, key, extra_args = client.uploads[0]
    assert bucket == uploader.BUCKET_NAME
    assert key == "raw/example.pb"
    assert extra_args["Metadata"]["sha256"] == checksum