import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConfidenceLabel, Evidence, Report } from "../api/types";
import { ConfidenceChip, EvidenceCard, ReportPanel } from "./components";
import { CONFIDENCE } from "./vocabulary";

afterEach(cleanup);

const detection: Evidence = {
  id: "e1",
  job_id: "j",
  evidence_type: "satellite_detection",
  source: "NASA FIRMS",
  observed_at: "2026-09-22T09:12:00Z",
  retrieved_at: "2026-09-24T07:07:21Z",
  geometry: { type: "Point", coordinates: [-117.2, 34.6] },
  properties: { confidence: "nominal", frp: 3.1, frp_units: "MW", satellite: "N21", instrument: "VIIRS" },
  quality_flags: [],
  limitations: ["A thermal anomaly is not an officially confirmed wildfire."],
  source_url: "https://firms.modaps.eosdis.nasa.gov/",
};

describe("EvidenceCard", () => {
  it("always shows source, observed and retrieved times and limitations", () => {
    render(<EvidenceCard ev={detection} />);
    expect(screen.getByText("Satellite heat detection (unverified)")).toBeTruthy();
    expect(screen.getByText("NASA FIRMS")).toBeTruthy();
    expect(screen.getByText("2026-09-22 09:12 UTC")).toBeTruthy();
    expect(screen.getByText("2026-09-24 07:07 UTC")).toBeTruthy();
    expect(screen.getByText(/not an officially confirmed wildfire/)).toBeTruthy();
  });
  it("says so when a source reports no limitations", () => {
    render(<EvidenceCard ev={{ ...detection, limitations: [] }} />);
    expect(screen.getByText("None reported by the source.")).toBeTruthy();
  });
  it("never calls a detection a confirmed fire", () => {
    const { container } = render(<EvidenceCard ev={detection} />);
    expect(container.textContent).not.toMatch(/confirmed fire/i);
  });
});

describe("ConfidenceChip", () => {
  it("uses the four contract labels", () => {
    for (const k of Object.keys(CONFIDENCE) as ConfidenceLabel[]) {
      render(<ConfidenceChip value={k} />);
      expect(screen.getByText(CONFIDENCE[k].label)).toBeTruthy();
      cleanup();
    }
    expect(CONFIDENCE.insufficient_evidence.help).toMatch(/does not mean nothing happened/);
  });
});

describe("ReportPanel", () => {
  const report: Report = {
    job_id: "j",
    confidence: "unverified_detection",
    sections: [
      { key: "observed", title: "What was observed", markdown: "2 detections [E4] [E7].", evidence_ids: ["a", "b"] },
      { key: "limitations", title: "Uncertainty and limitations", markdown: "- one\n- two", evidence_ids: [] },
      { key: "sources", title: "Sources", markdown: "- [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)", evidence_ids: [] },
    ],
    limitations: ["one", "two"],
    sources: [{ source: "NASA FIRMS", source_url: "https://firms.modaps.eosdis.nasa.gov/" }],
    pdf_url: null,
    generated_at: "2026-09-24T00:00:00Z",
  };
  it("renders sections, bullet limitations, links and maps citations to evidence ids", () => {
    const onCite = vi.fn();
    render(<ReportPanel report={report} onCite={onCite} />);
    expect(screen.getByText("Unverified detection")).toBeTruthy();
    expect(screen.getByText("two")).toBeTruthy();
    expect(screen.getByText("NASA FIRMS").getAttribute("href")).toBe("https://firms.modaps.eosdis.nasa.gov/");
    fireEvent.click(screen.getByText("E7"));
    expect(onCite).toHaveBeenCalledWith("b");
    expect(screen.getByText(/not an emergency or evacuation service/)).toBeTruthy();
  });
});
