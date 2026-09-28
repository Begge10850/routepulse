# RoutePulse warehouse model

## Purpose

Convert the audited GTFS-Realtime analysis window into typed analytical
tables that can be loaded into Snowflake and modelled with SQL and dbt.
This is an initial candidate model based on the GTFS-Realtime specification
and an inspected VBB snapshot. Field availability and table grains must be
validated across all 777 audited snapshots before the model is finalized.

## Raw source

- S3 bucket: `routepulse-raw-eu-central-1-9b355f4a`
- Region: `eu-central-1`
- Audited snapshots: 777
- Analysis duration: approximately 39.5 hours

The raw Protocol Buffer files remain immutable. Structured datasets are
derived from them and can be rebuilt.

## Table grains

### feed_snapshots

One row represents one audited GTFS-Realtime snapshot.

Important fields:

- snapshot_id
- attempt_number
- request_started_at
- feed_timestamp
- gtfs_realtime_version
- entity_count
- trip_update_count
- vehicle_position_count
- alert_count
- checksum_sha256
- source_path

### trip_updates

One row represents one TripUpdate entity observed in one snapshot.

Important fields:

- snapshot_id
- entity_id
- trip_id
- route_id
- direction_id
- start_date
- start_time
- trip_schedule_relationship
- vehicle_id
- trip_update_timestamp
- trip_delay

### stop_time_updates

One row represents one StopTimeUpdate belonging to one trip update in one
snapshot.

Important fields:

- snapshot_id
- entity_id
- trip_id
- route_id
- stop_id
- stop_sequence
- arrival_delay
- arrival_timestamp
- arrival_uncertainty
- departure_delay
- departure_timestamp
- departure_uncertainty
- stop_schedule_relationship

## Interpretation rules

- Missing optional values remain null; they are not converted to zero.
- A cancellation is counted only when explicitly reported.
- A skipped stop is counted only when explicitly reported.
- Missing realtime data is not proof that a scheduled service did not run.
- Feed-health metrics and transport-performance metrics remain separate.

## Storage format

The structured datasets will be written as Apache Parquet.

Parquet is a typed, compressed, column-oriented format. Snowflake can read
only the columns needed by a query, which is generally more efficient than
loading large CSV files.

## Observed realtime profile

The candidate model was evaluated across all 777 audited snapshots.

Observed row counts:

- Feed snapshots: 777
- Trip-update observations: 4,518,265
- Stop-time-update observations: 94,839,920
- Vehicle-position observations: 0
- Alert observations: 0
- Decode failures: 0

All feed entities in this analysis window were TripUpdate entities. This
finding applies only to the audited analysis window and does not imply that
the VBB endpoint can never publish VehiclePosition or Alert entities.

Trip ID, route ID, direction ID, start date, trip schedule relationship,
and trip-update timestamp were present in 100% of trip-update observations.

Stop ID was present in 100% of stop-time-update observations. Arrival and
departure timestamps were present in more than 99.8% of stop-time-update
observations.

Trip start time, trip-level delay, vehicle descriptor, vehicle ID, arrival
uncertainty, and departure uncertainty were absent from every applicable
record. These fields may remain nullable for schema stability, but analysis
must not depend on them.

The same transit trip may occur in multiple snapshots. Therefore, the
observed TripUpdate count is not a count of unique physical trips; it is a
count of trip observations over time.

The machine-readable profiling evidence is stored at
`evidence/profiling/realtime_field_profile.json`.