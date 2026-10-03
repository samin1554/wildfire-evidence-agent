// Feed filters and sort (client-side over the snapshot's top clusters).
import type { ActivityCluster } from "../api/types";

export type Sort = "rank" | "newest" | "detections";

export interface Filters {
  state: string; // "" = all states
  officialOnly: boolean;
  minDetections: number;
  hidePersistent: boolean;
  sort: Sort;
}

export const DEFAULT_FILTERS: Filters = {
  state: "",
  officialOnly: false,
  minDetections: 1,
  hidePersistent: true,
  sort: "rank",
};

export function applyFilters(clusters: ActivityCluster[], f: Filters): ActivityCluster[] {
  const out = clusters.filter(
    (c) =>
      (!f.state || c.place?.state === f.state) &&
      (!f.officialOnly || c.label === "officially_reported") &&
      c.detections >= f.minDetections &&
      (!f.hidePersistent || !c.persistent_heat_source),
  );
  const by: Record<Sort, (a: ActivityCluster, b: ActivityCluster) => number> = {
    rank: (a, b) => a.rank - b.rank,
    newest: (a, b) => b.last_seen.localeCompare(a.last_seen) || a.rank - b.rank,
    detections: (a, b) => b.detections - a.detections || a.rank - b.rank,
  };
  return [...out].sort(by[f.sort]);
}

export function statesIn(clusters: ActivityCluster[]): string[] {
  return [...new Set(clusters.map((c) => c.place?.state).filter((s): s is string => !!s))].sort();
}

export const SATELLITE_NAMES: Record<string, string> = { N: "Suomi-NPP", N20: "NOAA-20", N21: "NOAA-21" };
