import { useMemo, useState } from "react";
import { ConfidenceChip, EvidenceCard, ProgressList, ReportPanel } from "../analysis/components";
import { useAnalysis } from "../analysis/useAnalysis";
import { ERROR_HELP } from "../analysis/vocabulary";
import { TERMINAL, type EvidenceType, type Polygon } from "../api/types";
import { MapView } from "../map/MapView";
import { checkArea, PRESETS } from "../map/region";

const today = new Date().toISOString().slice(0, 10);

export function App() {
  const [aoi, setAoi] = useState<Polygon | null>(null);
  const [question, setQuestion] = useState<string>(PRESETS.lineFire.question);
  const [start, setStart] = useState<string>(PRESETS.lineFire.date_range.start);
  const [end, setEnd] = useState<string>(PRESETS.lineFire.date_range.end);
  const [selected, setSelected] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<EvidenceType | "all">("all");
  const { jobId, progress, error, results, submitting, submit, cancel } = useAnalysis();

  const running = !!jobId && !TERMINAL.has(progress.status);
  const areaProblem = checkArea(aoi);
  const dateProblem = !start || !end ? "Choose both dates." : end < start ? "The end date is before the start date." : null;

  const usePreset = (p: (typeof PRESETS)[keyof typeof PRESETS]) => {
    setAoi(p.area as Polygon);
    setQuestion(p.question);
    setStart(p.date_range.start);
    setEnd(p.date_range.end);
  };

  const evidence = results?.evidence ?? [];
  const shownEvidence = useMemo(
    () => evidence.filter((e) => typeFilter === "all" || e.evidence_type === typeFilter),
    [evidence, typeFilter],
  );
  const types = [...new Set(evidence.map((e) => e.evidence_type))];

  const select = (id: string) => {
    setSelected(id);
    setTypeFilter("all");
    setTimeout(() => document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };

  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="flex w-full flex-col overflow-y-auto border-r border-slate-200 bg-[#fbfaf7] md:w-[440px] md:min-w-[440px]">
        <header className="border-b border-slate-200 px-4 py-3">
          <h1 className="text-lg font-semibold">Inland Resilience Agent</h1>
          <p className="text-xs text-slate-600">
            Evidence-backed wildfire-impact research for San Bernardino County. Not an emergency, evacuation or
            prediction service: for emergencies call 911 and follow official alerts.
          </p>
        </header>

        <form
          className="space-y-3 border-b border-slate-200 px-4 py-4 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (areaProblem || dateProblem || !aoi) return;
            setSelected(null);
            submit({ question, analysis_type: "historical_fire_impact", date_range: { start, end }, area: aoi });
          }}
        >
          <div>
            <div className="mb-1 font-medium">Demo areas</div>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={running} onClick={() => usePreset(PRESETS.lineFire)} className="rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50 disabled:opacity-40">
                {PRESETS.lineFire.name}
              </button>
              <button type="button" disabled={running} onClick={() => usePreset(PRESETS.recent)} className="rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50 disabled:opacity-40">
                {PRESETS.recent.name}
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-500">Or draw your own area on the map.</p>
          </div>
          <label className="block">
            <span className="font-medium">Question</span>
            <textarea
              aria-label="Question"
              value={question}
              maxLength={2000}
              rows={3}
              onChange={(e) => setQuestion(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 bg-white p-2"
            />
          </label>
          <div className="flex gap-2">
            <label className="flex-1">
              <span className="font-medium">From</span>
              <input aria-label="From" type="date" value={start} max={today} onChange={(e) => setStart(e.target.value)} className="mt-1 w-full rounded border border-slate-300 bg-white p-1.5" />
            </label>
            <label className="flex-1">
              <span className="font-medium">To</span>
              <input aria-label="To" type="date" value={end} max={today} onChange={(e) => setEnd(e.target.value)} className="mt-1 w-full rounded border border-slate-300 bg-white p-1.5" />
            </label>
          </div>
          {(areaProblem || dateProblem) && <p className="text-xs text-amber-800">{areaProblem ?? dateProblem}</p>}
          {error && (
            <p role="alert" className="rounded bg-red-50 p-2 text-xs text-red-900">
              {error.message} {ERROR_HELP[error.code] ?? ""}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={!!areaProblem || !!dateProblem || !question.trim() || running || submitting}
              className="rounded bg-teal-700 px-3 py-1.5 font-medium text-white hover:bg-teal-800 disabled:opacity-40"
            >
              {submitting ? "Submitting…" : "Run analysis"}
            </button>
            {running && (
              <button type="button" onClick={cancel} className="rounded border border-slate-300 bg-white px-3 py-1.5">
                Cancel
              </button>
            )}
          </div>
        </form>

        {jobId && (
          <section className="border-b border-slate-200 px-4 py-4">
            <h2 className="mb-2 text-sm font-semibold">Progress</h2>
            <ProgressList progress={progress} />
          </section>
        )}

        {results?.report && (
          <section className="border-b border-slate-200 px-4 py-4">
            <ReportPanel report={results.report} onCite={select} />
          </section>
        )}

        {results && results.job.status === "completed" && (
          <section className="px-4 py-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Evidence ({evidence.length})</h2>
              {results.report && <ConfidenceChip value={results.report.confidence} />}
            </div>
            {types.length > 1 && (
              <select aria-label="Filter evidence" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as EvidenceType | "all")} className="mb-2 w-full rounded border border-slate-300 bg-white p-1 text-sm">
                <option value="all">All types</option>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
            {evidence.length === 0 ? (
              <p data-testid="no-evidence" className="text-sm text-slate-600">
                Insufficient evidence: no source returned data for this area and period. This does not mean nothing
                happened.
              </p>
            ) : (
              <div className="space-y-2">
                {shownEvidence.map((ev) => (
                  <EvidenceCard key={ev.id} ev={ev} highlight={ev.id === selected} onSelect={() => setSelected(ev.id)} />
                ))}
              </div>
            )}
          </section>
        )}
      </aside>
      <main className="h-[60vh] flex-1 md:h-full">
        <MapView
          aoi={aoi}
          onAoiChange={setAoi}
          layers={results?.layers ?? []}
          evidence={evidence}
          onSelectEvidence={select}
          locked={running}
        />
      </main>
    </div>
  );
}
