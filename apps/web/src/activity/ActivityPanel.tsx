// "Active now" (ADR-013): where satellites see heat right now, ranked. A cluster is a place to look at, not a fire.
import type { ActivityCluster, ActivitySnapshot } from "../api/types";
import { ConfidenceChip } from "../analysis/components";
import { applyFilters, SATELLITE_NAMES, statesIn, type Filters } from "./filters";

export function ago(iso: string, now = Date.now()): string {
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

export function clusterTitle(c: ActivityCluster): string {
  if (c.official?.incident_name) {
    const rx = c.official.incident_type === "prescribed burn" ? " (prescribed burn)" : "";
    return `${c.official.incident_name}${rx}`;
  }
  return "Unnamed heat cluster";
}

export function placeLabel(c: ActivityCluster): string {
  if (c.place) return `${c.place.county}, ${c.place.state}`;
  const [lon, lat] = c.centroid.coordinates;
  return `near ${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}°${lon < 0 ? "W" : "E"}`;
}

const TREND: Record<string, { text: string; tone: string }> = {
  new: { text: "New", tone: "bg-sky-100 text-sky-900" },
  growing: { text: "Growing ▲", tone: "bg-red-100 text-red-900" },
  stable: { text: "Steady", tone: "bg-slate-100 text-slate-700" },
  shrinking: { text: "Shrinking ▼", tone: "bg-emerald-100 text-emerald-900" },
};

export function TrendBadge({ c }: { c: ActivityCluster }) {
  if (!c.trend) return null;
  const t = TREND[c.trend.status];
  const title = c.trend.status === "new" ? "No detections here before the last 24 h" : `${c.trend.detections_24h_ago} detections here ~24 h ago`;
  return (
    <span data-testid="trend" title={title} className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${t.tone}`}>
      {t.text}
    </span>
  );
}

export interface ActivityPanelProps {
  snapshot: ActivitySnapshot | null;
  error: string | null;
  selected: string | null;
  filters: Filters;
  onFilters: (f: Filters) => void;
  onSelect: (c: ActivityCluster) => void;
  onAnalyse: (c: ActivityCluster) => void;
}

export function ActivityPanel({ snapshot, error, selected, filters, onFilters, onSelect, onAnalyse }: ActivityPanelProps) {
  if (error) return <p className="px-4 py-4 text-sm text-slate-600">{error}</p>;
  if (!snapshot) return <p className="px-4 py-4 text-sm text-slate-600">Loading recent satellite activity…</p>;
  const shown = applyFilters(snapshot.clusters, filters);
  const hiddenPersistent = filters.hidePersistent ? snapshot.clusters.filter((c) => c.persistent_heat_source).length : 0;
  const set = (patch: Partial<Filters>) => onFilters({ ...filters, ...patch });
  return (
    <section data-testid="activity" className="px-4 py-4 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="font-semibold">Recent satellite heat detections</h2>
        {snapshot.data_mode === "fixture" && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-700">
            recorded data
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-slate-600">
        Last {snapshot.window_days} days from 3 VIIRS satellites, clustered and ranked. Updated {ago(snapshot.generated_at)}.
        Pick one to analyse it.
      </p>

      <div data-testid="filters" className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <label className="flex flex-col">
          State
          <select aria-label="State" value={filters.state} onChange={(e) => set({ state: e.target.value })} className="rounded border border-slate-300 bg-white p-1">
            <option value="">All states</option>
            {statesIn(snapshot.clusters).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          Sort
          <select aria-label="Sort" value={filters.sort} onChange={(e) => set({ sort: e.target.value as Filters["sort"] })} className="rounded border border-slate-300 bg-white p-1">
            <option value="rank">Ranked</option>
            <option value="newest">Most recent</option>
            <option value="detections">Most detections</option>
          </select>
        </label>
        <label className="flex flex-col">
          Min detections
          <input aria-label="Min detections" type="number" min={1} value={filters.minDetections} onChange={(e) => set({ minDetections: Math.max(1, Number(e.target.value) || 1) })} className="rounded border border-slate-300 bg-white p-1" />
        </label>
        <div className="flex flex-col justify-end gap-1">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={filters.officialOnly} onChange={(e) => set({ officialOnly: e.target.checked })} />
            Officially reported only
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={filters.hidePersistent} onChange={(e) => set({ hidePersistent: e.target.checked })} />
            Hide persistent heat sources
          </label>
        </div>
      </div>

      {snapshot.clusters.length === 0 ? (
        <p data-testid="no-activity" className="text-slate-600">
          No recent heat detections in the window. That doesn&rsquo;t mean nothing is burning: clouds, smoke and
          satellite timing can hide fires.
        </p>
      ) : shown.length === 0 ? (
        <p data-testid="no-match" className="text-slate-600">No clusters match these filters.</p>
      ) : (
        <ol className="space-y-2">
          {shown.map((c) => (
            <li
              key={c.id}
              data-testid="activity-cluster"
              data-cluster={c.id}
              onClick={() => onSelect(c)}
              className={`cursor-pointer rounded-lg border bg-white p-3 shadow-sm ${c.id === selected ? "border-amber-500 ring-2 ring-amber-300" : "border-slate-200"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="font-semibold">
                  {c.rank}. {clusterTitle(c)}
                </span>
                <ConfidenceChip value={c.label} />
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-700">
                <span data-testid="place">{placeLabel(c)}</span>
                <TrendBadge c={c} />
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {c.detections} detection{c.detections === 1 ? "" : "s"} ({c.high_confidence} high confidence) · max{" "}
                {c.max_frp} {c.frp_units} · last seen {ago(c.last_seen)}
              </div>
              <div className="text-xs text-slate-500">
                Seen by {(c.satellites ?? []).map((s) => SATELLITE_NAMES[s] ?? s).join(", ")}
                {c.official?.gis_acres ? ` · official perimeter ${c.official.gis_acres.toLocaleString()} acres` : ""}
                {c.official?.percent_contained != null ? `, ${c.official.percent_contained}% contained` : ""}
                {!c.official && c.nearest_official
                  ? ` · nearest official incident: ${c.nearest_official.incident_name ?? "unnamed"}, ${c.nearest_official.distance_km} km away`
                  : ""}
              </div>
              {c.persistent_heat_source && (
                <p data-testid="persistent" className="mt-1 rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">
                  Likely persistent heat source (e.g. industrial): seen on {c.days_seen ?? 5} of the last 14 days, no
                  official fire perimeter.
                </p>
              )}
              {c.id === selected && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onAnalyse(c);
                  }}
                  className="mt-2 rounded bg-teal-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-teal-800"
                >
                  Analyse this area
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
      {hiddenPersistent > 0 && (
        <p className="mt-2 text-xs text-slate-500">{hiddenPersistent} persistent heat source(s) hidden.</p>
      )}
      <ul className="mt-3 ml-4 list-disc text-[11px] text-slate-500">
        {snapshot.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <p className="mt-1 text-[11px] text-slate-500">
        Sources:{" "}
        {snapshot.sources.map((s, i) => (
          <span key={s.source}>
            {i > 0 && ", "}
            <a href={s.source_url} target="_blank" rel="noreferrer" className="underline">
              {s.source}
            </a>
          </span>
        ))}
      </p>
    </section>
  );
}
