import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RoutePanel } from '../src/RoutePanel';
import type { RouteFeature } from '../src/types';

const route: RouteFeature = {
  serviceKey: 'tram:operator:M4', routeId: 'route-1', routeName: 'M4', routeLongName: 'Metrotram', mode: 'tram', agencyName: 'Example operator', scheduledTripCount: 20, termini: 'Alexanderplatz → Falkenberg', path: [[13.4, 52.5], [13.5, 52.6]],
  stops: [
    { stopId: 'a', name: 'Alexanderplatz', sequence: 0, position: [13.4, 52.5], delay: { observations: 10, timedObservations: 8, early: 1, nearSchedule: 4, minorDelay: 2, seriousDelay: 1, medianDelayMinutes: 0.5, p90DelayMinutes: 6 } },
    { stopId: 'b', name: 'Falkenberg', sequence: 1, position: [13.5, 52.6], delay: null },
  ],
};

describe('RoutePanel', () => {
  it('shows ordered stops and reported-delay evidence', () => {
    render(<RoutePanel route={route} onClose={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'M4' })).toBeInTheDocument();
    expect(screen.getByText('Alexanderplatz', { selector: '.stop-name span' })).toBeInTheDocument();
    expect(screen.getByText('Falkenberg', { selector: '.stop-name span' })).toBeInTheDocument();
    expect(screen.getByText('8 timed visits')).toBeInTheDocument();
    expect(screen.getByText('No reported timing')).toBeInTheDocument();
  });

  it('closes without mutating the route', () => {
    const onClose = vi.fn();
    render(<RoutePanel route={route} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'Close route details' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
