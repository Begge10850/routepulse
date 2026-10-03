"""Static contract checks for the RoutePulse Streamlit application."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "app" / "streamlit_app.py"
MODEL_PATH = ROOT / "sql" / "12_dashboard_ui_models.sql"


def require(source: str, text: str):
    assert text in source, f"Required source contract missing: {text}"


def forbid(source: str, text: str):
    assert text not in source, f"Forbidden stale UI or wording remains: {text}"


def main():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    models = MODEL_PATH.read_text(encoding="utf-8")
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
        "def load_scope_metrics()",
        "def load_headline_line_metrics()",
        "def load_headline_hour_metrics()",
        "def load_station_metrics()",
        "def prepare_station_ranking(scope_mode: str, station_region: str)",
        "def load_network_paths()",
        "def load_state_boundary_features()",
        "def prepare_network_map_data(mode: str)",
        "map_data, line_count, coordinate_count = prepare_network_map_data(",
        "at or below this level",
        "Unmatched/unknown",
        "Outside Berlin-Brandenburg",
        "Scheduled GTFS paths for passenger-facing services observed during",
        "as more than 5 minutes behind the timetable.** Missing delay figures",
        "Which stations were late most often?",
        "Stations with the most frequent serious delays",
        "Where are these stations?",
        "Every station in this ranking rests on only 100–299 visits",
        "Numbers match the ranking; the top three station names are shown.",
        "Which lines were reported late most often?",
        "Which transport modes were late most often?",
        "above to compare its individual lines.",
        "Most often late",
        "Most late stop visits",
        "See where a line runs",
        "The strongest well-supported high-rate signal",
        "How complete is our delay data?",
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
        "selected_view == \"Stations\"",
        "height=700",
    ):
        require(source, required)

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
        "MODE_LABEL\"] = mode_data.apply",
    ):
        forbid(source, stale)

    assert source.count("selected_view ==") == 6
    assert "GROUP BY observation_hour_berlin" in models
    assert "scope_metric_events = source_events" in models
    assert "COUNT(*) = 1755847" in models

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
