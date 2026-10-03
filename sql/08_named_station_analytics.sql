USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

CREATE OR REPLACE TRANSIENT TABLE STATION_PERFORMANCE AS
WITH named_observations AS (
    SELECT
        COALESCE(s.parent_station, s.stop_id) AS station_id,
        COALESCE(parent.stop_name, s.stop_name) AS station_name,
        COALESCE(parent.stop_lat, s.stop_lat) AS station_lat,
        COALESCE(parent.stop_lon, s.stop_lon) AS station_lon,
        r.trip_id,
        r.route_id,
        r.stop_schedule_relationship,
        COALESCE(
            r.arrival_delay_seconds,
            r.departure_delay_seconds
        ) AS reported_delay_seconds
    FROM ROUTEPULSE.RAW.STOP_TIME_UPDATES AS r
    INNER JOIN ROUTEPULSE.RAW.GTFS_STOPS AS s
        ON r.stop_id = s.stop_id
    LEFT JOIN ROUTEPULSE.RAW.GTFS_STOPS AS parent
        ON s.parent_station = parent.stop_id
)
SELECT
    station_id,
    station_name,
    station_lat,
    station_lon,
    COUNT(*) AS stop_observations,
    COUNT(DISTINCT trip_id) AS distinct_trips,
    COUNT(DISTINCT route_id) AS distinct_routes,

    COUNT_IF(
        stop_schedule_relationship = 'SKIPPED'
    ) AS skipped_stop_observations,

    ROUND(
        100.0 * COUNT_IF(
            stop_schedule_relationship = 'SKIPPED'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS skipped_stop_percentage,

    COUNT_IF(
        reported_delay_seconds IS NOT NULL
    ) AS delay_observations,

    ROUND(
        100.0 * COUNT_IF(
            reported_delay_seconds IS NOT NULL
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,

    ROUND(
        AVG(reported_delay_seconds),
        2
    ) AS average_reported_delay_seconds,

    ROUND(
        MEDIAN(reported_delay_seconds),
        2
    ) AS median_reported_delay_seconds,

    ROUND(
        PERCENTILE_CONT(0.90)
        WITHIN GROUP (ORDER BY reported_delay_seconds),
        2
    ) AS p90_reported_delay_seconds,

    COUNT_IF(
        reported_delay_seconds > 300
    ) AS delayed_over_five_minutes_observations,

    ROUND(
        100.0 * COUNT_IF(
            reported_delay_seconds > 300
        ) / NULLIF(
            COUNT_IF(reported_delay_seconds IS NOT NULL),
            0
        ),
        2
    ) AS delayed_over_five_minutes_percentage

FROM named_observations
GROUP BY
    station_id,
    station_name,
    station_lat,
    station_lon;

CREATE OR REPLACE VIEW ROUTE_PERFORMANCE_NAMED AS
SELECT
    rp.*,
    gr.route_short_name,
    gr.route_long_name,
    gr.route_type,
    CASE gr.route_type
        WHEN 0 THEN 'Tram'
        WHEN 1 THEN 'Subway'
        WHEN 2 THEN 'Rail'
        WHEN 3 THEN 'Bus'
        WHEN 4 THEN 'Ferry'
        WHEN 100 THEN 'Railway'
        WHEN 109 THEN 'Suburban rail'
        WHEN 400 THEN 'Urban railway'
        WHEN 700 THEN 'Bus'
        WHEN 900 THEN 'Tram'
        ELSE 'Other'
    END AS transport_mode,
    COALESCE(
        NULLIF(gr.route_short_name, ''),
        NULLIF(gr.route_long_name, ''),
        rp.route_id
    ) AS route_display_name
FROM ROUTEPULSE.ANALYTICS.ROUTE_PERFORMANCE AS rp
LEFT JOIN ROUTEPULSE.RAW.GTFS_ROUTES AS gr
    ON REPLACE(rp.route_id, '-', '_') = gr.route_id;

SELECT
    COUNT(*) AS named_stations,
    SUM(stop_observations) AS represented_stop_observations
FROM ROUTEPULSE.ANALYTICS.STATION_PERFORMANCE;

SELECT
    station_name,
    stop_observations,
    distinct_routes,
    skipped_stop_percentage,
    delay_coverage_percentage,
    average_reported_delay_seconds,
    p90_reported_delay_seconds,
    delayed_over_five_minutes_percentage
FROM ROUTEPULSE.ANALYTICS.STATION_PERFORMANCE
WHERE stop_observations >= 10000
ORDER BY delayed_over_five_minutes_percentage DESC
LIMIT 20;

SELECT
    route_display_name,
    transport_mode,
    stop_observations,
    skipped_stop_percentage,
    average_reported_delay_seconds,
    delayed_over_five_minutes_percentage
FROM ROUTEPULSE.ANALYTICS.ROUTE_PERFORMANCE_NAMED
WHERE stop_observations >= 10000
ORDER BY delayed_over_five_minutes_percentage DESC
LIMIT 20;

SELECT
    SUM(stop_observations) AS stop_observations,
    SUM(delay_observations) AS delay_observations,
    ROUND(
        100.0 * SUM(delay_observations)
        / NULLIF(SUM(stop_observations), 0),
        2
    ) AS overall_delay_coverage_percentage,
    SUM(skipped_stop_observations) AS skipped_stop_observations
FROM ROUTEPULSE.ANALYTICS.STATION_PERFORMANCE;

SELECT
    station_name,
    stop_observations,
    distinct_routes,
    delay_observations,
    delay_coverage_percentage,
    average_reported_delay_seconds,
    p90_reported_delay_seconds,
    delayed_over_five_minutes_percentage
FROM ROUTEPULSE.ANALYTICS.STATION_PERFORMANCE
WHERE stop_observations >= 10000
  AND delay_observations >= 1000
ORDER BY delayed_over_five_minutes_percentage DESC NULLS LAST
LIMIT 20;

SELECT
    station_name,
    stop_observations,
    distinct_routes,
    skipped_stop_observations,
    skipped_stop_percentage
FROM ROUTEPULSE.ANALYTICS.STATION_PERFORMANCE
WHERE stop_observations >= 10000
ORDER BY skipped_stop_percentage DESC NULLS LAST
LIMIT 20;

SELECT
    route_display_name,
    transport_mode,
    stop_observations,
    delay_coverage_percentage,
    average_reported_delay_seconds,
    p90_reported_delay_seconds,
    delayed_over_five_minutes_percentage
FROM ROUTEPULSE.ANALYTICS.ROUTE_PERFORMANCE_NAMED
WHERE stop_observations >= 10000
  AND delay_observations >= 1000
ORDER BY delayed_over_five_minutes_percentage DESC NULLS LAST
LIMIT 20;

CREATE OR REPLACE VIEW ROUTEPULSE.ANALYTICS.SERVICE_PERFORMANCE AS
SELECT
    route_display_name,
    transport_mode,

    SUM(stop_observations) AS stop_observations,

    SUM(skipped_stop_observations) AS skipped_stop_observations,
    ROUND(
        100.0 * SUM(skipped_stop_observations)
        / NULLIF(SUM(stop_observations), 0),
        2
    ) AS skipped_stop_percentage,

    SUM(delay_observations) AS delay_observations,
    ROUND(
        100.0 * SUM(delay_observations)
        / NULLIF(SUM(stop_observations), 0),
        2
    ) AS delay_coverage_percentage,

    ROUND(
        SUM(
            average_reported_delay_seconds
            * delay_observations
        ) / NULLIF(SUM(delay_observations), 0),
        2
    ) AS average_reported_delay_seconds,

    ROUND(
        SUM(
            delayed_over_five_minutes_percentage
            * delay_observations
        ) / NULLIF(SUM(delay_observations), 0),
        2
    ) AS delayed_over_five_minutes_percentage

FROM ROUTEPULSE.ANALYTICS.ROUTE_PERFORMANCE_NAMED
GROUP BY
    route_display_name,
    transport_mode;

SELECT
    route_display_name,
    transport_mode,
    stop_observations,
    delay_observations,
    delay_coverage_percentage,
    average_reported_delay_seconds,
    delayed_over_five_minutes_percentage
FROM ROUTEPULSE.ANALYTICS.SERVICE_PERFORMANCE
WHERE stop_observations >= 10000
  AND delay_observations >= 1000
ORDER BY delayed_over_five_minutes_percentage DESC NULLS LAST
LIMIT 15;
