# RoutePulse 3D network prototype

An isolated React, TypeScript, deck.gl and MapLibre prototype that renders representative scheduled VBB route shapes as five geographically aligned, independently selectable layers. The vertical exploded arrangement is an interface metaphor; it does not represent physical elevation or tunnel depth.

This folder does not import or change the existing Streamlit dashboard. Browser data are static, compact and contain no Snowflake or AWS credentials.

## Run locally

```bash
npm install
python3 -m venv .venv-export
.venv-export/bin/python -m pip install -r requirements-export.txt
.venv-export/bin/python scripts/aggregate_delays.py \
  '/path/to/stop_time_updates/*.parquet' work/delay-stats.json \
  --temp-directory work/duckdb-tmp
.venv-export/bin/python scripts/export_gtfs.py \
  /path/to/local/vbb-gtfs public/data \
  --delay-stats work/delay-stats.json
npm run dev
```

## Verify

```bash
npm test
python3 -m pytest tests/test_export.py
npm run lint
npm run build
```

The exporter retains one most-frequently scheduled shape per passenger-facing service and samples its ordered points for the browser. It also attaches the ordered stops of a representative scheduled trip. Exact source geometry remains WGS84 longitude/latitude; only the deck.gl z-coordinate changes during the exploded view.

The delay reducer reproduces RoutePulse's event grain: it keeps the latest update for each trip, service date, stop sequence and stop ID, then calculates the documented timing categories. The interface always labels these values as feed-reported timing during the retained sample, not verified actual arrivals.

The dark geographic reference uses OpenFreeMap/OpenMapTiles data derived from OpenStreetMap and retains MapLibre's automatic attribution control.

## Checkpoint 1 acceptance criteria

- all modes align when combined;
- combined/exploded animation and camera orbit work;
- Bus, Tram, U-Bahn, S-Bahn and Regional rail are independent checkboxes and may all be selected;
- the layout works at desktop and phone widths;
- reduced-motion preferences skip the animation;
- the interface discloses that layer spacing is illustrative;
- VBB attribution and CC BY 4.0 are visible;
- no deployment or portfolio integration is included.

## Checkpoint 2 interaction

- hover a route to see its line, mode and representative termini;
- click it to isolate the path and display its ordered stops;
- inspect timing availability, per-stop median and P90 reported delay, and the share reported more than five minutes late;
- routes without usable timing remain selectable and explicitly show `No reported timing`.
- switch between the muted coloured `Atlas` basemap and the near-black `Focus` presentation treatment;
- distinguish Regional rail with violet rather than the visually similar Tram red.
