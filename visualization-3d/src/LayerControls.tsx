import type { ModeId, RouteFeature } from './types';
import { MODE_ORDER, MODES } from './types';

interface Props {
  exploded: boolean;
  mapTheme: 'atlas' | 'focus';
  enabled: Set<ModeId>;
  routeColorMode: 'modes' | 'lines';
  focusedRoutes: RouteFeature[];
  onExplodedChange: (value: boolean) => void;
  onMapThemeChange: (value: 'atlas' | 'focus') => void;
  onModeChange: (mode: ModeId, value: boolean) => void;
  onRouteColorModeChange: (value: 'modes' | 'lines') => void;
  onRouteSelect: (route: RouteFeature) => void;
  onReset: () => void;
}

export function LayerControls({ exploded, mapTheme, enabled, routeColorMode, focusedRoutes, onExplodedChange, onMapThemeChange, onModeChange, onRouteColorModeChange, onRouteSelect, onReset }: Props) {
  return <section className="control-card" aria-label="Transport layer controls">
    <div className="control-heading">
      <div>
        <span className="eyebrow">Layer controls</span>
        <h2>Network assembly</h2>
      </div>
      <button className="reset-button" onClick={onReset} type="button">Reset view</button>
    </div>
    {enabled.size === 1 && <div className="line-focus-controls">
      <span>Route colours</span>
      <div className="view-switch" role="group" aria-label="Route colour display">
        <button className={routeColorMode === 'modes' ? 'active' : ''} aria-pressed={routeColorMode === 'modes'} onClick={() => onRouteColorModeChange('modes')}>Mode</button>
        <button className={routeColorMode === 'lines' ? 'active' : ''} aria-pressed={routeColorMode === 'lines'} onClick={() => onRouteColorModeChange('lines')}>Lines</button>
      </div>
      {routeColorMode === 'lines' && <><label htmlFor="route-search">Find a route</label><input id="route-search" list="route-options" placeholder="Type U2, U7, S1…" onChange={(event) => { const route = focusedRoutes.find(item => item.routeName.toLowerCase() === event.target.value.toLowerCase()); if (route) onRouteSelect(route); }} /><datalist id="route-options">{focusedRoutes.map(route => <option key={route.serviceKey} value={route.routeName}>{route.termini}</option>)}</datalist></>}
    </div>}
    <div className="view-switch" role="group" aria-label="Layer arrangement">
      <button className={!exploded ? 'active' : ''} aria-pressed={!exploded} onClick={() => onExplodedChange(false)}>Combined</button>
      <button className={exploded ? 'active' : ''} aria-pressed={exploded} onClick={() => onExplodedChange(true)}>Exploded</button>
    </div>
    <div className="theme-row">
      <span>Map treatment</span>
      <div className="theme-switch" role="group" aria-label="Map treatment">
        <button className={mapTheme === 'atlas' ? 'active' : ''} aria-pressed={mapTheme === 'atlas'} onClick={() => onMapThemeChange('atlas')}>Atlas</button>
        <button className={mapTheme === 'focus' ? 'active' : ''} aria-pressed={mapTheme === 'focus'} onClick={() => onMapThemeChange('focus')}>Focus</button>
      </div>
    </div>
    <fieldset>
      <legend>Visible modes <span>{enabled.size}/5</span></legend>
      <div className="mode-list">
        {MODE_ORDER.map((mode) => <label key={mode} className="mode-option">
          <input type="checkbox" checked={enabled.has(mode)} onChange={(event) => onModeChange(mode, event.target.checked)} />
          <span className="checkmark" style={{ '--mode-color': `rgb(${MODES[mode].color.join(',')})` } as React.CSSProperties} />
          <span>{MODES[mode].label}</span>
        </label>)}
      </div>
    </fieldset>
    <p className="disclaimer"><span aria-hidden="true">↕</span> Vertical spacing is illustrative, not physical elevation or tunnel depth.</p>
  </section>;
}
