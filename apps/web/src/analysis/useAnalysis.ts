// One analysis run: POST → SSE progress → results (evidence, layers, report) once terminal.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import {
  TERMINAL,
  type AnalysisJob,
  type CreateAnalysisRequest,
  type Evidence,
  type JobEvent,
  type Layer,
  type Report,
} from "../api/types";
import { applyEvent, initialProgress, type Progress } from "./progress";

export interface Results {
  job: AnalysisJob;
  evidence: Evidence[];
  layers: Layer[];
  report: Report | null;
}

type Action = { type: "reset" } | { type: "event"; ev: JobEvent };

function reducer(state: Progress, action: Action): Progress {
  return action.type === "reset" ? initialProgress : applyEvent(state, action.ev);
}

export function useAnalysis() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, dispatch] = useReducer(reducer, initialProgress);
  const [error, setError] = useState<ApiError | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const source = useRef<EventSource | null>(null);

  const close = () => {
    source.current?.close();
    source.current = null;
  };

  const submit = useCallback(async (req: CreateAnalysisRequest) => {
    close();
    dispatch({ type: "reset" });
    setResults(null);
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.createAnalysis(req);
      setJobId(created.job_id);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "NETWORK", "Could not reach the API."));
    } finally {
      setSubmitting(false);
    }
  }, []);

  // live progress; EventSource reconnects by itself and sends Last-Event-ID, the API replays from there
  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(api.eventsUrl(jobId));
    source.current = es;
    es.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data) as JobEvent;
        dispatch({ type: "event", ev });
        if (TERMINAL.has(ev.status)) es.close();
      } catch {
        /* ignore malformed event */
      }
    };
    return () => es.close();
  }, [jobId]);

  // results once terminal
  useEffect(() => {
    if (!jobId || !TERMINAL.has(progress.status) || progress.seq < 0) return;
    let stale = false;
    (async () => {
      const job = await api.getJob(jobId);
      if (job.status !== "completed") {
        if (!stale) setResults({ job, evidence: [], layers: [], report: null });
        return;
      }
      const [evidence, layers, report] = await Promise.all([
        api.getAllEvidence(jobId),
        api.getLayers(jobId),
        api.getReport(jobId),
      ]);
      if (!stale) setResults({ job, evidence, layers, report });
    })().catch((e) => !stale && setError(e instanceof ApiError ? e : new ApiError(0, "NETWORK", String(e))));
    return () => {
      stale = true;
    };
  }, [jobId, progress.status, progress.seq]);

  /** Reopen an existing analysis (e.g. from a shared ?job= link): live progress if running, results if done. */
  const attach = useCallback(async (id: string) => {
    close();
    dispatch({ type: "reset" });
    setResults(null);
    setError(null);
    try {
      await api.getJob(id);
      setJobId(id);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? new ApiError(404, "NOT_FOUND", "This analysis isn't available.")
          : new ApiError(0, "NETWORK", "Could not reach the API."),
      );
    }
  }, []);

  const cancel = useCallback(async () => {
    if (jobId) await api.cancel(jobId).catch(() => undefined);
  }, [jobId]);

  return { jobId, progress, error, results, submitting, submit, attach, cancel };
}
