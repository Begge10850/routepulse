import type { MapViewState } from '@deck.gl/core';
import { useEffect, useRef, useState } from 'react';
import { loadMode } from './data';
import { LayerControls } from './LayerControls';
import { RoutePanel } from './RoutePanel';
import { TransportMap } from './TransportMap';
import type { ModeData, ModeId, RouteFeature } from './types';
import { MODE_ORDER, MODES } from './types';

const INITIAL_VIEW: MapViewState = { longitude: 13.32, latitude: 52.48, zoom: 7.25, pitch: 56, bearing: -18 };

export default function App() {
  const [data, setData] = useState<Partial<Record<ModeId, ModeData>>>({});
  const [enabled, setEnabled] = useState<Set<ModeId>>(new Set(MODE_ORDER));
  const [exploded, setExploded] = useState(true);
  const [explodeFactor, setExplodeFactor] = useState(1);
  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW);
  const [selected, setSelected] = useState<RouteFeature | null>(null);
  const [error, setError] = useState('');
  const animationRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    Promise.all(MODE_ORDER.map(loadMode)).then((modes) => setData(Object.fromEntries(modes.map(mode => [mode.mode, mode])))).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) {
      animationRef.current = requestAnimationFrame(() => setExplodeFactor(exploded ? 1 : 0));
      return () => cancelAnimationFrame(animationRef.current ?? 0);
    }
    cancelAnimationFrame(animationRef.current ?? 0);
    const from = explodeFactor;
    const to = exploded ? 1 : 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - start) / 900, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setExplodeFactor(from + (to - from) * eased);
      if (progress < 1) animationRef.current = requestAnimationFrame(tick);
    };
    animationRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationRef.current ?? 0);
  // explodeFactor intentionally sampled at transition start only.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exploded]);

  function toggleMode(mode: ModeId, value: boolean) {
    if (!value && selected?.mode === mode) setSelected(null);
    setEnabled(current => {
      const next = new Set(current);
      if (value) next.add(mode); else next.delete(mode);
      return next;
    });
  }

  const routeCount = Object.values(data).reduce((sum, mode) => sum + (mode?.routes.length ?? 0), 0);

  return <main>
    <div className="map-stage"><TransportMap data={data} enabled={enabled} explodeFactor={explodeFactor} viewState={viewState} selected={selected} onSelect={setSelected} onViewStateChange={setViewState} /></div>
    <header className="masthead">
      <a className="brand" href="#top" aria-label="RoutePulse home"><span className="pulse-mark" />ROUTE<span>PULSE</span></a>
      <span className="prototype-label">3D network prototype</span>
    </header>
    {!selected && <section className="intro" id="top">
      <p className="eyebrow">Berlin + Brandenburg · scheduled network</p>
      <h1>See the system.<br /><em>Layer by layer.</em></h1>
      <p className="lede">Five transport networks, one shared geography. Rotate the model, separate the layers, and read the region as a connected system.</p>
      <div className="stats"><span><strong>{routeCount || '—'}</strong> representative routes</span><span><strong>5</strong> transport modes</span></div>
      <p className="select-prompt"><span>↗</span> Hover and click any route to inspect its journey</p>
    </section>}
    {selected && <RoutePanel route={selected} onClose={() => setSelected(null)} />}
    <aside className="controls"><LayerControls exploded={exploded} enabled={enabled} onExplodedChange={setExploded} onModeChange={toggleMode} onReset={() => setViewState({ ...INITIAL_VIEW })} /></aside>
    <div className="map-hint" aria-hidden="true"><span>Drag to orbit</span><span>Scroll to zoom</span></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="layer-key" aria-hidden="true">{MODE_ORDER.map(mode => enabled.has(mode) && <div key={mode} style={{ '--mode-color': `rgb(${MODES[mode].color.join(',')})` } as React.CSSProperties}>{MODES[mode].label}</div>)}</div>
    <footer>Transport: VBB, CC BY 4.0 · Basemap: OpenFreeMap / OpenMapTiles / OpenStreetMap contributors</footer>
  </main>;
}
