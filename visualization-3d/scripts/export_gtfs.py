#!/usr/bin/env python3
"""Create browser-safe route geometry, patterns and stop evidence from VBB GTFS."""
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

def load_delay_stats(path: Path | None) -> dict[str, dict[str, dict]]:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["routes"]

def export(gtfs: Path, output: Path, delay_stats_path: Path | None = None) -> None:
    agencies = {r["agency_id"]: r["agency_name"] for r in rows(gtfs / "agency.txt")}
    routes = {r["route_id"]: r for r in rows(gtfs / "routes.txt") if r["route_type"] in TYPE_TO_MODE}
    shape_trips: Counter[tuple[str, str]] = Counter()
    sample_trip: dict[tuple[str, str], str] = {}
    for trip in rows(gtfs / "trips.txt"):
        if trip["route_id"] in routes and trip["shape_id"]:
            shape_trips[(trip["route_id"], trip["shape_id"])] += 1
            sample_trip.setdefault((trip["route_id"], trip["shape_id"]), trip["trip_id"])
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

    chosen_trips = {sample_trip[(route_id, shape_id)] for route_id, shape_id, _ in selected.values()}
    trip_stops: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for stop_time in rows(gtfs / "stop_times.txt"):
        if stop_time["trip_id"] in chosen_trips:
            trip_stops[stop_time["trip_id"]].append((int(stop_time["stop_sequence"]), stop_time["stop_id"]))
    stops = {r["stop_id"]: r for r in rows(gtfs / "stops.txt")}
    delay_stats = load_delay_stats(delay_stats_path)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for service_key, (route_id, shape_id, count) in selected.items():
        route = routes[route_id]
        path = compact_path(shape_points[shape_id])
        if len(path) < 2 or not all(math.isfinite(value) for point in path for value in point): continue
        mode = TYPE_TO_MODE[route["route_type"]]
        name = route["route_short_name"] or route["route_long_name"] or route_id
        representative_trip = sample_trip[(route_id, shape_id)]
        ordered_stops = []
        for sequence, stop_id in sorted(trip_stops[representative_trip]):
            stop = stops.get(stop_id)
            if not stop or not stop["stop_lat"] or not stop["stop_lon"]:
                continue
            ordered_stops.append({
                "stopId": stop_id,
                "name": stop["stop_name"],
                "sequence": sequence,
                "position": [round(float(stop["stop_lon"]), 6), round(float(stop["stop_lat"]), 6)],
                "delay": delay_stats.get(route_id, {}).get(stop_id),
            })
        termini = f"{ordered_stops[0]['name']} → {ordered_stops[-1]['name']}" if ordered_stops else "Representative direction unavailable"
        grouped[mode].append({
            "serviceKey": service_key,
            "routeId": route_id,
            "routeName": name,
            "routeLongName": route["route_long_name"],
            "mode": mode,
            "agencyName": agencies.get(route["agency_id"], "VBB operator"),
            "scheduledTripCount": count,
            "termini": termini,
            "path": path,
            "stops": ordered_stops,
        })

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
    parser.add_argument("--delay-stats", type=Path)
    args = parser.parse_args()
    export(args.gtfs, args.output, args.delay_stats)
