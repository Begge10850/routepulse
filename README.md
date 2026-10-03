# RoutePulse

RoutePulse is an evaluated mobility-data pipeline for monitoring the
availability, freshness, and quality of public transport information.

**Live dashboard:**
[routepulse-qdwrvckapptwi9xp74ueuuo.streamlit.app](https://routepulse-qdwrvckapptwi9xp74ueuuo.streamlit.app/)

The project will collect official VBB GTFS and GTFS-Realtime data, preserve
raw snapshots, structure selected records, load validated datasets into
Snowflake, and calculate documented data-quality and operational metrics.

## Current status

The evaluated analysis window and dashboard are complete:

- 777 audited GTFS-Realtime snapshots collected over approximately 39.5 hours;
- 94,839,920 stop-time-update observations converted to typed Parquet;
- immutable source snapshots and collection evidence preserved in Amazon S3;
- raw, analytical and presentation models built in Snowflake;
- an interactive Streamlit operations dashboard validated against additive SQL
  numerators and denominators;
- a restricted Snowflake service identity prepared for public Streamlit
  Community Cloud deployment;
- a public Streamlit Community Cloud deployment verified against the read-only
  Snowflake service identity.

## Implemented pipeline

1. Collect official VBB static and realtime transport data.
2. Audit and preserve immutable raw snapshots and collection metadata.
3. Decode selected GTFS-Realtime records and profile field availability.
4. Convert structured records to compressed Apache Parquet.
5. Upload the audited analysis window to Amazon S3.
6. Load and model raw, static and analytical data in Snowflake.
7. Validate uniqueness, reconciliation, missing-data handling and dashboard
   metric correctness.
8. Present station, line, time, network and data-quality findings in Streamlit.

## Important limitation

Realtime-feed availability does not automatically represent transport
operations. Missing realtime records must not be interpreted as proof that a
scheduled journey was cancelled or did not operate.

## Repository guide

- `src/routepulse/` — collection and storage package;
- `scripts/` — auditable collection, profiling, conversion and upload steps;
- `tests/` — unit tests for the Python pipeline;
- `evidence/` — retained collection, profiling, conversion and cloud evidence;
- `sql/` — ordered Snowflake loading, modelling and validation scripts;
- `app/streamlit_app.py` — Streamlit dashboard;
- `docs/` — data-source, warehouse, dashboard-validation and deployment notes.

The full implementation journey, analytical decisions, validation evidence and
remaining work are preserved in
[`docs/project_journey.md`](docs/project_journey.md).
The preservation boundary is documented in
[`docs/artifact_inventory.md`](docs/artifact_inventory.md).
Reproducible setup, collection, testing, conversion, upload and deployment
commands are retained in
[`docs/reproduction_commands.md`](docs/reproduction_commands.md).

## Development setup

RoutePulse targets Python 3.12. Install the pipeline package with development
dependencies using:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

The public dashboard has separate runtime dependencies in `requirements.txt`.
Deployment instructions are in `docs/community_cloud_deployment.md`.
