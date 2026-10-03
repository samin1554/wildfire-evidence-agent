import { Fragment, type ReactNode } from "react";
import type { ConfidenceLabel, Evidence, Report } from "../api/types";
import { STAGES, stageState, type Progress } from "./progress";
import { CONFIDENCE, EVIDENCE_LABEL } from "./vocabulary";

const fmt = (iso: string) => new Date(iso).toISOString().replace("T", " ").slice(0, 16) + " UTC";

export function ConfidenceChip({ value }: { value: ConfidenceLabel }) {
  const c = CONFIDENCE[value];
  return (
    <span
      data-testid="confidence-chip"
      title={c.help}
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${c.tone}`}
    >
      {c.label}
    </span>
  );
}

const ICON = { done: "●", active: "◐", pending: "○", skipped: "–", stopped: "○" } as const;

export function ProgressList({ progress }: { progress: Progress }) {
  const ended = progress.status === "failed" || progress.status === "cancelled";
  return (
    <div data-testid="progress">
      <div className="mb-2 h-1.5 w-full overflow-hidden rounded bg-slate-200">
        <div
          className={`h-full transition-all ${ended ? "bg-slate-400" : "bg-emerald-600"}`}
          style={{ width: `${progress.progress}%` }}
        />
      </div>
      <ol className="space-y-1 text-sm">
        {STAGES.map((s) => {
          const st = stageState(progress, s.status);
          return (
            <li key={s.status} data-state={st} data-status={s.status} className="flex items-center gap-2">
              <span
                className={
                  st === "done"
                    ? "text-emerald-700"
                    : st === "active"
                      ? "animate-pulse text-amber-600"
                      : "text-slate-400"
                }
              >
                {ICON[st]}
              </span>
              <span className={st === "pending" || st === "skipped" || st === "stopped" ? "text-slate-400" : ""}>
                {s.label}
                {st === "skipped" ? " (not needed)" : ""}
              </span>
            </li>
          );
        })}
        {ended && (
          <li data-status={progress.status} className="flex items-center gap-2 font-medium text-red-800">
            <span>✕</span>
            <span>{progress.status === "failed" ? "Stopped" : "Cancelled"}</span>
          </li>
        )}
      </ol>
      {progress.message && <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-900">{progress.message}</p>}
    </div>
  );
}

function summarize(ev: Evidence): string {
  const p = ev.properties as Record<string, unknown>;
  switch (ev.evidence_type) {
    case "satellite_detection":
      return `${p.satellite ?? ""} ${p.instrument ?? ""} · confidence ${p.confidence ?? "?"} · FRP ${p.frp ?? "?"} ${p.frp_units ?? ""}`;
    case "official_perimeter":
      return `${p.incident_name ?? "Perimeter"} · ${p.gis_acres ?? "?"} acres`;
    case "weather_forecast":
      return `Forecast office ${p.office ?? ""}`;
    case "deterministic_calculation":
      if ("dnbr_median" in p)
        return `dNBR median ${p.dnbr_median} (${p.before_date} → ${p.after_date}), ${p.valid_pixel_pct}% usable pixels`;
      if ("ndvi_change_median" in p)
        return `NDVI change median ${p.ndvi_change_median} (${p.before_date} → ${p.after_date})`;
      return String(p.method ?? "Calculation");
    case "agent_inference":
      return "AI wording of the cited evidence";
    default:
      return String(p.method ?? p.date ?? "");
  }
}

export function EvidenceCard({ ev, highlight, onSelect }: { ev: Evidence; highlight?: boolean; onSelect?: () => void }) {
  return (
    <article
      data-testid="evidence-card"
      id={`ev-${ev.id}`}
      onClick={onSelect}
      className={`cursor-pointer rounded-lg border bg-white p-3 text-sm shadow-sm ${highlight ? "border-amber-500 ring-2 ring-amber-300" : "border-slate-200"}`}
    >
      <header className="mb-1 flex items-start justify-between gap-2">
        <span className="font-semibold">{EVIDENCE_LABEL[ev.evidence_type]}</span>
        <a href={ev.source_url} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-sky-700 underline">
          source
        </a>
      </header>
      <p className="text-slate-700">{summarize(ev)}</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 text-xs text-slate-600">
        <dt>Source</dt>
        <dd>{ev.source}</dd>
        <dt>Observed</dt>
        <dd>{fmt(ev.observed_at)}</dd>
        <dt>Retrieved</dt>
        <dd>{fmt(ev.retrieved_at)}</dd>
        {ev.quality_flags.length > 0 && (
          <>
            <dt>Flags</dt>
            <dd>{ev.quality_flags.join(", ")}</dd>
          </>
        )}
      </dl>
      <div className="mt-2 text-xs">
        <span className="font-medium text-slate-700">Limitations</span>
        {ev.limitations.length ? (
          <ul className="ml-4 list-disc text-slate-600">
            {ev.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">None reported by the source.</p>
        )}
      </div>
    </article>
  );
}

/** Minimal markdown: paragraphs, "- " bullets, [text](url) links, and [E3]-style citation refs. */
export function Markdown({ text, onCite }: { text: string; onCite?: (ref: string) => void }) {
  const inline = (s: string): ReactNode[] =>
    s.split(/(\[[^\]]+\]\([^)]+\)|\[E\d+\])/g).map((part, i) => {
      const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link)
        return (
          <a key={i} href={link[2]} target="_blank" rel="noreferrer" className="text-sky-700 underline">
            {link[1]}
          </a>
        );
      const cite = part.match(/^\[(E\d+)\]$/);
      if (cite)
        return (
          <button key={i} onClick={() => onCite?.(cite[1])} className="mx-0.5 rounded bg-slate-200 px-1 text-[10px] font-mono">
            {cite[1]}
          </button>
        );
      return <Fragment key={i}>{part}</Fragment>;
    });
  const lines = text.split("\n").filter((l) => l.trim());
  const bullets = lines.every((l) => l.startsWith("- "));
  return bullets ? (
    <ul className="ml-4 list-disc">
      {lines.map((l, i) => (
        <li key={i}>{inline(l.slice(2))}</li>
      ))}
    </ul>
  ) : (
    <>
      {lines.map((l, i) => (
        <p key={i} className="mb-1">
          {inline(l)}
        </p>
      ))}
    </>
  );
}

export function ReportPanel({ report, onCite }: { report: Report; onCite: (evidenceId: string) => void }) {
  return (
    <section data-testid="report" className="space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold">Report</h2>
        <ConfidenceChip value={report.confidence} />
      </div>
      {report.sections.map((s) => {
        // evidence_ids lists the section's distinct refs in order of first appearance (worker: agent/graph.py)
        const refs = [...new Set(s.markdown.match(/\[E\d+\]/g) ?? [])].map((r) => r.slice(1, -1));
        return (
          <div key={s.key} data-section={s.key}>
            <h3 className="font-semibold text-slate-800">{s.title}</h3>
            <div className={s.key === "limitations" ? "rounded bg-amber-50 p-2 text-amber-950" : "text-slate-700"}>
              <Markdown
                text={s.markdown}
                onCite={(ref) => {
                  const id = s.evidence_ids[refs.indexOf(ref)];
                  if (id) onCite(id);
                }}
              />
            </div>
          </div>
        );
      })}
      <p className="text-xs text-slate-500">
        Generated {fmt(report.generated_at)}. Research tool, not an emergency or evacuation service.
      </p>
    </section>
  );
}
