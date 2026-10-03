import { describe, expect, it } from "vitest";
import type { JobEvent, JobStatus } from "../api/types";
import { applyEvent, initialProgress, stageState } from "./progress";

const ev = (seq: number, status: JobStatus, extra: Partial<JobEvent> = {}): JobEvent => ({
  schema_version: "1",
  job_id: "j",
  seq,
  status,
  progress: seq * 10,
  stage: status,
  at: "2026-09-24T00:00:00Z",
  ...extra,
});

describe("progress reducer", () => {
  it("follows events in order", () => {
    let p = initialProgress;
    for (const [i, s] of (["queued", "validating", "retrieving_data", "completed"] as JobStatus[]).entries())
      p = applyEvent(p, ev(i, s));
    expect(p.status).toBe("completed");
    expect(p.seen).toEqual(["queued", "validating", "retrieving_data", "completed"]);
  });

  it("ignores duplicates and out-of-order events (reconnect replay)", () => {
    let p = applyEvent(initialProgress, ev(3, "verifying_evidence"));
    p = applyEvent(p, ev(2, "retrieving_data"));
    p = applyEvent(p, ev(3, "verifying_evidence"));
    expect(p.status).toBe("verifying_evidence");
    expect(p.seq).toBe(3);
  });

  it("keeps a terminal status final and surfaces the message", () => {
    let p = applyEvent(initialProgress, ev(2, "failed", { error_code: "EMERGENCY_REDIRECT", message: "call 911" }));
    p = applyEvent(p, ev(5, "validating"));
    expect(p.status).toBe("failed");
    expect(p.message).toBe("call 911");
    expect(p.errorCode).toBe("EMERGENCY_REDIRECT");
  });

  it("marks skipped and stopped stages", () => {
    let p = initialProgress;
    for (const [i, s] of (["validating", "retrieving_data", "verifying_evidence"] as JobStatus[]).entries())
      p = applyEvent(p, ev(i + 1, s));
    expect(stageState(p, "processing_satellite")).toBe("skipped");
    expect(stageState(p, "verifying_evidence")).toBe("active");
    expect(stageState(p, "completed")).toBe("pending");
    p = applyEvent(p, ev(9, "cancelled"));
    expect(stageState(p, "generating_report")).toBe("stopped");
    expect(stageState(p, "retrieving_data")).toBe("done");
  });
});
