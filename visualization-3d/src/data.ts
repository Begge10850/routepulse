import type { ModeData, ModeId } from './types';
import { MODES } from './types';

const cache = new Map<ModeId, Promise<ModeData>>();

export function loadMode(mode: ModeId): Promise<ModeData> {
  if (!cache.has(mode)) {
    cache.set(mode, fetch(`${import.meta.env.BASE_URL}data/${MODES[mode].file}`).then(async (response) => {
      if (!response.ok) throw new Error(`Could not load ${MODES[mode].label} routes`);
      return response.json() as Promise<ModeData>;
    }));
  }
  return cache.get(mode)!;
}
