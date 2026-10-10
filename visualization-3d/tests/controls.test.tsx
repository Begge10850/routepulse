import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LayerControls } from '../src/LayerControls';
import { MODE_ORDER } from '../src/types';

describe('LayerControls', () => {
  it('allows all five modes to remain selected simultaneously', () => {
    render(<LayerControls exploded mapTheme="atlas" enabled={new Set(MODE_ORDER)} onExplodedChange={vi.fn()} onMapThemeChange={vi.fn()} onModeChange={vi.fn()} onReset={vi.fn()} />);
    MODE_ORDER.forEach((mode, index) => expect(screen.getAllByRole('checkbox')[index]).toBeChecked());
  });

  it('reports independent mode and arrangement changes', () => {
    const onModeChange = vi.fn();
    const onExplodedChange = vi.fn();
    const onMapThemeChange = vi.fn();
    render(<LayerControls exploded mapTheme="atlas" enabled={new Set(MODE_ORDER)} onExplodedChange={onExplodedChange} onMapThemeChange={onMapThemeChange} onModeChange={onModeChange} onReset={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tram' }));
    fireEvent.click(screen.getByRole('button', { name: 'Combined' }));
    fireEvent.click(screen.getByRole('button', { name: 'Focus' }));
    expect(onModeChange).toHaveBeenCalledWith('tram', false);
    expect(onExplodedChange).toHaveBeenCalledWith(false);
    expect(onMapThemeChange).toHaveBeenCalledWith('focus');
  });
});
