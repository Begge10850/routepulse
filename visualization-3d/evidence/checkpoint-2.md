# Checkpoint 2 verification

Date: 2026-10-10  
Branch: `codex/routepulse-3d`

## Implemented

- OpenFreeMap dark geographic basemap through MapLibre with automatic OpenFreeMap, OpenMapTiles and OpenStreetMap attribution;
- hover tooltip for line, mode and representative termini;
- direct route selection from the deck.gl paths;
- highlighted selected path and stop markers while other services are dimmed;
- route panel with operator, termini and ordered representative stops;
- reported-delay journey bars, timing availability, timed-visit counts, median, P90 and serious-delay share;
- explicit missing-timing state;
- responsive desktop and phone journey panels.

## Delay-method reconciliation

The DuckDB export applies the retained RoutePulse event key and keeps the latest snapshot update for each trip, service date, stop sequence and stop ID.

| Measure | Result |
|---|---:|
| Raw stop-time update rows scanned | 94,839,920 |
| Unique observed stop visits retained | 1,755,847 |
| Visits with usable reported timing | 1,528,723 |
| Timing availability | 87.06% |
| Realtime route IDs represented | 984 |
| Route/stop aggregate pairs | 42,840 |

The 1,755,847 retained events exactly match the previously validated RoutePulse total documented in the handover.

## Test results

| Check | Result |
|---|---|
| Vitest control and journey-panel behaviour | 4 passed |
| Python geometry, ordered-stop and delay-category contract | passed |
| Timing categories sum to timed observations | passed for every exported route stop |
| ESLint | passed |
| TypeScript + Vite production build | passed |
| Desktop route click and populated journey | passed |
| Phone route click and missing-timing state | passed |
| Basemap attribution exposed in accessibility tree | passed |

## Limitations

- Ordered stops describe one representative scheduled direction, not every route variant.
- Stop metrics pool unique observed visits at that route and stop across the short 39.5-hour Friday/weekend sample; they do not describe a particular vehicle's end-to-end run.
- GTFS-Realtime timing values may be predictions. They are not independently verified actual arrival times.
- Routes absent from the retained realtime sample correctly show no reported timing.
- The OpenFreeMap public tile service requires network access. A deployment decision and real-device performance test remain pending.
- The production JavaScript build is functional but still produces large-chunk warnings; code splitting should be addressed before portfolio integration.
