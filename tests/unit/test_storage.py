from types import SimpleNamespace

import pytest

from routepulse import storage


def test_sha256_checksum_is_repeatable() -> None:
    first_checksum = storage.sha256_bytes(b"RoutePulse")
    second_checksum = storage.sha256_bytes(b"RoutePulse")

    assert first_checksum == second_checksum
    assert len(first_checksum) == 64


def test_different_payloads_have_different_checksums() -> None:
    assert storage.sha256_bytes(b"first") != storage.sha256_bytes(b"second")


def test_atomic_write_creates_complete_file(tmp_path) -> None:
    destination = tmp_path / "snapshot.pb"
    payload = b"complete snapshot"

    storage.atomic_write_bytes(destination, payload)

    assert destination.read_bytes() == payload
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_write_refuses_to_replace_existing_file(tmp_path) -> None:
    destination = tmp_path / "snapshot.pb"
    destination.write_bytes(b"original")

    with pytest.raises(FileExistsError, match="Snapshot already exists"):
        storage.atomic_write_bytes(destination, b"replacement")

    assert destination.read_bytes() == b"original"


def test_rejects_insufficient_disk_space(tmp_path, monkeypatch) -> None:
    fake_disk_usage = SimpleNamespace(free=14 * storage.BYTES_PER_GIBIBYTE)

    monkeypatch.setattr(
        storage.shutil,
        "disk_usage",
        lambda path: fake_disk_usage,
    )

    with pytest.raises(OSError, match="at least 15 GiB is required"):
        storage.ensure_minimum_free_space(tmp_path, minimum_gb=15)