export const MODE_ORDER = ['bus', 'tram', 'ubahn', 'sbahn', 'regional'] as const;
export type ModeId = (typeof MODE_ORDER)[number];

export interface RouteFeature {
  serviceKey: string;
  routeId: string;
  routeName: string;
  routeLongName: string;
  mode: ModeId;
  agencyName: string;
  scheduledTripCount: number;
  termini: string;
  path: [number, number][];
  stops: RouteStop[];
}

export interface DelayStats {
  observations: number;
  timedObservations: number;
  early: number;
  nearSchedule: number;
  minorDelay: number;
  seriousDelay: number;
  medianDelayMinutes: number | null;
  p90DelayMinutes: number | null;
}

export interface RouteStop {
  stopId: string;
  name: string;
  sequence: number;
  position: [number, number];
  delay: DelayStats | null;
}

export interface ModeData {
  mode: ModeId;
  routes: RouteFeature[];
}

export interface ModeConfig {
  label: string;
  color: [number, number, number];
  elevation: number;
  file: string;
}

export const MODES: Record<ModeId, ModeConfig> = {
  bus: { label: 'Bus', color: [245, 158, 11], elevation: 12000, file: 'bus.json' },
  tram: { label: 'Tram', color: [225, 29, 72], elevation: 24000, file: 'tram.json' },
  ubahn: { label: 'U-Bahn', color: [59, 130, 246], elevation: 36000, file: 'ubahn.json' },
  sbahn: { label: 'S-Bahn', color: [34, 197, 94], elevation: 48000, file: 'sbahn.json' },
  regional: { label: 'Regional rail', color: [168, 85, 247], elevation: 60000, file: 'regional-rail.json' },
};
