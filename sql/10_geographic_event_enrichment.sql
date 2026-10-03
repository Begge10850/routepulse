USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- Final event grain for the dashboard.
--
-- Region is assigned from the state containing the observed stop. It is not
-- inferred from a route name, operator headquarters or route-wide coverage.
-- Realtime and static stop IDs use two observed representations: unprefixed
-- IDs with optional leading zeroes, and namespaced IDs such as
-- de:15090:8010121. A normalized ID is used only when every static candidate
-- for that ID belongs to the same region. This recovers the region, but not a
-- station name or coordinate. IDs without a deterministic regional match are
-- retained as Unmatched/unknown rather than mislabeled as outside the study
-- area.
-- The route catalogue contributes passenger-facing service names, the single
-- evidence-based transport-mode mapping and scheduled geographic coverage.
CREATE OR REPLACE TRANSIENT TABLE STOP_EVENTS_GEOGRAPHIC AS
WITH normalized_static_stops AS (
    SELECT DISTINCT
        stop_id,
        CASE
            WHEN stop_id LIKE '%:%'
                THEN LTRIM(SPLIT_PART(stop_id, ':', 3), '0')
            ELSE LTRIM(stop_id, '0')
        END AS normalized_stop_id,
        COALESCE(state_name, 'Outside Berlin-Brandenburg')
            AS candidate_region,
        state_code AS candidate_region_code
    FROM GTFS_STOPS_GEOGRAPHIC
),

recoverable_stop_regions AS (
    SELECT
        normalized_stop_id,
        MIN(candidate_region) AS recovered_region,
        MIN(candidate_region_code) AS recovered_region_code
    FROM normalized_static_stops
    WHERE normalized_stop_id IS NOT NULL
      AND normalized_stop_id <> ''
    GROUP BY normalized_stop_id
    HAVING COUNT(DISTINCT candidate_region) = 1
)

SELECT
    e.trip_id,
    e.start_date,
    e.stop_sequence,
    e.stop_id,
    e.route_id AS observed_route_id,
    c.static_route_id,
    e.direction_id,
    e.observed_at_utc,
    CONVERT_TIMEZONE(
        'UTC',
        'Europe/Berlin',
        e.observed_at_utc::TIMESTAMP_NTZ
    ) AS observed_at_berlin,
    e.arrival_delay_seconds,
    e.departure_delay_seconds,
    e.reported_delay_seconds,
    e.stop_schedule_relationship,

    stops.stop_name AS station_name,
    stops.stop_lat AS station_lat,
    stops.stop_lon AS station_lon,
    stops.stop_geography,
    CASE
        WHEN stops.stop_id IS NOT NULL
            THEN COALESCE(stops.state_name, 'Outside Berlin-Brandenburg')
        WHEN recovered.normalized_stop_id IS NOT NULL
            THEN recovered.recovered_region
        ELSE 'Unmatched/unknown'
    END AS event_region,
    CASE
        WHEN stops.stop_id IS NOT NULL THEN stops.state_code
        WHEN recovered.normalized_stop_id IS NOT NULL
            THEN recovered.recovered_region_code
        ELSE NULL
    END AS event_region_code,
    CASE
        WHEN stops.stop_id IS NOT NULL THEN 'Exact stop ID'
        WHEN recovered.normalized_stop_id IS NOT NULL
            THEN 'Normalized stop ID'
        ELSE 'Unmatched/unknown'
    END AS event_region_match_method,

    c.agency_id,
    c.agency_name,
    c.route_short_name,
    c.route_long_name,
    c.route_type,
    c.route_display_name,
    c.transport_mode,
    c.german_service_category,
    c.scheduled_stop_count,
    c.berlin_stop_count,
    c.brandenburg_stop_count,
    c.outside_stop_count,
    c.serves_berlin,
    c.serves_brandenburg,
    c.extends_outside_study_area,
    c.route_geographic_scope
FROM UNIQUE_STOP_EVENTS AS e
LEFT JOIN GTFS_STOPS_GEOGRAPHIC AS stops
    ON e.stop_id = stops.stop_id
LEFT JOIN recoverable_stop_regions AS recovered
    ON stops.stop_id IS NULL
   AND CASE
        WHEN e.stop_id LIKE '%:%'
            THEN LTRIM(SPLIT_PART(e.stop_id, ':', 3), '0')
        ELSE LTRIM(e.stop_id, '0')
       END = recovered.normalized_stop_id
LEFT JOIN ROUTE_GEOGRAPHIC_CATALOG AS c
    ON REPLACE(e.route_id, '-', '_') = c.static_route_id;

-- Validation 1: enrichment must preserve the deduplicated event grain.
SELECT
    (SELECT COUNT(*) FROM UNIQUE_STOP_EVENTS) AS source_event_rows,
    COUNT(*) AS enriched_event_rows,
    COUNT_IF(station_name IS NULL) AS events_without_station,
    COUNT_IF(event_region_match_method = 'Normalized stop ID')
        AS events_with_recovered_region,
    COUNT_IF(event_region = 'Unmatched/unknown') AS events_without_region,
    COUNT_IF(static_route_id IS NULL) AS events_without_catalogued_route,
    COUNT_IF(transport_mode IS NULL) AS events_without_transport_mode
FROM STOP_EVENTS_GEOGRAPHIC;

-- Validation 2: the event key must remain unique after both joins.
SELECT COUNT(*) AS duplicate_event_keys
FROM (
    SELECT
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    FROM STOP_EVENTS_GEOGRAPHIC
    GROUP BY
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    HAVING COUNT(*) > 1
);

-- Validation 3: explain every geographic match. For the current collection,
-- the expected recovered/unknown event counts are 8,468 and 16,205.
SELECT
    event_region_match_method,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT stop_id) AS realtime_stop_ids
FROM STOP_EVENTS_GEOGRAPHIC
GROUP BY event_region_match_method
ORDER BY unique_stop_events DESC;

-- Validation 4: reconcile the state split and its delay-data coverage.
SELECT
    event_region,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT observed_route_id) AS observed_route_ids,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS events_with_delay_data,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_data_availability_percentage,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds > 300)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS late_over_five_minutes_percentage,
    ROUND(MEDIAN(reported_delay_seconds) / 60.0, 2)
        AS median_delay_minutes,
    ROUND(
        PERCENTILE_CONT(0.90) WITHIN GROUP (
            ORDER BY reported_delay_seconds
        ) / 60.0,
        2
    ) AS p90_delay_minutes
FROM STOP_EVENTS_GEOGRAPHIC
GROUP BY event_region
ORDER BY unique_stop_events DESC;

-- Validation 5: verify the consolidated passenger-mode/category mapping.
SELECT
    transport_mode,
    german_service_category,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT observed_route_id) AS observed_route_ids
FROM STOP_EVENTS_GEOGRAPHIC
GROUP BY
    transport_mode,
    german_service_category
ORDER BY
    transport_mode,
    unique_stop_events DESC;

-- Validation 6: all 984 observed technical route IDs should reconcile to the
-- catalogue and to scheduled route shapes. A zero count is required for each
-- unmatched measure before the final dashboard is treated as validated.
SELECT
    COUNT(DISTINCT observed_route_id) AS observed_route_ids,
    COUNT(DISTINCT static_route_id) AS catalogued_route_ids,
    COUNT(DISTINCT paths.route_id) AS routes_with_drawable_shapes,
    COUNT_IF(static_route_id IS NULL) AS event_rows_without_catalogue_match,
    COUNT_IF(paths.route_id IS NULL) AS event_rows_without_shape_match
FROM STOP_EVENTS_GEOGRAPHIC AS events
LEFT JOIN (
    SELECT DISTINCT route_id
    FROM MAP_ROUTE_PATHS_RENDER
) AS paths
    ON events.static_route_id = paths.route_id;
