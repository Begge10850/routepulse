# RoutePulse 3D network prototype

An isolated React, TypeScript and deck.gl prototype that renders representative scheduled VBB route shapes as five geographically aligned, independently selectable layers. The vertical exploded arrangement is an interface metaphor; it does not represent physical elevation or tunnel depth.

This folder does not import or change the existing Streamlit dashboard. Browser data are static, compact and contain no Snowflake or AWS credentials.

## Run locally

```bash
npm install
python3 scripts/export_gtfs.py /path/to/local/vbb-gtfs public/data
npm run dev
```

## Verify

```bash
npm test
python3 -m pytest tests/test_export.py
npm run lint
npm run build
```

The exporter retains one most-frequently scheduled shape per GTFS route and samples its ordered points for the browser. Exact source geometry remains WGS84 longitude/latitude; only the deck.gl z-coordinate changes during the exploded view.

## Checkpoint 1 acceptance criteria

- all modes align when combined;
- combined/exploded animation and camera orbit work;
- Bus, Tram, U-Bahn, S-Bahn and Regional rail are independent checkboxes and may all be selected;
- the layout works at desktop and phone widths;
- reduced-motion preferences skip the animation;
- the interface discloses that layer spacing is illustrative;
- VBB attribution and CC BY 4.0 are visible;
- no deployment or portfolio integration is included.
