USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- RoutePulse v4 presentation aggregates.
--
-- These tables preserve additive numerators and denominators. The Streamlit
-- app calculates and displays rates from the counts stored at the grain needed
-- by each view; it never averages percentages across groups.

CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_SCOPE_METRICS AS
WITH by_mode AS (
    SELECT
        transport_mode AS scope_mode,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events,
        ROUND(
            PERCENTILE_CONT(0.90) WITHIN GROUP (
                ORDER BY reported_delay_seconds
            ) / 60.0,
            2
        ) AS p90_delay_minutes
    FROM STOP_EVENTS_GEOGRAPHIC
    WHERE transport_mode IS NOT NULL
    GROUP BY transport_mode
),
all_modes AS (
    SELECT
        'All modes' AS scope_mode,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events,
        ROUND(
            PERCENTILE_CONT(0.90) WITHIN GROUP (
                ORDER BY reported_delay_seconds
            ) / 60.0,
            2
        ) AS p90_delay_minutes
    FROM STOP_EVENTS_GEOGRAPHIC
)
SELECT * FROM by_mode
UNION ALL
SELECT * FROM all_modes;


CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_STATION_METRICS AS
WITH by_mode AS (
    SELECT
        transport_mode AS scope_mode,
        event_region,
        station_display_name AS station_name,
        AVG(station_lat) AS station_lat,
        AVG(station_lon) AS station_lon,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_LINE_FOCUS
    WHERE station_display_name IS NOT NULL
      AND transport_mode IS NOT NULL
    GROUP BY transport_mode, event_region, station_display_name
),
all_modes AS (
    SELECT
        'All modes' AS scope_mode,
        event_region,
        station_display_name AS station_name,
        AVG(station_lat) AS station_lat,
        AVG(station_lon) AS station_lon,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_LINE_FOCUS
    WHERE station_display_name IS NOT NULL
    GROUP BY event_region, station_display_name
)
SELECT * FROM by_mode
UNION ALL
SELECT * FROM all_modes;


CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_LINE_METRICS AS
WITH by_mode AS (
    SELECT
        transport_mode AS scope_mode,
        focus_service_key,
        route_display_name,
        transport_mode,
        german_service_category,
        agency_name,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_LINE_FOCUS
    WHERE focus_service_key IS NOT NULL
      AND transport_mode IS NOT NULL
    GROUP BY
        transport_mode,
        focus_service_key,
        route_display_name,
        german_service_category,
        agency_name
),
all_modes AS (
    SELECT
        'All modes' AS scope_mode,
        focus_service_key,
        route_display_name,
        transport_mode,
        german_service_category,
        agency_name,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_LINE_FOCUS
    WHERE focus_service_key IS NOT NULL
    GROUP BY
        focus_service_key,
        route_display_name,
        transport_mode,
        german_service_category,
        agency_name
)
SELECT * FROM by_mode
UNION ALL
SELECT * FROM all_modes;


CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_HOUR_METRICS AS
WITH by_mode AS (
    SELECT
        transport_mode AS scope_mode,
        observation_hour_berlin,
        is_partial_collection_hour,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events,
        ROUND(
            PERCENTILE_CONT(0.90) WITHIN GROUP (
                ORDER BY reported_delay_seconds
            ) / 60.0,
            2
        ) AS p90_delay_minutes
    FROM STOP_EVENTS_LINE_FOCUS
    WHERE transport_mode IS NOT NULL
    GROUP BY
        transport_mode,
        observation_hour_berlin,
        is_partial_collection_hour
),
all_modes AS (
    SELECT
        'All modes' AS scope_mode,
        observation_hour_berlin,
        is_partial_collection_hour,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events,
        ROUND(
            PERCENTILE_CONT(0.90) WITHIN GROUP (
                ORDER BY reported_delay_seconds
            ) / 60.0,
            2
        ) AS p90_delay_minutes
    FROM STOP_EVENTS_LINE_FOCUS
    GROUP BY observation_hour_berlin, is_partial_collection_hour
)
SELECT * FROM by_mode
UNION ALL
SELECT * FROM all_modes;


CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_REGION_METRICS AS
WITH by_mode AS (
    SELECT
        transport_mode AS scope_mode,
        event_region,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_GEOGRAPHIC
    WHERE transport_mode IS NOT NULL
    GROUP BY transport_mode, event_region
),
all_modes AS (
    SELECT
        'All modes' AS scope_mode,
        event_region,
        COUNT(*) AS unique_stop_events,
        COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
        COUNT_IF(reported_delay_seconds > 300) AS late_events
    FROM STOP_EVENTS_GEOGRAPHIC
    GROUP BY event_region
)
SELECT * FROM by_mode
UNION ALL
SELECT * FROM all_modes;


CREATE OR REPLACE TRANSIENT TABLE DASHBOARD_CATEGORY_METRICS AS
SELECT
    transport_mode AS scope_mode,
    german_service_category,
    COUNT(*) AS unique_stop_events,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_reported_events,
    COUNT_IF(reported_delay_seconds > 300) AS late_events
FROM STOP_EVENTS_GEOGRAPHIC
WHERE transport_mode IN ('Bus', 'Regional rail')
  AND german_service_category IS NOT NULL
GROUP BY transport_mode, german_service_category;


-- Validation 1: every scope aggregate must reconcile to its source population.
WITH reconciliation AS (
    SELECT
        scope.scope_mode,
        scope.unique_stop_events AS scope_metric_events,
        IFF(
            scope.scope_mode = 'All modes',
            (SELECT COUNT(*) FROM STOP_EVENTS_GEOGRAPHIC),
            (
                SELECT COUNT(*)
                FROM STOP_EVENTS_GEOGRAPHIC AS events
                WHERE events.transport_mode = scope.scope_mode
            )
        ) AS source_events
    FROM DASHBOARD_SCOPE_METRICS AS scope
)
SELECT
    scope_mode,
    scope_metric_events,
    source_events,
    scope_metric_events = source_events AS event_count_matches
FROM reconciliation
ORDER BY scope_mode;

-- Validation 2: the corrected geographic split must total 1,755,847.
SELECT
    event_region,
    unique_stop_events,
    delay_reported_events,
    late_events
FROM DASHBOARD_REGION_METRICS
WHERE scope_mode = 'All modes'
ORDER BY CASE event_region
    WHEN 'Berlin' THEN 1
    WHEN 'Brandenburg' THEN 2
    WHEN 'Outside Berlin-Brandenburg' THEN 3
    WHEN 'Unmatched/unknown' THEN 4
    ELSE 5
END;

-- Validation 3: quantify the two warning badges before publishing.
SELECT
    scope_mode,
    COUNT_IF(delay_reported_events >= 100) AS eligible_lines,
    COUNT_IF(delay_reported_events BETWEEN 100 AND 299) AS low_sample_lines,
    COUNT_IF(
        delay_reported_events >= 100
        AND 100.0 * delay_reported_events / NULLIF(unique_stop_events, 0) < 60
    ) AS low_coverage_lines
FROM DASHBOARD_LINE_METRICS
WHERE scope_mode <> 'All modes'
GROUP BY scope_mode
ORDER BY scope_mode;

-- Validation 4: the event-grain table remains unchanged by presentation work.
SELECT
    COUNT(*) AS event_rows,
    COUNT(*) = 1755847 AS expected_event_count,
    COUNT_IF(event_region = 'Berlin') AS berlin_events,
    COUNT_IF(event_region = 'Brandenburg') AS brandenburg_events,
    COUNT_IF(event_region = 'Outside Berlin-Brandenburg') AS outside_events,
    COUNT_IF(event_region = 'Unmatched/unknown') AS unmatched_events
FROM STOP_EVENTS_GEOGRAPHIC;
