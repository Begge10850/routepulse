# Snowflake SQL pipeline

This directory contains the reproducible Snowflake portion of RoutePulse. Run
the numbered scripts in order unless a script explicitly says otherwise.

## Current stages

| Stage | Purpose | Importance |
|---|---|---|
| 01 | Create the warehouse, database, RAW and ANALYTICS schemas, and Parquet file format | Critical foundation; every later stage depends on these objects |
| 02 | Create the read-only Snowflake storage integration for the processed S3 prefix | Critical security boundary between Snowflake and S3; requires the matching AWS IAM trust configuration |
| 03 | Bind the S3 location, storage integration and Parquet format in an external stage, then list visible files | Critical access bridge; the `LIST` result verifies that Snowflake can see the source Parquet objects |
| 04 | Create typed transient raw tables, load the three realtime datasets and reconcile their row counts | Critical ingestion layer; `ABORT_STATEMENT` makes a malformed load fail rather than silently continue |
| 05 | Build route, hourly and collection-level baseline metrics directly from repeated raw feed observations | Important early analytical baseline and source of raw collection KPIs; its rates are snapshot-observation rates, not the deduplicated stop-visit rates introduced in stage 09 |
| 06 | Define the static GTFS CSV format and the stops/routes reference-table schemas, then profile their contents | Critical reference-data foundation for stage 09; the exported worksheet does not include the commands that populate these two tables, so that loading step remains to be recovered |
| 07 | Validate GTFS table population, quantify exact stop/normalized route ID matches, and preview stakeholder-readable names | Important data-integration evidence; validation only, with no object creation or data loading |
| 08 | Build named station, named route and aggregated service summaries from the raw repeated observations | Important historical analytical layer; superseded for final dashboard rates by the deduplicated event grain introduced in stage 09 |
| 09 | Deduplicate repeated realtime observations into one retained stop visit and enrich it with static GTFS fields | Critical analytical grain |
| 10 | Assign stop regions and construct geographic route/map references | Critical for regional analysis and maps |
| 11 | Build passenger-facing line definitions, representative directions and line-focus events | Critical for line rankings and route highlighting |
| 12 | Materialize additive dashboard aggregates by scope, line, hour, station, region and category | Critical presentation layer |
| 13 | Create the restricted service identity and warehouse used by public Streamlit | Deployment-only; not part of metric calculation |

## Known clean-rebuild gaps

All numbered worksheets are retained, but the recovered sequence does not yet
contain every prerequisite needed to rebuild the current dashboard from an
empty Snowflake database:

- stage 06 defines `RAW.GTFS_STOPS` and `RAW.GTFS_ROUTES` but does not load
  their CSV rows;
- later map models reference `RAW.GTFS_TRIPS`, `RAW.GTFS_STOP_TIMES`,
  `ANALYTICS.GTFS_STOPS_GEOGRAPHIC` and
  `ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG`, whose definitions/loading steps are
  not present in the recovered numbered worksheets.

These are documented recovery tasks, not evidence that the deployed objects
are absent from the existing Snowflake account.

## Retained investigation worksheets

Read-only exploratory and diagnostic SQL is kept separately under
`sql/quality/` so it cannot be mistaken for a numbered build stage:

- `route_mode_and_static_reference_audit.sql` investigates route-type
  classifications, expected Potsdam tram observations, available static GTFS
  tables and the configured raw-stage inventory;
- `geographic_unmatched_stop_diagnostics.sql` traces unmatched realtime stop
  IDs through static stops, trips and stop times and measures whether a region
  can be recovered deterministically.

The original `geographical.sql` also contained an earlier model definition
that treated missing stop matches as outside Berlin-Brandenburg. That obsolete
write statement is not retained as executable SQL because stage 10 contains
the corrected `Unmatched/unknown` and normalized-region recovery behaviour.

## Deployment-specific setup

`sql/setup/snowflake_streamlit_access.sql` preserves the role and privilege
setup used for the original Snowflake-hosted Streamlit application. It creates
separate app-owner and viewer roles and must be run only after replacing the
`<DEPLOYER_USER>` placeholder. It is intentionally separate from stage 13,
which creates the restricted service identity used by public Streamlit
Community Cloud.

## What belongs in Git

Include SQL that:

- creates schemas, stages, file formats, tables or views;
- loads the audited realtime Parquet files or static GTFS reference data;
- transforms raw data into documented analytical grains;
- validates row counts, uniqueness, null handling or reconciliation;
- grants the minimum privileges required to run the application.

Do not commit passwords, private keys, tokens, storage credentials, presigned
URLs or temporary scratch queries. Replace account-specific values with clear
placeholders where possible.
