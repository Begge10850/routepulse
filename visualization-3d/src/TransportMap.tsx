import DeckGL from '@deck.gl/react';
import { MapView, type MapViewState, type Position } from '@deck.gl/core';
import { PathLayer, PolygonLayer } from '@deck.gl/layers';
import { useMemo } from 'react';
import type { ModeData, ModeId, RouteFeature } from './types';
import { MODE_ORDER, MODES } from './types';

interface Props { data: Partial<Record<ModeId, ModeData>>; enabled: Set<ModeId>; explodeFactor: number; viewState: MapViewState; onViewStateChange: (view: MapViewState) => void; }

const referencePlane = [[12.5, 51.95], [14.15, 51.95], [14.15, 53.15], [12.5, 53.15]] as [number, number][];

export function TransportMap({ data, enabled, explodeFactor, viewState, onViewStateChange }: Props) {
  const layers = useMemo(() => {
    const plane = new PolygonLayer({ id: 'reference-plane', data: [{ polygon: referencePlane }], getPolygon: d => d.polygon, getFillColor: [10, 29, 36, 220], getLineColor: [104, 139, 147, 130], lineWidthMinPixels: 1, stroked: true, filled: true, pickable: false });
    const paths = MODE_ORDER.map((mode) => new PathLayer<RouteFeature>({
      id: `routes-${mode}`,
      data: data[mode]?.routes ?? [],
      visible: enabled.has(mode),
      getPath: route => route.path.map(([lon, lat]) => [lon, lat, MODES[mode].elevation * explodeFactor] as Position),
      getColor: [...MODES[mode].color, mode === 'bus' ? 165 : 215],
      getWidth: mode === 'bus' ? 2.1 : 3.4,
      widthUnits: 'pixels',
      widthMinPixels: 1,
      jointRounded: true,
      capRounded: true,
      pickable: false,
      updateTriggers: { getPath: [explodeFactor] },
      transitions: { getPath: { duration: 900, type: 'interpolation' } },
    }));
    return [plane, ...paths];
  }, [data, enabled, explodeFactor]);

  return <DeckGL
    layers={layers}
    views={new MapView({ repeat: false })}
    viewState={viewState}
    controller={{ dragRotate: true, touchRotate: true, inertia: true }}
    onViewStateChange={({ viewState: next }) => onViewStateChange(next as MapViewState)}
    getCursor={({ isDragging }) => isDragging ? 'grabbing' : 'grab'}
  />;
}
