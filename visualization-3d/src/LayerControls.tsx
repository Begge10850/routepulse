import type { ModeId } from './types';
import { MODE_ORDER, MODES } from './types';

interface Props {
  exploded: boolean;
  mapTheme: 'atlas' | 'focus';
  enabled: Set<ModeId>;
  onExplodedChange: (value: boolean) => void;
  onMapThemeChange: (value: 'atlas' | 'focus') => void;
  onModeChange: (mode: ModeId, value: boolean) => void;
  onReset: () => void;
}

export function LayerControls({ exploded, mapTheme, enabled, onExplodedChange, onMapThemeChange, onModeChange, onReset }: Props) {
  return <section className="control-card" aria-label="Transport layer controls">
    <div className="control-heading">
      <div>
        <span className="eyebrow">Layer controls</span>
        <h2>Network assembly</h2>
      </div>
      <button className="reset-button" onClick={onReset} type="button">Reset view</button>
    </div>
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
