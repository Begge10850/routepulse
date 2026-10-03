"""Static safety and packaging checks for the public RoutePulse deployment."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app" / "streamlit_app.py"
REQUIREMENTS = ROOT / "requirements.txt"
GITIGNORE = ROOT / ".gitignore"
SECRETS_EXAMPLE = ROOT / ".streamlit" / "secrets.toml.example"
ACCESS_SQL = ROOT / "sql" / "13_community_cloud_access.sql"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    app_text = APP.read_text(encoding="utf-8")
    requirements = REQUIREMENTS.read_text(encoding="utf-8").lower()
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    secrets_example = SECRETS_EXAMPLE.read_text(encoding="utf-8")
    access_sql = ACCESS_SQL.read_text(encoding="utf-8").upper()

    ast.parse(app_text, filename=str(APP))
    require("routepulse_snowflake" in app_text, "Community secret block missing")
    require("SNOWFLAKE_JWT" in app_text, "Key-pair authentication missing")
    require("load_pem_private_key" in app_text, "PEM key conversion missing")
    require('st.connection("snowflake")' in app_text, "Native fallback missing")

    for dependency in (
        "streamlit",
        "snowflake-snowpark-python",
        "pandas",
        "altair",
        "pydeck",
        "cryptography",
    ):
        require(dependency in requirements, f"Missing dependency: {dependency}")

    for ignored in (".streamlit/secrets.toml", ".secrets/", "*.p8", "*.pem"):
        require(ignored in gitignore, f"Sensitive path is not ignored: {ignored}")

    require(
        "PASTE_THE_UNENCRYPTED_PKCS8_PRIVATE_KEY_HERE" in secrets_example,
        "Secrets example should contain a placeholder, not a real key",
    )
    require(
        "ROUTEPULSE_PUBLIC_READER" in access_sql
        and "ROUTEPULSE_PUBLIC_SERVICE" in access_sql,
        "Dedicated public identity is missing",
    )
    require("TYPE = SERVICE" in access_sql, "Service user type is missing")
    require("GRANT SELECT" in access_sql, "Read grants are missing")
    for forbidden in ("GRANT INSERT", "GRANT UPDATE", "GRANT DELETE", "GRANT OWNERSHIP"):
        require(forbidden not in access_sql, f"Unsafe public grant found: {forbidden}")

    scan_suffixes = {".py", ".toml", ".md", ".sql", ".yml", ".yaml", ".txt"}
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    for path in ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() in scan_suffixes
            and ".venv" not in path.parts
            and ".secrets" not in path.parts
            and path != ROOT / ".streamlit" / "secrets.toml"
        ):
            text = path.read_text(encoding="utf-8", errors="ignore")
            require(
                private_key_marker not in text
                or path == SECRETS_EXAMPLE,
                f"Possible committed private key in {path.relative_to(ROOT)}",
            )

    print("RoutePulse Community Cloud packaging checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
