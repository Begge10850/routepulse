USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- RoutePulse timing-methodology validation.
--
-- early:              more than 1 minute ahead of schedule
-- near schedule:      1 minute early through 1 minute late
-- minor delay:        more than 1 through 5 minutes late
-- serious delay:      more than 5 minutes late
-- unavailable:        no reported timing value

-- 1. Show the headline timing distribution for every dashboard scope.
SELECT
    scope_mode,
    scope_region,
    unique_stop_events,
    delay_reported_events AS visits_with_timing_information,
    early_events,
    near_schedule_events,
    minor_delay_events,
    late_events AS serious_delay_events,
    timing_unavailable_events,
    ROUND(
        100.0 * early_events / NULLIF(delay_reported_events, 0),
        2
    ) AS early_percentage,
    ROUND(
        100.0 * near_schedule_events / NULLIF(delay_reported_events, 0),
        2
    ) AS near_schedule_percentage,
    ROUND(
        100.0 * minor_delay_events / NULLIF(delay_reported_events, 0),
        2
    ) AS minor_delay_percentage,
    ROUND(
        100.0 * late_events / NULLIF(delay_reported_events, 0),
        2
    ) AS serious_delay_percentage,
    ROUND(
        100.0 * timing_unavailable_events / NULLIF(unique_stop_events, 0),
        2
    ) AS timing_unavailable_percentage
FROM DASHBOARD_SCOPE_METRICS
ORDER BY
    CASE scope_region
        WHEN 'All regions' THEN 1
        WHEN 'Berlin' THEN 2
        WHEN 'Brandenburg' THEN 3
        ELSE 4
    END,
    CASE scope_mode
        WHEN 'All modes' THEN 1
        WHEN 'Bus' THEN 2
        WHEN 'Tram' THEN 3
        WHEN 'U-Bahn' THEN 4
        WHEN 'S-Bahn' THEN 5
        WHEN 'Regional rail' THEN 6
        ELSE 7
    END;

-- 2. Every aggregate row must reconcile to both its timed and total population.
WITH validation_rows AS (
    SELECT
        'DASHBOARD_SCOPE_METRICS' AS model_name,
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_SCOPE_METRICS
    UNION ALL
    SELECT
        'DASHBOARD_STATION_METRICS',
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_STATION_METRICS
    UNION ALL
    SELECT
        'DASHBOARD_LINE_METRICS',
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_LINE_METRICS
    UNION ALL
    SELECT
        'DASHBOARD_HOUR_METRICS',
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_HOUR_METRICS
    UNION ALL
    SELECT
        'DASHBOARD_REGION_METRICS',
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_REGION_METRICS
    UNION ALL
    SELECT
        'DASHBOARD_CATEGORY_METRICS',
        unique_stop_events,
        delay_reported_events,
        early_events,
        near_schedule_events,
        minor_delay_events,
        late_events,
        timing_unavailable_events
    FROM DASHBOARD_CATEGORY_METRICS
),
validation_summary AS (
SELECT
    model_name,
    COUNT(*) AS aggregate_rows,
    COUNT_IF(
        delay_reported_events
        <> early_events + near_schedule_events + minor_delay_events + late_events
    ) AS timing_category_mismatches,
    COUNT_IF(
        unique_stop_events
        <> delay_reported_events + timing_unavailable_events
    ) AS availability_mismatches
FROM validation_rows
GROUP BY model_name
)
SELECT
    model_name,
    aggregate_rows,
    timing_category_mismatches,
    availability_mismatches,
    timing_category_mismatches = 0
        AND availability_mismatches = 0 AS all_rows_reconcile
FROM validation_summary
ORDER BY model_name;

-- 3. Serious-delay counts must remain identical to the existing >5-minute rule.
WITH serious_delay_validation AS (
SELECT
    COUNT_IF(reported_delay_seconds > 300) AS source_serious_delay_events,
    (
        SELECT late_events
        FROM DASHBOARD_SCOPE_METRICS
        WHERE scope_mode = 'All modes'
          AND scope_region = 'All regions'
    ) AS dashboard_serious_delay_events
FROM STOP_EVENTS_GEOGRAPHIC
)
SELECT
    source_serious_delay_events,
    dashboard_serious_delay_events,
    source_serious_delay_events = dashboard_serious_delay_events
        AS serious_delay_count_matches
FROM serious_delay_validation;
