USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;

CREATE OR REPLACE TABLE ANALYTICS.ROUTE_PERFORMANCE AS
WITH STOP_OBSERVATIONS AS (
    SELECT
        route_id,
        snapshot_id,
        trip_id,
        stop_id,
        stop_schedule_relationship,
        COALESCE(
            arrival_delay_seconds,
            departure_delay_seconds
        ) AS reported_delay_seconds
    FROM RAW.STOP_TIME_UPDATES
    WHERE route_id IS NOT NULL
)
SELECT
    route_id,
    COUNT(*) AS stop_observations,
    COUNT(DISTINCT snapshot_id) AS snapshots_observed,
    COUNT(DISTINCT trip_id) AS distinct_trip_ids,
    COUNT(DISTINCT stop_id) AS distinct_stop_ids,
    COUNT_IF(
        stop_schedule_relationship = 'SKIPPED'
    ) AS skipped_stop_observations,
    ROUND(
        100.0 * COUNT_IF(
            stop_schedule_relationship = 'SKIPPED'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS skipped_stop_percentage,
    COUNT(reported_delay_seconds) AS delay_observations,
    ROUND(
        100.0 * COUNT(reported_delay_seconds)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    ROUND(AVG(reported_delay_seconds), 2)
        AS average_reported_delay_seconds,
    ROUND(
        APPROX_PERCENTILE(reported_delay_seconds, 0.90),
        2
    ) AS p90_reported_delay_seconds,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds > 300)
        / NULLIF(COUNT(reported_delay_seconds), 0),
        2
    ) AS delayed_over_five_minutes_percentage
FROM STOP_OBSERVATIONS
GROUP BY route_id;

CREATE OR REPLACE TABLE ANALYTICS.HOURLY_OPERATIONS AS
WITH TIMED_OBSERVATIONS AS (
    SELECT
        DATE_TRUNC(
            'HOUR',
            COALESCE(arrival_timestamp, departure_timestamp)
        ) AS observation_hour,
        COALESCE(
            arrival_delay_seconds,
            departure_delay_seconds
        ) AS reported_delay_seconds,
        stop_schedule_relationship
    FROM RAW.STOP_TIME_UPDATES
)
SELECT
    observation_hour,
    COUNT(*) AS stop_observations,
    COUNT_IF(
        stop_schedule_relationship = 'SKIPPED'
    ) AS skipped_stop_observations,
    COUNT(reported_delay_seconds) AS delay_observations,
    ROUND(
        AVG(reported_delay_seconds),
        2
    ) AS average_reported_delay_seconds,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds > 300)
        / NULLIF(COUNT(reported_delay_seconds), 0),
        2
    ) AS delayed_over_five_minutes_percentage
FROM TIMED_OBSERVATIONS
WHERE observation_hour IS NOT NULL
GROUP BY observation_hour;

CREATE OR REPLACE TABLE ANALYTICS.KPI_SUMMARY AS
SELECT
    (SELECT COUNT(*) FROM RAW.FEED_SNAPSHOTS)
        AS feed_snapshots,
    (SELECT COUNT(*) FROM RAW.TRIP_UPDATES)
        AS trip_observations,
    (SELECT COUNT(*) FROM RAW.STOP_TIME_UPDATES)
        AS stop_observations,
    (
        SELECT COUNT(DISTINCT route_id)
        FROM RAW.TRIP_UPDATES
    ) AS distinct_routes,
    (
        SELECT COUNT(DISTINCT stop_id)
        FROM RAW.STOP_TIME_UPDATES
    ) AS distinct_stops,
    (
        SELECT COUNT_IF(
            trip_schedule_relationship = 'CANCELED'
        )
        FROM RAW.TRIP_UPDATES
    ) AS canceled_trip_observations,
    (
        SELECT COUNT_IF(
            stop_schedule_relationship = 'SKIPPED'
        )
        FROM RAW.STOP_TIME_UPDATES
    ) AS skipped_stop_observations,
    (
        SELECT ROUND(
            100.0 * COUNT(
                COALESCE(
                    arrival_delay_seconds,
                    departure_delay_seconds
                )
            ) / NULLIF(COUNT(*), 0),
            2
        )
        FROM RAW.STOP_TIME_UPDATES
    ) AS reported_delay_coverage_percentage,
    (
        SELECT ROUND(
            AVG(
                COALESCE(
                    arrival_delay_seconds,
                    departure_delay_seconds
                )
            ),
            2
        )
        FROM RAW.STOP_TIME_UPDATES
    ) AS average_reported_delay_seconds,
    (
        SELECT ROUND(
            100.0 * COUNT_IF(
                COALESCE(
                    arrival_delay_seconds,
                    departure_delay_seconds
                ) > 300
            )
            / NULLIF(
                COUNT(
                    COALESCE(
                        arrival_delay_seconds,
                        departure_delay_seconds
                    )
                ),
                0
            ),
            2
        )
        FROM RAW.STOP_TIME_UPDATES
    ) AS delayed_over_five_minutes_percentage;

SELECT * FROM ANALYTICS.KPI_SUMMARY;
