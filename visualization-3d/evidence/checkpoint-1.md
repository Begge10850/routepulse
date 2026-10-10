# Checkpoint 1 verification

Date: 2026-10-10  
Branch: `codex/routepulse-3d`

## Implemented

- isolated React/TypeScript/deck.gl application under `visualization-3d/`;
- five WGS84 route layers exported from the local VBB GTFS Static source;
- shared longitude/latitude geometry in combined mode;
- illustrative z-offsets in exploded mode;
- animated Combined/Exploded control;
- independent Bus, Tram, U-Bahn, S-Bahn and Regional rail checkboxes, all selected by default;
- orbit, pitch, pan and zoom camera controls;
- desktop and phone control layouts;
- reduced-motion handling and explicit non-physical-height disclosure;
- visible VBB CC BY 4.0 attribution.

## Retained data checks

`public/data/metadata.json` records per-file route counts, point counts, byte sizes and SHA-256 hashes. The Python contract test checks:

- five non-empty mode files;
- every route has at least two points;
- every coordinate is finite;
- every coordinate falls within the broad Berlin/Brandenburg service-area guardrail;
- declared route counts match exported arrays.

## Test results

| Check | Result |
|---|---|
| Vitest control behaviour | 2 passed |
| Python exported-data contract | 1 passed |
| ESLint | passed |
| TypeScript + Vite production build | passed |
| Desktop visual inspection, 1440 × 900 | passed |
| Phone visual inspection, 390 × 844 | passed |
| Combined/Exploded state via browser accessibility tree | passed |
| Independent Tram toggle while other modes remained selected | passed |

## Limitations at this checkpoint

- The static export is rebuilt directly from the retained local GTFS tables because the exact Snowflake map export is not in Git. It yields 1,173 passenger-facing representative routes rather than the deployed dashboard's documented 957 paths; this is a transparent prototype-data difference, not a claim of parity.
- The neutral reference surface is intentionally not a redistributed state boundary because the current boundary object's source licence is unresolved.
- Vertical spacing is deliberately illustrative and has no physical elevation meaning.
- Line picking, route details, ordered stops and reported-delay exploration are deferred until user approval, as requested.
- Real-phone performance has not yet been measured; the phone checkpoint is responsive browser emulation only.
