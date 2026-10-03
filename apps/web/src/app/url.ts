// Shareable state in the address bar: ?tab=active&cluster=… or ?tab=analyse&job=…, plus feed filters.
import { DEFAULT_FILTERS, type Filters, type Sort } from "../activity/filters";

export interface UrlState {
  tab: "active" | "analyse";
  cluster: string | null;
  job: string | null;
  filters: Filters;
}

const SORTS: Sort[] = ["rank", "newest", "detections"];

export function parseUrl(search: string): UrlState {
  const q = new URLSearchParams(search);
  const min = Number(q.get("min"));
  const sort = q.get("sort") as Sort;
  return {
    tab: q.get("tab") === "analyse" || q.has("job") ? "analyse" : "active",
    cluster: q.get("cluster"),
    job: q.get("job"),
    filters: {
      state: /^[A-Z]{2}$/.test(q.get("state") ?? "") ? (q.get("state") as string) : DEFAULT_FILTERS.state,
      officialOnly: q.get("official") === "1",
      minDetections: Number.isInteger(min) && min >= 1 ? min : DEFAULT_FILTERS.minDetections,
      hidePersistent: q.get("persistent") !== "show",
      sort: SORTS.includes(sort) ? sort : DEFAULT_FILTERS.sort,
    },
  };
}

export function toSearch(s: UrlState): string {
  const q = new URLSearchParams();
  q.set("tab", s.tab);
  if (s.tab === "active" && s.cluster) q.set("cluster", s.cluster);
  if (s.tab === "analyse" && s.job) q.set("job", s.job);
  const f = s.filters;
  if (f.state) q.set("state", f.state);
  if (f.officialOnly) q.set("official", "1");
  if (f.minDetections > 1) q.set("min", String(f.minDetections));
  if (!f.hidePersistent) q.set("persistent", "show");
  if (f.sort !== "rank") q.set("sort", f.sort);
  return `?${q}`;
}

export function writeUrl(s: UrlState): void {
  const next = toSearch(s);
  if (next !== window.location.search) window.history.replaceState(null, "", next);
}
