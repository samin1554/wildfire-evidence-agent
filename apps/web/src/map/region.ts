// Client-side area checks (S1): quick feedback before submit. The Go API validates again in PostGIS.
import type { Polygon } from "../api/types";

// providers.yaml areas.sb_county_bbox, until the county polygon lands (S4)
export const REGION_BBOX: [number, number, number, number] = [-117.8, 33.8, -114.1, 35.9];
export const MAX_AREA_KM2 = 5000;

export const PRESETS = {
  lineFire: {
    name: "Line Fire 2024 (Highland / Running Springs)",
    question: "How badly did the Line Fire burn this area, and what do official sources report?",
    date_range: { start: "2024-08-01", end: "2024-10-31" },
    area: box(-117.15, 34.1, -116.97, 34.21),
  },
  recent: {
    name: "Recent detections (Victorville / Apple Valley)",
    question: "Were there satellite heat detections in this area in the last few days?",
    // fixture data was recorded 2026-09-19 → 24; in fixture mode the worker treats 2026-09-24 as "today"
    date_range: { start: "2026-09-19", end: "2026-09-24" },
    area: box(-117.36, 34.58, -117.08, 34.65),
  },
} as const;

export function box(w: number, s: number, e: number, n: number): Polygon {
  return {
    type: "Polygon",
    coordinates: [
      [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ],
    ],
  };
}

export function bounds(p: Polygon): [number, number, number, number] {
  const pts = p.coordinates[0];
  const xs = pts.map((c) => c[0]);
  const ys = pts.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Approximate geodesic area (km²) of a WGS84 ring (spherical excess formula). */
export function areaKm2(p: Polygon): number {
  const R = 6371.0088;
  const ring = p.coordinates[0];
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    sum += ((x2 - x1) * Math.PI) / 180 * (2 + Math.sin((y1 * Math.PI) / 180) + Math.sin((y2 * Math.PI) / 180));
  }
  return Math.abs((sum * R * R) / 2);
}

function segmentsCross(a: number[], b: number[], c: number[], d: number[]): boolean {
  const o = (p: number[], q: number[], r: number[]) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  return o(a, b, c) * o(a, b, d) < 0 && o(c, d, a) * o(c, d, b) < 0;
}

export function selfIntersects(p: Polygon): boolean {
  const r = p.coordinates[0];
  const n = r.length - 1;
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue; // adjacent through the closing point
      if (segmentsCross(r[i], r[i + 1], r[j], r[j + 1])) return true;
    }
  }
  return false;
}

/** null if OK, otherwise a message for the user. */
export function checkArea(p: Polygon | null): string | null {
  if (!p) return "Draw an area on the map or pick a demo area.";
  if (p.coordinates[0].length < 4) return "The area needs at least three corners.";
  if (selfIntersects(p)) return "The polygon's edges cross. Redraw it without crossing lines.";
  const [w, s, e, n] = bounds(p);
  const [rw, rs, re, rn] = REGION_BBOX;
  if (w < rw || s < rs || e > re || n > rn) return "The area must be inside San Bernardino County.";
  if (areaKm2(p) > MAX_AREA_KM2) return `The area is too large (max ${MAX_AREA_KM2.toLocaleString()} km²).`;
  return null;
}
