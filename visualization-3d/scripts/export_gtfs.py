#!/usr/bin/env python3
"""Create browser-safe representative route geometry from a local VBB GTFS folder."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

TYPE_TO_MODE = {"3": "bus", "700": "bus", "900": "tram", "400": "ubahn", "109": "sbahn", "100": "regional", "106": "regional"}
MODE_FILES = {"bus": "bus.json", "tram": "tram.json", "ubahn": "ubahn.json", "sbahn": "sbahn.json", "regional": "regional-rail.json"}

def rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as source:
        yield from csv.DictReader(source)

def compact_path(points: list[tuple[int, float, float]], stride: int = 3) -> list[list[float]]:
    ordered = [(lon, lat) for _, lat, lon in sorted(points)]
    sampled = ordered[::stride]
    if ordered and sampled[-1] != ordered[-1]: sampled.append(ordered[-1])
    return [[round(lon, 6), round(lat, 6)] for lon, lat in sampled]

def export(gtfs: Path, output: Path) -> None:
    agencies = {r["agency_id"]: r["agency_name"] for r in rows(gtfs / "agency.txt")}
    routes = {r["route_id"]: r for r in rows(gtfs / "routes.txt") if r["route_type"] in TYPE_TO_MODE}
    shape_trips: Counter[tuple[str, str]] = Counter()
    for trip in rows(gtfs / "trips.txt"):
        if trip["route_id"] in routes and trip["shape_id"]:
            shape_trips[(trip["route_id"], trip["shape_id"])] += 1
    selected: dict[str, tuple[str, str, int]] = {}
    for (route_id, shape_id), count in shape_trips.items():
        route = routes[route_id]
        mode = TYPE_TO_MODE[route["route_type"]]
        name = route["route_short_name"] or route["route_long_name"] or route_id
        service_key = f"{mode}:{route['agency_id']}:{name}"
        if count > selected.get(service_key, ("", "", -1))[2]:
            selected[service_key] = (route_id, shape_id, count)
    wanted_shapes = {shape_id for _, shape_id, _ in selected.values()}
    shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for point in rows(gtfs / "shapes.txt"):
        if point["shape_id"] in wanted_shapes:
            shape_points[point["shape_id"]].append((int(point["shape_pt_sequence"]), float(point["shape_pt_lat"]), float(point["shape_pt_lon"])))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for service_key, (route_id, shape_id, count) in selected.items():
        route = routes[route_id]
        path = compact_path(shape_points[shape_id])
        if len(path) < 2 or not all(math.isfinite(value) for point in path for value in point): continue
        mode = TYPE_TO_MODE[route["route_type"]]
        name = route["route_short_name"] or route["route_long_name"] or route_id
        grouped[mode].append({"serviceKey": service_key, "routeName": name, "mode": mode, "agencyName": agencies.get(route["agency_id"], "VBB operator"), "scheduledTripCount": count, "path": path})

    output.mkdir(parents=True, exist_ok=True)
    metadata = {"source": "VBB GTFS Static", "licence": "CC BY 4.0", "coordinateSystem": "EPSG:4326", "generatedFiles": {}}
    for mode, filename in MODE_FILES.items():
        payload = {"mode": mode, "routes": grouped[mode]}
        target = output / filename
        target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        points = sum(len(route["path"]) for route in grouped[mode])
        metadata["generatedFiles"][filename] = {"routes": len(grouped[mode]), "points": points, "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("gtfs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.gtfs, args.output)
