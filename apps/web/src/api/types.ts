// Hand-written from contracts/openapi.yaml and contracts/*.schema.json (the source of truth).
// If a contract changes, change these types in the same PR.

export type JobStatus =
  | "queued"
  | "validating"
  | "retrieving_data"
  | "processing_satellite"
  | "verifying_evidence"
  | "generating_report"
  | "completed"
  | "failed"
  | "cancelled";

export const TERMINAL: ReadonlySet<JobStatus> = new Set(["completed", "failed", "cancelled"]);

export type EvidenceType =
  | "satellite_detection"
  | "satellite_measurement"
  | "official_perimeter"
  | "official_hazard_zone"
  | "weather_observation"
  | "weather_forecast"
  | "weather_alert"
  | "air_quality_observation"
  | "deterministic_calculation"
  | "agent_inference";

export type ConfidenceLabel =
  | "unverified_detection"
  | "corroborated_signal"
  | "officially_reported"
  | "insufficient_evidence";

export interface Polygon {
  type: "Polygon";
  coordinates: number[][][];
}
export interface MultiPolygon {
  type: "MultiPolygon";
  coordinates: number[][][][];
}
export type AreaGeometry = Polygon | MultiPolygon;

export interface Geometry {
  type: string;
  coordinates: unknown;
}

export interface DateRange {
  start: string; // YYYY-MM-DD
  end: string;
}

export interface CreateAnalysisRequest {
  question: string;
  analysis_type: "historical_fire_impact";
  date_range: DateRange;
  area?: AreaGeometry;
  area_id?: string;
}

export interface CreateAnalysisResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
}

export interface AnalysisJob {
  id: string;
  status: JobStatus;
  progress: number;
  question: string;
  analysis_type: string;
  area_id: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested_at: string | null;
}

export interface JobEvent {
  schema_version: "1";
  job_id: string;
  seq: number;
  status: JobStatus;
  progress: number;
  stage: string;
  message?: string | null;
  error_code?: string | null;
  at: string;
}

export interface Evidence {
  id: string;
  job_id: string | null;
  evidence_type: EvidenceType;
  source: string;
  source_record_id?: string | null;
  observed_at: string;
  retrieved_at: string;
  geometry: Geometry | null;
  properties: Record<string, unknown>;
  quality_flags: string[];
  limitations: string[];
  source_url: string;
}

export interface EvidencePage {
  items: Evidence[];
  next_cursor: string | null;
}

export interface LegendItem {
  label: string;
  color: string;
}

export interface Layer {
  id: string;
  title: string;
  kind: "vector" | "raster";
  evidence_types?: EvidenceType[];
  tile_template?: string | null;
  bounds?: [number, number, number, number] | null;
  legend: LegendItem[];
  attribution: string;
  observed_from?: string | null;
  observed_to?: string | null;
  expires_at?: string | null;
}

export type SectionKey =
  | "short_answer"
  | "observed"
  | "calculated"
  | "official"
  | "agreement"
  | "limitations"
  | "layers_and_charts"
  | "sources";

export interface ReportSection {
  key: SectionKey;
  title: string;
  markdown: string;
  evidence_ids: string[];
}

export interface Report {
  job_id: string;
  confidence: ConfidenceLabel;
  sections: ReportSection[];
  limitations: string[];
  sources: { source: string; source_url: string }[];
  pdf_url: string | null;
  generated_at: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// GET /v1/activity (ADR-013)
export interface ActivityCluster {
  id: string;
  rank: number;
  label: "unverified_detection" | "officially_reported";
  centroid: { type: "Point"; coordinates: [number, number] };
  footprint: Geometry;
  suggested_area: Polygon;
  detections: number;
  high_confidence: number;
  max_frp: number;
  total_frp?: number;
  frp_units: "MW";
  first_seen: string;
  last_seen: string;
  satellites?: string[];
  official: {
    incident_name: string | null;
    gis_acres?: number | null;
    percent_contained?: number | null;
    incident_type?: string | null;
    source: string;
  } | null;
  nearest_official: { incident_name: string | null; distance_km: number } | null;
  place: { county: string; state: string } | null;
  trend: { status: "new" | "growing" | "stable" | "shrinking"; detections_24h_ago: number } | null;
  persistent_heat_source: boolean;
  days_seen?: number;
}

export interface ActivitySnapshot {
  generated_at: string;
  data_mode: "live" | "fixture";
  window_days: number;
  detections_considered?: number;
  sources: { source: string; source_url: string }[];
  limitations: string[];
  clusters: ActivityCluster[];
}
