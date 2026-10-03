"""Test RoutePulse's restricted Streamlit-to-Snowflake connection."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from snowflake.snowpark import Session

ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = Path(
    os.environ.get(
        "ROUTEPULSE_SECRETS_PATH",
        ROOT / ".streamlit" / "secrets.toml",
    )
)


def main() -> None:
    config = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))[
        "routepulse_snowflake"
    ]
    key = serialization.load_pem_private_key(
        config["private_key"].encode("utf-8"),
        password=None,
    )
    key_der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    parameters = {
        name: config[name]
        for name in (
            "account",
            "user",
            "role",
            "warehouse",
            "database",
            "schema",
        )
    }
    parameters.update(
        {
            "authenticator": "SNOWFLAKE_JWT",
            "private_key": key_der,
            "session_parameters": {
                "QUERY_TAG": "routepulse_migration_test"
            },
        }
    )

    session = Session.builder.configs(parameters).create()
    try:
        identity = session.sql(
            "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()"
        ).collect()[0]
        model_count = session.sql(
            "SELECT COUNT(*) FROM ROUTEPULSE.ANALYTICS.KPI_SUMMARY"
        ).collect()[0][0]
        print(
            f"Connected as {identity[0]} with role {identity[1]} "
            f"on {identity[2]}."
        )
        print(
            "Read-only dashboard model test returned "
            f"{model_count:,} KPI rows."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
