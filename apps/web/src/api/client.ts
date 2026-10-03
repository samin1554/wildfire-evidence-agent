// The only way the web app talks to the backend: our Go API under /v1 (contracts/openapi.yaml).
import type {
  AnalysisJob,
  ApiErrorBody,
  CreateAnalysisRequest,
  CreateAnalysisResponse,
  Evidence,
  EvidencePage,
  Layer,
  Report,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    let body: Partial<ApiErrorBody> = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, body.code ?? `HTTP_${res.status}`, body.message ?? res.statusText, body.details);
  }
  return (await res.json()) as T;
}

export const api = {
  createAnalysis: (req: CreateAnalysisRequest) =>
    call<CreateAnalysisResponse>("/v1/analyses", { method: "POST", body: JSON.stringify(req) }),
  getJob: (id: string) => call<AnalysisJob>(`/v1/analyses/${id}`),
  cancel: (id: string) => call<AnalysisJob>(`/v1/analyses/${id}/cancel`, { method: "POST" }),
  getLayers: (id: string) => call<{ layers: Layer[] }>(`/v1/analyses/${id}/layers`).then((r) => r.layers),
  getReport: (id: string) => call<Report>(`/v1/analyses/${id}/report`),
  eventsUrl: (id: string) => `/v1/analyses/${id}/events`,
  /** Every evidence item for a job (follows next_cursor). */
  async getAllEvidence(id: string): Promise<Evidence[]> {
    const out: Evidence[] = [];
    let cursor: string | null = null;
    for (let page = 0; page < 50; page++) {
      const qs = new URLSearchParams({ limit: "500", ...(cursor ? { cursor } : {}) });
      const res: EvidencePage = await call<EvidencePage>(`/v1/analyses/${id}/evidence?${qs}`);
      out.push(...res.items);
      cursor = res.next_cursor;
      if (!cursor) break;
    }
    return out;
  },
};
