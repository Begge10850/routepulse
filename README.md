# RoutePulse

RoutePulse is an evaluated mobility-data pipeline for monitoring the
availability, freshness, and quality of public transport information.

The project will collect official VBB GTFS and GTFS-Realtime data, preserve
raw snapshots, structure selected records, load validated datasets into
Snowflake, and calculate documented data-quality and operational metrics.

## Current status

Phase 1: repository and Python environment setup.

The data collector has not been implemented or started yet.

## Planned pipeline

1. Collect official VBB static and realtime transport data.
2. Preserve immutable raw snapshots and collection metadata.
3. Decode selected GTFS-Realtime records.
4. Store structured records in compressed Parquet files.
5. Load and model the data in Snowflake.
6. Validate data quality and SQL metric correctness.
7. Present defensible findings and documented limitations.

## Important limitation

Realtime-feed availability does not automatically represent transport
operations. Missing realtime records must not be interpreted as proof that a
scheduled journey was cancelled or did not operate.

## Development setup

RoutePulse currently targets Python 3.12.

Detailed installation and reproduction instructions will be added as the
project develops.

# RoutePulse

RoutePulse is an evaluated mobility-data pipeline for monitoring the
availability, freshness, and quality of public transport information.

The project will collect official VBB GTFS and GTFS-Realtime data, preserve
raw snapshots, structure selected records, load validated datasets into
Snowflake, and calculate documented data-quality and operational metrics.

## Current status

Phase 1: repository and Python environment setup.

The data collector has not been implemented or started yet.

## Planned pipeline

1. Collect official VBB static and realtime transport data.
2. Preserve immutable raw snapshots and collection metadata.
3. Decode selected GTFS-Realtime records.
4. Store structured records in compressed Parquet files.
5. Load and model the data in Snowflake.
6. Validate data quality and SQL metric correctness.
7. Present defensible findings and documented limitations.

## Important limitation

Realtime-feed availability does not automatically represent transport
operations. Missing realtime records must not be interpreted as proof that a
scheduled journey was cancelled or did not operate.

## Development setup

RoutePulse currently targets Python 3.12.

Detailed installation and reproduction instructions will be added as the
project develops.

