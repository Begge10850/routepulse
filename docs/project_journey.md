# RoutePulse project journey and decision record

## Why this record exists

This document preserves the reasoning, implementation changes, validation
evidence and remaining work behind RoutePulse. It is intended to support the
GitHub repository, a future portfolio website and interview preparation.

It distinguishes what has been implemented and tested from what still needs
production verification. Numerical claims below come from retained project
evidence or validated Snowflake models; they are not estimates added for
presentation.

## Problem and business question

RoutePulse investigates where and when the observed VBB public-transport feed
reported serious delays, which services deserved operational review and how
confident a reader should be in those findings.

The dashboard is descriptive. It does not claim that a high reported delay
rate proves a cause, measures passenger impact or represents normal weekday
performance.

## Implemented architecture

`VBB GTFS-Realtime + GTFS Static → Python/PyArrow → Amazon S3 → Snowflake → Streamlit`

The pipeline separates four concerns:

1. **Collection and evidence** — retain immutable source snapshots, request
   metadata and checksums.
2. **Typed storage** — decode Protocol Buffers and convert selected records to
   compressed Parquet.
3. **SQL modelling** — establish analytical grain, join static reference data,
   enrich geography, define passenger-facing lines and materialize additive
   dashboard aggregates.
4. **Presentation** — explain the results and their limitations through an
   interactive Streamlit dashboard.

## Data collection and retained evidence

The evaluated collection window contains:

- 777 audited GTFS-Realtime snapshots;
- approximately 39.5 hours, from Friday afternoon through Sunday morning;
- 4,518,265 TripUpdate observations;
- 94,839,920 StopTimeUpdate observations;
- zero snapshot decode failures in the audited window;
- no VehiclePosition or Alert entities observed in this specific sample.

Raw snapshots remain immutable. The repository retains machine-readable
collection inventories, source checksums, profiling results, Parquet conversion
summaries and S3 upload evidence under `evidence/`.

## Analytical grain and metric rules

The realtime feed repeats active trips roughly every three minutes. Counting
every raw row as a separate transport event would severely inflate the
analysis. SQL stage 09 therefore retains the latest observation for each
trip/date/stop event.

The validated analytical model contains 1,755,847 observed stop visits and zero
duplicate event keys after validation.

Important metric rules:

- a **stop visit** is one retained observation for a vehicle trip at a stop;
- **late** means a reported delay above 300 seconds;
- missing delay figures remain null and are never converted to zero;
- rates use only stop visits containing a delay figure;
- dashboard aggregates retain additive numerators and denominators rather than
  averaging percentages across groups;
- the first and final collection hours are partial and are labelled as such;
- low-sample and low-coverage results receive visible caveats.

## Snowflake SQL stages

The final repository will contain the complete ordered SQL pipeline. Stages
Stages 01–08 have been exported and reviewed. The recovered stage 06 defines
the static stops and routes schemas and profiles their contents, but does not
include the commands that populated those tables; that loading step remains a
reproducibility gap. The later map models also depend on static trips,
stop-times and geographic reference objects whose creation is not yet present
in the recovered numbered worksheets.

The retained stages are:

- **01 — environment setup:** creates the XSMALL auto-suspending warehouse,
  database, RAW and ANALYTICS schemas, and Parquet file format;
- **02 — storage integration:** defines the read-only trust boundary through
  which Snowflake accesses only the processed realtime S3 prefix;
- **03 — external stage:** binds the S3 location, integration and Parquet
  format, then lists visible source files as an access check;
- **04 — raw-table loading:** creates typed transient tables for feed snapshots,
  trip updates and stop-time updates, loads them with fail-fast COPY commands,
  and returns row counts for reconciliation;
- **05 — initial analytical models:** builds route, hourly and collection-level
  summaries directly from repeated raw feed observations. These models retain
  the original snapshot-observation grain and provide raw collection KPIs;
- **06 — GTFS reference schemas:** defines the CSV format and transient static
  stops/routes tables, then checks row counts, identifier uniqueness, missing
  names and representative records. The recovered worksheet does not show how
  the CSV rows were loaded into these tables;
- **07 — GTFS join validation:** confirms that the reference tables contain
  rows, measures exact stop-ID and normalized route-ID match coverage, and
  previews readable station and route names. It validates the loaded state but
  does not perform the missing reference-data load;
- **08 — named station analytics:** joins raw repeated stop observations to
  parent-station names and coordinates, enriches the route-level stage-05
  summary with static names and modes, and builds an aggregated service view.
  It remains a historical snapshot-observation layer; stage 09 establishes the
  deduplicated grain used by the final dashboard;
- **09 — unique stop events:** deduplicates repeated realtime observations and
  joins passenger-facing static GTFS fields;
- **10 — geographic enrichment:** assigns observed stop regions and constructs
  geographic route/map references while preserving unmatched events;
- **11 — line-focus models:** defines passenger-facing lines and representative
  scheduled patterns for ranking and map highlighting;
- **12 — dashboard presentation models:** materializes scope, line, hour,
  station, regional and service-category aggregates;
- **13 — Community Cloud access:** creates a restricted service user, read-only
  role and separate XSMALL warehouse for the public application.

Stage 13 is operational rather than analytical. It must not be interpreted as
part of the metric logic.

### Retained SQL investigations

Two unnumbered Snowflake worksheets were reviewed separately from the build
pipeline. The original `analysis.sql` is preserved as a read-only quality
script covering route-type classification, Potsdam tram visibility, static
GTFS table inventory and stage inspection. The diagnostic portion of
`geographical.sql` is also preserved as a read-only quality script; it records
the unmatched-stop investigation that led to normalized regional recovery.

The earlier write statement embedded in `geographical.sql` is superseded by
stage 10 and is not runnable from the quality script. It would otherwise
misclassify unmatched stops as outside Berlin-Brandenburg and overwrite the
corrected model.

## Dashboard evolution

The dashboard was iterated after visual review and plain-language feedback.
The major corrections were:

### Navigation and first screen

- retained one prominent transport-mode control;
- simplified navigation to Network map, Stations, Lines, When and Data quality;
- reduced duplicated KPI explanations and tightened first-screen spacing;
- defined “late” once beneath the KPI cards;
- replaced technical “unique stop event” wording with “observed stop visit.”

### Network map

- restored a general network map showing representative scheduled paths for
  the selected transport mode;
- clearly stated that paths are planned GTFS routes, not live vehicle traces;
- increased the map height to improve readability;
- used a dense-network colour strategy without implying delay severity.

### Stations

- renamed the section to ask which stations were late most often;
- explained rates as visits out of every 100 with a delay figure;
- retained a small Berlin/Brandenburg selector;
- made limited-sample results visually paler and labelled them as early signals;
- directly labelled the selected mode average;
- aligned ranked stations with their map locations and improved takeaways.

### Lines

- distinguished the all-modes comparison from individual line rankings;
- used termini in line labels and moved operator detail to tooltips;
- added sample and coverage caveats to ranking labels and headlines;
- changed “Highlight a line” to “See where a line runs”;
- separated “most often late” from “most late stop visits” so rate and volume
  are not confused.

### When

- replaced a dual-axis chart with two vertically stacked panels sharing time;
- displayed the selected punctuality measure above hourly observation volume;
- made the two calendar days explicit on the time axis;
- used hollow grey points for hours with fewer than 100 delay reports;
- retained markers for partial first and last hours;
- removed the line-by-hour heatmap and its query.

### Data quality

- reframed the section as “How complete is our delay data?”;
- explained that shorter bars mean less evidence about actual punctuality;
- grouped modes into very complete, mostly complete and partial coverage;
- clarified that the mode chart always compares all modes while the regional
  table follows the selected mode;
- explained and visually separated the Unmatched/unknown regional row.

## Public Streamlit migration

The Snowflake-hosted application requires viewers to have Snowflake access.
The portfolio version therefore targets Streamlit Community Cloud, where
visitors can open a normal public URL without a Snowflake account.

The original Snowflake-hosted deployment roles are preserved separately in
`sql/setup/snowflake_streamlit_access.sql`. That worksheet grants native app
creation rights to an app-owner role and discovery access to a viewer role;
its personal deployer username is replaced by a repository-safe placeholder.
It is retained for architectural history and native redeployment, not used by
the Community Cloud runtime.

The native app's `snowflake.yml` manifest and Snowflake-specific
`pyproject.toml` are retained under
`deployment/snowflake_native_snapshot/`. They are kept as deployment evidence
rather than active root configuration because the public build uses a normal
Community Cloud `requirements.txt`, while the root `pyproject.toml` describes
the Python collection pipeline. The comment-only native Streamlit config was
not allowed to replace the repository's actual dark-theme configuration.

The current `app/streamlit_app.py` supports both environments:

- inside Snowflake it uses the native Streamlit Snowflake session;
- outside Snowflake it uses key-pair authentication supplied through protected
  Streamlit secrets.

The public connection was tested locally with:

- user `ROUTEPULSE_PUBLIC_SERVICE`;
- role `ROUTEPULSE_PUBLIC_READER`;
- warehouse `ROUTEPULSE_PUBLIC_WH`;
- successful read access to the dashboard KPI model.

The private key remains outside Git. Repository files contain placeholders
only. The service role has read access to the required presentation data and no
INSERT, UPDATE, DELETE or OWNERSHIP grants.

## Verification completed

- The complete Python pipeline suite passed: 37 unit tests covering collection,
  configuration, storage, auditing, profiling, Parquet conversion and S3 upload.
- Python syntax checks passed for the Streamlit application.
- The RoutePulse dashboard static-contract validator passed.
- Community Cloud packaging and credential-exclusion checks passed.
- The RSA private/public key pair was cryptographically validated.
- The restricted service identity successfully authenticated to Snowflake.
- A read-only query against `ROUTEPULSE.ANALYTICS.KPI_SUMMARY` succeeded.
- Local browser smoke tests rendered the Network map, Data quality and Bus Lines
  views without connection or query errors.
- A deprecated Streamlit width parameter discovered during runtime testing was
  replaced and rechecked.

These checks demonstrate implementation and selected integration behaviour.
They do not yet constitute production validation of the publicly deployed URL.

## Limitations and responsible interpretation

- The sample spans only 39.5 Friday/weekend hours and does not represent a
  normal weekday commute.
- Delay figures are predictions reported by the feed, not independently
  measured arrivals.
- Missing delay figures reduce confidence and are excluded from rates.
- Observations cluster within trips, hours and disruptions; rankings are
  descriptive rather than causal statistical estimates.
- High observed delay does not establish root cause, passenger impact or
  revenue impact.
- Representative map paths show scheduled service geography, not live vehicle
  movement.
- Streamlit query results are cached for up to ten minutes.

## Remaining work

1. Recover or reconstruct and verify the omitted static GTFS loading commands
   used to populate the stage-06 stops and routes tables.
2. Recover the definitions/loading steps for `RAW.GTFS_TRIPS`,
   `RAW.GTFS_STOP_TIMES`, `ANALYTICS.GTFS_STOPS_GEOGRAPHIC` and
   `ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG`, which later map models require.
3. Run a complete clean-order SQL dependency review.
4. Commit and push the integrated SQL, Streamlit and documentation changes.
5. Configure protected secrets in Streamlit Community Cloud.
6. Deploy and verify the public URL in an incognito browser.
7. Confirm all modes and views against the deployed Snowflake connection.
8. Add warehouse cost protection and monitor public usage.
9. Consider a separate future pipeline for periodically refreshing the
   underlying VBB data; this is not part of the current static analysis-window
   release.

## Interview-ready summary

RoutePulse is not simply a dashboard. It is an evidence-backed mobility-data
pipeline that preserves raw realtime observations, converts them into typed
columnar data, models a defensible event grain in Snowflake and exposes the
results with visible data-quality caveats. The central analytical decision was
to deduplicate repeated feed snapshots into one retained stop visit before
calculating delay rates. The central communication decision was to show both
operational findings and the completeness limitations that determine how much
those findings can be trusted.
