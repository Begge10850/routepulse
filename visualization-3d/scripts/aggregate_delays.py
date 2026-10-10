#!/usr/bin/env python3
"""Deduplicate RoutePulse snapshots and export compact route/stop delay evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def aggregate(parquet_glob: str, output: Path, temp_directory: Path) -> None:
    temp_directory.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute("SET temp_directory = ?", [str(temp_directory)])
    connection.execute("SET preserve_insertion_order = false")
    result = connection.execute(
        """
        WITH latest AS (
            SELECT
                replace(route_id, '-', '_') AS route_id,
                stop_id,
                coalesce(arrival_delay_seconds, departure_delay_seconds)
                    AS reported_delay_seconds
            FROM read_parquet(?)
            QUALIFY row_number() OVER (
                PARTITION BY trip_id, start_date, stop_sequence, stop_id
                ORDER BY attempt_number DESC, snapshot_id DESC
            ) = 1
        )
        SELECT
            route_id,
            stop_id,
            count(*)::INTEGER AS observations,
            count(reported_delay_seconds)::INTEGER AS timed_observations,
            count(*) FILTER (
                WHERE reported_delay_seconds < -60
            )::INTEGER AS early,
            count(*) FILTER (
                WHERE reported_delay_seconds BETWEEN -60 AND 60
            )::INTEGER AS near_schedule,
            count(*) FILTER (
                WHERE reported_delay_seconds > 60
                  AND reported_delay_seconds <= 300
            )::INTEGER AS minor_delay,
            count(*) FILTER (
                WHERE reported_delay_seconds > 300
            )::INTEGER AS serious_delay,
            round(median(reported_delay_seconds) / 60.0, 1)
                AS median_delay_minutes,
            round(quantile_cont(reported_delay_seconds, 0.9) / 60.0, 1)
                AS p90_delay_minutes
        FROM latest
        GROUP BY route_id, stop_id
        ORDER BY route_id, stop_id
        """,
        [parquet_glob],
    ).fetchall()
    routes: dict[str, dict[str, dict]] = {}
    for row in result:
        route_id, stop_id, observations, timed, early, near, minor, serious, median, p90 = row
        routes.setdefault(route_id, {})[stop_id] = {
            "observations": observations,
            "timedObservations": timed,
            "early": early,
            "nearSchedule": near,
            "minorDelay": minor,
            "seriousDelay": serious,
            "medianDelayMinutes": median,
            "p90DelayMinutes": p90,
        }
    payload = {
        "method": "Latest retained update per trip, date, stop sequence and stop; RoutePulse analytical timing categories.",
        "routes": routes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet_glob")
    parser.add_argument("output", type=Path)
    parser.add_argument("--temp-directory", type=Path, required=True)
    args = parser.parse_args()
    aggregate(args.parquet_glob, args.output, args.temp_directory)
