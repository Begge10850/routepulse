"""Safe storage helpers for RoutePulse snapshots."""

import hashlib
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

BYTES_PER_GIBIBYTE = 1024**3


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 checksum of a byte payload."""
    return hashlib.sha256(payload).hexdigest()


def available_disk_gb(path: Path) -> float:
    """Return available disk space for a path in gibibytes."""
    free_bytes = shutil.disk_usage(path).free
    return free_bytes / BYTES_PER_GIBIBYTE


def ensure_minimum_free_space(path: Path, minimum_gb: int) -> float:
    """Raise an error when available disk space is below the minimum."""
    free_gb = available_disk_gb(path)

    if free_gb < minimum_gb:
        raise OSError(
            f"Only {free_gb:.2f} GiB is available; "
            f"at least {minimum_gb} GiB is required",
        )

    return free_gb


def atomic_write_bytes(destination: Path, payload: bytes) -> None:
    """Write bytes atomically without replacing an existing snapshot."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        raise FileExistsError(f"Snapshot already exists: {destination}")

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

        raise