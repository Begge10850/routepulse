# Data sources

## Access record

This source record was reviewed on 2026-09-25.

## VBB GTFS static schedule

Provider: Verkehrsverbund Berlin-Brandenburg GmbH (VBB)

Official information page:

https://unternehmen.vbb.de/digitale-services/datensaetze/

The static GTFS dataset contains scheduled public-transport information for
the VBB region. VBB currently describes the dataset as a ZIP archive updated
twice weekly.

The exact download URL must be captured when the dataset is downloaded,
because the public information page may redirect to a downloadable file.

## VBB GTFS-Realtime feed

Provider: Verkehrsverbund Berlin-Brandenburg GmbH (VBB)

Feed information page:

https://production.gtfsrt.vbb.de/

Realtime endpoint:

https://production.gtfsrt.vbb.de/data

The feed:

- uses the GTFS-Realtime format;
- is encoded using Protocol Buffers;
- can be accessed without authentication;
- permits up to 60 requests per minute;
- requests an informative User-Agent;
- supplies an ETag header for HTTP caching;
- is licensed under CC BY 4.0.

RoutePulse currently plans one request every three minutes. This equals
approximately 0.33 requests per minute and is well below the published limit.

## Current coverage warning

On 2026-09-25, the official realtime-feed page displayed the following
operational warning:

> Due to problems with the data source behind this feed, the feed has been
> lacking some data since 2026-06-04 16:00. VBB did not provide an estimated
> restoration date on the page at the time of review.

This limitation affects how RoutePulse results may be interpreted.

RoutePulse must not assume that absence from the realtime feed means that a
scheduled journey was cancelled or did not operate. Feed-health findings and
transport-performance findings must be reported separately.

The collection evaluation should measure:

- request success;
- feed freshness;
- entity counts;
- collection gaps;
- duplicate or unchanged responses;
- identifier matching against the static GTFS schedule;
- periods with unusual reductions in available realtime records.

## Licence and attribution

VBB states that these datasets are provided under the Creative Commons
Attribution 4.0 International licence:

https://creativecommons.org/licenses/by/4.0/

Required project attribution:

Data source: Verkehrsverbund Berlin-Brandenburg GmbH (VBB), used under
CC BY 4.0.

The source information page also warns that datasets may contain errors or be
incomplete and that VBB provides no warranty.

The dataset licence applies to VBB data. A separate software licence for the
RoutePulse source code will be selected and documented independently.

## GTFS-Realtime specification

Specification documentation:

https://gtfs.org/documentation/realtime/

GTFS-Realtime represents live public-transport information using Protocol
Buffers. A realtime feed is interpreted relative to a corresponding static
GTFS schedule.

RoutePulse will inspect the actual feed before assuming that TripUpdates,
VehiclePositions, or Alerts are present.