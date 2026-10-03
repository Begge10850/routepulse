USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- One row per observed trip/date/stop event.
-- The source feed repeats active trips about every three minutes. This table
-- retains the latest update observed for each stop event in the collection
-- window. It does not claim to represent every scheduled service.
CREATE OR REPLACE TRANSIENT TABLE UNIQUE_STOP_EVENTS AS
SELECT
    s.trip_id,
    s.start_date,
    s.stop_sequence,
    s.stop_id,
    s.route_id,
    s.direction_id,
    f.request_started_at AS observed_at_utc,
    s.arrival_delay_seconds,
    s.departure_delay_seconds,
    COALESCE(
        s.arrival_delay_seconds,
        s.departure_delay_seconds
    ) AS reported_delay_seconds,
    s.stop_schedule_relationship
FROM RAW.STOP_TIME_UPDATES AS s
JOIN RAW.FEED_SNAPSHOTS AS f
    ON s.snapshot_id = f.snapshot_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY
        s.trip_id,
        s.start_date,
        s.stop_sequence,
        s.stop_id
    ORDER BY
        f.request_started_at DESC,
        s.snapshot_id DESC
) = 1;

-- Add passenger-facing stop, service and transport-mode fields. ROUTE_ID in
-- realtime uses hyphens where the static GTFS reference uses underscores.
CREATE OR REPLACE VIEW STOP_EVENTS_ENRICHED AS
SELECT
    e.*,
    gs.stop_name AS station_name,
    gs.stop_lat AS station_lat,
    gs.stop_lon AS station_lon,
    gr.route_short_name,
    gr.route_long_name,
    gr.route_type,
    -- Map only route-type codes observed in this VBB collection. Codes 100
    -- and 106 both contain regional passenger services in the actual data;
    -- the more specific German service category is derived below.
    CASE gr.route_type
        WHEN 3 THEN 'Bus'
        WHEN 100 THEN 'Regional rail'
        WHEN 106 THEN 'Regional rail'
        WHEN 109 THEN 'S-Bahn'
        WHEN 400 THEN 'U-Bahn'
        WHEN 700 THEN 'Bus'
        WHEN 900 THEN 'Tram'
        ELSE 'Needs review'
    END AS transport_mode,
    CASE
        WHEN gr.route_type IN (100, 106)
             AND UPPER(COALESCE(gr.route_short_name, '')) LIKE 'RB%'
            THEN 'Regionalbahn (RB)'
        WHEN gr.route_type IN (100, 106)
             AND UPPER(COALESCE(gr.route_short_name, '')) LIKE 'RE%'
            THEN 'Regional-Express (RE)'
        WHEN gr.route_type IN (100, 106)
             AND UPPER(COALESCE(gr.route_short_name, '')) = 'FEX'
            THEN 'Flughafen-Express (FEX)'
        WHEN gr.route_type IN (100, 106)
            THEN 'Other regional rail'
        WHEN gr.route_type = 109 THEN 'S-Bahn'
        WHEN gr.route_type = 400 THEN 'U-Bahn'
        WHEN gr.route_type IN (3, 700)
             AND UPPER(COALESCE(gr.route_short_name, '')) LIKE 'M%'
            THEN 'MetroBus (M)'
        WHEN gr.route_type IN (3, 700)
             AND UPPER(COALESCE(gr.route_short_name, '')) LIKE 'X%'
            THEN 'ExpressBus (X)'
        WHEN gr.route_type IN (3, 700)
             AND UPPER(COALESCE(gr.route_short_name, '')) LIKE 'N%'
            THEN 'NightBus (N)'
        WHEN gr.route_type IN (3, 700) THEN 'Numbered bus route'
        WHEN gr.route_type = 900 THEN 'Tram'
        ELSE 'Needs review'
    END AS german_service_category,
    COALESCE(
        NULLIF(gr.route_short_name, ''),
        NULLIF(gr.route_long_name, ''),
        e.route_id
    ) AS route_display_name,
    CONVERT_TIMEZONE(
        'UTC',
        'Europe/Berlin',
        e.observed_at_utc::TIMESTAMP_NTZ
    ) AS observed_at_berlin
FROM UNIQUE_STOP_EVENTS AS e
LEFT JOIN RAW.GTFS_STOPS AS gs
    ON e.stop_id = gs.stop_id
LEFT JOIN RAW.GTFS_ROUTES AS gr
    ON REPLACE(e.route_id, '-', '_') = gr.route_id;

-- Event-level station metrics. "On time" is defined as no more than two
-- minutes early and no more than five minutes late. Delay rates remain
-- conditional on events with an explicit delay value.
CREATE OR REPLACE VIEW STATION_PERFORMANCE_EVENTS AS
SELECT
    station_name,
    transport_mode,
    COUNT(*) AS stop_events,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    COUNT_IF(reported_delay_seconds < -120) AS early_events,
    COUNT_IF(reported_delay_seconds BETWEEN -120 AND 300) AS on_time_events,
    COUNT_IF(reported_delay_seconds > 300) AS late_over_five_minutes_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds < -120)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS early_percentage,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds BETWEEN -120 AND 300)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS on_time_percentage,
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
FROM STOP_EVENTS_ENRICHED
WHERE station_name IS NOT NULL
GROUP BY station_name, transport_mode;

CREATE OR REPLACE VIEW SERVICE_PERFORMANCE_EVENTS AS
SELECT
    route_display_name,
    route_long_name,
    transport_mode,
    COUNT(*) AS stop_events,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    COUNT_IF(reported_delay_seconds < -120) AS early_events,
    COUNT_IF(reported_delay_seconds BETWEEN -120 AND 300) AS on_time_events,
    COUNT_IF(reported_delay_seconds > 300) AS late_over_five_minutes_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds < -120)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS early_percentage,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds BETWEEN -120 AND 300)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS on_time_percentage,
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
FROM STOP_EVENTS_ENRICHED
WHERE route_display_name IS NOT NULL
GROUP BY route_display_name, route_long_name, transport_mode;

CREATE OR REPLACE VIEW MODE_PERFORMANCE_EVENTS AS
SELECT
    transport_mode,
    COUNT(*) AS stop_events,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds < -120)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS early_percentage,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds BETWEEN -120 AND 300)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS on_time_percentage,
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
FROM STOP_EVENTS_ENRICHED
GROUP BY transport_mode;

CREATE OR REPLACE VIEW HOURLY_OPERATIONS_EVENTS AS
SELECT
    DATE_TRUNC('hour', observed_at_berlin) AS observation_hour_berlin,
    COUNT(*) AS stop_events,
    COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_events,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    ) AS delay_coverage_percentage,
    ROUND(MEDIAN(reported_delay_seconds) / 60.0, 2)
        AS median_delay_minutes,
    ROUND(
        PERCENTILE_CONT(0.90) WITHIN GROUP (
            ORDER BY reported_delay_seconds
        ) / 60.0,
        2
    ) AS p90_delay_minutes,
    ROUND(
        100.0 * COUNT_IF(reported_delay_seconds > 300)
        / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0),
        2
    ) AS late_over_five_minutes_percentage
FROM STOP_EVENTS_ENRICHED
GROUP BY observation_hour_berlin;

-- Validation 1: the event table should be substantially smaller than the raw
-- repeated-snapshot table, and every event key should be unique.
SELECT
    (SELECT COUNT(*) FROM RAW.STOP_TIME_UPDATES) AS raw_snapshot_rows,
    (SELECT COUNT(*) FROM UNIQUE_STOP_EVENTS) AS unique_stop_events,
    ROUND(
        100.0 * unique_stop_events / NULLIF(raw_snapshot_rows, 0),
        2
    ) AS retained_percentage;

SELECT
    (SELECT COUNT(*) FROM UNIQUE_STOP_EVENTS) AS event_rows,
    COUNT(*) AS duplicate_event_keys
FROM (
    SELECT
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    FROM UNIQUE_STOP_EVENTS
    GROUP BY
        trip_id,
        start_date,
        stop_sequence,
        stop_id
    HAVING COUNT(*) > 1
);

-- Validation 2: review mode coverage and event-level reliability results.
SELECT *
FROM MODE_PERFORMANCE_EVENTS
ORDER BY stop_events DESC;

-- Validation 3: confirm the event-level collection window in Berlin time.
SELECT
    MIN(observed_at_berlin) AS first_event_berlin,
    MAX(observed_at_berlin) AS last_event_berlin,
    ROUND(
        DATEDIFF(
            'second',
            MIN(observed_at_berlin),
            MAX(observed_at_berlin)
        ) / 3600.0,
        2
    ) AS observed_window_hours
FROM STOP_EVENTS_ENRICHED;
