# RoutePulse artifact inventory

This inventory records what has been preserved in the Git repository, what is
retained only on the development machine and what is deliberately excluded.
It prevents “saved” from being confused with a literal recording of every
editor action or terminal command.

## Versioned project artifacts

The original repository contains or is being prepared to contain:

- Python collection, auditing, profiling, conversion and S3 upload code;
- unit tests for the Python pipeline;
- machine-readable collection, profiling, conversion and cloud evidence;
- source-data and warehouse-model documentation;
- the validated Streamlit dashboard at `app/streamlit_app.py`;
- ordered Snowflake SQL stages under `sql/`;
- retained read-only Snowflake investigation worksheets under `sql/quality/`;
- the Snowflake-native Streamlit owner/viewer role setup under `sql/setup/`;
- the original Snowflake-native app manifest and dependency metadata under
  `deployment/snowflake_native_snapshot/`;
- Streamlit dependencies and non-secret configuration;
- dashboard and Community Cloud deployment documentation;
- static application and deployment-safety validators under
  `tests/validation/`;
- the project journey, decision record, limitations and remaining work.
- the reproducible terminal workflow in `docs/reproduction_commands.md`.

## Pending versioned artifacts

- the static GTFS loading command or worksheet that originally populated the
  stops and routes tables created by stage 06;
- the definitions/loading steps for static trips and stop times plus the
  geographic stops and route-catalogue objects required by later map models;
- exact stage descriptions and dependency notes for those worksheets;
- final public deployment evidence and public URL verification results.

## Retained locally but intentionally excluded from Git

- `.env` values;
- `.streamlit/secrets.toml`;
- the Snowflake service private key and local `.secrets/` directory;
- Python virtual environments, caches, logs and build artifacts;
- downloaded static GTFS files and boundary data under `data/gtfs/`;
- earlier Streamlit prototypes and development-only working copies in
  `/Users/trevaogwang/Documents/Codex/2026-09-25/we`.

The final v4 behaviour is preserved in `app/streamlit_app.py`; the earlier app
files remain local for historical reference but are not intended for the public
repository because publishing multiple obsolete entrypoints would make the
deployment and code review ambiguous.

## Not preserved verbatim

- every VS Code keystroke;
- complete terminal scrollback;
- transient UI state;
- every intermediate query result;
- the full chat transcript.

The substantive reasoning and changes from those sessions are preserved in
`docs/project_journey.md`, while reproducible code, tests and evidence are kept
in their appropriate project directories.
