"""Static contract checks for the RoutePulse Streamlit application."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "app" / "streamlit_app.py"
MODEL_PATH = ROOT / "sql" / "12_dashboard_ui_models.sql"
TIMING_VALIDATION_PATH = ROOT / "sql" / "15_validate_timing_categories.sql"
TIMING_METHOD_PATH = ROOT / "docs" / "timing_methodology.md"


def require(source: str, text: str):
    assert text in source, f"Required source contract missing: {text}"


def forbid(source: str, text: str):
    assert text not in source, f"Forbidden stale UI or wording remains: {text}"


def main():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    models = MODEL_PATH.read_text(encoding="utf-8")
    timing_validation = TIMING_VALIDATION_PATH.read_text(encoding="utf-8")
    timing_method = TIMING_METHOD_PATH.read_text(encoding="utf-8")
    ast.parse(source)

    for required in (
        '"Transport mode"',
        '"Network map", "Stations", "Lines", "When", "Data quality"',
        "DASHBOARD_SCOPE_METRICS",
        "DASHBOARD_STATION_METRICS",
        "DASHBOARD_LINE_METRICS",
        "DASHBOARD_HOUR_METRICS",
        "DASHBOARD_REGION_METRICS",
        "MIN_RANK_DELAY_EVENTS = 100",
        "LOW_SAMPLE_UPPER = 300",
        "LOW_COVERAGE_PERCENTAGE = 60.0",
        "MIN_HEADLINE_HOUR_DELAY_EVENTS = 100",
        "PRESENTATION_CACHE_TTL_SECONDS = 3600",
        'initial_sidebar_state="expanded"',
        "with st.sidebar:",
        'AREA_OPTIONS = ["All regions", "Berlin", "Brandenburg"]',
        '"Observed stop area"',
        "def load_scope_metrics()",
        "def load_headline_line_metrics()",
        "def load_headline_hour_metrics()",
        "def load_station_metrics()",
        "def prepare_station_ranking(scope_mode: str, scope_region: str)",
        "def load_category_metrics()",
        "def load_region_metrics()",
        "def load_network_paths()",
        "def load_state_boundary_features()",
        "def prepare_network_map_data(",
        "scope_region: str,",
        "map_data, line_count, coordinate_count = prepare_network_map_data(",
        "9 in 10 timing reports were no more delayed than this",
        "Unmatched/unknown",
        "Outside Berlin-Brandenburg",
        "Scheduled GTFS paths for passenger-facing services observed during",
        "reported as more than 5 minutes behind the timetable.** Missing timing values",
        "How did the timed visits compare with the schedule?",
        'class="rp-timing-stack"',
        'class="rp-timing-grid"',
        "timed visits</div>",
        "How RoutePulse defines early, near schedule and late",
        "Reported >1 min early",
        "Within 1 min of schedule",
        "1–5 min late",
        ">5 min late",
        "Timing-data availability",
        "Which stations were late most often?",
        "Stations with the most frequent serious delays",
        "Where are these stations?",
        "Every station in this ranking rests on only 100–299 visits",
        "hover a circle for its station name and ",
        "timing breakdown. Larger circles",
        "Which lines were reported late most often?",
        "Which transport modes were late most often?",
        "above to compare its individual lines.",
        "Highest serious-delay share",
        "Largest number of serious delays",
        "See where a line runs",
        "The strongest well-supported serious-delay share",
        "How complete is our timing data?",
        "Very complete (>90%)",
        "Mostly complete (75–90%)",
        "Partial (<75%)",
        "The grey Unmatched/unknown row",
        "alt.vconcat(",
        "day_band,",
        'hourly["ELIGIBLE_MEASURE"]',
        'day_summary["DAY_LABEL"]',
        '"%A %d %b"',
        "Observation hour and day (Berlin time)",
        "MAP_ROUTE_PATHS_RENDER",
        "STATE_BOUNDARIES",
        'selected_view == "Network map"',
        'selected_view == "Stations"',
        "height=700",
    ):
        require(source, required)

    assert source.index('"Observed stop area"') < source.index('"Transport mode"'), (
        "Observed stop area must appear before Transport mode in the sidebar"
    )
    require(source, ".block-container { padding-top: 5rem !important; }")

    for stale in (
        "Map mode",
        "Map operator",
        "Passenger-facing services",
        "highest-risk",
        "feed start-up",
        "were shorter than this",
        "28,304 events outside",
        "Line-by-hour heatmap",
        "def render_heatmap",
        'resolve_scale(y="independent")',
        'with st.expander("Technical definitions"',
        "Rate versus observed volume",
        "Highlight a line",
        "How far can you trust this?",
        "Station delay-rate ranking",
        "Location of the ranked stations",
        "def render_line_scatter",
        'MODE_LABEL"] = mode_data.apply',
    ):
        forbid(source, stale)

    assert source.count("selected_view ==") == 5
    assert "GROUP BY scope_region, observation_hour_berlin" in models
    assert "scope_metric_events = source_events" in models
    assert "COUNT(*) = 1755847" in models
    assert models.count("AS early_events") == 11
    assert models.count("AS near_schedule_events") == 11
    assert models.count("AS minor_delay_events") == 11
    assert models.count("AS timing_unavailable_events") == 11
    for reconciliation_contract in (
        "timing_category_mismatches",
        "availability_mismatches",
        "all_rows_reconcile",
        "serious_delay_count_matches",
    ):
        require(models + timing_validation, reconciliation_contract)
    for methodology_contract in (
        "reported_delay_seconds < -60",
        "reported_delay_seconds BETWEEN -60 AND 60",
        "reported_delay_seconds > 60 AND reported_delay_seconds <= 300",
        "reported_delay_seconds > 300",
        "Predictions, not confirmed outcomes",
        "Interview-ready explanation",
    ):
        require(timing_method, methodology_contract)

    for stale_wording in (
        "delay figure",
        "Delay-data availability",
        "Highest observed line rate",
        "Highest observed line volume",
    ):
        forbid(source, stale_wording)

    referenced_dashboard_tables = set(
        re.findall(r"ROUTEPULSE\.ANALYTICS\.(DASHBOARD_[A-Z_]+)", source)
    )
    created_dashboard_tables = set(
        re.findall(
            r"CREATE OR REPLACE TRANSIENT TABLE\s+(DASHBOARD_[A-Z_]+)",
            models,
        )
    )
    assert referenced_dashboard_tables == created_dashboard_tables, (
        "The Streamlit app and presentation-model SQL disagree: "
        f"referenced={sorted(referenced_dashboard_tables)}, "
        f"created={sorted(created_dashboard_tables)}"
    )
    print("RoutePulse v4 static contract checks passed.")


if __name__ == "__main__":
    main()
