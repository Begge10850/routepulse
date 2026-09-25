# Realtime field selection

## Decision date

2026-09-25

## Observed feed structure

The inspected VBB GTFS-Realtime snapshot contained:

- 9,171 total entities;
- 9,171 TripUpdate entities;
- 0 VehiclePosition entities;
- 0 Alert entities;
- 0 deleted entities.

The initial collector will preserve the complete raw Protocol Buffer response.
It will not assume that VehiclePositions or Alerts are available.

## Collection-manifest fields

Each collection attempt should record:

- collection attempt identifier;
- request start timestamp in UTC;
- request end timestamp in UTC;
- request duration in milliseconds;
- HTTP status code;
- success or failure status;
- retry count;
- error type;
- error message;
- response ETag;
- response Last-Modified value;
- response Content-Type;
- response Content-Length, when supplied;
- downloaded byte count;
- SHA-256 checksum;
- raw snapshot path;
- feed timestamp in UTC;
- GTFS-Realtime version;
- total entity count;
- TripUpdate count;
- VehiclePosition count;
- Alert count;
- deleted-entity count;
- available disk space;
- whether the response was saved, duplicated, or not modified.

## TripUpdate fields for later decoding

The structured decoding phase should retain, when present:

- snapshot identifier;
- collection timestamp;
- feed timestamp;
- entity identifier;
- trip ID;
- route ID;
- direction ID;
- start date;
- start time;
- trip schedule relationship;
- vehicle identifier;
- TripUpdate timestamp;
- TripUpdate delay.

## StopTimeUpdate fields for later decoding

The structured decoding phase should retain, when present:

- snapshot identifier;
- entity identifier;
- trip ID;
- route ID;
- stop ID;
- stop sequence;
- arrival delay;
- arrival timestamp;
- arrival uncertainty;
- departure delay;
- departure timestamp;
- departure uncertainty;
- stop schedule relationship.

## Important interpretation rules

Missing realtime records must not be treated as proof that a scheduled journey
did not operate.

A cancellation may only be counted when the feed explicitly reports an
applicable cancellation schedule relationship.

A skipped stop may only be counted when it is explicitly marked as skipped.

Missing optional Protocol Buffer fields must remain missing. They must not be
silently converted into meaningful zero values.

Feed-health findings and transport-performance findings must be reported
separately.