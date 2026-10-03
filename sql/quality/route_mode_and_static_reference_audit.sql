USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA RAW;

SELECT
    route_type,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT route_id) AS route_ids,
    LISTAGG(
        DISTINCT route_display_name,
        ', '
    ) WITHIN GROUP (
        ORDER BY route_display_name
    ) AS example_services
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_ENRICHED
WHERE transport_mode = 'Other'
GROUP BY route_type
ORDER BY unique_stop_events DESC;

SELECT
    route_type,
    transport_mode,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT route_id) AS route_ids,
    LISTAGG(
        DISTINCT route_display_name,
        ', '
    ) WITHIN GROUP (
        ORDER BY route_display_name
    ) AS example_services
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_ENRICHED
GROUP BY route_type, transport_mode
ORDER BY route_type;

SELECT
    route_type,
    transport_mode,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT route_id) AS route_ids,
    LISTAGG(
        DISTINCT route_display_name,
        ', '
    ) WITHIN GROUP (
        ORDER BY route_display_name
    ) AS example_services
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_ENRICHED
GROUP BY route_type, transport_mode
ORDER BY route_type;

SELECT
    route_type,
    COUNT(*) AS unique_stop_events,
    COUNT(DISTINCT route_id) AS route_ids,
    LISTAGG(
        DISTINCT route_display_name,
        ', '
    ) WITHIN GROUP (
        ORDER BY route_display_name
    ) AS example_services
FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_ENRICHED
WHERE route_type IN (109, 400, 401, 402)
GROUP BY route_type
ORDER BY route_type;

WITH route_summary AS (
    SELECT
        gr.route_type,
        COALESCE(
            NULLIF(gr.route_short_name, ''),
            NULLIF(gr.route_long_name, ''),
            e.route_id
        ) AS service_name,
        COUNT(*) AS unique_stop_events
    FROM ROUTEPULSE.ANALYTICS.UNIQUE_STOP_EVENTS AS e
    LEFT JOIN ROUTEPULSE.RAW.GTFS_ROUTES AS gr
        ON REPLACE(e.route_id, '-', '_') = gr.route_id
    GROUP BY
        gr.route_type,
        service_name
),

ranked_routes AS (
    SELECT
        route_type,
        service_name,
        unique_stop_events,
        ROW_NUMBER() OVER (
            PARTITION BY route_type
            ORDER BY unique_stop_events DESC, service_name
        ) AS service_rank
    FROM route_summary
)

SELECT
    route_type,
    COUNT(*) AS route_count,
    SUM(unique_stop_events) AS unique_stop_events,
    LISTAGG(
        IFF(service_rank <= 20, service_name, NULL),
        ', '
    ) WITHIN GROUP (
        ORDER BY service_rank
    ) AS example_services
FROM ranked_routes
GROUP BY route_type
ORDER BY route_type;

WITH expected_potsdam_trams AS (
    SELECT column1 AS tram_line
    FROM VALUES
        ('91'),
        ('92'),
        ('93'),
        ('94'),
        ('96'),
        ('98'),
        ('99')
),

observed_trams AS (
    SELECT
        route_display_name AS tram_line,
        COUNT(*) AS unique_stop_events,
        COUNT(DISTINCT trip_id) AS observed_trips
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_ENRICHED
    WHERE route_type = 900
      AND route_display_name IN (
          '91', '92', '93', '94', '96', '98', '99'
      )
    GROUP BY route_display_name
)

SELECT
    expected.tram_line,
    IFF(
        observed.tram_line IS NOT NULL,
        'Observed',
        'Not observed'
    ) AS collection_status,
    COALESCE(observed.unique_stop_events, 0) AS unique_stop_events,
    COALESCE(observed.observed_trips, 0) AS observed_trips
FROM expected_potsdam_trams AS expected
LEFT JOIN observed_trams AS observed
    ON expected.tram_line = observed.tram_line
ORDER BY TRY_TO_NUMBER(expected.tram_line);

-- Check 1: Does tram 98 exist in the static GTFS reference?
SELECT
    route_id,
    route_short_name,
    route_long_name,
    route_type
FROM ROUTEPULSE.RAW.GTFS_ROUTES
WHERE route_short_name = '98'
  AND route_type = 900;

-- Check 2: Did line 98 appear in the raw realtime records?
SELECT
    COUNT(*) AS raw_stop_update_rows,
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            updates.trip_id,
            updates.start_date
        )
    ) AS observed_trip_instances
FROM ROUTEPULSE.RAW.STOP_TIME_UPDATES AS updates
INNER JOIN ROUTEPULSE.RAW.GTFS_ROUTES AS routes
    ON REPLACE(updates.route_id, '-', '_') = routes.route_id
WHERE routes.route_short_name = '98'
  AND routes.route_type = 900;

-- Check 3: Did line 98 reach the deduplicated event table?
SELECT
    COUNT(*) AS unique_stop_events,
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            events.trip_id,
            events.start_date
        )
    ) AS observed_trip_instances
FROM ROUTEPULSE.ANALYTICS.UNIQUE_STOP_EVENTS AS events
INNER JOIN ROUTEPULSE.RAW.GTFS_ROUTES AS routes
    ON REPLACE(events.route_id, '-', '_') = routes.route_id
WHERE routes.route_short_name = '98'
  AND routes.route_type = 900;

SELECT
    table_name,
    row_count
FROM ROUTEPULSE.INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'RAW'
  AND table_name IN (
      'GTFS_ROUTES',
      'GTFS_STOPS',
      'GTFS_TRIPS',
      'GTFS_STOP_TIMES',
      'GTFS_SHAPES',
      'GTFS_AGENCY',
      'GTFS_AGENCIES'
  )
ORDER BY table_name;

SHOW STAGES IN SCHEMA ROUTEPULSE.RAW;
