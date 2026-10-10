import type { DelayStats, RouteFeature } from './types';
import { MODES } from './types';

interface Props { route: RouteFeature; onClose: () => void; }

function percent(value: number, total: number) {
  return total ? `${Math.round(value * 100 / total)}%` : '—';
}

function DelayBar({ delay }: { delay: DelayStats | null }) {
  if (!delay || delay.timedObservations === 0) return <div className="no-timing">No reported timing</div>;
  const total = delay.timedObservations;
  return <div className="delay-bar" aria-label={`${percent(delay.seriousDelay, total)} reported more than five minutes late`}>
    <i className="early" style={{ width: percent(delay.early, total) }} />
    <i className="near" style={{ width: percent(delay.nearSchedule, total) }} />
    <i className="minor" style={{ width: percent(delay.minorDelay, total) }} />
    <i className="serious" style={{ width: percent(delay.seriousDelay, total) }} />
  </div>;
}

function aggregate(route: RouteFeature): DelayStats {
  const result: DelayStats = { observations: 0, timedObservations: 0, early: 0, nearSchedule: 0, minorDelay: 0, seriousDelay: 0, medianDelayMinutes: null, p90DelayMinutes: null };
  route.stops.forEach(({ delay }) => {
    if (!delay) return;
    result.observations += delay.observations;
    result.timedObservations += delay.timedObservations;
    result.early += delay.early;
    result.nearSchedule += delay.nearSchedule;
    result.minorDelay += delay.minorDelay;
    result.seriousDelay += delay.seriousDelay;
  });
  return result;
}

export function RoutePanel({ route, onClose }: Props) {
  const summary = aggregate(route);
  const coverage = percent(summary.timedObservations, summary.observations);
  const seriousShare = percent(summary.seriousDelay, summary.timedObservations);
  const color = `rgb(${MODES[route.mode].color.join(',')})`;
  return <aside className="route-panel" aria-label={`Selected route ${route.routeName}`}>
    <div className="route-panel-head">
      <div><span className="route-mode" style={{ color }}>{MODES[route.mode].label}</span><h2>{route.routeName}</h2></div>
      <button type="button" onClick={onClose} aria-label="Close route details">×</button>
    </div>
    <p className="route-termini">{route.termini}</p>
    <p className="route-agency">{route.agencyName}</p>
    <div className="route-metrics">
      <span><strong>{route.stops.length}</strong> stops</span>
      <span><strong>{coverage}</strong> timing available</span>
      <span><strong>{seriousShare}</strong> &gt;5 min late</span>
    </div>
    <div className="journey-heading">
      <div><span className="eyebrow">Reported-delay journey</span><h3>Representative direction</h3></div>
      <div className="delay-legend"><i className="near" />Near <i className="minor" />1–5m <i className="serious" />5m+</div>
    </div>
    <p className="journey-note">One retained observation per trip and stop. Values describe feed reports during the 39.5-hour sample—not verified actual arrivals.</p>
    <ol className="stop-list">
      {route.stops.map((stop, index) => {
        const delay = stop.delay;
        return <li key={`${stop.stopId}:${stop.sequence}`}>
          <span className="stop-node" style={{ borderColor: color }}>{index + 1}</span>
          <div className="stop-content">
            <div className="stop-name"><span>{stop.name}</span>{delay?.timedObservations ? <small>{delay.timedObservations.toLocaleString()} timed visits</small> : null}</div>
            <DelayBar delay={delay} />
            {delay?.timedObservations ? <div className="stop-stats"><span>Median {delay.medianDelayMinutes ?? '—'} min</span><span>P90 {delay.p90DelayMinutes ?? '—'} min</span><span>{percent(delay.seriousDelay, delay.timedObservations)} serious</span></div> : null}
          </div>
        </li>;
      })}
    </ol>
  </aside>;
}
