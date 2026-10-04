# Timing-category validation — 2026-10-04

The updated presentation models and `sql/15_validate_timing_categories.sql`
were executed in Snowflake by the project owner before deployment.

## Aggregate reconciliation

| Model | Aggregate rows | Timing-category mismatches | Availability mismatches | All rows reconcile |
|---|---:|---:|---:|---|
| `DASHBOARD_CATEGORY_METRICS` | 21 | 0 | 0 | `TRUE` |
| `DASHBOARD_HOUR_METRICS` | 676 | 0 | 0 | `TRUE` |
| `DASHBOARD_LINE_METRICS` | 4,004 | 0 | 0 | `TRUE` |
| `DASHBOARD_REGION_METRICS` | 20 | 0 | 0 | `TRUE` |
| `DASHBOARD_SCOPE_METRICS` | 17 | 0 | 0 | `TRUE` |
| `DASHBOARD_STATION_METRICS` | 46,861 | 0 | 0 | `TRUE` |

For every aggregate row, the four timed categories reproduce the timed
population, and the timed plus unavailable categories reproduce the total
observed population.

## Serious-delay preservation

| Check | Result |
|---|---:|
| Direct source count where `reported_delay_seconds > 300` | 87,587 |
| Dashboard all-mode/all-region serious-delay count | 87,587 |
| Counts match | `TRUE` |

This confirms that adding early, on/near-schedule, minor-delay and unavailable
counts did not change the established more-than-five-minute serious-delay
measure.

## Local release checks

- Ruff lint: passed.
- Python compilation: passed.
- Streamlit static contract checks: passed.
- Community Cloud packaging checks: passed.
- Python unit tests: 37 passed.

The remaining release evidence is the public-app smoke test after the commit is
deployed by Streamlit Community Cloud.

## Public-app smoke test

The first deployment displayed the new timing distribution and stakeholder
wording correctly. Area and mode filters switched to Brandenburg bus results,
the station view loaded, and the data-quality view reconciled 289,860 selected
stop visits. Browser inspection exposed a Deck.gl error in the redundant
top-three station-name text layer. That layer was removed while retaining the
numbered map markers, ranking labels and hover tooltips.

The follow-up deployment passed in a clean browser session:

- the station view rendered with no browser console errors;
- the area and mode controls switched to `Brandenburg · Bus`;
- the data-quality view loaded for that scope;
- its regional rows reconciled to 289,860 selected-scope stop visits; and
- no browser console errors were recorded after the filter and view changes.

## Timing-distribution display correction

The percentage-only chart was replaced after a public-app check showed its
0–100% scale but not the category marks. The replacement is a deterministic
stacked distribution with four directly labelled result cards, so it does not
depend on hover interaction and remains readable when the main content area is
narrow.

The public all-mode/all-region view was checked after deployment and displayed:

| Timing category | Share | Timed stop visits |
|---|---:|---:|
| Reported more than 1 minute early | 5.0% | 75,983 |
| On/near schedule, within 1 minute | 67.8% | 1,035,925 |
| 1–5 minutes late | 21.5% | 329,195 |
| More than 5 minutes late | 5.7% | 87,587 |

The four counts total 1,528,690 timed stop visits, and the displayed shares
partition that population to 100% subject to one-decimal rounding. The existing
area, transport-mode and analysis controls were unchanged, and the correction
introduced no additional Snowflake query.
