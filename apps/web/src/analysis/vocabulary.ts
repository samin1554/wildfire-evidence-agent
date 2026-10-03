// User-facing words. A FIRMS hotspot is never a "confirmed fire"; missing data never means "nothing happened".
import type { ConfidenceLabel, EvidenceType } from "../api/types";

export const CONFIDENCE: Record<ConfidenceLabel, { label: string; help: string; tone: string }> = {
  officially_reported: {
    label: "Officially reported",
    help: "An official source (e.g. a fire perimeter) covers this area and period.",
    tone: "bg-violet-100 text-violet-900 border-violet-300",
  },
  corroborated_signal: {
    label: "Corroborated signal",
    help: "Two independent kinds of evidence agree; not officially confirmed.",
    tone: "bg-amber-100 text-amber-900 border-amber-300",
  },
  unverified_detection: {
    label: "Unverified detection",
    help: "One kind of evidence only (e.g. satellite heat detections). Not a confirmed fire.",
    tone: "bg-orange-100 text-orange-900 border-orange-300",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    help: "The available sources can't answer this. That does not mean nothing happened.",
    tone: "bg-slate-100 text-slate-800 border-slate-300",
  },
};

export const EVIDENCE_LABEL: Record<EvidenceType, string> = {
  satellite_detection: "Satellite heat detection (unverified)",
  satellite_measurement: "Satellite measurement",
  official_perimeter: "Official perimeter",
  official_hazard_zone: "Official hazard zone",
  weather_observation: "Weather observation",
  weather_forecast: "Weather forecast",
  weather_alert: "Weather alert",
  air_quality_observation: "Air quality observation",
  deterministic_calculation: "Calculation (deterministic)",
  agent_inference: "AI interpretation (not an observation)",
};

export const ERROR_HELP: Record<string, string> = {
  AREA_OUTSIDE_REGION: "Draw the area inside California.",
  AREA_TOO_LARGE: "Draw a smaller area (up to 5,000 km²).",
  DATE_RANGE_TOO_LONG: "Choose a date range of up to 3 years.",
  INVALID_GEOMETRY: "The polygon is not valid. Redraw it without crossing lines.",
};
