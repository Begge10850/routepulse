USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- RoutePulse v2.1 line-focus foundations.
--
-- A passenger-facing line is mode + agency + displayed route name. Static
-- technical route IDs that share those fields remain part of one line. A
-- canonical pattern is the most frequent ordered stop pattern for that line
-- and direction in the loaded static reference. This is a reference pattern,
-- not a claim about the exact trips scheduled during the 39.5-hour sample.

CREATE OR REPLACE TRANSIENT TABLE TRIP_STOP_PATTERNS AS
WITH ordered_trip_stops AS (
    SELECT
        trips.trip_id,
        trips.route_id AS static_route_id,
        trips.direction_id,
        trips.trip_headsign,
        catalogue.transport_mode,
        catalogue.german_service_category,
        catalogue.agency_id,
        catalogue.agency_name,
        catalogue.route_display_name,
        CONCAT_WS(
            '|',
            COALESCE(catalogue.transport_mode, 'Unknown mode'),
            COALESCE(catalogue.agency_id, 'Unknown agency'),
            COALESCE(catalogue.route_display_name, 'Unnamed route')
        ) AS focus_service_key,
        stop_times.stop_id,
        stop_times.stop_sequence,
        ROW_NUMBER() OVER (
            PARTITION BY trips.trip_id
            ORDER BY
                TRY_TO_NUMBER(stop_times.stop_sequence),
                stop_times.stop_sequence,
                stop_times.stop_id
        ) AS stop_order,
        ROW_NUMBER() OVER (
            PARTITION BY trips.trip_id
            ORDER BY
                TRY_TO_NUMBER(stop_times.stop_sequence) DESC,
                stop_times.stop_sequence DESC,
                stop_times.stop_id DESC
        ) AS reverse_stop_order
    FROM ROUTEPULSE.RAW.GTFS_TRIPS AS trips
    JOIN ROUTEPULSE.RAW.GTFS_STOP_TIMES AS stop_times
        ON trips.trip_id = stop_times.trip_id
    JOIN ROUTEPULSE.ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG AS catalogue
        ON trips.route_id = catalogue.static_route_id
),

trip_patterns AS (
    SELECT
        trip_id,
        static_route_id,
        direction_id,
        trip_headsign,
        transport_mode,
        german_service_category,
        agency_id,
        agency_name,
        route_display_name,
        focus_service_key,
        COUNT(*) AS stop_count,
        MAX(IFF(stop_order = 1, stop_id, NULL)) AS first_stop_id,
        MAX(IFF(reverse_stop_order = 1, stop_id, NULL)) AS last_stop_id,
        LISTAGG(stop_id, '>') WITHIN GROUP (
            ORDER BY stop_order
        ) AS stop_pattern_signature
    FROM ordered_trip_stops
    GROUP BY
        trip_id,
        static_route_id,
        direction_id,
        trip_headsign,
        transport_mode,
        german_service_category,
        agency_id,
        agency_name,
        route_display_name,
        focus_service_key
)

SELECT
    trip_patterns.*,
    SHA2(stop_pattern_signature, 256) AS route_pattern_id
FROM trip_patterns;


CREATE OR REPLACE TRANSIENT TABLE LINE_DIRECTION_REFERENCE AS
WITH pattern_frequency AS (
    SELECT
        focus_service_key,
        transport_mode,
        german_service_category,
        agency_id,
        agency_name,
        route_display_name,
        direction_id,
        route_pattern_id,
        stop_pattern_signature,
        stop_count,
        first_stop_id,
        last_stop_id,
        MIN(trip_id) AS canonical_trip_id,
        MIN(trip_headsign) AS supporting_headsign,
        COUNT(*) AS static_reference_trips,
        COUNT(DISTINCT static_route_id) AS technical_route_ids
    FROM TRIP_STOP_PATTERNS
    GROUP BY
        focus_service_key,
        transport_mode,
        german_service_category,
        agency_id,
        agency_name,
        route_display_name,
        direction_id,
        route_pattern_id,
        stop_pattern_signature,
        stop_count,
        first_stop_id,
        last_stop_id
),

ranked_patterns AS (
    SELECT
        pattern_frequency.*,
        COUNT(*) OVER (
            PARTITION BY focus_service_key, direction_id
        ) AS pattern_variant_count,
        ROW_NUMBER() OVER (
            PARTITION BY focus_service_key, direction_id
            ORDER BY
                static_reference_trips DESC,
                stop_count DESC,
                route_pattern_id
        ) AS pattern_rank
    FROM pattern_frequency
)

SELECT
    ranked.focus_service_key,
    ranked.transport_mode,
    ranked.german_service_category,
    ranked.agency_id,
    ranked.agency_name,
    ranked.route_display_name,
    ranked.direction_id,
    ranked.route_pattern_id AS canonical_pattern_id,
    ranked.canonical_trip_id,
    ranked.supporting_headsign,
    ranked.stop_count AS canonical_stop_count,
    ranked.static_reference_trips,
    ranked.technical_route_ids,
    ranked.pattern_variant_count,
    GREATEST(ranked.pattern_variant_count - 1, 0)
        AS alternate_pattern_count,
    ranked.first_stop_id,
    first_stop.stop_name AS first_stop_name,
    ranked.last_stop_id,
    last_stop.stop_name AS last_stop_name
FROM ranked_patterns AS ranked
LEFT JOIN ROUTEPULSE.ANALYTICS.GTFS_STOPS_GEOGRAPHIC AS first_stop
    ON ranked.first_stop_id = first_stop.stop_id
LEFT JOIN ROUTEPULSE.ANALYTICS.GTFS_STOPS_GEOGRAPHIC AS last_stop
    ON ranked.last_stop_id = last_stop.stop_id
WHERE ranked.pattern_rank = 1;


CREATE OR REPLACE TRANSIENT TABLE LINE_CANONICAL_STOPS AS
SELECT
    reference.focus_service_key,
    reference.transport_mode,
    reference.agency_id,
    reference.agency_name,
    reference.route_display_name,
    reference.direction_id,
    reference.canonical_pattern_id,
    reference.first_stop_name,
    reference.last_stop_name,
    stop_times.stop_sequence,
    stop_times.stop_id,
    CASE
        WHEN stop_times.stop_id LIKE '%:%'
            THEN LTRIM(SPLIT_PART(stop_times.stop_id, ':', 3), '0')
        ELSE LTRIM(stop_times.stop_id, '0')
    END AS normalized_stop_id,
    stops.stop_name,
    stops.stop_lat,
    stops.stop_lon,
    stops.state_name,
    ROW_NUMBER() OVER (
        PARTITION BY
            reference.focus_service_key,
            reference.direction_id,
            reference.canonical_pattern_id
        ORDER BY
            TRY_TO_NUMBER(stop_times.stop_sequence),
            stop_times.stop_sequence,
            stop_times.stop_id
    ) AS stop_order
FROM LINE_DIRECTION_REFERENCE AS reference
JOIN ROUTEPULSE.RAW.GTFS_STOP_TIMES AS stop_times
    ON reference.canonical_trip_id = stop_times.trip_id
LEFT JOIN ROUTEPULSE.ANALYTICS.GTFS_STOPS_GEOGRAPHIC AS stops
    ON stop_times.stop_id = stops.stop_id;


CREATE OR REPLACE TRANSIENT TABLE STOP_EVENTS_LINE_FOCUS AS
WITH event_bounds AS (
    SELECT
        MIN(observed_at_berlin) AS first_event_berlin,
        MAX(observed_at_berlin) AS last_event_berlin
    FROM STOP_EVENTS_GEOGRAPHIC
)

SELECT
    events.*,
    COALESCE(events.direction_id, patterns.direction_id)
        AS focus_direction_id,
    COALESCE(
        patterns.focus_service_key,
        CONCAT_WS(
            '|',
            COALESCE(events.transport_mode, 'Unknown mode'),
            COALESCE(events.agency_id, 'Unknown agency'),
            COALESCE(events.route_display_name, 'Unnamed route')
        )
    ) AS focus_service_key,
    patterns.route_pattern_id,
    patterns.stop_count AS trip_pattern_stop_count,
    patterns.first_stop_id AS trip_first_stop_id,
    patterns.last_stop_id AS trip_last_stop_id,
    reference.canonical_pattern_id,
    reference.first_stop_name AS canonical_first_stop_name,
    reference.last_stop_name AS canonical_last_stop_name,
    reference.canonical_stop_count,
    reference.alternate_pattern_count,
    IFF(
        patterns.route_pattern_id = reference.canonical_pattern_id,
        TRUE,
        FALSE
    ) AS is_canonical_pattern,
    CASE
        WHEN events.stop_id LIKE '%:%'
            THEN LTRIM(SPLIT_PART(events.stop_id, ':', 3), '0')
        ELSE LTRIM(events.stop_id, '0')
    END AS normalized_stop_id,
    CASE
        WHEN events.event_region = 'Berlin'
             AND events.station_name ILIKE 'Berlin, %'
            THEN CONCAT(
                SUBSTR(events.station_name, LENGTH('Berlin, ') + 1),
                ' (Berlin)'
            )
        ELSE events.station_name
    END AS station_display_name,
    DATE_TRUNC('hour', events.observed_at_berlin) AS observation_hour_berlin,
    IFF(
        DATE_TRUNC('hour', events.observed_at_berlin) IN (
            DATE_TRUNC('hour', bounds.first_event_berlin),
            DATE_TRUNC('hour', bounds.last_event_berlin)
        ),
        TRUE,
        FALSE
    ) AS is_partial_collection_hour,
    IFF(events.reported_delay_seconds IS NOT NULL, 1, 0)
        AS has_delay_value,
    IFF(events.reported_delay_seconds > 300, 1, 0)
        AS is_over_five_minutes_late
FROM STOP_EVENTS_GEOGRAPHIC AS events
LEFT JOIN TRIP_STOP_PATTERNS AS patterns
    ON events.trip_id = patterns.trip_id
LEFT JOIN LINE_DIRECTION_REFERENCE AS reference
    ON COALESCE(
        patterns.focus_service_key,
        CONCAT_WS(
            '|',
            COALESCE(events.transport_mode, 'Unknown mode'),
            COALESCE(events.agency_id, 'Unknown agency'),
            COALESCE(events.route_display_name, 'Unnamed route')
        )
       ) = reference.focus_service_key
   AND COALESCE(
        TO_VARCHAR(COALESCE(events.direction_id, patterns.direction_id)),
        'Unknown'
       )
       = COALESCE(TO_VARCHAR(reference.direction_id), 'Unknown')
CROSS JOIN event_bounds AS bounds;


CREATE OR REPLACE TRANSIENT TABLE LINE_STOP_HOUR_METRICS AS
SELECT
    focus_service_key,
    transport_mode,
    german_service_category,
    agency_id,
    agency_name,
    route_display_name,
    focus_direction_id,
    route_pattern_id,
    canonical_pattern_id,
    is_canonical_pattern,
    normalized_stop_id,
    station_display_name,
    station_lat,
    station_lon,
    event_region,
    stop_sequence,
    observation_hour_berlin,
    is_partial_collection_hour,
    COUNT(*) AS unique_stop_events,
    SUM(has_delay_value) AS delay_reported_events,
    SUM(is_over_five_minutes_late) AS late_events,
    ROUND(
        100.0 * SUM(has_delay_value) / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    ROUND(
        100.0 * SUM(is_over_five_minutes_late)
        / NULLIF(SUM(has_delay_value), 0),
        2
    ) AS late_percentage,
    ROUND(
        PERCENTILE_CONT(0.90) WITHIN GROUP (
            ORDER BY reported_delay_seconds
        ) / 60.0,
        2
    ) AS p90_delay_minutes
FROM STOP_EVENTS_LINE_FOCUS
GROUP BY
    focus_service_key,
    transport_mode,
    german_service_category,
    agency_id,
    agency_name,
    route_display_name,
    focus_direction_id,
    route_pattern_id,
    canonical_pattern_id,
    is_canonical_pattern,
    normalized_stop_id,
    station_display_name,
    station_lat,
    station_lon,
    event_region,
    stop_sequence,
    observation_hour_berlin,
    is_partial_collection_hour;


-- Validation 1: the line-focus event table must preserve the corrected event
-- table exactly. The expected row count for this collection is 1,755,847.
SELECT
    (SELECT COUNT(*) FROM STOP_EVENTS_GEOGRAPHIC) AS source_event_rows,
    COUNT(*) AS line_focus_event_rows,
    COUNT_IF(route_pattern_id IS NULL) AS events_without_static_pattern,
    COUNT_IF(stop_sequence IS NULL) AS events_without_stop_sequence
FROM STOP_EVENTS_LINE_FOCUS;

-- Validation 2: no join is allowed to duplicate the event key.
SELECT COUNT(*) AS duplicate_event_keys
FROM (
    SELECT
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    FROM STOP_EVENTS_LINE_FOCUS
    GROUP BY
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    HAVING COUNT(*) > 1
);

-- Validation 3: one canonical reference row per line and direction.
SELECT COUNT(*) AS duplicate_line_directions
FROM (
    SELECT
        focus_service_key,
        direction_id
    FROM LINE_DIRECTION_REFERENCE
    GROUP BY focus_service_key, direction_id
    HAVING COUNT(*) > 1
);

-- Validation 4: quantify the graceful profile fallback by mode. A mode with
-- missing sequences still supports line KPIs, maps and hourly analysis.
SELECT
    transport_mode,
    COUNT(*) AS unique_stop_events,
    COUNT_IF(stop_sequence IS NULL) AS events_without_stop_sequence,
    COUNT_IF(route_pattern_id IS NULL) AS events_without_static_pattern,
    COUNT(DISTINCT focus_service_key) AS passenger_facing_lines
FROM STOP_EVENTS_LINE_FOCUS
GROUP BY transport_mode
ORDER BY unique_stop_events DESC;
