USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- Read-only investigation retained from the original geographical.sql
-- worksheet. Run after sql/10_geographic_event_enrichment.sql.
--
-- The original worksheet also contained an earlier CREATE OR REPLACE version
-- of STOP_EVENTS_GEOGRAPHIC that classified unmatched stops as outside the
-- study area. That superseded definition is deliberately not executable here;
-- stage 10 contains the corrected normalized-region recovery logic.

SELECT event_region, COUNT(*)
FROM STOP_EVENTS_GEOGRAPHIC
GROUP BY event_region;

SELECT
    event_region,
    COUNT(*) AS event_count,
    COUNT_IF(station_name IS NULL) AS events_without_station_match,
    COUNT_IF(stop_geography IS NULL) AS events_without_coordinates,
    COUNT(DISTINCT stop_id) AS distinct_stops
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
GROUP BY event_region
ORDER BY event_count DESC;

SELECT
    CASE
        WHEN station_name IS NULL
          OR stop_geography IS NULL
            THEN 'Unmatched/unknown'
        ELSE event_region
    END AS corrected_event_region,
    COUNT(*) AS event_count,
    COUNT(DISTINCT stop_id) AS distinct_stop_ids
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
GROUP BY corrected_event_region
ORDER BY event_count DESC;

SELECT
    events.stop_id,
    COUNT(*) AS event_count,
    MAX(IFF(raw_stops.stop_id IS NOT NULL, 1, 0)) AS exists_in_raw_gtfs_stops
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC AS events
LEFT JOIN ROUTEPULSE.RAW.GTFS_STOPS AS raw_stops
    ON events.stop_id = raw_stops.stop_id
WHERE events.station_name IS NULL
GROUP BY events.stop_id
ORDER BY event_count DESC;

SELECT
    COALESCE(transport_mode, 'Unknown mode') AS transport_mode,
    COALESCE(agency_name, 'Unknown operator') AS operator,
    COALESCE(route_display_name, observed_route_id) AS service,
    COUNT(*) AS unmatched_events,
    COUNT(DISTINCT stop_id) AS unmatched_stop_ids
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
WHERE station_name IS NULL
GROUP BY
    transport_mode,
    agency_name,
    COALESCE(route_display_name, observed_route_id)
ORDER BY unmatched_events DESC;

SELECT
    COALESCE(agency_name, 'Unknown operator') AS operator,
    COUNT(*) AS unmatched_events,
    COUNT(DISTINCT stop_id) AS unmatched_stop_ids,
    COUNT(DISTINCT observed_route_id) AS affected_route_ids,
    ROUND(
        100.0 * COUNT(*)
        / SUM(COUNT(*)) OVER (),
        2
    ) AS share_of_unmatched_events
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
WHERE station_name IS NULL
GROUP BY agency_name
ORDER BY unmatched_events DESC;

WITH unmatched_stops AS (
    SELECT DISTINCT stop_id
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    WHERE station_name IS NULL
),
static_stop_time_ids AS (
    SELECT DISTINCT stop_id
    FROM ROUTEPULSE.RAW.GTFS_STOP_TIMES
)
SELECT
    COUNT(*) AS unmatched_stop_ids,
    COUNT_IF(stop_times.stop_id IS NOT NULL)
        AS found_in_static_stop_times,
    COUNT_IF(stop_times.stop_id IS NULL)
        AS absent_from_static_stop_times
FROM unmatched_stops
LEFT JOIN static_stop_time_ids AS stop_times
    ON unmatched_stops.stop_id = stop_times.stop_id;

WITH unmatched_trips AS (
    SELECT DISTINCT trip_id
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    WHERE station_name IS NULL
),
static_trips AS (
    SELECT DISTINCT trip_id
    FROM ROUTEPULSE.RAW.GTFS_TRIPS
)
SELECT
    COUNT(*) AS unmatched_event_trip_ids,
    COUNT_IF(static_trips.trip_id IS NOT NULL)
        AS trips_found_in_static_gtfs,
    COUNT_IF(static_trips.trip_id IS NULL)
        AS trips_absent_from_static_gtfs
FROM unmatched_trips
LEFT JOIN static_trips
    ON unmatched_trips.trip_id = static_trips.trip_id;

WITH unmatched_events AS (
    SELECT
        trip_id,
        stop_sequence,
        stop_id AS realtime_stop_id
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    WHERE station_name IS NULL
)
SELECT
    COUNT(*) AS unmatched_events,
    COUNT_IF(static_times.stop_id IS NOT NULL)
        AS matched_by_trip_and_sequence,
    COUNT_IF(static_times.stop_id IS NULL)
        AS still_unmatched,
    COUNT(DISTINCT unmatched.realtime_stop_id)
        AS realtime_stop_ids,
    COUNT(DISTINCT static_times.stop_id)
        AS recovered_static_stop_ids
FROM unmatched_events AS unmatched
LEFT JOIN ROUTEPULSE.RAW.GTFS_STOP_TIMES AS static_times
    ON unmatched.trip_id = static_times.trip_id
   AND unmatched.stop_sequence = static_times.stop_sequence;

WITH stop_pairs AS (
    SELECT
        events.stop_id AS realtime_stop_id,
        static_times.stop_id AS static_stop_id,
        COUNT(*) AS event_count
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC AS events
    JOIN ROUTEPULSE.RAW.GTFS_STOP_TIMES AS static_times
        ON events.trip_id = static_times.trip_id
       AND events.stop_sequence = static_times.stop_sequence
    WHERE events.station_name IS NULL
    GROUP BY
        events.stop_id,
        static_times.stop_id
),
mapping_quality AS (
    SELECT
        realtime_stop_id,
        COUNT(DISTINCT static_stop_id) AS possible_static_stop_ids,
        SUM(event_count) AS event_count
    FROM stop_pairs
    GROUP BY realtime_stop_id
)
SELECT
    COUNT(*) AS realtime_stop_ids,
    COUNT_IF(possible_static_stop_ids = 1) AS deterministic_mappings,
    COUNT_IF(possible_static_stop_ids > 1) AS ambiguous_mappings,
    SUM(IFF(possible_static_stop_ids = 1, event_count, 0))
        AS events_with_deterministic_mapping,
    SUM(IFF(possible_static_stop_ids > 1, event_count, 0))
        AS events_with_ambiguous_mapping
FROM mapping_quality;

WITH sample_trip AS (
    SELECT
        trip_id,
        COUNT(*) AS event_count
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    WHERE station_name IS NULL
    GROUP BY trip_id
    ORDER BY event_count DESC
    LIMIT 1
),
combined_stops AS (
    SELECT DISTINCT
        'REALTIME' AS source,
        events.trip_id,
        events.stop_sequence,
        events.stop_id
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC AS events
    JOIN sample_trip
        ON events.trip_id = sample_trip.trip_id
    WHERE events.station_name IS NULL

    UNION ALL

    SELECT DISTINCT
        'STATIC' AS source,
        static_times.trip_id,
        static_times.stop_sequence,
        static_times.stop_id
    FROM ROUTEPULSE.RAW.GTFS_STOP_TIMES AS static_times
    JOIN sample_trip
        ON static_times.trip_id = sample_trip.trip_id
)
SELECT *
FROM combined_stops
ORDER BY
    TRY_TO_NUMBER(stop_sequence),
    source;

WITH unmatched_event_counts AS (
    SELECT
        stop_id AS realtime_stop_id,
        COUNT(*) AS event_count
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    WHERE station_name IS NULL
    GROUP BY stop_id
),

unmatched_ids AS (
    SELECT
        realtime_stop_id,
        event_count,
        CASE
            WHEN realtime_stop_id LIKE '%:%'
                THEN LTRIM(SPLIT_PART(realtime_stop_id, ':', 3), '0')
            ELSE LTRIM(realtime_stop_id, '0')
        END AS normalized_stop_id
    FROM unmatched_event_counts
),

static_ids AS (
    SELECT DISTINCT
        stop_id AS static_stop_id,
        stop_name,
        state_name,
        CASE
            WHEN stop_id LIKE '%:%'
                THEN LTRIM(SPLIT_PART(stop_id, ':', 3), '0')
            ELSE LTRIM(stop_id, '0')
        END AS normalized_stop_id
    FROM ROUTEPULSE.ANALYTICS.GTFS_STOPS_GEOGRAPHIC
),

mapping_quality AS (
    SELECT
        realtime.realtime_stop_id,
        realtime.event_count,
        COUNT(DISTINCT static.static_stop_id)
            AS candidate_static_stop_ids,
        COUNT(
            DISTINCT IFF(
                static.static_stop_id IS NULL,
                NULL,
                COALESCE(
                    static.state_name,
                    'Outside Berlin-Brandenburg'
                )
            )
        ) AS candidate_regions
    FROM unmatched_ids AS realtime
    LEFT JOIN static_ids AS static
        ON realtime.normalized_stop_id = static.normalized_stop_id
    GROUP BY
        realtime.realtime_stop_id,
        realtime.event_count
)

SELECT
    CASE
        WHEN candidate_static_stop_ids = 0
            THEN 'No normalized match'
        WHEN candidate_regions = 1
            THEN 'Region recoverable'
        ELSE 'Ambiguous region'
    END AS mapping_status,
    COUNT(*) AS realtime_stop_ids,
    SUM(event_count) AS affected_events
FROM mapping_quality
GROUP BY mapping_status
ORDER BY affected_events DESC;
