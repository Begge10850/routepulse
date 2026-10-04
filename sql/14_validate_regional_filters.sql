USE ROLE ACCOUNTADMIN;
USE WAREHOUSE ROUTEPULSE_WH;
USE DATABASE ROUTEPULSE;
USE SCHEMA ANALYTICS;

-- Confirm the regional dashboard totals created by 12_dashboard_ui_models.sql.
SELECT
    scope_region,
    unique_stop_events,
    delay_reported_events,
    late_events
FROM DASHBOARD_SCOPE_METRICS
WHERE scope_mode = 'All modes'
ORDER BY
    CASE scope_region
        WHEN 'All regions' THEN 1
        WHEN 'Berlin' THEN 2
        WHEN 'Brandenburg' THEN 3
        ELSE 4
    END;

-- Confirm every presentation model contains the three dashboard scopes.
SELECT
    'DASHBOARD_SCOPE_METRICS' AS model_name,
    COUNT(*) AS row_count,
    COUNT_IF(scope_region = 'All regions') AS all_region_rows,
    COUNT_IF(scope_region = 'Berlin') AS berlin_rows,
    COUNT_IF(scope_region = 'Brandenburg') AS brandenburg_rows
FROM DASHBOARD_SCOPE_METRICS

UNION ALL

SELECT
    'DASHBOARD_STATION_METRICS',
    COUNT(*),
    COUNT_IF(scope_region = 'All regions'),
    COUNT_IF(scope_region = 'Berlin'),
    COUNT_IF(scope_region = 'Brandenburg')
FROM DASHBOARD_STATION_METRICS

UNION ALL

SELECT
    'DASHBOARD_LINE_METRICS',
    COUNT(*),
    COUNT_IF(scope_region = 'All regions'),
    COUNT_IF(scope_region = 'Berlin'),
    COUNT_IF(scope_region = 'Brandenburg')
FROM DASHBOARD_LINE_METRICS

UNION ALL

SELECT
    'DASHBOARD_HOUR_METRICS',
    COUNT(*),
    COUNT_IF(scope_region = 'All regions'),
    COUNT_IF(scope_region = 'Berlin'),
    COUNT_IF(scope_region = 'Brandenburg')
FROM DASHBOARD_HOUR_METRICS

UNION ALL

SELECT
    'DASHBOARD_CATEGORY_METRICS',
    COUNT(*),
    COUNT_IF(scope_region = 'All regions'),
    COUNT_IF(scope_region = 'Berlin'),
    COUNT_IF(scope_region = 'Brandenburg')
FROM DASHBOARD_CATEGORY_METRICS
ORDER BY model_name;
