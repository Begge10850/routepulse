"""Load and validate RoutePulse configuration."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from dotenv import load_dotenv


@dataclass(frozen=True)
class CollectorConfig:
    """Validated settings used by the realtime collector."""

    realtime_url: str
    interval_seconds: int
    duration_hours: int
    request_timeout_seconds: int
    minimum_free_disk_gb: int
    user_agent: str

    @property
    def expected_attempts(self) -> int:
        """Calculate the number of scheduled attempts for the full run."""
        duration_seconds = self.duration_hours * 60 * 60
        return duration_seconds // self.interval_seconds

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Self:
        """Create validated configuration from named text values."""
        realtime_url = _required_text(values, "VBB_REALTIME_URL")
        user_agent = _required_text(values, "USER_AGENT")

        if not realtime_url.startswith("https://"):
            raise ValueError("VBB_REALTIME_URL must use HTTPS")

        return cls(
            realtime_url=realtime_url,
            interval_seconds=_positive_integer(
                values,
                "COLLECTION_INTERVAL_SECONDS",
            ),
            duration_hours=_positive_integer(
                values,
                "COLLECTION_DURATION_HOURS",
            ),
            request_timeout_seconds=_positive_integer(
                values,
                "REQUEST_TIMEOUT_SECONDS",
            ),
            minimum_free_disk_gb=_positive_integer(
                values,
                "MINIMUM_FREE_DISK_GB",
            ),
            user_agent=user_agent,
        )


def _required_text(values: Mapping[str, str], name: str) -> str:
    """Read a required non-empty text setting."""
    value = values.get(name, "").strip()

    if not value:
        raise ValueError(f"{name} is required")

    return value


def _positive_integer(values: Mapping[str, str], name: str) -> int:
    """Read a required integer greater than zero."""
    raw_value = _required_text(values, name)

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")

    return value


def load_config(env_path: Path | None = None) -> CollectorConfig:
    """Load a dotenv file and return validated collector configuration."""
    load_dotenv(dotenv_path=env_path, override=False)
    return CollectorConfig.from_mapping(os.environ)