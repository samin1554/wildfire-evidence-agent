// "Active now" (ADR-013): where satellites see heat right now, ranked. A cluster is a place to look at, not a fire.
import type { ActivityCluster, ActivitySnapshot } from "../api/types";
import { ConfidenceChip } from "../analysis/components";

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

export interface ActivityPanelProps {
  snapshot: ActivitySnapshot | null;
  error: string | null;
  selected: string | null;
  onSelect: (c: ActivityCluster) => void;
  onAnalyse: (c: ActivityCluster) => void;
}

export function ActivityPanel({ snapshot, error, selected, onSelect, onAnalyse }: ActivityPanelProps) {
  if (error) return <p className="px-4 py-4 text-sm text-slate-600">{error}</p>;
  if (!snapshot) return <p className="px-4 py-4 text-sm text-slate-600">Loading recent satellite activity…</p>;
  const [lon, lat] = [0, 1]; // GeoJSON order
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
        Last {snapshot.window_days} days, clustered and ranked. Updated {ago(snapshot.generated_at)}. Pick one to
        analyse it.
      </p>
      {snapshot.clusters.length === 0 ? (
        <p data-testid="no-activity" className="text-slate-600">
          No recent heat detections in the window. That doesn&rsquo;t mean nothing is burning: clouds, smoke and
          satellite timing can hide fires.
        </p>
      ) : (
        <ol className="space-y-2">
          {snapshot.clusters.map((c) => (
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
              <div className="mt-1 text-xs text-slate-600">
                {c.detections} detection{c.detections === 1 ? "" : "s"} ({c.high_confidence} high confidence) · max{" "}
                {c.max_frp} {c.frp_units} · last seen {ago(c.last_seen)}
              </div>
              <div className="text-xs text-slate-500">
                {c.centroid.coordinates[lat].toFixed(2)}°N, {Math.abs(c.centroid.coordinates[lon]).toFixed(2)}°W
                {c.official?.gis_acres ? ` · official perimeter ${c.official.gis_acres.toLocaleString()} acres` : ""}
                {c.official?.percent_contained != null ? `, ${c.official.percent_contained}% contained` : ""}
              </div>
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
