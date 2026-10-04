# RoutePulse timing methodology

## What RoutePulse measures

RoutePulse analyses one retained observation for each vehicle trip at each stop in
the sample. This unit is called an **observed stop visit**. The underlying
GTFS-Realtime field is a signed timing difference in seconds:

- a negative value means the service was reported ahead of the timetable;
- zero means it matched the timetable exactly;
- a positive value means it was reported behind the timetable; and
- a missing value means that no usable timing comparison was available.

A populated timing value therefore does **not** automatically mean the service was
late. It only means the feed supplied information that can be compared with the
timetable.

## RoutePulse timing categories

Every observed stop visit belongs to exactly one of these categories:

| Category | SQL condition | Plain-language meaning |
|---|---|---|
| Reported more than 1 minute early | `reported_delay_seconds < -60` | More than 60 seconds ahead of schedule |
| On/near schedule (within 1 minute) | `reported_delay_seconds BETWEEN -60 AND 60` | From exactly 1 minute early through exactly 1 minute late |
| Reported 1–5 minutes late | `reported_delay_seconds > 60 AND reported_delay_seconds <= 300` | More than 1 minute but no more than 5 minutes behind schedule |
| Reported more than 5 minutes late | `reported_delay_seconds > 300` | More than 5 minutes behind schedule |
| Timing unavailable | `reported_delay_seconds IS NULL` | No usable timing value was supplied |

The first four categories form the **timed population**. They are mutually
exclusive and must add up to the number of visits with timing information. Adding
the timing-unavailable visits must then reproduce the total observed stop visits.

## Denominators and dashboard measures

The serious-delay share uses only visits with timing information:

```text
serious-delay share = visits reported >5 minutes late / timed visits
```

Timing-data availability uses all observed visits:

```text
timing-data availability = timed visits / all observed stop visits
```

Missing timing values are never converted to zero and never counted as on time.
This distinction matters: a route can appear punctual among its timed visits while
still having incomplete timing coverage.

## Why RoutePulse uses a five-minute threshold

RoutePulse uses more than five minutes behind schedule as its headline
**serious-delay** threshold. It creates a consistent comparison across modes and is
close to the public VBB regional-rail punctuality definition, where a train is
counted as punctual if it is less than six minutes late. It is not claimed to be a
single contractual rule used identically by every bus, tram, U-Bahn, S-Bahn, and
regional-rail operator.

Public reporting conventions differ. For example, BVG has published punctuality
definitions that distinguish early departures and mode-specific late thresholds,
while Deutsche Bahn publishes its own passenger and operational punctuality
measures. RoutePulse therefore labels its buckets as **RoutePulse analytical
categories** and explains the boundaries directly in the app.

References:

- [GTFS-Realtime reference](https://gtfs.org/documentation/realtime/reference/)
- [VBB regional-rail quality methodology](https://unternehmen.vbb.de/qualitaet-im-oepnv/regionalverkehr/methodik/)
- [BVG 2024 annual report](https://www.bvg.de/dam/jcr%3A70a93fa8-74b3-4b45-917f-41d7494576fa/bvg-geschaeftsbericht-2024.pdf)
- [Deutsche Bahn glossary and punctuality definitions](https://zbir.deutschebahn.com/2025/en/glossary/)

## What P90 reported delay means

P90 is the 90th percentile of the available signed timing values. If P90 is 3.7
minutes, 90% of the timed visits had a reported delay of 3.7 minutes or less, and
the remaining 10% had a larger reported delay. P90 is useful because it describes
the difficult upper end of the distribution without being controlled by a single
extreme observation. It complements—not replaces—the category counts and the
serious-delay share.

## Predictions, not confirmed outcomes

GTFS-Realtime trip updates may contain predictions. RoutePulse says **reported
early** and **reported late** because these values are not independently verified
actual arrival or departure timestamps. The analysis describes what the feed
reported during the collection window; it does not prove a cause, passenger
impact, contractual breach, or operator performance over a normal month.

## Evidence safeguards

- Station and line rankings begin at 100 timed visits.
- Results based on 100–299 timed visits are visually marked as early signals.
- Timing-data availability below 60% is called out as limited coverage.
- The first and last collection hours are marked as partial and excluded from the
  headline complete-hour comparison.
- Berlin and Brandenburg can be analysed separately so dense Berlin services do
  not obscure Brandenburg patterns.
- The sample covers only 39.5 Friday/weekend hours, so rankings are preliminary.

## Validation and reproducibility

Run the scripts in this order:

1. `sql/12_dashboard_ui_models.sql` recreates the presentation aggregates.
2. `sql/15_validate_timing_categories.sql` checks the category totals.

For every aggregate row, both statements must be true:

```text
timed visits = early + near schedule + minor delay + serious delay
all observed visits = timed visits + timing unavailable
```

The validation script also confirms that the dashboard's serious-delay count is
identical to a direct source count using `reported_delay_seconds > 300`.

## Interview-ready explanation

“I began with GTFS-Realtime stop updates and consolidated repeated snapshots to
one observation per trip and stop. The feed's timing field is signed, so a value
can mean early, near schedule, or late—it is not automatically a delay. I created
five mutually exclusive categories, kept missing timing separate, and pre-aggregated
them by mode, region, station, line, and hour in Snowflake. I validated that the
four timed categories reproduce the timed denominator and that timed plus missing
reproduce the total. Streamlit reads those compact tables, which keeps filters fast
and makes every percentage's denominator explicit.”
