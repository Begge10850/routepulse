import pytest

from routepulse.config import CollectorConfig

VALID_VALUES = {
    "VBB_REALTIME_URL": "https://production.gtfsrt.vbb.de/data",
    "COLLECTION_INTERVAL_SECONDS": "180",
    "COLLECTION_DURATION_HOURS": "48",
    "REQUEST_TIMEOUT_SECONDS": "30",
    "MINIMUM_FREE_DISK_GB": "15",
    "USER_AGENT": "RoutePulse/0.1 (+https://github.com/example/routepulse)",
}


def test_builds_valid_configuration() -> None:
    config = CollectorConfig.from_mapping(VALID_VALUES)

    assert config.realtime_url == "https://production.gtfsrt.vbb.de/data"
    assert config.interval_seconds == 180
    assert config.expected_attempts == 960


def test_rejects_zero_collection_interval() -> None:
    values = {
        **VALID_VALUES,
        "COLLECTION_INTERVAL_SECONDS": "0",
    }

    with pytest.raises(
        ValueError,
        match="COLLECTION_INTERVAL_SECONDS must be greater than zero",
    ):
        CollectorConfig.from_mapping(values)


def test_rejects_non_integer_timeout() -> None:
    values = {
        **VALID_VALUES,
        "REQUEST_TIMEOUT_SECONDS": "thirty",
    }

    with pytest.raises(
        ValueError,
        match="REQUEST_TIMEOUT_SECONDS must be an integer",
    ):
        CollectorConfig.from_mapping(values)


def test_rejects_non_https_feed_url() -> None:
    values = {
        **VALID_VALUES,
        "VBB_REALTIME_URL": "http://example.com/feed",
    }

    with pytest.raises(
        ValueError,
        match="VBB_REALTIME_URL must use HTTPS",
    ):
        CollectorConfig.from_mapping(values)