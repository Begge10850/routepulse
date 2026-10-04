import html
import json
import logging
import math

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(
    page_title="RoutePulse: Berlin–Brandenburg Operations Snapshot",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)


LOGGER = logging.getLogger(__name__)


def community_cloud_config():
    """Return public-app secrets when running outside Snowflake."""
    try:
        return st.secrets.get("routepulse_snowflake")
    except (FileNotFoundError, KeyError):
        return None


@st.cache_resource
def create_snowflake_session():
    """Connect in either Streamlit Community Cloud or Snowflake preview."""
    public_config = community_cloud_config()
    if not public_config:
        return st.connection("snowflake").session()

    from cryptography.hazmat.primitives import serialization
    from snowflake.snowpark import Session

    private_key = serialization.load_pem_private_key(
        public_config["private_key"].encode("utf-8"),
        password=None,
    )
    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    connection_parameters = {
        "account": public_config["account"],
        "user": public_config["user"],
        "role": public_config["role"],
        "warehouse": public_config["warehouse"],
        "database": public_config["database"],
        "schema": public_config["schema"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key": private_key_der,
        "session_parameters": {"QUERY_TAG": "routepulse_public_streamlit"},
    }
    return Session.builder.configs(connection_parameters).create()


try:
    session = create_snowflake_session()
except Exception:
    LOGGER.exception("RoutePulse could not establish its Snowflake session")
    st.error(
        "RoutePulse cannot connect to its data service right now. "
        "Please try again shortly or contact the app owner."
    )
    st.stop()


@st.cache_data(ttl=600, show_spinner=False)
def run_query(query: str) -> pd.DataFrame:
    return session.sql(query).to_pandas()


def sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def parse_json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


MODE_OPTIONS = [
    "All modes",
    "Bus",
    "Tram",
    "U-Bahn",
    "S-Bahn",
    "Regional rail",
]
AREA_OPTIONS = ["All regions", "Berlin", "Brandenburg"]
MODE_COLORS = {
    "Bus": "#F59E0B",
    "Regional rail": "#EF4444",
    "S-Bahn": "#22C55E",
    "Tram": "#E11D48",
    "U-Bahn": "#3B82F6",
}
RATE_BAR_COLOR = "#F59E0B"
COVERAGE_BAR_COLOR = "#64748B"
TIMING_CATEGORY_COLORS = {
    "Reported >1 min early": "#38BDF8",
    "On/near schedule (within 1 min)": "#22C55E",
    "1–5 min late": "#F59E0B",
    ">5 min late": "#EF4444",
}
NETWORK_LINE_PALETTE = [
    "#60A5FA",
    "#F59E0B",
    "#34D399",
    "#F472B6",
    "#A78BFA",
    "#22D3EE",
    "#FB7185",
    "#FACC15",
    "#4ADE80",
    "#818CF8",
    "#2DD4BF",
    "#FB923C",
    "#C084FC",
    "#38BDF8",
    "#E879F9",
    "#A3E635",
    "#F87171",
    "#14B8A6",
    "#EAB308",
    "#8B5CF6",
]
REGION_ORDER = [
    "Berlin",
    "Brandenburg",
    "Outside Berlin-Brandenburg",
    "Unmatched/unknown",
]
MIN_RANK_DELAY_EVENTS = 100
LOW_SAMPLE_UPPER = 300
LOW_COVERAGE_PERCENTAGE = 60.0
MIN_HEADLINE_HOUR_DELAY_EVENTS = 100
PRESENTATION_CACHE_TTL_SECONDS = 3600
VIEW_OPTIONS = ["Network map", "Stations", "Lines", "When", "Data quality"]


def service_description(row, include_termini: bool = True) -> str:
    """Return a stakeholder-readable mode, line and optional route description."""
    mode = str(row.get("TRANSPORT_MODE", "Service"))
    mode_label = "Regional-rail" if mode == "Regional rail" else mode
    description = f"{mode_label} line {row['ROUTE_DISPLAY_NAME']}"
    termini = row.get("TERMINI")
    if include_termini and pd.notna(termini):
        first_direction = str(termini).split(" / ")[0]
        description += f" ({first_direction})"
    return description


def timing_distribution_frame(event_kpi: pd.Series) -> pd.DataFrame:
    """Create the four mutually exclusive timing categories for one scope."""
    timed_visits = int(event_kpi["DELAY_EVENTS"])
    categories = [
        ("Reported >1 min early", int(event_kpi["EARLY_EVENTS"])),
        ("On/near schedule (within 1 min)", int(event_kpi["NEAR_SCHEDULE_EVENTS"])),
        ("1–5 min late", int(event_kpi["MINOR_DELAY_EVENTS"])),
        (">5 min late", int(event_kpi["LATE_EVENTS"])),
    ]
    return pd.DataFrame(
        [
            {
                "Timing category": label,
                "Stop visits": count,
                "Share of timed visits": (
                    100.0 * count / timed_visits if timed_visits else 0.0
                ),
                "Colour": TIMING_CATEGORY_COLORS[label],
                "Timing population": f"{timed_visits:,} visits with timing information",
            }
            for label, count in categories
        ]
    )


def render_timing_distribution(event_kpi: pd.Series):
    """Render a compact schedule-position profile for the active dashboard scope."""
    timing = timing_distribution_frame(event_kpi)
    category_order = list(TIMING_CATEGORY_COLORS)
    timing["category_order"] = timing["Timing category"].map(
        {label: index for index, label in enumerate(category_order)}
    )
    chart = (
        alt.Chart(timing)
        .mark_bar(cornerRadius=4)
        .encode(
            x=alt.X(
                "Share of timed visits:Q",
                stack="normalize",
                axis=alt.Axis(format="%", title=None, tickCount=5),
            ),
            color=alt.Color(
                "Timing category:N",
                scale=alt.Scale(
                    domain=category_order,
                    range=[TIMING_CATEGORY_COLORS[item] for item in category_order],
                ),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            order=alt.Order(
                "category_order:Q",
                sort="ascending",
            ),
            tooltip=[
                alt.Tooltip("Timing category:N", title="Timing category"),
                alt.Tooltip("Stop visits:Q", title="Stop visits", format=","),
                alt.Tooltip(
                    "Share of timed visits:Q",
                    title="Share of timed visits (%)",
                    format=".2f",
                ),
                alt.Tooltip("Timing population:N", title="Denominator"),
            ],
        )
        .properties(height=54)
    )
    st.altair_chart(chart, width="stretch")


def choose_segment(
    label: str,
    options: list,
    default: str,
    key: str,
    label_visibility: str = "visible",
):
    if hasattr(st, "segmented_control"):
        value = st.segmented_control(
            label,
            options,
            default=default,
            key=key,
            label_visibility=label_visibility,
        )
    else:
        value = st.radio(
            label,
            options,
            index=options.index(default),
            horizontal=True,
            key=key,
            label_visibility=label_visibility,
        )
    return value or default


def rgba(hex_color: str, alpha: int = 220) -> list:
    color = str(hex_color).strip().lstrip("#")
    if len(color) != 6:
        color = "64748B"
    try:
        return [
            int(color[0:2], 16),
            int(color[2:4], 16),
            int(color[4:6], 16),
            alpha,
        ]
    except ValueError:
        return [100, 116, 139, alpha]


def evidence_suffix(delay_events: int, coverage: float) -> str:
    badges = []
    if MIN_RANK_DELAY_EVENTS <= delay_events < LOW_SAMPLE_UPPER:
        badges.append("limited sample")
    if coverage < LOW_COVERAGE_PERCENTAGE:
        badges.append("low data availability")
    return ", " + ", ".join(badges) if badges else ""


def add_ranking_labels(
    data: pd.DataFrame,
    name_column: str,
    number_items: bool = False,
    show_sample_in_label: bool = True,
    show_counts_in_rate_label: bool = True,
) -> pd.DataFrame:
    plot = data.copy().reset_index(drop=True)

    def display_label(row):
        prefix = f"{int(row.name) + 1}. " if number_items else ""
        sample = (
            f" · {int(row['DELAY_EVENTS']):,} timed visits"
            if show_sample_in_label
            else ""
        )
        visible_badges = []
        if show_sample_in_label and int(row["DELAY_EVENTS"]) < LOW_SAMPLE_UPPER:
            visible_badges.append("limited sample")
        if float(row["DELAY_COVERAGE"]) < LOW_COVERAGE_PERCENTAGE:
            visible_badges.append("low data availability")
        badge_text = " · " + " · ".join(visible_badges) if visible_badges else ""
        return f"{prefix}{row[name_column]}{sample}{badge_text}"

    plot["DISPLAY_LABEL"] = plot.apply(display_label, axis=1)
    if show_counts_in_rate_label:
        plot["RATE_LABEL"] = plot.apply(
            lambda row: (
                f"{float(row['LATE_PERCENTAGE']):.1f}% — "
                f"{int(row['LATE_EVENTS']):,} of {int(row['DELAY_EVENTS']):,}"
            ),
            axis=1,
        )
    else:
        plot["RATE_LABEL"] = plot["LATE_PERCENTAGE"].map(
            lambda value: f"{float(value):.1f}%"
        )
    plot["EVIDENCE_NOTE"] = plot.apply(
        lambda row: (
            (
                "Early signal: fewer than 300 visits with timing information"
                if int(row["DELAY_EVENTS"]) < LOW_SAMPLE_UPPER
                else "Larger evidence base"
            )
            + (
                "; fewer than 60% of visits had timing information"
                if float(row["DELAY_COVERAGE"]) < LOW_COVERAGE_PERCENTAGE
                else ""
            )
        ),
        axis=1,
    )
    return plot


def ranking_chart(
    data: pd.DataFrame,
    name_column: str,
    color: str,
    scope_average: float | None = None,
    height: int = 390,
    number_items: bool = False,
    show_sample_in_label: bool = True,
    show_counts_in_rate_label: bool = True,
    fade_limited_samples: bool = False,
    average_label: str | None = None,
    label_limit: int = 330,
):
    plot = add_ranking_labels(
        data,
        name_column,
        number_items=number_items,
        show_sample_in_label=show_sample_in_label,
        show_counts_in_rate_label=show_counts_in_rate_label,
    )
    maximum = max(
        float(plot["LATE_PERCENTAGE"].max()),
        float(scope_average) if scope_average is not None else 0.0,
        1.0,
    )
    tooltip_fields = [
        alt.Tooltip(f"{name_column}:N", title="Name"),
    ]
    if "AGENCY_NAME" in plot.columns:
        tooltip_fields.append(alt.Tooltip("AGENCY_NAME:N", title="Operator"))
    if "TERMINI" in plot.columns:
        tooltip_fields.append(alt.Tooltip("TERMINI:N", title="Start → end"))
    tooltip_fields.extend(
        [
            alt.Tooltip("LATE_PERCENTAGE:Q", title="Over 5 min (%)", format=".2f"),
            alt.Tooltip("EARLY_EVENTS:Q", title=">1 min early", format=","),
            alt.Tooltip(
                "NEAR_SCHEDULE_EVENTS:Q",
                title="Within 1 min of schedule",
                format=",",
            ),
            alt.Tooltip("MINOR_DELAY_EVENTS:Q", title="1–5 min late", format=","),
            alt.Tooltip("LATE_EVENTS:Q", title=">5 min late", format=","),
            alt.Tooltip(
                "DELAY_EVENTS:Q",
                title="Visits with timing information",
                format=",",
            ),
            alt.Tooltip("STOP_EVENTS:Q", title="Observed stop visits", format=","),
            alt.Tooltip(
                "DELAY_COVERAGE:Q",
                title="Timing-data availability (%)",
                format=".2f",
            ),
            alt.Tooltip("EVIDENCE_NOTE:N", title="Evidence note"),
        ]
    )
    bars = (
        alt.Chart(plot)
        .mark_bar(color=color, cornerRadiusEnd=5)
        .encode(
            y=alt.Y(
                "DISPLAY_LABEL:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=label_limit),
            ),
            x=alt.X(
                "LATE_PERCENTAGE:Q",
                title="Timed visits reported over 5 minutes late (%)",
                scale=alt.Scale(domain=[0, maximum * 1.22]),
            ),
            opacity=(
                alt.condition(
                    f"datum.DELAY_EVENTS < {LOW_SAMPLE_UPPER}",
                    alt.value(0.42),
                    alt.value(1.0),
                )
                if fade_limited_samples
                else alt.value(1.0)
            ),
            tooltip=tooltip_fields,
        )
        .properties(height=height)
    )
    labels = (
        alt.Chart(plot)
        .mark_text(align="left", baseline="middle", dx=6, color="#E5E7EB")
        .encode(
            y=alt.Y("DISPLAY_LABEL:N", sort="-x"),
            x="LATE_PERCENTAGE:Q",
            text="RATE_LABEL:N",
        )
    )
    chart = bars + labels
    if scope_average is not None:
        average_text = average_label or f"Average: {scope_average:.1f}%"
        average_data = pd.DataFrame(
            {"scope_average": [scope_average], "average_label": [average_text]}
        )
        rule = (
            alt.Chart(average_data)
            .mark_rule(color="#93C5FD", strokeDash=[6, 4], strokeWidth=2)
            .encode(
                x="scope_average:Q",
                tooltip=[
                    alt.Tooltip(
                        "scope_average:Q", title="Scope average (%)", format=".2f"
                    )
                ],
            )
        )
        rule_label = (
            alt.Chart(average_data)
            .mark_text(
                align="left",
                baseline="top",
                dx=5,
                dy=4,
                color="#BFDBFE",
                fontWeight=600,
            )
            .encode(
                x="scope_average:Q",
                y=alt.value(4),
                text="average_label:N",
            )
        )
        chart = chart + rule + rule_label
    return chart


def point_color(late_percentage: float, delay_events: int) -> list:
    if delay_events < MIN_RANK_DELAY_EVENTS:
        return [107, 114, 128, 180]
    if late_percentage >= 20:
        return [239, 68, 68, 220]
    if late_percentage >= 10:
        return [249, 115, 22, 220]
    return [245, 158, 11, 210]


def view_state_from_points(points: pd.DataFrame) -> pdk.ViewState:
    latitude_span = float(points["station_lat"].max() - points["station_lat"].min())
    longitude_span = float(points["station_lon"].max() - points["station_lon"].min())
    span = max(latitude_span, longitude_span)
    zoom = 11.0 if span <= 0.12 else 9.5 if span <= 0.4 else 8.0 if span <= 1.0 else 7.0
    return pdk.ViewState(
        latitude=float(points["station_lat"].mean()),
        longitude=float(points["station_lon"].mean()),
        zoom=max(7.0, zoom),
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_scope_metrics() -> pd.DataFrame:
    """Load every transport-mode and area KPI for local filter switching."""
    return run_query(
        """
        SELECT
            scope_mode,
            scope_region,
            unique_stop_events AS stop_events,
            delay_reported_events AS delay_events,
            early_events,
            near_schedule_events,
            minor_delay_events,
            late_events,
            timing_unavailable_events,
            ROUND(
                100.0 * delay_reported_events
                / NULLIF(unique_stop_events, 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * late_events
                / NULLIF(delay_reported_events, 0), 2
            ) AS late_percentage,
            p90_delay_minutes
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_SCOPE_METRICS
        """
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_headline_line_metrics() -> pd.DataFrame:
    """Load line summaries for every mode and area once per cache cycle."""
    return run_query(
        """
        SELECT
            scope_mode,
            scope_region,
            focus_service_key,
            route_display_name,
            transport_mode,
            german_service_category,
            agency_name,
            unique_stop_events AS stop_events,
            delay_reported_events AS delay_events,
            early_events,
            near_schedule_events,
            minor_delay_events,
            late_events,
            timing_unavailable_events,
            ROUND(
                100.0 * delay_reported_events
                / NULLIF(unique_stop_events, 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * late_events
                / NULLIF(delay_reported_events, 0), 2
            ) AS late_percentage,
            termini.termini
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_LINE_METRICS AS metrics
        LEFT JOIN (
            SELECT
                focus_service_key,
                LISTAGG(
                    CONCAT(first_stop_name, ' → ', last_stop_name),
                    ' / '
                ) WITHIN GROUP (ORDER BY direction_id) AS termini
            FROM ROUTEPULSE.ANALYTICS.LINE_DIRECTION_REFERENCE
            GROUP BY focus_service_key
        ) AS termini USING (focus_service_key)
        """
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_headline_hour_metrics() -> pd.DataFrame:
    """Load hourly summaries for every mode and area once per cache cycle."""
    return run_query(
        """
        SELECT
            scope_mode,
            scope_region,
            observation_hour_berlin,
            is_partial_collection_hour,
            unique_stop_events AS stop_events,
            delay_reported_events AS delay_events,
            early_events,
            near_schedule_events,
            minor_delay_events,
            late_events,
            timing_unavailable_events,
            ROUND(
                100.0 * delay_reported_events
                / NULLIF(unique_stop_events, 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * late_events
                / NULLIF(delay_reported_events, 0), 2
            ) AS late_percentage,
            p90_delay_minutes
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_HOUR_METRICS
        """
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_station_metrics() -> pd.DataFrame:
    """Load compact station rankings for every mode and supported region."""
    return run_query(
        f"""
        SELECT
            stations.scope_mode,
            stations.scope_region,
            stations.station_name,
            stations.station_lat,
            stations.station_lon,
            stations.unique_stop_events AS stop_events,
            stations.delay_reported_events AS delay_events,
            stations.early_events,
            stations.near_schedule_events,
            stations.minor_delay_events,
            stations.late_events,
            stations.timing_unavailable_events,
            ROUND(
                100.0 * stations.delay_reported_events
                / NULLIF(stations.unique_stop_events, 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * stations.late_events
                / NULLIF(stations.delay_reported_events, 0), 2
            ) AS late_percentage,
            ROUND(
                100.0 * scope.late_events
                / NULLIF(scope.delay_reported_events, 0), 2
            ) AS scope_late_percentage
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_STATION_METRICS AS stations
        JOIN ROUTEPULSE.ANALYTICS.DASHBOARD_SCOPE_METRICS AS scope
          ON stations.scope_mode = scope.scope_mode
         AND stations.scope_region = scope.scope_region
        WHERE stations.delay_reported_events >= {MIN_RANK_DELAY_EVENTS}
        """
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def prepare_station_ranking(scope_mode: str, scope_region: str) -> pd.DataFrame:
    """Filter and rank cached station metrics without another warehouse query."""
    station_data = load_station_metrics()
    station_data = station_data[
        (station_data["SCOPE_MODE"] == scope_mode)
        & (station_data["SCOPE_REGION"] == scope_region)
    ].copy()
    station_data = station_data.sort_values(
        ["LATE_PERCENTAGE", "DELAY_EVENTS"],
        ascending=[False, False],
    ).head(10)
    station_data = station_data.reset_index(drop=True)
    station_data["STATION_RANK"] = station_data.index + 1
    return station_data


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_category_metrics() -> pd.DataFrame:
    """Load service-category summaries for every supported area."""
    return run_query(
        """
        SELECT
            scope_mode,
            scope_region,
            german_service_category,
            unique_stop_events AS stop_events,
            delay_reported_events AS delay_events,
            early_events,
            near_schedule_events,
            minor_delay_events,
            late_events,
            timing_unavailable_events,
            ROUND(
                100.0 * delay_reported_events
                / NULLIF(unique_stop_events, 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * late_events
                / NULLIF(delay_reported_events, 0), 2
            ) AS late_percentage
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_CATEGORY_METRICS
        """
    )


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_region_metrics() -> pd.DataFrame:
    """Load the complete regional reconciliation table once."""
    return run_query(
        """
        SELECT
            scope_mode,
            event_region,
            unique_stop_events,
            delay_reported_events AS events_with_timing_data,
            early_events,
            near_schedule_events,
            minor_delay_events,
            late_events,
            timing_unavailable_events,
            ROUND(
                100.0 * delay_reported_events
                / NULLIF(unique_stop_events, 0), 2
            ) AS timing_data_availability,
            ROUND(
                100.0 * late_events
                / NULLIF(delay_reported_events, 0), 2
            ) AS over_five_minutes_late
        FROM ROUTEPULSE.ANALYTICS.DASHBOARD_REGION_METRICS
        """
    )


window = run_query(
    """
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
        ) AS observed_window_hours,
        COUNT(*) AS all_unique_stop_events
    FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
    """
).iloc[0]
raw_kpi = run_query("SELECT * FROM ROUTEPULSE.ANALYTICS.KPI_SUMMARY").iloc[0]

with st.sidebar:
    st.title("Explore RoutePulse")
    st.caption(
        "Change the analysis here. Collapse this panel when you want more "
        "room for charts and maps."
    )
    selected_area = st.selectbox(
        "Observed stop area",
        AREA_OPTIONS,
        index=0,
        key="area_filter_v1",
        help=(
            "Berlin and Brandenburg are assigned from each observed stop's "
            "location. Cross-border lines can appear in both areas."
        ),
    )
    selected_mode = st.selectbox(
        "Transport mode",
        MODE_OPTIONS,
        index=0,
        key="mode_filter_v5",
    )
    selected_view = st.radio(
        "Analysis",
        VIEW_OPTIONS,
        index=0,
        key="view_navigation_v5",
    )
    selected_hour_metric = "% over 5 minutes"
    if selected_view == "When":
        st.divider()
        selected_hour_metric = st.radio(
            "Hourly measure",
            ["% over 5 minutes", "P90 delay"],
            index=0,
            key="hour_measure_v5",
        )

collection_start = pd.to_datetime(window["FIRST_EVENT_BERLIN"])
collection_end = pd.to_datetime(window["LAST_EVENT_BERLIN"])
collection_hours = float(window["OBSERVED_WINDOW_HOURS"])

st.title("🚌 RoutePulse: Berlin–Brandenburg Operations Snapshot")
st.markdown(
    "**Business question:** Where and when did the observed VBB data show the "
    "most serious delays, which services should operations review, and how "
    "confident can we be in those findings?"
)
st.warning(
    f"**Observed window:** {collection_start:%a %d %b %Y, %H:%M} to "
    f"{collection_end:%a %d %b %Y, %H:%M} Berlin time "
    f"({collection_hours:.1f} hours). This Friday/weekend sample does not "
    "represent a normal weekday commute."
)

scope_mode_label = "all modes" if selected_mode == "All modes" else selected_mode
st.caption(f"Showing: {scope_mode_label} · {selected_area} · {selected_view.lower()}")

scope_metrics = load_scope_metrics()
selected_scope_metrics = scope_metrics[
    (scope_metrics["SCOPE_MODE"] == selected_mode)
    & (scope_metrics["SCOPE_REGION"] == selected_area)
]
if selected_scope_metrics.empty:
    st.info(
        "No observed stop visits are available for this transport mode and "
        "area combination. Choose another scope in the sidebar."
    )
    st.stop()
event_kpi = selected_scope_metrics.iloc[0]

if int(event_kpi["STOP_EVENTS"]) == 0:
    st.info("No observed stop visits match this transport mode and area.")
    st.stop()

late_percentage = float(event_kpi["LATE_PERCENTAGE"])
one_in_n = round(100.0 / late_percentage) if late_percentage > 0 else None
one_in_text = (
    f"Roughly 1 in {one_in_n:,} timed stop visits was reported seriously late"
    if one_in_n
    else "No timed stop visit was reported more than 5 minutes late"
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 5rem !important; }
    .rp-card-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.3rem 0 0.35rem 0;
    }
    .rp-card {
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 18px;
        padding: 0.8rem 0.95rem;
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.76), rgba(15, 23, 42, 0.62));
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
        min-height: 112px;
    }
    .rp-card-accent { width: 34px; height: 3px; background: #60A5FA; border-radius: 3px; }
    .rp-card-label { color: #94A3B8; font-size: 0.82rem; margin-top: 0.45rem; }
    .rp-card-value { color: #F8FAFC; font-size: 2.15rem; font-weight: 650; line-height: 1.05; margin: 0.18rem 0; }
    .rp-card-copy { color: #CBD5E1; font-size: 0.84rem; line-height: 1.35; }
    .rp-build-strip {
        border: 1px solid rgba(96, 165, 250, 0.32);
        border-radius: 12px;
        padding: 0.55rem 0.75rem;
        background: rgba(30, 64, 175, 0.13);
        color: #DBEAFE;
        margin: 0.25rem 0 0.55rem 0;
    }
    @media (max-width: 760px) {
        .rp-card-grid { grid-template-columns: 1fr; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

card_html = f"""
<div class="rp-card-grid">
  <div class="rp-card">
    <div class="rp-card-accent"></div>
    <div class="rp-card-label">Serious delays (&gt;5 min)</div>
    <div class="rp-card-value">{late_percentage:.1f}%</div>
    <div class="rp-card-copy">{html.escape(one_in_text)}</div>
  </div>
  <div class="rp-card">
    <div class="rp-card-accent"></div>
    <div class="rp-card-label">Upper-range reported delay (P90)</div>
    <div class="rp-card-value">{float(event_kpi["P90_DELAY_MINUTES"]):.1f} min</div>
    <div class="rp-card-copy">9 in 10 timing reports were no more delayed than this</div>
  </div>
  <div class="rp-card">
    <div class="rp-card-accent"></div>
    <div class="rp-card-label">Timing-data availability</div>
    <div class="rp-card-value">{float(event_kpi["DELAY_COVERAGE"]):.1f}%</div>
    <div class="rp-card-copy">Share of observed stop visits containing timing information</div>
  </div>
</div>
"""
st.markdown(card_html, unsafe_allow_html=True)
st.caption(
    f"Based on {int(event_kpi['STOP_EVENTS']):,} observed stop visits, of which "
    f"{int(event_kpi['DELAY_EVENTS']):,} included timing information. A stop visit "
    "is one retained observation for a vehicle trip at a stop. **Seriously late = "
    "reported as more than 5 minutes behind the timetable.** Missing timing values "
    "are never treated as zero."
)

st.markdown("#### How did the timed visits compare with the schedule?")
st.caption(
    "The four categories below partition every stop visit that contained timing "
    "information; they always add to 100%."
)
render_timing_distribution(event_kpi)

with st.expander(
    "How RoutePulse defines early, near schedule and late", expanded=False
):
    st.markdown(
        """
        - **Reported early:** more than 1 minute ahead of schedule.
        - **Within 1 minute of schedule:** from 1 minute early through 1 minute late.
        - **Minor delay:** more than 1 and up to 5 minutes late.
        - **Serious delay:** more than 5 minutes late.
        - **Timing unavailable:** the realtime stop update contained no usable timing value.

        These are RoutePulse analytical categories, applied consistently so transport
        modes can be compared. The five-minute serious-delay threshold closely follows
        VBB public regional-rail reporting, but it is not presented as every operator's
        contractual punctuality definition. GTFS-Realtime values can be predictions;
        “reported early” or “reported late” does not necessarily mean a confirmed actual
        arrival or departure. Full details are recorded in the project methodology.
        """
    )

line_insights = (
    load_headline_line_metrics()
    .loc[
        lambda data: (
            (data["SCOPE_MODE"] == selected_mode)
            & (data["SCOPE_REGION"] == selected_area)
            & (data["DELAY_EVENTS"] >= MIN_RANK_DELAY_EVENTS)
        )
    ]
    .sort_values(
        ["LATE_PERCENTAGE", "LATE_EVENTS"],
        ascending=[False, False],
    )
)

headline_hours = (
    load_headline_hour_metrics()
    .loc[
        lambda data: (
            (data["SCOPE_MODE"] == selected_mode)
            & (data["SCOPE_REGION"] == selected_area)
            & (data["DELAY_EVENTS"] >= MIN_HEADLINE_HOUR_DELAY_EVENTS)
        )
    ]
    .sort_values(
        ["LATE_PERCENTAGE", "DELAY_EVENTS"],
        ascending=[False, False],
    )
)

st.subheader("What stands out in this selection")
if not line_insights.empty:
    top_rate = line_insights.loc[line_insights["LATE_PERCENTAGE"].idxmax()]
    top_volume = line_insights.loc[line_insights["LATE_EVENTS"].idxmax()]
    top_rate_service = service_description(top_rate)
    top_volume_service = service_description(top_volume)
    st.markdown(
        f"- **Highest serious-delay share:** {top_rate_service} had "
        f"{float(top_rate['LATE_PERCENTAGE']):.1f}% of its "
        f"{int(top_rate['DELAY_EVENTS']):,} timed stop visits reported more than "
        f"5 minutes late"
        f"{evidence_suffix(int(top_rate['DELAY_EVENTS']), float(top_rate['DELAY_COVERAGE']))}. "
        f"**Largest number of serious delays:** {top_volume_service} recorded "
        f"{int(top_volume['LATE_EVENTS']):,} seriously late stop visits from "
        f"{int(top_volume['DELAY_EVENTS']):,} timed visits"
        f"{evidence_suffix(int(top_volume['DELAY_EVENTS']), float(top_volume['DELAY_COVERAGE']))}."
    )
complete_headline_hours = headline_hours[
    ~headline_hours["IS_PARTIAL_COLLECTION_HOUR"].fillna(False)
]
if not complete_headline_hours.empty:
    peak_hour = complete_headline_hours.loc[
        complete_headline_hours["LATE_PERCENTAGE"].idxmax()
    ]
    peak_time = pd.to_datetime(peak_hour["OBSERVATION_HOUR_BERLIN"])
    peak_hour_evidence = evidence_suffix(
        int(peak_hour["DELAY_EVENTS"]), float(peak_hour["DELAY_COVERAGE"])
    )
    st.markdown(
        f"- **Most difficult complete hour:** At {peak_time:%A %H:%M}, "
        f"{float(peak_hour['LATE_PERCENTAGE']):.1f}% of "
        f"{int(peak_hour['DELAY_EVENTS']):,} timed stop visits were over "
        f"five minutes late{peak_hour_evidence}. The first and last collection "
        "hours were partial."
    )
st.markdown(
    f"- **Confidence:** timing information covers {float(event_kpi['DELAY_COVERAGE']):.1f}% "
    f"of this scope, and the collection spans only {collection_hours:.1f} "
    "Friday/weekend hours. Rankings are preliminary."
)

st.markdown(
    f"""
    <div class="rp-build-strip">
      <strong>How this was built</strong><br/>
      VBB GTFS-Realtime and Static → S3 → Snowflake → Streamlit ·
      {int(raw_kpi["STOP_OBSERVATIONS"]):,} raw stop-status rows →
      {int(window["ALL_UNIQUE_STOP_EVENTS"]):,} observed stop visits →
      zero duplicate event keys after validation
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_network_paths() -> pd.DataFrame:
    """Load and parse all representative network paths once per cache cycle."""
    network_paths = run_query(
        """
        WITH ranked_paths AS (
            SELECT
                CONCAT_WS(
                    '|',
                    COALESCE(catalogue.transport_mode, 'Unknown mode'),
                    COALESCE(catalogue.agency_id, 'Unknown agency'),
                    COALESCE(catalogue.route_display_name, 'Unnamed route')
                ) AS focus_service_key,
                catalogue.route_display_name,
                catalogue.transport_mode,
                catalogue.agency_name,
                paths.route_id,
                paths.shape_id,
                paths.scheduled_trip_count,
                paths.map_point_count,
                paths.minimum_latitude,
                paths.maximum_latitude,
                paths.minimum_longitude,
                paths.maximum_longitude,
                paths.map_path_coordinates,
                ROW_NUMBER() OVER (
                    PARTITION BY CONCAT_WS(
                        '|',
                        COALESCE(catalogue.transport_mode, 'Unknown mode'),
                        COALESCE(catalogue.agency_id, 'Unknown agency'),
                        COALESCE(catalogue.route_display_name, 'Unnamed route')
                    )
                    ORDER BY
                        paths.scheduled_trip_count DESC,
                        paths.map_point_count DESC,
                        paths.shape_id
                ) AS path_rank
            FROM ROUTEPULSE.ANALYTICS.MAP_ROUTE_PATHS_RENDER AS paths
            JOIN ROUTEPULSE.ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG AS catalogue
                ON paths.route_id = catalogue.static_route_id
            WHERE catalogue.transport_mode IS NOT NULL
        ),
        termini AS (
            SELECT
                focus_service_key,
                LISTAGG(
                    CONCAT(
                        COALESCE(first_stop_name, 'Unknown start'),
                        ' → ',
                        COALESCE(last_stop_name, 'Unknown end')
                    ),
                    ' / '
                ) WITHIN GROUP (ORDER BY direction_id) AS termini
            FROM ROUTEPULSE.ANALYTICS.LINE_DIRECTION_REFERENCE
            GROUP BY focus_service_key
        )
        SELECT
            ranked_paths.focus_service_key,
            ranked_paths.route_display_name,
            ranked_paths.transport_mode,
            ranked_paths.agency_name,
            ranked_paths.route_id,
            ranked_paths.shape_id,
            ranked_paths.scheduled_trip_count,
            ranked_paths.map_point_count,
            ranked_paths.minimum_latitude,
            ranked_paths.maximum_latitude,
            ranked_paths.minimum_longitude,
            ranked_paths.maximum_longitude,
            termini.termini,
            TO_JSON(ranked_paths.map_path_coordinates) AS map_path_json
        FROM ranked_paths
        LEFT JOIN termini
            ON ranked_paths.focus_service_key = termini.focus_service_key
        WHERE ranked_paths.path_rank = 1
        ORDER BY ranked_paths.transport_mode, ranked_paths.route_display_name
        """
    )
    if network_paths.empty:
        return network_paths

    network_paths["path"] = network_paths["MAP_PATH_JSON"].map(parse_json_value)
    return network_paths[
        network_paths["path"].map(
            lambda path: isinstance(path, list) and len(path) >= 2
        )
    ].copy()


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def load_state_boundary_features() -> dict:
    """Return the simplified Berlin and Brandenburg boundaries once."""
    boundaries = run_query(
        """
        SELECT
            state_name,
            ST_ASGEOJSON(
                ST_SIMPLIFY(boundary_geography, 100, TRUE)
            )::VARCHAR AS boundary_geojson
        FROM ROUTEPULSE.ANALYTICS.STATE_BOUNDARIES
        WHERE state_name IN ('Berlin', 'Brandenburg')
        ORDER BY state_name
        """
    )
    features = []
    for _, boundary in boundaries.iterrows():
        geometry = parse_json_value(boundary["BOUNDARY_GEOJSON"])
        if geometry:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"state_name": boundary["STATE_NAME"]},
                    "geometry": geometry,
                }
            )
    return {"type": "FeatureCollection", "features": features}


@st.cache_data(ttl=PRESENTATION_CACHE_TTL_SECONDS, show_spinner=False)
def prepare_network_map_data(
    mode: str,
    scope_region: str,
) -> tuple[pd.DataFrame, int, int]:
    """Filter and style cached paths without another Snowflake round trip."""
    network_paths = load_network_paths()
    observed_services = load_headline_line_metrics()
    observed_services = observed_services[
        (observed_services["SCOPE_MODE"] == mode)
        & (observed_services["SCOPE_REGION"] == scope_region)
    ]
    service_keys = set(observed_services["FOCUS_SERVICE_KEY"].dropna())
    network_paths = network_paths[
        network_paths["FOCUS_SERVICE_KEY"].isin(service_keys)
    ].copy()
    if mode != "All modes":
        network_paths = network_paths[network_paths["TRANSPORT_MODE"] == mode].copy()
    else:
        network_paths = network_paths.copy()
    if network_paths.empty:
        return network_paths, 0, 0

    if mode == "All modes":
        network_paths["color"] = network_paths["TRANSPORT_MODE"].map(
            lambda transport_mode: rgba(
                MODE_COLORS.get(transport_mode, COVERAGE_BAR_COLOR), 215
            )
        )
    elif mode == "Bus":
        network_paths["color"] = [rgba(MODE_COLORS["Bus"], 215)] * len(network_paths)
    else:
        service_keys = sorted(network_paths["FOCUS_SERVICE_KEY"].unique())
        service_colors = {
            key: rgba(NETWORK_LINE_PALETTE[index % len(NETWORK_LINE_PALETTE)], 220)
            for index, key in enumerate(service_keys)
        }
        network_paths["color"] = network_paths["FOCUS_SERVICE_KEY"].map(service_colors)

    map_data = network_paths.rename(
        columns={
            "ROUTE_DISPLAY_NAME": "line_name",
            "TRANSPORT_MODE": "transport_mode",
            "AGENCY_NAME": "operator_name",
            "TERMINI": "termini",
            "SCHEDULED_TRIP_COUNT": "scheduled_trip_count",
        }
    ).copy()
    map_data["termini"] = map_data["termini"].fillna("Termini unavailable")
    return (
        map_data,
        int(network_paths["FOCUS_SERVICE_KEY"].nunique()),
        int(network_paths["MAP_POINT_COUNT"].fillna(0).sum()),
    )


def render_network_map():
    st.header("Where do the observed services run?")
    st.caption(
        "Scheduled GTFS paths for passenger-facing services observed during "
        "this sample. Lines show planned routes, not realtime vehicle movements."
    )
    map_data, line_count, coordinate_count = prepare_network_map_data(
        selected_mode,
        selected_area,
    )
    if map_data.empty:
        st.info(f"No scheduled map paths are available for {scope_mode_label}.")
        return

    boundary_geojson = load_state_boundary_features()
    if selected_area != "All regions":
        boundary_geojson = {
            "type": "FeatureCollection",
            "features": [
                feature
                for feature in boundary_geojson["features"]
                if feature["properties"]["state_name"] == selected_area
            ],
        }

    layers = []
    if boundary_geojson["features"]:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=boundary_geojson,
                id="state-boundaries",
                stroked=True,
                filled=True,
                get_fill_color=[245, 158, 11, 18],
                get_line_color=[148, 163, 184, 190],
                line_width_min_pixels=1,
                pickable=False,
            )
        )
    layers.append(
        pdk.Layer(
            "PathLayer",
            data=map_data,
            id="representative-network-paths",
            get_path="path",
            get_color="color",
            get_width=4 if selected_mode != "All modes" else 2.5,
            width_min_pixels=2,
            pickable=True,
            auto_highlight=True,
        )
    )

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=(
                pdk.ViewState(latitude=52.52, longitude=13.405, zoom=9.0)
                if selected_area == "Berlin"
                else (
                    pdk.ViewState(latitude=52.40, longitude=13.20, zoom=7.0)
                    if selected_area == "Brandenburg"
                    else pdk.ViewState(
                        latitude=52.35,
                        longitude=13.25,
                        zoom=(
                            6.7
                            if selected_mode in ["All modes", "Regional rail"]
                            else 7.4
                        ),
                    )
                )
            ),
            layers=layers,
            tooltip={
                "html": (
                    "<b>{line_name}</b><br/>"
                    "{transport_mode} · {operator_name}<br/>"
                    "{termini}<br/>"
                    "Representative scheduled path"
                )
            },
        ),
        width="stretch",
        height=700,
    )

    metric_columns = st.columns(3)
    metric_columns[0].metric("Passenger-facing lines", f"{line_count:,}")
    metric_columns[1].metric("Representative paths", f"{len(map_data):,}")
    metric_columns[2].metric("Rendered coordinates", f"{coordinate_count:,}")
    if selected_mode == "All modes":
        legend = " &nbsp; ".join(
            f'<span style="color:{color}">●</span> {mode}'
            for mode, color in MODE_COLORS.items()
        )
        st.markdown(
            f'<div style="font-size:0.84rem;color:#94A3B8"><strong>Map key:</strong> {legend}</div>',
            unsafe_allow_html=True,
        )
    elif selected_mode == "Bus":
        st.caption("All bus lines use one colour to keep the dense network readable.")
    else:
        st.caption(
            "Colours distinguish passenger-facing lines in this mode; hover a "
            "path for its line, operator and scheduled start→end description."
        )
    st.info(
        f"**Map reading:** {line_count:,} observed {scope_mode_label} "
        f"passenger-facing lines had stop visits in {selected_area} and have "
        "a representative scheduled path here. Cross-border paths may extend "
        "beyond the selected stop area. "
        "The map describes network coverage, not delay severity or live movement."
    )


def render_stations():
    st.header("Which stations were late most often?")
    st.caption(
        "Out of every 100 timed visits at each station, "
        "how many were reported more than 5 minutes behind the timetable?"
    )
    station_data = prepare_station_ranking(
        selected_mode,
        selected_area,
    )
    if station_data.empty:
        st.info(
            f"Not enough {selected_area} stations have at least "
            f"{MIN_RANK_DELAY_EVENTS:,} stop visits with timing information for "
            f"{scope_mode_label}."
        )
        return

    scope_average = float(station_data.iloc[0]["SCOPE_LATE_PERCENTAGE"])
    average_mode_label = "All-mode" if selected_mode == "All modes" else selected_mode
    chart_column, map_column = st.columns([1.12, 1])
    with chart_column:
        st.subheader("Stations with the most frequent serious delays")
        st.caption(
            "The ranking starts at 100 stop visits with timing information. Paler "
            "bars rest on fewer visits and should be treated as early signals."
        )
        st.altair_chart(
            ranking_chart(
                station_data,
                "STATION_NAME",
                RATE_BAR_COLOR,
                scope_average=scope_average,
                height=390,
                number_items=True,
                show_sample_in_label=False,
                show_counts_in_rate_label=False,
                fade_limited_samples=True,
                average_label=(f"{average_mode_label} average: {scope_average:.1f}%"),
                label_limit=390,
            ),
            width="stretch",
        )
        st.caption(
            "Paler bars rest on 100–299 timed visits; treat them "
            "as an early signal. The dashed line is labelled with the selected "
            "region-and-mode average."
        )

    mapped_stations = station_data.dropna(subset=["STATION_LAT", "STATION_LON"]).copy()
    with map_column:
        st.subheader("Where are these stations?")
        st.caption(
            "Numbers match the ranking; hover a circle for its station name and "
            "timing breakdown. Larger circles had more timed visits."
        )
        if mapped_stations.empty:
            st.info("Coordinates are unavailable for the ranked stations.")
        else:
            station_points = mapped_stations.rename(
                columns={
                    "STATION_NAME": "station_name",
                    "STATION_LAT": "station_lat",
                    "STATION_LON": "station_lon",
                    "LATE_PERCENTAGE": "late_percentage",
                    "EARLY_EVENTS": "early_events",
                    "NEAR_SCHEDULE_EVENTS": "near_schedule_events",
                    "MINOR_DELAY_EVENTS": "minor_delay_events",
                    "LATE_EVENTS": "late_events",
                    "DELAY_EVENTS": "delay_events",
                    "DELAY_COVERAGE": "delay_coverage",
                    "STATION_RANK": "station_rank",
                }
            )
            station_points["rank_label"] = station_points["station_rank"].map(
                lambda value: str(int(value))
            )
            station_points["fill_color"] = station_points.apply(
                lambda row: point_color(
                    float(row["late_percentage"]), int(row["delay_events"])
                ),
                axis=1,
            )
            station_points["point_radius"] = station_points["delay_events"].map(
                lambda count: max(170, min(850, math.sqrt(float(count)) * 18))
            )
            station_layer = pdk.Layer(
                "ScatterplotLayer",
                data=station_points,
                id="ranked-stations",
                get_position="[station_lon, station_lat]",
                get_fill_color="fill_color",
                get_line_color=[255, 255, 255, 210],
                get_radius="point_radius",
                radius_min_pixels=7,
                radius_max_pixels=24,
                line_width_min_pixels=1,
                stroked=True,
                pickable=True,
                auto_highlight=True,
            )
            rank_layer = pdk.Layer(
                "TextLayer",
                data=station_points,
                id="ranked-station-numbers",
                get_position="[station_lon, station_lat]",
                get_text="rank_label",
                get_color=[255, 255, 255, 255],
                get_size=13,
                get_text_anchor="middle",
                get_alignment_baseline="center",
                billboard=True,
                pickable=False,
            )
            st.pydeck_chart(
                pdk.Deck(
                    map_style=None,
                    initial_view_state=view_state_from_points(station_points),
                    layers=[station_layer, rank_layer],
                    tooltip={
                        "html": (
                            "<b>{station_name}</b><br/>"
                            "Rank: {rank_label}<br/>"
                            "Reported over 5 minutes late: {late_percentage}%<br/>"
                            "Reported &gt;1 min early: {early_events}<br/>"
                            "Within 1 min of schedule: {near_schedule_events}<br/>"
                            "Reported 1–5 min late: {minor_delay_events}<br/>"
                            "Reported &gt;5 min late: {late_events}<br/>"
                            "Visits with timing information: {delay_events}<br/>"
                            "Timing-data availability: {delay_coverage}%"
                        )
                    },
                ),
                width="stretch",
                height=430,
            )
            st.markdown(
                """
                <div style="font-size:0.82rem;color:#94A3B8;line-height:1.7">
                  <strong>Dot colours:</strong>
                  <span style="color:#F59E0B">●</span> under 10% &nbsp;
                  <span style="color:#F97316">●</span> 10–19.9% &nbsp;
                  <span style="color:#EF4444">●</span> 20% or more.
                  Numbers match the bars. Larger dots contain more visits with
                  timing information.
                </div>
                """,
                unsafe_allow_html=True,
            )

    if (
        station_data["DELAY_EVENTS"]
        .between(MIN_RANK_DELAY_EVENTS, LOW_SAMPLE_UPPER - 1)
        .all()
    ):
        st.warning(
            "Every station in this ranking rests on only 100–299 visits with a "
            "timing value. Treat the ranking as an early signal, not a verdict."
        )

    top_station = station_data.iloc[0]
    relative_rate = (
        float(top_station["LATE_PERCENTAGE"]) / scope_average
        if scope_average > 0
        else None
    )
    early_signal = (
        f" That is only {int(top_station['DELAY_EVENTS']):,} visits, so treat "
        "it as an early signal, not a verdict."
        if int(top_station["DELAY_EVENTS"]) < LOW_SAMPLE_UPPER
        else ""
    )
    comparison = (
        f", roughly {relative_rate:.1f} times the "
        if relative_rate is not None
        else ", compared with the "
    )
    st.info(
        f"**What this means:** At {top_station['STATION_NAME']}, "
        f"{int(top_station['LATE_EVENTS']):,} of "
        f"{int(top_station['DELAY_EVENTS']):,} visits with timing information "
        f"({float(top_station['LATE_PERCENTAGE']):.1f}%) were reported more than "
        f"5 minutes late{comparison}{selected_area} {scope_mode_label} "
        f"average of {scope_average:.1f}%.{early_signal} This does not establish "
        "a cause."
    )


def render_mode_comparison():
    st.header("Which transport modes were late most often?")
    st.caption(
        "Of the stop visits with timing information, what percentage were reported "
        "more than 5 minutes behind the timetable? Select one transport mode "
        "above to compare its individual lines."
    )
    mode_data = load_scope_metrics()
    mode_data = mode_data[
        (mode_data["SCOPE_MODE"] != "All modes")
        & (mode_data["SCOPE_REGION"] == selected_area)
    ].copy()
    mode_data = mode_data.rename(columns={"SCOPE_MODE": "TRANSPORT_MODE"})
    mode_data = mode_data.sort_values("LATE_PERCENTAGE", ascending=False)
    mode_data["MODE_LABEL"] = mode_data["TRANSPORT_MODE"]
    mode_data["RATE_LABEL"] = mode_data.apply(
        lambda row: (
            f"{float(row['LATE_PERCENTAGE']):.1f}% "
            f"({int(row['LATE_EVENTS']):,}/{int(row['DELAY_EVENTS']):,})"
        ),
        axis=1,
    )
    chart = (
        alt.Chart(mode_data)
        .mark_bar(color=RATE_BAR_COLOR, cornerRadiusEnd=5)
        .encode(
            y=alt.Y("MODE_LABEL:N", sort="-x", title=None),
            x=alt.X("LATE_PERCENTAGE:Q", title="Over 5 minutes late (%)"),
            tooltip=[
                alt.Tooltip("TRANSPORT_MODE:N", title="Mode"),
                alt.Tooltip("LATE_PERCENTAGE:Q", title="Over 5 min (%)", format=".2f"),
                alt.Tooltip("EARLY_EVENTS:Q", title=">1 min early", format=","),
                alt.Tooltip("NEAR_SCHEDULE_EVENTS:Q", title="Within 1 min", format=","),
                alt.Tooltip("MINOR_DELAY_EVENTS:Q", title="1–5 min late", format=","),
                alt.Tooltip("LATE_EVENTS:Q", title=">5 min late", format=","),
                alt.Tooltip(
                    "DELAY_COVERAGE:Q",
                    title="Timing-data availability (%)",
                    format=".2f",
                ),
                alt.Tooltip(
                    "DELAY_EVENTS:Q", title="Visits with timing information", format=","
                ),
            ],
        )
        .properties(height=350)
    )
    labels = (
        alt.Chart(mode_data)
        .mark_text(align="left", baseline="middle", dx=6, color="#E5E7EB")
        .encode(
            y=alt.Y("MODE_LABEL:N", sort="-x"),
            x="LATE_PERCENTAGE:Q",
            text="RATE_LABEL:N",
        )
    )
    st.altair_chart(chart + labels, width="stretch")
    top_mode = mode_data.iloc[0]
    st.info(
        f"**Observed takeaway:** {top_mode['TRANSPORT_MODE']} had the highest "
        f"share of timed visits reported more than 5 minutes late: "
        f"{float(top_mode['LATE_PERCENTAGE']):.1f}%"
        f"{evidence_suffix(int(top_mode['DELAY_EVENTS']), float(top_mode['DELAY_COVERAGE']))}. "
        "Timing-data availability is shown on hover because reporting "
        "completeness differs by mode."
    )


def render_lines():
    if selected_mode == "All modes":
        render_mode_comparison()
        return

    st.header("Which lines were reported late most often?")
    st.caption(
        "Out of every 100 timed stop visits on a line, how many were reported "
        "more than 5 minutes behind the timetable?"
    )

    line_data = load_headline_line_metrics()
    line_data = line_data[
        (line_data["SCOPE_MODE"] == selected_mode)
        & (line_data["SCOPE_REGION"] == selected_area)
        & (line_data["DELAY_EVENTS"] >= MIN_RANK_DELAY_EVENTS)
    ].copy()
    line_data = line_data.sort_values(
        ["LATE_PERCENTAGE", "DELAY_EVENTS"],
        ascending=[False, False],
    )
    if line_data.empty:
        st.info(
            f"No {selected_mode} line in {selected_area} meets the minimum of "
            f"{MIN_RANK_DELAY_EVENTS:,} stop visits with timing information."
        )
        return

    def line_with_termini(row):
        return service_description(row).replace(" → ", " to ")

    line_data["LINE_LABEL"] = line_data.apply(
        line_with_termini,
        axis=1,
    )
    line_data["LINE_OPTION_LABEL"] = line_data["LINE_LABEL"]
    top_ten = line_data.head(10).copy()
    st.caption(
        "Paler bars rest on fewer than 300 timed stop visits; "
        "treat them as early signals. Operator and full route details are in "
        "the tooltip."
    )
    st.altair_chart(
        ranking_chart(
            top_ten,
            "LINE_LABEL",
            RATE_BAR_COLOR,
            height=390,
            show_sample_in_label=False,
            show_counts_in_rate_label=True,
            fade_limited_samples=True,
            label_limit=680,
        ),
        width="stretch",
    )

    rate_column, volume_column = st.columns(2)
    with rate_column:
        st.subheader("Highest serious-delay share")
        st.caption(
            "Largest percentage of timed visits reported more than 5 minutes late."
        )
        for _, row in line_data.nlargest(5, "LATE_PERCENTAGE").iterrows():
            evidence_note = (
                " — early signal" if int(row["DELAY_EVENTS"]) < LOW_SAMPLE_UPPER else ""
            )
            st.markdown(
                f"**{service_description(row, include_termini=False)}** — "
                f"{float(row['LATE_PERCENTAGE']):.1f}% "
                f"({int(row['LATE_EVENTS']):,} of "
                f"{int(row['DELAY_EVENTS']):,} timed visits){evidence_note}"
            )
    with volume_column:
        st.subheader("Largest number of serious delays")
        st.caption("Most stop visits reported more than 5 minutes late.")
        for _, row in line_data.nlargest(5, "LATE_EVENTS").iterrows():
            st.markdown(
                f"**{service_description(row, include_termini=False)}** — "
                f"{int(row['LATE_EVENTS']):,} seriously late stop visits "
                f"(from {int(row['DELAY_EVENTS']):,} timed visits)"
            )

    line_labels = line_data.set_index("FOCUS_SERVICE_KEY")[
        "LINE_OPTION_LABEL"
    ].to_dict()
    line_keys = line_data["FOCUS_SERVICE_KEY"].tolist()
    previous_line = st.session_state.get("highlight_line_v4", "None")
    if previous_line not in ["None", *line_keys]:
        st.session_state["highlight_line_v4"] = "None"
    with st.sidebar:
        st.divider()
        selected_line_key = st.selectbox(
            "See where a line runs",
            ["None", *line_keys],
            format_func=lambda key: line_labels.get(key, key),
            key="highlight_line_v4",
            help="This controls only the detailed line map, not the global scope.",
        )

    if selected_line_key != "None":
        render_selected_line_map(selected_line_key, line_labels[selected_line_key])
    else:
        st.caption(
            "Choose a line to draw one representative scheduled path and the "
            "stops observed in this sample. No route is drawn by default."
        )

    top_rate = line_data.loc[line_data["LATE_PERCENTAGE"].idxmax()]
    supported_lines = line_data[
        (line_data["DELAY_EVENTS"] >= LOW_SAMPLE_UPPER)
        & (line_data["DELAY_COVERAGE"] >= LOW_COVERAGE_PERCENTAGE)
    ]
    supported_rate = (
        supported_lines.loc[supported_lines["LATE_PERCENTAGE"].idxmax()]
        if not supported_lines.empty
        else top_rate
    )
    takeaway = (
        f"**What this means:** The strongest well-supported serious-delay share "
        f"was {service_description(supported_rate)}: "
        f"{int(supported_rate['LATE_EVENTS']):,} of "
        f"{int(supported_rate['DELAY_EVENTS']):,} timed visits "
        f"({float(supported_rate['LATE_PERCENTAGE']):.1f}%) were reported more "
        "than 5 minutes late."
    )
    if top_rate["FOCUS_SERVICE_KEY"] != supported_rate["FOCUS_SERVICE_KEY"]:
        takeaway += (
            f" {service_description(top_rate)} had a higher observed share "
            f"of {float(top_rate['LATE_PERCENTAGE']):.1f}%, but that came from "
            f"only {int(top_rate['DELAY_EVENTS']):,} visits, so treat it as an "
            "early signal rather than a verdict."
        )
    else:
        takeaway += " It also had the highest serious-delay share overall."
    st.info(takeaway)

    if selected_mode in ["Bus", "Regional rail"]:
        with st.expander(
            f"Compare types of {selected_mode.lower()} service",
            expanded=False,
        ):
            render_category_comparison()


def render_selected_line_map(service_key: str, line_label: str):
    line_path = run_query(
        f"""
        WITH selected_routes AS (
            SELECT static_route_id
            FROM ROUTEPULSE.ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG
            WHERE CONCAT_WS(
                '|',
                COALESCE(transport_mode, 'Unknown mode'),
                COALESCE(agency_id, 'Unknown agency'),
                COALESCE(route_display_name, 'Unnamed route')
            ) = {sql_string(service_key)}
        )
        SELECT
            paths.route_id,
            paths.route_display_name,
            paths.transport_mode,
            paths.agency_name,
            paths.shape_id,
            paths.scheduled_trip_count,
            paths.map_point_count,
            paths.minimum_latitude,
            paths.maximum_latitude,
            paths.minimum_longitude,
            paths.maximum_longitude,
            TO_JSON(paths.map_path_coordinates) AS map_path_json
        FROM ROUTEPULSE.ANALYTICS.MAP_ROUTE_PATHS_RENDER AS paths
        JOIN selected_routes
            ON paths.route_id = selected_routes.static_route_id
        QUALIFY ROW_NUMBER() OVER (
            ORDER BY paths.scheduled_trip_count DESC, paths.map_point_count DESC
        ) = 1
        """
    )
    area_predicate = (
        ""
        if selected_area == "All regions"
        else f"AND event_region = {sql_string(selected_area)}"
    )
    line_stops = run_query(
        f"""
        SELECT
            station_display_name AS station_name,
            AVG(station_lat) AS station_lat,
            AVG(station_lon) AS station_lon,
            COUNT(*) AS stop_events,
            COUNT_IF(reported_delay_seconds IS NOT NULL) AS delay_events,
            COUNT_IF(reported_delay_seconds < -60) AS early_events,
            COUNT_IF(
                reported_delay_seconds BETWEEN -60 AND 60
            ) AS near_schedule_events,
            COUNT_IF(
                reported_delay_seconds > 60
                AND reported_delay_seconds <= 300
            ) AS minor_delay_events,
            COUNT_IF(reported_delay_seconds > 300) AS late_events,
            ROUND(
                100.0 * COUNT_IF(reported_delay_seconds IS NOT NULL)
                / NULLIF(COUNT(*), 0), 2
            ) AS delay_coverage,
            ROUND(
                100.0 * COUNT_IF(reported_delay_seconds > 300)
                / NULLIF(COUNT_IF(reported_delay_seconds IS NOT NULL), 0), 2
            ) AS late_percentage
        FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_LINE_FOCUS
        WHERE focus_service_key = {sql_string(service_key)}
          {area_predicate}
          AND station_display_name IS NOT NULL
          AND station_lat IS NOT NULL
          AND station_lon IS NOT NULL
        GROUP BY station_display_name
        ORDER BY station_name
        """
    )
    layers = []
    path_points = pd.DataFrame()
    if not line_path.empty:
        path_points = line_path.copy()
        path_points["path"] = path_points["MAP_PATH_JSON"].map(parse_json_value)
        path_points = path_points[
            path_points["path"].map(lambda path: path is not None and len(path) >= 2)
        ].copy()
        if not path_points.empty:
            path_points["color"] = [
                rgba(MODE_COLORS.get(selected_mode, "#60A5FA"), 225)
            ] * len(path_points)
            path_points["tooltip_title"] = line_label
            path_points["tooltip_detail"] = path_points.apply(
                lambda row: (
                    f"Representative scheduled path · "
                    f"{int(row['SCHEDULED_TRIP_COUNT']):,} static trips"
                ),
                axis=1,
            )
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=path_points,
                    id="selected-line-path",
                    get_path="path",
                    get_color="color",
                    get_width=5,
                    width_min_pixels=3,
                    pickable=True,
                    auto_highlight=True,
                )
            )

    stop_points = pd.DataFrame()
    if not line_stops.empty:
        stop_points = line_stops.rename(
            columns={
                "STATION_NAME": "station_name",
                "STATION_LAT": "station_lat",
                "STATION_LON": "station_lon",
                "LATE_PERCENTAGE": "late_percentage",
                "EARLY_EVENTS": "early_events",
                "NEAR_SCHEDULE_EVENTS": "near_schedule_events",
                "MINOR_DELAY_EVENTS": "minor_delay_events",
                "LATE_EVENTS": "late_events",
                "DELAY_EVENTS": "delay_events",
                "DELAY_COVERAGE": "delay_coverage",
            }
        ).copy()
        stop_points["fill_color"] = stop_points.apply(
            lambda row: point_color(
                float(row["late_percentage"] or 0), int(row["delay_events"])
            ),
            axis=1,
        )
        stop_points["point_radius"] = stop_points["delay_events"].map(
            lambda count: max(120, min(520, math.sqrt(float(count)) * 14))
        )
        stop_points["tooltip_title"] = stop_points["station_name"]
        stop_points["tooltip_detail"] = stop_points.apply(
            lambda row: (
                f"{float(row['late_percentage']):.1f}% over 5 minutes late · "
                f"{int(row['early_events']):,} >1 min early · "
                f"{int(row['near_schedule_events']):,} within 1 min · "
                f"{int(row['minor_delay_events']):,} 1–5 min late · "
                f"{int(row['late_events']):,} >5 min late · "
                f"{int(row['delay_events']):,} timed visits"
            ),
            axis=1,
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=stop_points,
                id="selected-line-stops",
                get_position="[station_lon, station_lat]",
                get_fill_color="fill_color",
                get_line_color=[255, 255, 255, 210],
                get_radius="point_radius",
                radius_min_pixels=4,
                radius_max_pixels=14,
                stroked=True,
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            )
        )

    if not layers:
        st.info("No map geometry is available for this passenger-facing line.")
        return

    if not stop_points.empty:
        study_area_stops = stop_points[
            stop_points["station_lat"].between(51.3, 53.6)
            & stop_points["station_lon"].between(11.2, 15.0)
        ]
        map_view = view_state_from_points(
            study_area_stops if not study_area_stops.empty else stop_points
        )
    else:
        path_row = path_points.iloc[0]
        map_view = pdk.ViewState(
            latitude=(
                float(path_row["MINIMUM_LATITUDE"])
                + float(path_row["MAXIMUM_LATITUDE"])
            )
            / 2,
            longitude=(
                float(path_row["MINIMUM_LONGITUDE"])
                + float(path_row["MAXIMUM_LONGITUDE"])
            )
            / 2,
            zoom=7.5,
        )
    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=map_view,
            layers=layers,
            tooltip={"html": "<b>{tooltip_title}</b><br/>{tooltip_detail}"},
        ),
        width="stretch",
        height=430,
    )
    st.caption(
        "The line uses one representative scheduled GTFS path; the dots show "
        "stops observed in the realtime sample. It is not a vehicle trace."
    )


def render_category_comparison():
    category_data = load_category_metrics()
    category_data = category_data[
        (category_data["SCOPE_MODE"] == selected_mode)
        & (category_data["SCOPE_REGION"] == selected_area)
        & (category_data["DELAY_EVENTS"] >= MIN_RANK_DELAY_EVENTS)
    ].copy()
    category_data = category_data.sort_values("LATE_PERCENTAGE", ascending=False)
    if category_data.empty:
        st.info("No service category meets the evidence threshold.")
        return
    category_data["RATE_LABEL"] = category_data["LATE_PERCENTAGE"].map(
        lambda value: f"{float(value):.1f}%"
    )
    chart = (
        alt.Chart(category_data)
        .mark_bar(color=RATE_BAR_COLOR, cornerRadiusEnd=5)
        .encode(
            y=alt.Y("GERMAN_SERVICE_CATEGORY:N", sort="-x", title=None),
            x=alt.X("LATE_PERCENTAGE:Q", title="Over 5 minutes late (%)"),
            tooltip=[
                alt.Tooltip("GERMAN_SERVICE_CATEGORY:N", title="Category"),
                alt.Tooltip("LATE_PERCENTAGE:Q", title="Over 5 min (%)", format=".2f"),
                alt.Tooltip("EARLY_EVENTS:Q", title=">1 min early", format=","),
                alt.Tooltip(
                    "NEAR_SCHEDULE_EVENTS:Q",
                    title="Within 1 min of schedule",
                    format=",",
                ),
                alt.Tooltip("MINOR_DELAY_EVENTS:Q", title="1–5 min late", format=","),
                alt.Tooltip("LATE_EVENTS:Q", title=">5 min late", format=","),
                alt.Tooltip(
                    "DELAY_EVENTS:Q",
                    title="Visits with timing information",
                    format=",",
                ),
                alt.Tooltip(
                    "DELAY_COVERAGE:Q",
                    title="Timing-data availability (%)",
                    format=".2f",
                ),
            ],
        )
        .properties(height=max(180, 48 * len(category_data)))
    )
    labels = (
        alt.Chart(category_data)
        .mark_text(align="left", baseline="middle", dx=6, color="#E5E7EB")
        .encode(
            y=alt.Y("GERMAN_SERVICE_CATEGORY:N", sort="-x"),
            x="LATE_PERCENTAGE:Q",
            text="RATE_LABEL:N",
        )
    )
    st.altair_chart(chart + labels, width="stretch")


def render_when():
    st.header("When were services early, near schedule or late?")
    metric_choice = selected_hour_metric
    hourly = load_headline_hour_metrics()
    hourly = hourly[
        (hourly["SCOPE_MODE"] == selected_mode)
        & (hourly["SCOPE_REGION"] == selected_area)
    ].copy()
    hourly = hourly.sort_values("OBSERVATION_HOUR_BERLIN")
    if hourly.empty:
        st.info("No hourly observations are available for this mode.")
        return
    hourly["OBSERVATION_HOUR_BERLIN"] = pd.to_datetime(
        hourly["OBSERVATION_HOUR_BERLIN"]
    )
    hourly["OBSERVATION_DAY"] = hourly["OBSERVATION_HOUR_BERLIN"].dt.floor("D")
    day_summary = (
        hourly.groupby("OBSERVATION_DAY", as_index=False)
        .agg(
            DAY_START=("OBSERVATION_HOUR_BERLIN", "min"),
            DAY_END=("OBSERVATION_HOUR_BERLIN", "max"),
        )
        .sort_values("OBSERVATION_DAY")
    )
    day_summary["DAY_CENTER"] = (
        day_summary["DAY_START"]
        + (day_summary["DAY_END"] - day_summary["DAY_START"]) / 2
    )
    day_summary["DAY_LABEL"] = day_summary["OBSERVATION_DAY"].dt.strftime("%A %d %b")
    first_day_index = day_summary.index[0]
    last_day_index = day_summary.index[-1]
    if (
        day_summary.loc[first_day_index, "DAY_START"]
        > day_summary.loc[first_day_index, "OBSERVATION_DAY"]
    ):
        day_summary.loc[first_day_index, "DAY_LABEL"] += " (partial)"
    if day_summary.loc[last_day_index, "DAY_END"] < (
        day_summary.loc[last_day_index, "OBSERVATION_DAY"] + pd.Timedelta(hours=23)
    ):
        day_summary.loc[last_day_index, "DAY_LABEL"] += " (partial)"
    day_boundaries = day_summary.iloc[1:][["OBSERVATION_DAY"]].copy()
    measure_column = (
        "LATE_PERCENTAGE"
        if metric_choice == "% over 5 minutes"
        else "P90_DELAY_MINUTES"
    )
    measure_title = (
        "Over 5 minutes late (%)"
        if metric_choice == "% over 5 minutes"
        else "P90 reported delay (minutes)"
    )
    hourly["ELIGIBLE"] = hourly["DELAY_EVENTS"] >= MIN_HEADLINE_HOUR_DELAY_EVENTS
    hourly["ELIGIBLE_MEASURE"] = hourly[measure_column].where(hourly["ELIGIBLE"])
    eligible_points = hourly[hourly["ELIGIBLE"] & hourly[measure_column].notna()]
    low_sample_points = hourly[(~hourly["ELIGIBLE"]) & hourly[measure_column].notna()]
    partial_rows = hourly[
        hourly["IS_PARTIAL_COLLECTION_HOUR"].fillna(False)
        & hourly[measure_column].notna()
    ]

    shared_x = alt.X(
        "OBSERVATION_HOUR_BERLIN:T",
        title=None,
        axis=alt.Axis(labels=False, ticks=False),
    )
    measure_tooltips = [
        alt.Tooltip(
            "OBSERVATION_HOUR_BERLIN:T",
            title="Hour",
            format="%a %d %b, %H:%M",
        ),
        alt.Tooltip(f"{measure_column}:Q", title=measure_title, format=".2f"),
        alt.Tooltip("EARLY_EVENTS:Q", title=">1 min early", format=","),
        alt.Tooltip(
            "NEAR_SCHEDULE_EVENTS:Q",
            title="Within 1 min of schedule",
            format=",",
        ),
        alt.Tooltip("MINOR_DELAY_EVENTS:Q", title="1–5 min late", format=","),
        alt.Tooltip("LATE_EVENTS:Q", title=">5 min late", format=","),
        alt.Tooltip(
            "DELAY_EVENTS:Q",
            title="Visits with timing information",
            format=",",
        ),
        alt.Tooltip("IS_PARTIAL_COLLECTION_HOUR:N", title="Partial hour"),
    ]
    eligible_line = (
        alt.Chart(hourly)
        .mark_line(color=RATE_BAR_COLOR, strokeWidth=2.5)
        .encode(
            x=shared_x,
            y=alt.Y("ELIGIBLE_MEASURE:Q", title=measure_title),
            tooltip=measure_tooltips,
        )
    )
    solid_points = (
        alt.Chart(eligible_points)
        .mark_point(color=RATE_BAR_COLOR, filled=True, size=52)
        .encode(
            x=shared_x,
            y=alt.Y(f"{measure_column}:Q", title=measure_title),
            tooltip=measure_tooltips,
        )
    )
    hollow_points = (
        alt.Chart(low_sample_points)
        .mark_point(color="#9CA3AF", filled=False, size=70, strokeWidth=2)
        .encode(
            x=shared_x,
            y=alt.Y(f"{measure_column}:Q", title=measure_title),
            tooltip=measure_tooltips,
        )
    )
    partial_points = (
        alt.Chart(partial_rows)
        .mark_point(shape="diamond", size=120, color="#F87171", filled=True)
        .encode(
            x=shared_x,
            y=alt.Y(f"{measure_column}:Q", title=measure_title),
            tooltip=measure_tooltips,
        )
    )
    top_panel = alt.layer(
        eligible_line,
        solid_points,
        hollow_points,
        partial_points,
    ).properties(height=245)
    volume_panel = (
        alt.Chart(hourly)
        .mark_bar(color=COVERAGE_BAR_COLOR, opacity=0.72)
        .encode(
            x=alt.X(
                "OBSERVATION_HOUR_BERLIN:T",
                title=None,
                axis=alt.Axis(
                    format="%H:%M",
                    tickCount=14,
                    labelOverlap="greedy",
                ),
            ),
            y=alt.Y("DELAY_EVENTS:Q", title="Stop visits with timing information"),
            tooltip=[
                alt.Tooltip(
                    "OBSERVATION_HOUR_BERLIN:T",
                    title="Hour",
                    format="%a %d %b, %H:%M",
                ),
                alt.Tooltip(
                    "DELAY_EVENTS:Q",
                    title="Visits with timing information",
                    format=",",
                ),
                alt.Tooltip("IS_PARTIAL_COLLECTION_HOUR:N", title="Partial hour"),
            ],
        )
        .properties(height=125)
    )
    day_axis_holder = (
        alt.Chart(day_summary)
        .mark_point(opacity=0)
        .encode(
            x=alt.X(
                "DAY_CENTER:T",
                axis=alt.Axis(
                    title="Observation hour and day (Berlin time)",
                    labels=False,
                    ticks=False,
                    domain=False,
                ),
            ),
            y=alt.value(12),
        )
    )
    day_boundary_rules = (
        alt.Chart(day_boundaries)
        .mark_rule(color="#64748B", strokeDash=[4, 4], opacity=0.75)
        .encode(x=alt.X("OBSERVATION_DAY:T", axis=None))
    )
    day_labels = (
        alt.Chart(day_summary)
        .mark_text(color="#CBD5E1", fontWeight=600, baseline="middle")
        .encode(
            x=alt.X("DAY_CENTER:T", axis=None),
            y=alt.value(12),
            text="DAY_LABEL:N",
        )
    )
    day_band = alt.layer(
        day_axis_holder,
        day_boundary_rules,
        day_labels,
    ).properties(height=26)
    st.altair_chart(
        alt.vconcat(
            top_panel,
            volume_panel,
            day_band,
            spacing=8,
        ).resolve_scale(x="shared"),
        width="stretch",
    )
    st.caption(
        "Solid points have at least 100 timed visits. Hollow grey points have "
        "fewer than 100 and do not connect into the headline line. Red diamonds "
        "mark the partial first and last collection hours."
    )

    eligible = hourly[
        (hourly["DELAY_EVENTS"] >= MIN_HEADLINE_HOUR_DELAY_EVENTS)
        & (~hourly["IS_PARTIAL_COLLECTION_HOUR"].fillna(False))
    ]
    if eligible.empty:
        st.info(
            "No complete hour meets the minimum evidence threshold for a "
            "headline comparison."
        )
    else:
        peak = eligible.loc[eligible[measure_column].idxmax()]
        peak_time = pd.to_datetime(peak["OBSERVATION_HOUR_BERLIN"])
        if metric_choice == "% over 5 minutes":
            line_scope = (
                "all observed" if selected_mode == "All modes" else selected_mode
            )
            takeaway = (
                f"Across {line_scope} lines, among complete hours with at least "
                f"{MIN_HEADLINE_HOUR_DELAY_EVENTS:,} timed visits, "
                f"{peak_time:%A %H:%M} had the highest observed share over five "
                f"minutes late: {float(peak['LATE_PERCENTAGE']):.1f}% of "
                f"{int(peak['DELAY_EVENTS']):,} timed visits"
                f"{evidence_suffix(int(peak['DELAY_EVENTS']), float(peak['DELAY_COVERAGE']))}."
            )
        else:
            line_scope = (
                "all observed" if selected_mode == "All modes" else selected_mode
            )
            takeaway = (
                f"Across {line_scope} lines, among complete hours with at least "
                f"{MIN_HEADLINE_HOUR_DELAY_EVENTS:,} timed visits, "
                f"{peak_time:%A %H:%M} had the highest observed P90 reported "
                f"delay: {float(peak['P90_DELAY_MINUTES']):.2f} minutes from "
                f"{int(peak['DELAY_EVENTS']):,} timed visits"
                f"{evidence_suffix(int(peak['DELAY_EVENTS']), float(peak['DELAY_COVERAGE']))}."
            )
        st.info(f"**Observed takeaway:** {takeaway}")


def render_data_quality():
    st.header("How complete is our timing data?")
    st.caption(
        "Shorter bars mean more observed stop visits were missing timing "
        "information, so we know less about how they compared with the timetable. "
        "This measures data availability—not punctuality or accuracy."
    )
    st.subheader("Timing information available by transport mode")
    st.caption(
        f"This compares every mode within {selected_area}; it does not change "
        "with the selected transport-mode control."
    )
    coverage_by_mode = load_scope_metrics()
    coverage_by_mode = coverage_by_mode[
        (coverage_by_mode["SCOPE_MODE"] != "All modes")
        & (coverage_by_mode["SCOPE_REGION"] == selected_area)
    ].copy()
    coverage_by_mode = coverage_by_mode.rename(
        columns={
            "SCOPE_MODE": "TRANSPORT_MODE",
            "STOP_EVENTS": "UNIQUE_STOP_EVENTS",
            "DELAY_EVENTS": "DELAY_REPORTED_EVENTS",
            "DELAY_COVERAGE": "DELAY_DATA_AVAILABILITY",
        }
    ).sort_values("DELAY_DATA_AVAILABILITY", ascending=False)
    coverage_by_mode["AVAILABILITY_GROUP"] = coverage_by_mode[
        "DELAY_DATA_AVAILABILITY"
    ].map(
        lambda value: (
            "Very complete (>90%)"
            if float(value) > 90
            else (
                "Mostly complete (75–90%)" if float(value) >= 75 else "Partial (<75%)"
            )
        )
    )
    coverage_by_mode["AVAILABILITY_LABEL"] = coverage_by_mode.apply(
        lambda row: (
            f"{float(row['DELAY_DATA_AVAILABILITY']):.1f}% · "
            f"{row['AVAILABILITY_GROUP'].split(' (')[0]}"
        ),
        axis=1,
    )
    coverage_chart = (
        alt.Chart(coverage_by_mode)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("TRANSPORT_MODE:N", sort="-x", title=None),
            x=alt.X(
                "DELAY_DATA_AVAILABILITY:Q",
                title="Observed stop visits with timing information (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.Color(
                "AVAILABILITY_GROUP:N",
                title="How much timing information is available",
                scale=alt.Scale(
                    domain=[
                        "Very complete (>90%)",
                        "Mostly complete (75–90%)",
                        "Partial (<75%)",
                    ],
                    range=["#64748B", "#94A3B8", "#F59E0B"],
                ),
            ),
            tooltip=[
                alt.Tooltip("TRANSPORT_MODE:N", title="Mode"),
                alt.Tooltip("AVAILABILITY_GROUP:N", title="Availability group"),
                alt.Tooltip(
                    "DELAY_DATA_AVAILABILITY:Q",
                    title="Timing-data availability (%)",
                    format=".2f",
                ),
                alt.Tooltip(
                    "UNIQUE_STOP_EVENTS:Q", title="Observed stop visits", format=","
                ),
                alt.Tooltip(
                    "DELAY_REPORTED_EVENTS:Q",
                    title="Visits with timing information",
                    format=",",
                ),
                alt.Tooltip("EARLY_EVENTS:Q", title=">1 min early", format=","),
                alt.Tooltip(
                    "NEAR_SCHEDULE_EVENTS:Q",
                    title="Within 1 min of schedule",
                    format=",",
                ),
                alt.Tooltip("MINOR_DELAY_EVENTS:Q", title="1–5 min late", format=","),
                alt.Tooltip("LATE_EVENTS:Q", title=">5 min late", format=","),
            ],
        )
        .properties(height=290)
    )
    coverage_labels = (
        alt.Chart(coverage_by_mode)
        .mark_text(align="left", baseline="middle", dx=6, color="#E5E7EB")
        .encode(
            y=alt.Y("TRANSPORT_MODE:N", sort="-x"),
            x="DELAY_DATA_AVAILABILITY:Q",
            text="AVAILABILITY_LABEL:N",
        )
    )
    st.altair_chart(coverage_chart + coverage_labels, width="stretch")

    region_metrics = load_region_metrics()
    region_metrics = region_metrics[
        region_metrics["SCOPE_MODE"] == selected_mode
    ].copy()
    region_rows = []
    displayed_regions = (
        REGION_ORDER if selected_area == "All regions" else [selected_area]
    )
    for region_name in displayed_regions:
        match = region_metrics[region_metrics["EVENT_REGION"] == region_name]
        if match.empty:
            region_rows.append(
                {
                    "Observed stop region": region_name,
                    "Unique stop events": 0,
                    "Events with timing data": 0,
                    "Timing-data availability (%)": 0.0,
                    "Reported >1 min early": 0,
                    "Within 1 min": 0,
                    "Reported 1–5 min late": 0,
                    "Reported >5 min late": 0,
                    "Timing unavailable": 0,
                    "Over 5 minutes late (%)": None,
                }
            )
        else:
            row = match.iloc[0]
            region_rows.append(
                {
                    "Observed stop region": region_name,
                    "Unique stop events": int(row["UNIQUE_STOP_EVENTS"]),
                    "Events with timing data": int(row["EVENTS_WITH_TIMING_DATA"]),
                    "Timing-data availability (%)": float(
                        row["TIMING_DATA_AVAILABILITY"]
                    ),
                    "Reported >1 min early": int(row["EARLY_EVENTS"]),
                    "Within 1 min": int(row["NEAR_SCHEDULE_EVENTS"]),
                    "Reported 1–5 min late": int(row["MINOR_DELAY_EVENTS"]),
                    "Reported >5 min late": int(row["LATE_EVENTS"]),
                    "Timing unavailable": int(row["TIMING_UNAVAILABLE_EVENTS"]),
                    "Over 5 minutes late (%)": float(row["OVER_FIVE_MINUTES_LATE"]),
                }
            )
    region_table = pd.DataFrame(region_rows)
    total_events = int(region_table["Unique stop events"].sum())
    total_timed_events = int(region_table["Events with timing data"].sum())
    region_table = pd.concat(
        [
            region_table,
            pd.DataFrame(
                [
                    {
                        "Observed stop region": "Total",
                        "Unique stop events": total_events,
                        "Events with timing data": total_timed_events,
                        "Timing-data availability (%)": (
                            100.0 * total_timed_events / total_events
                            if total_events
                            else 0.0
                        ),
                        "Reported >1 min early": int(
                            region_table["Reported >1 min early"].sum()
                        ),
                        "Within 1 min": int(region_table["Within 1 min"].sum()),
                        "Reported 1–5 min late": int(
                            region_table["Reported 1–5 min late"].sum()
                        ),
                        "Reported >5 min late": int(
                            region_table["Reported >5 min late"].sum()
                        ),
                        "Timing unavailable": int(
                            region_table["Timing unavailable"].sum()
                        ),
                        "Over 5 minutes late (%)": (
                            100.0
                            * region_table["Reported >5 min late"].sum()
                            / total_timed_events
                            if total_timed_events
                            else None
                        ),
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    st.subheader("Where were the selected stop visits recorded?")
    st.caption(f"Selected scope: {selected_mode} · {selected_area}.")
    region_display = region_table.rename(
        columns={
            "Unique stop events": "Observed stop visits",
            "Events with timing data": "Visits with timing information",
            "Timing-data availability (%)": "Timing-data availability (%)",
            "Over 5 minutes late (%)": "Reported over 5 minutes late (%)",
        }
    ).copy()
    region_display["Observed stop visits"] = region_display["Observed stop visits"].map(
        lambda value: f"{int(value):,}"
    )
    region_display["Visits with timing information"] = region_display[
        "Visits with timing information"
    ].map(lambda value: f"{int(value):,}")
    for count_column in (
        "Reported >1 min early",
        "Within 1 min",
        "Reported 1–5 min late",
        "Reported >5 min late",
        "Timing unavailable",
    ):
        region_display[count_column] = region_display[count_column].map(
            lambda value: f"{int(value):,}"
        )
    region_display["Timing-data availability (%)"] = region_display[
        "Timing-data availability (%)"
    ].map(lambda value: f"{float(value):.1f}%")
    region_display["Reported over 5 minutes late (%)"] = region_display[
        "Reported over 5 minutes late (%)"
    ].map(lambda value: "—" if pd.isna(value) else f"{float(value):.1f}%")
    region_style = region_display.style.apply(
        lambda row: (
            ["background-color: rgba(100, 116, 139, 0.20)"] * len(row)
            if row["Observed stop region"] == "Unmatched/unknown"
            else [""] * len(row)
        ),
        axis=1,
    )
    st.dataframe(
        region_style,
        width="stretch",
        hide_index=True,
    )
    if selected_area == "All regions":
        st.caption(
            "The grey Unmatched/unknown row contains realtime stop visits without "
            "a matched static station and/or usable coordinates, so they could not "
            "be assigned to Berlin, Brandenburg or outside both states. It remains "
            "included in the all-region total."
        )
    if total_events != int(event_kpi["STOP_EVENTS"]):
        st.error(
            "Regional rows do not reconcile to the selected-mode stop-visit total. "
            "Review EVENT_REGION before publishing."
        )
    elif (
        selected_mode == "All modes"
        and selected_area == "All regions"
        and total_events != 1_755_847
    ):
        st.warning(
            f"The all-mode total is {total_events:,}, not the validated "
            "1,755,847. Confirm that the source collection has not changed."
        )
    else:
        st.success(
            f"Regional rows reconcile to {total_events:,} selected-scope "
            "observed stop visits."
        )

    st.subheader("Limitations")
    st.markdown(
        f"""
        - The collection spans only **{collection_hours:.1f} hours**: Friday
          afternoon/evening and a weekend, without a normal weekday commute.
        - Timing values are feed predictions as reported, not independently
          measured arrivals.
        - Missing timing values are excluded from timing rates and never treated
          as zero.
        - Events cluster within trips, hours and disruptions; rankings are
          descriptive and preliminary.
        - The dashboard identifies where reported serious delay was higher; it does
          not establish causes, passenger impact or revenue effects.
        """
    )

    with st.expander("About the data", expanded=False):
        render_about_data()


def render_about_data():
    validation = run_query(
        """
        SELECT
            COUNT(*) AS event_rows,
            COUNT(DISTINCT observed_route_id) AS observed_route_ids,
            COUNT_IF(station_name IS NULL) AS events_without_station,
            COUNT_IF(static_route_id IS NULL) AS events_without_catalogued_route,
            COUNT_IF(transport_mode IS NULL) AS events_without_mode
        FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
        """
    ).iloc[0]
    route_coverage = run_query(
        """
        WITH static_routes AS (
            SELECT
                CASE route_type
                    WHEN 3 THEN 'Bus'
                    WHEN 100 THEN 'Regional rail'
                    WHEN 106 THEN 'Regional rail'
                    WHEN 109 THEN 'S-Bahn'
                    WHEN 400 THEN 'U-Bahn'
                    WHEN 700 THEN 'Bus'
                    WHEN 900 THEN 'Tram'
                    ELSE 'Needs review'
                END AS transport_mode,
                COUNT(DISTINCT route_id) AS static_route_ids
            FROM ROUTEPULSE.RAW.GTFS_ROUTES
            GROUP BY transport_mode
        ),
        observed_routes AS (
            SELECT
                transport_mode,
                COUNT(DISTINCT static_route_id) AS observed_route_ids
            FROM ROUTEPULSE.ANALYTICS.ROUTE_GEOGRAPHIC_CATALOG
            GROUP BY transport_mode
        )
        SELECT
            static_routes.transport_mode AS "Transport mode",
            static_routes.static_route_ids AS "Static route IDs",
            COALESCE(observed_routes.observed_route_ids, 0) AS "Observed route IDs"
        FROM static_routes
        LEFT JOIN observed_routes USING (transport_mode)
        ORDER BY static_routes.static_route_ids DESC
        """
    )
    st.markdown(
        f"**Pipeline:** VBB GTFS-Realtime and Static → Python/PyArrow → S3 → "
        f"Snowflake → Streamlit. **{int(raw_kpi['STOP_OBSERVATIONS']):,}** raw "
        f"stop-status rows were consolidated to "
        f"**{int(validation['EVENT_ROWS']):,}** observed stop visits. The validated "
        "event key had zero duplicates."
    )
    st.dataframe(route_coverage, width="stretch", hide_index=True)
    st.caption(
        "A route present in static GTFS but absent from this realtime sample is "
        "static-only for this window; that does not prove the service does not run."
    )

    potsdam = run_query(
        """
        WITH expected_lines(line_name) AS (
            SELECT column1
            FROM VALUES ('91'), ('92'), ('93'), ('94'), ('96'), ('98'), ('99')
        ),
        static_lines AS (
            SELECT DISTINCT route_short_name AS line_name
            FROM ROUTEPULSE.RAW.GTFS_ROUTES
            WHERE route_type = 900
              AND route_short_name IN ('91', '92', '93', '94', '96', '98', '99')
        ),
        observed_lines AS (
            SELECT DISTINCT route_display_name AS line_name
            FROM ROUTEPULSE.ANALYTICS.STOP_EVENTS_GEOGRAPHIC
            WHERE transport_mode = 'Tram'
              AND route_display_name IN ('91', '92', '93', '94', '96', '98', '99')
        )
        SELECT
            COUNT_IF(static_lines.line_name IS NOT NULL) AS static_lines_found,
            COUNT_IF(observed_lines.line_name IS NOT NULL) AS realtime_lines_observed,
            LISTAGG(
                IFF(observed_lines.line_name IS NULL, expected_lines.line_name, NULL),
                ', '
            ) WITHIN GROUP (ORDER BY expected_lines.line_name) AS static_only_lines
        FROM expected_lines
        LEFT JOIN static_lines USING (line_name)
        LEFT JOIN observed_lines USING (line_name)
        """
    ).iloc[0]
    st.markdown(
        f"**Potsdam tram reference:** {int(potsdam['STATIC_LINES_FOUND']):,} "
        f"lines existed in the static feed; "
        f"{int(potsdam['REALTIME_LINES_OBSERVED']):,} produced realtime "
        f"observations. Line(s) {potsdam['STATIC_ONLY_LINES'] or 'none'} had no "
        "realtime observation during this sample."
    )

    details = pd.DataFrame(
        {
            "Measure": [
                "All observed stop visits",
                "Observed technical route IDs",
                "Stop visits without a station match",
                "Stop visits without a catalogued route",
                "Stop visits without a transport mode",
            ],
            "Value": [
                int(validation["EVENT_ROWS"]),
                int(validation["OBSERVED_ROUTE_IDS"]),
                int(validation["EVENTS_WITHOUT_STATION"]),
                int(validation["EVENTS_WITHOUT_CATALOGUED_ROUTE"]),
                int(validation["EVENTS_WITHOUT_MODE"]),
            ],
        }
    )
    details["Value"] = details["Value"].map(lambda value: f"{int(value):,}")
    st.dataframe(
        details,
        width="stretch",
        hide_index=True,
    )
    st.markdown(
        "**Metric definitions:** an observed stop visit is the latest retained "
        "snapshot for a trip, service date, stop sequence and stop. A timed visit "
        "is reported early when its signed timing value is below −60 seconds, "
        "within 1 minute of schedule from −60 through +60 seconds, 1–5 minutes "
        "late above +60 through +300 seconds, and seriously late above +300 "
        "seconds. Timing-data availability is the share of observed stop visits "
        "with timing information; P90 is the value at or below which 90% of "
        "reported timing values fall. A passenger-facing "
        "line is a transport mode + GTFS agency + displayed route name; multiple "
        "technical route IDs can belong to one line."
    )
    st.caption(
        "Map paths use browser-simplified GTFS shapes; unsimplified geometry "
        "remains in the Snowflake MAP_ROUTE_PATHS table. Core models are built "
        "by 09_unique_stop_events.sql, 10_geographic_event_enrichment.sql and "
        "11_line_focus_models.sql."
    )


if selected_view == "Network map":
    render_network_map()
elif selected_view == "Stations":
    render_stations()
elif selected_view == "Lines":
    render_lines()
elif selected_view == "When":
    render_when()
else:
    render_data_quality()

st.caption(
    "Source: VBB GTFS-Realtime and GTFS Static data processed through Python, "
    "PyArrow, Amazon S3 and Snowflake. Results describe this collection window only."
)
