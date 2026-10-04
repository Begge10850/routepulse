# RoutePulse reproduction and verification commands

## Purpose and evidence boundary

This runbook preserves the terminal workflows used or supported by the actual
RoutePulse scripts. It is not presented as a byte-for-byte export of historical
terminal scrollback: commands that were never logged cannot be recovered
reliably. Instead, each command below is tied to versioned code or retained
evidence and is suitable for reproduction or verification.

Run commands from the repository root:

```bash
cd /Users/trevaogwang/Documents/mobile-projects/routepulse
```

Do not paste `.env`, Streamlit secrets, private keys or AWS credentials into
terminal transcripts, screenshots, documentation or Git.

## Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

Populate `.env` locally before collection. It is ignored by Git.

## Unit and static checks

```bash
pytest
pytest tests/unit/test_collector.py
pytest tests/unit/test_audit_collection.py
pytest tests/unit/test_profile_analysis_window.py
pytest tests/unit/test_convert_realtime_to_parquet.py
pytest tests/unit/test_upload_analysis_window.py
ruff check .
python tests/validation/validate_streamlit_app.py
python tests/validation/validate_community_cloud.py
python -m py_compile app/streamlit_app.py
```

The preserved repository state passed all 37 unit tests plus both Streamlit
validation scripts.

## Single-snapshot collection checks

Collect and validate one realtime snapshot:

```bash
python scripts/collect_once.py
```

Inspect a retained Protocol Buffer snapshot:

```bash
python scripts/inspect_snapshot.py PATH_TO_SNAPSHOT.pb
```

Compare realtime identifiers with a static GTFS ZIP archive:

```bash
python scripts/check_identifier_compatibility.py \
  PATH_TO_SNAPSHOT.pb \
  PATH_TO_STATIC_GTFS.zip
```

## Scheduled collector tests and collection

Short controlled scheduling test:

```bash
python scripts/run_collector.py \
  --max-attempts 3 \
  --interval-seconds 5
```

Run the configured collector schedule:

```bash
python scripts/run_collector.py
```

The production analysis used a five-minute interval. The collection manifest
is written under `logs/`, which is intentionally ignored because the audited
summary and selected inventory are retained under `evidence/collection/`.

On macOS, sleep/wake state can be retained for collection diagnostics with:

```bash
pmset -g log > evidence/collection_sleep_wake_log_YYYYMMDD.txt
```

## Audit and freeze the analysis window

```bash
python scripts/audit_collection.py
```

The retained result for this project is:

- 791 selected attempts;
- 777 saved snapshots;
- 10 not-modified responses;
- 4 duplicate responses;
- zero missing snapshots, sidecars or checksum mismatches;
- approximately 39.5 hours in the selected analysis window.

## Profile the audited window

```bash
python scripts/profile_analysis_window.py
```

This writes `evidence/profiling/realtime_field_profile.json`. The retained
profile covers all 777 snapshots with zero decode failures.

## Convert realtime snapshots to Parquet

Small controlled conversion test:

```bash
python scripts/convert_realtime_to_parquet.py \
  --limit 2 \
  --output /tmp/routepulse-parquet-test
```

Convert the complete audited inventory:

```bash
python scripts/convert_realtime_to_parquet.py
```

The retained conversion summary records:

- 777 feed-snapshot rows;
- 4,518,265 trip-update rows;
- 94,839,920 stop-time-update rows;
- zero failed snapshots;
- 60 Parquet files across the three datasets.

## Validate and upload the analysis window to S3

Always run the non-mutating dry run first:

```bash
python scripts/upload_analysis_window.py
```

Execute the validated upload, then rerun it to verify idempotency:

```bash
python scripts/upload_analysis_window.py --execute
python scripts/upload_analysis_window.py --execute
```

The retained upload evidence records 1,556 initially uploaded objects and zero
new uploads on the idempotency rerun. Server-side encryption and account-level
public-access blocking were verified and recorded in
`evidence/cloud/s3_upload_summary.json`.

## Snowflake SQL execution

The numbered files in `sql/` form the reproducible Snowflake sequence. Stages
All numbered stages 01–13 are retained. A complete clean-order run is not yet
possible because the recovered worksheets omit several static-reference
loading and geographic-model definitions described below. The retained order is:

```text
sql/01_setup.sql
sql/02_storage_integration.sql
sql/03_external_stage.sql
sql/04_load_raw_tables.sql
sql/05_analytics_models.sql
sql/06_gtfs_reference_tables.sql
sql/07_validate_gtfs_joins.sql
sql/08_named_station_analytics.sql
sql/09_unique_stop_events.sql
sql/10_geographic_event_enrichment.sql
sql/11_line_focus_models.sql
sql/12_dashboard_ui_models.sql
sql/13_community_cloud_access.sql
sql/14_validate_regional_filters.sql
sql/15_validate_timing_categories.sql
```

Before running stage 02, replace `<AWS_ACCOUNT_ID>` with the account that owns
the documented IAM role and configure that role's trust policy using the values
returned by `DESC INTEGRATION`. Do not commit those account-specific values.

The retained expected stage-04 reconciliation counts are 777 feed snapshots,
4,518,265 trip updates and 94,839,920 stop-time updates. Treat a mismatch as a
signal to review the selected source window and staged objects before proceeding.

Stage 05 summarizes the repeated raw feed observations. Do not interpret its
route or hourly percentages as deduplicated stop-visit rates; stage 09 later
establishes the retained one-row-per-trip/date/stop analytical grain used for
the final dashboard.

Stage 06 creates the static GTFS stops/routes schemas and validation queries,
but the recovered worksheet does not contain a `COPY INTO`, `INSERT` or other
loading command for those tables. A clean rebuild therefore requires the
original loading step to be recovered or reconstructed and verified before
running its validation queries or stage 09.

Stage 07 is a read-only validation worksheet. Its first result confirms that
the stops/routes tables contain rows; subsequent results measure identifier
match coverage and preview the readable names produced by successful joins.
The repeated stop-table checks at the end are retained from the original
worksheet for fidelity, even though they overlap earlier checks.

Stage 08 creates early named-station and service summaries directly from the
repeated raw observations. Its rates are historical baseline outputs, not the
deduplicated stop-visit rates established by stage 09.

The numbered worksheets do not yet define or load `RAW.GTFS_TRIPS`,
`RAW.GTFS_STOP_TIMES`, `ANALYTICS.GTFS_STOPS_GEOGRAPHIC` or
`ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG`, although later route-map models require
them. Recover and verify those build steps before claiming clean reproducibility.

Run their embedded validation queries and retain the output relevant to row
counts, uniqueness, reconciliation and null handling. Do not publish query
results containing credentials or private identifiers.

After the numbered analytical models exist, the retained read-only
investigations can be run separately:

```text
sql/quality/route_mode_and_static_reference_audit.sql
sql/quality/geographic_unmatched_stop_diagnostics.sql
```

The second script intentionally excludes the obsolete model-replacement
statement from the original `geographical.sql`; it queries the corrected stage
10 model without mutating it.

For an optional Snowflake-hosted Streamlit deployment, replace
`<DEPLOYER_USER>` and run:

```text
sql/setup/snowflake_streamlit_access.sql
```

This native-app role setup is separate from the public Community Cloud service
identity created by stage 13.

The original native app manifest and package metadata are archived under
`deployment/snowflake_native_snapshot/`. Read that directory's README before
reassembling the original Snowsight project layout; it is not the active
Community Cloud deployment directory.

## Public Streamlit environment

```bash
python3.12 -m venv .venv-dashboard
source .venv-dashboard/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Use this separate environment for the dashboard. The pipeline dependency
`gtfs-realtime-bindings` and Streamlit currently require incompatible major
versions of `protobuf`; keeping the runtimes separate makes both installations
deterministic.

Generate a service key pair for a new deployment:

```bash
mkdir -p .secrets
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM \
  -out .secrets/routepulse_rsa_key.p8 -nocrypt
openssl rsa -in .secrets/routepulse_rsa_key.p8 -pubout \
  -out .secrets/routepulse_rsa_key.pub
chmod 600 .secrets/routepulse_rsa_key.p8
```

Configure the ignored `.streamlit/secrets.toml` from
`.streamlit/secrets.toml.example`, then test the restricted connection:

```bash
python scripts/test_public_snowflake_connection.py
```

To test against an existing protected secrets file without copying it into the
repository, set `ROUTEPULSE_SECRETS_PATH` to that file for this command.

Run the full dashboard locally:

```bash
streamlit run app/streamlit_app.py
```

The verified connection used the dedicated service user, read-only role and
public XSMALL warehouse. Browser smoke testing covered the Network map, Data
quality and Bus Lines views.

## Git safety checks before committing

```bash
git status --short --ignored
git diff --check
git grep --cached -n -- 'BEGIN PRIVATE KEY'
```

The final command should return no staged private-key material. Review every
staged file before committing. Do not use `git add .` until ignored raw data and
secret paths have been verified.
