// Progress state from SSE job events. Events can repeat (reconnects replay the DB snapshot) or arrive out of
// order; the highest `seq` wins and a terminal status is final.
import { TERMINAL, type JobEvent, type JobStatus } from "../api/types";

export const STAGES: { status: JobStatus; label: string }[] = [
  { status: "queued", label: "Queued" },
  { status: "validating", label: "Checking the question, area and dates" },
  { status: "retrieving_data", label: "Retrieving data from approved sources" },
  { status: "processing_satellite", label: "Processing satellite imagery" },
  { status: "verifying_evidence", label: "Verifying evidence" },
  { status: "generating_report", label: "Writing the cited report" },
  { status: "completed", label: "Completed" },
];

export interface Progress {
  seq: number;
  status: JobStatus;
  progress: number;
  stage: string;
  seen: JobStatus[]; // statuses reached, in order
  message?: string | null;
  errorCode?: string | null;
}

export const initialProgress: Progress = { seq: -1, status: "queued", progress: 0, stage: "Queued", seen: [] };

export function applyEvent(state: Progress, ev: JobEvent): Progress {
  if (ev.seq <= state.seq) return state; // duplicate or stale
  if (TERMINAL.has(state.status) && state.seq >= 0) return state;
  const seen = state.seen.includes(ev.status) ? state.seen : [...state.seen, ev.status];
  return {
    seq: ev.seq,
    status: ev.status,
    progress: ev.progress,
    stage: ev.stage,
    seen,
    message: ev.message ?? state.message,
    errorCode: ev.error_code ?? null,
  };
}

export type StageState = "done" | "active" | "pending" | "skipped" | "stopped";

export function stageState(p: Progress, status: JobStatus): StageState {
  const order = STAGES.findIndex((s) => s.status === status);
  const current = STAGES.findIndex((s) => s.status === p.status);
  if (p.status === "failed" || p.status === "cancelled") {
    return p.seen.includes(status) ? "done" : "stopped";
  }
  if (status === p.status) return p.status === "completed" ? "done" : "active";
  if (p.seen.includes(status)) return "done";
  if (current > order) return "skipped"; // e.g. no satellite stage for a recent-detections question
  return "pending";
}
