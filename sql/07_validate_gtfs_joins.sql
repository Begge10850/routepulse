USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;

-- 1. Confirm both reference-table loads.
SELECT
    (SELECT COUNT(*) FROM RAW.GTFS_STOPS) AS gtfs_stop_rows,
    (SELECT COUNT(*) FROM RAW.GTFS_ROUTES) AS gtfs_route_rows;

-- 2. Measure how many real-time stop observations match a named GTFS stop.
SELECT
    COUNT(*) AS total_stop_observations,
    COUNT_IF(g.stop_id IS NOT NULL) AS matched_stop_observations,
    COUNT_IF(g.stop_id IS NULL) AS unmatched_stop_observations,
    ROUND(
        100.0 * COUNT_IF(g.stop_id IS NOT NULL) / NULLIF(COUNT(*), 0),
        2
    ) AS stop_name_match_percentage
FROM RAW.STOP_TIME_UPDATES AS r
LEFT JOIN RAW.GTFS_STOPS AS g
    ON r.stop_id = g.stop_id;

-- 3. Measure how many real-time trip observations match a named GTFS route.
-- Real-time IDs use a hyphen where static GTFS uses an underscore.
SELECT
    COUNT(*) AS total_trip_observations,
    COUNT_IF(g.route_id IS NOT NULL) AS matched_route_observations,
    COUNT_IF(g.route_id IS NULL) AS unmatched_route_observations,
    ROUND(
        100.0 * COUNT_IF(g.route_id IS NOT NULL) / NULLIF(COUNT(*), 0),
        2
    ) AS route_name_match_percentage
FROM RAW.TRIP_UPDATES AS r
LEFT JOIN RAW.GTFS_ROUTES AS g
    ON REPLACE(r.route_id, '-', '_') = g.route_id;

-- 4. Preview stakeholder-readable station names.
SELECT
    r.stop_id,
    g.stop_name,
    g.parent_station,
    g.platform_code,
    COUNT(*) AS observations
FROM RAW.STOP_TIME_UPDATES AS r
JOIN RAW.GTFS_STOPS AS g
    ON r.stop_id = g.stop_id
GROUP BY
    r.stop_id,
    g.stop_name,
    g.parent_station,
    g.platform_code
ORDER BY observations DESC
LIMIT 20;

-- 5. Preview stakeholder-readable route names.
SELECT
    r.route_id AS realtime_route_id,
    g.route_short_name,
    g.route_long_name,
    COUNT(*) AS observations
FROM RAW.TRIP_UPDATES AS r
JOIN RAW.GTFS_ROUTES AS g
    ON REPLACE(r.route_id, '-', '_') = g.route_id
GROUP BY
    r.route_id,
    g.route_short_name,
    g.route_long_name
ORDER BY observations DESC
LIMIT 20;

SELECT COUNT(*) AS gtfs_stop_rows
FROM ROUTEPULSE.RAW.GTFS_STOPS;

SELECT
    COUNT(*) AS total_stop_observations,
    COUNT_IF(g.stop_id IS NOT NULL) AS matched_stop_observations,
    COUNT_IF(g.stop_id IS NULL) AS unmatched_stop_observations,
    ROUND(
        100.0 * COUNT_IF(g.stop_id IS NOT NULL) / NULLIF(COUNT(*), 0),
        2
    ) AS stop_name_match_percentage
FROM ROUTEPULSE.RAW.STOP_TIME_UPDATES AS r
LEFT JOIN ROUTEPULSE.RAW.GTFS_STOPS AS g
    ON r.stop_id = g.stop_id;

SELECT
    g.stop_name,
    g.platform_code,
    COUNT(*) AS stop_observations
FROM ROUTEPULSE.RAW.STOP_TIME_UPDATES AS r
JOIN ROUTEPULSE.RAW.GTFS_STOPS AS g
    ON r.stop_id = g.stop_id
GROUP BY
    g.stop_name,
    g.platform_code
ORDER BY stop_observations DESC
LIMIT 20;
