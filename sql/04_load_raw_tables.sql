USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA RAW;

CREATE OR REPLACE TRANSIENT TABLE FEED_SNAPSHOTS (
    snapshot_id VARCHAR,
    attempt_number INTEGER,
    request_started_at TIMESTAMP_TZ,
    feed_timestamp TIMESTAMP_TZ,
    gtfs_realtime_version VARCHAR,
    entity_count INTEGER,
    trip_update_count INTEGER,
    stop_time_update_count INTEGER,
    vehicle_position_count INTEGER,
    alert_count INTEGER,
    deleted_entity_count INTEGER,
    checksum_sha256 VARCHAR,
    source_path VARCHAR
);

CREATE OR REPLACE TRANSIENT TABLE TRIP_UPDATES (
    snapshot_id VARCHAR,
    attempt_number INTEGER,
    entity_id VARCHAR,
    trip_id VARCHAR,
    route_id VARCHAR,
    direction_id INTEGER,
    start_date VARCHAR,
    start_time VARCHAR,
    trip_schedule_relationship VARCHAR,
    vehicle_id VARCHAR,
    trip_update_timestamp TIMESTAMP_TZ,
    trip_delay_seconds INTEGER,
    stop_time_update_count INTEGER
);

CREATE OR REPLACE TRANSIENT TABLE STOP_TIME_UPDATES (
    snapshot_id VARCHAR,
    attempt_number INTEGER,
    entity_id VARCHAR,
    trip_id VARCHAR,
    route_id VARCHAR,
    direction_id INTEGER,
    start_date VARCHAR,
    stop_id VARCHAR,
    stop_sequence INTEGER,
    stop_schedule_relationship VARCHAR,
    arrival_delay_seconds INTEGER,
    arrival_timestamp TIMESTAMP_TZ,
    arrival_uncertainty_seconds INTEGER,
    departure_delay_seconds INTEGER,
    departure_timestamp TIMESTAMP_TZ,
    departure_uncertainty_seconds INTEGER
);

COPY INTO FEED_SNAPSHOTS
FROM @ROUTEPULSE_S3_STAGE/feed_snapshots/
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = ABORT_STATEMENT;

COPY INTO TRIP_UPDATES
FROM @ROUTEPULSE_S3_STAGE/trip_updates/
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = ABORT_STATEMENT;

COPY INTO STOP_TIME_UPDATES
FROM @ROUTEPULSE_S3_STAGE/stop_time_updates/
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = ABORT_STATEMENT;

SELECT
    'FEED_SNAPSHOTS' AS table_name,
    COUNT(*) AS row_count
FROM FEED_SNAPSHOTS

UNION ALL

SELECT
    'TRIP_UPDATES',
    COUNT(*)
FROM TRIP_UPDATES

UNION ALL

SELECT
    'STOP_TIME_UPDATES',
    COUNT(*)
FROM STOP_TIME_UPDATES
ORDER BY table_name;
