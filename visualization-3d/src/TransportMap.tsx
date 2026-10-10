import DeckGL from '@deck.gl/react';
import { MapView, type MapViewState, type PickingInfo, type Position } from '@deck.gl/core';
import { PathLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import { useMemo } from 'react';
import { Map } from 'react-map-gl/maplibre';
import { setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { ModeData, ModeId, RouteFeature, RouteStop } from './types';
import { MODE_ORDER, MODES } from './types';

interface Props { data: Partial<Record<ModeId, ModeData>>; enabled: Set<ModeId>; explodeFactor: number; viewState: MapViewState; selected: RouteFeature | null; onSelect: (route: RouteFeature | null) => void; onViewStateChange: (view: MapViewState) => void; }

const referencePlane = [[12.5, 51.95], [14.15, 51.95], [14.15, 53.15], [12.5, 53.15]] as [number, number][];
setWorkerUrl(workerUrl);

export function TransportMap({ data, enabled, explodeFactor, viewState, selected, onSelect, onViewStateChange }: Props) {
  const layers = useMemo(() => {
    const plane = new PolygonLayer({ id: 'reference-plane', data: [{ polygon: referencePlane }], getPolygon: d => d.polygon, getFillColor: [10, 29, 36, 18], getLineColor: [104, 139, 147, 80], lineWidthMinPixels: 1, stroked: true, filled: true, pickable: false });
    const paths = MODE_ORDER.map((mode) => new PathLayer<RouteFeature>({
      id: `routes-${mode}`,
      data: data[mode]?.routes ?? [],
      visible: enabled.has(mode),
      getPath: route => route.path.map(([lon, lat]) => [lon, lat, MODES[mode].elevation * explodeFactor] as Position),
      getColor: route => [...MODES[mode].color, selected && selected.serviceKey !== route.serviceKey ? 45 : mode === 'bus' ? 165 : mode === 'regional' ? 150 : 215],
      getWidth: mode === 'bus' ? 2.1 : 3.4,
      widthUnits: 'pixels',
      widthMinPixels: 1,
      jointRounded: true,
      capRounded: true,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 160],
      updateTriggers: { getPath: [explodeFactor], getColor: [selected?.serviceKey] },
      transitions: { getPath: { duration: 900, type: 'interpolation' } },
    }));
    const selectionElevation = selected ? MODES[selected.mode].elevation * explodeFactor : 0;
    const selectedPath = selected ? new PathLayer<RouteFeature>({ id: 'selected-route', data: [selected], getPath: route => route.path.map(([lon, lat]) => [lon, lat, selectionElevation] as Position), getColor: [255, 255, 255, 245], getWidth: 7, widthUnits: 'pixels', pickable: false }) : null;
    const selectedStops = selected ? new ScatterplotLayer<RouteStop>({ id: 'selected-stops', data: selected.stops, getPosition: stop => [...stop.position, selectionElevation] as Position, getRadius: 5, radiusUnits: 'pixels', getFillColor: [7, 16, 21, 255], getLineColor: [...MODES[selected.mode].color, 255], lineWidthMinPixels: 2, stroked: true, pickable: false }) : null;
    return [plane, ...paths, selectedPath, selectedStops].filter(Boolean);
  }, [data, enabled, explodeFactor, selected]);

  return <DeckGL
    layers={layers}
    views={new MapView({ repeat: false })}
    viewState={viewState}
    controller={{ dragRotate: true, touchRotate: true, inertia: true }}
    onViewStateChange={({ viewState: next }) => onViewStateChange(next as MapViewState)}
    onClick={(info: PickingInfo<RouteFeature>) => onSelect(info.object ?? null)}
    getTooltip={({ object }: PickingInfo<RouteFeature>) => object ? { text: `${object.routeName} · ${MODES[object.mode].label}\n${object.termini}` } : null}
    getCursor={({ isDragging }) => isDragging ? 'grabbing' : 'grab'}
  >
    <Map mapStyle="https://tiles.openfreemap.org/styles/dark" reuseMaps />
  </DeckGL>;
}
