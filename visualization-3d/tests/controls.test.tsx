import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LayerControls } from '../src/LayerControls';
import { MODE_ORDER } from '../src/types';

describe('LayerControls', () => {
  it('allows all five modes to remain selected simultaneously', () => {
    render(<LayerControls exploded enabled={new Set(MODE_ORDER)} onExplodedChange={vi.fn()} onModeChange={vi.fn()} onReset={vi.fn()} />);
    MODE_ORDER.forEach((mode, index) => expect(screen.getAllByRole('checkbox')[index]).toBeChecked());
  });

  it('reports independent mode and arrangement changes', () => {
    const onModeChange = vi.fn();
    const onExplodedChange = vi.fn();
    render(<LayerControls exploded enabled={new Set(MODE_ORDER)} onExplodedChange={onExplodedChange} onModeChange={onModeChange} onReset={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tram' }));
    fireEvent.click(screen.getByRole('button', { name: 'Combined' }));
    expect(onModeChange).toHaveBeenCalledWith('tram', false);
    expect(onExplodedChange).toHaveBeenCalledWith(false);
  });
});
