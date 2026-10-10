import type { RouteFeature } from './types';

const U_BAHN_COLORS: Record<string, [number, number, number]> = {
  U1: [82, 161, 74], U2: [218, 37, 55], U3: [33, 141, 82], U4: [248, 205, 35],
  U5: [130, 83, 50], U6: [126, 79, 151], U7: [82, 169, 221], U8: [47, 63, 141], U9: [238, 117, 37],
};

const PALETTE: [number, number, number][] = [
  [236, 72, 153], [14, 165, 233], [250, 204, 21], [168, 85, 247], [20, 184, 166],
  [249, 115, 22], [99, 102, 241], [132, 204, 22], [244, 63, 94], [6, 182, 212],
  [217, 70, 239], [234, 179, 8],
];

function hash(value: string) {
  let result = 0;
  for (const character of value) result = ((result << 5) - result + character.charCodeAt(0)) | 0;
  return Math.abs(result);
}

export function getRouteColor(route: RouteFeature): [number, number, number] {
  const name = route.routeName.trim().toUpperCase();
  return U_BAHN_COLORS[name] ?? PALETTE[hash(route.serviceKey) % PALETTE.length];
}
