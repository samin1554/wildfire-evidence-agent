import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActivityCluster, ActivitySnapshot } from "../api/types";
import { ActivityPanel, ago, clusterTitle } from "./ActivityPanel";

afterEach(cleanup);

const cluster = (over: Partial<ActivityCluster> = {}): ActivityCluster => ({
  id: "c1",
  rank: 1,
  label: "unverified_detection",
  centroid: { type: "Point", coordinates: [-119.0, 44.0] },
  footprint: { type: "Point", coordinates: [-119.0, 44.0] },
  suggested_area: { type: "Polygon", coordinates: [[[-119.1, 43.9], [-118.9, 43.9], [-118.9, 44.1], [-119.1, 44.1], [-119.1, 43.9]]] },
  detections: 12,
  high_confidence: 3,
  max_frp: 40.5,
  frp_units: "MW",
  first_seen: "2026-10-02T06:00:00Z",
  last_seen: "2026-10-03T06:00:00Z",
  official: null,
  ...over,
});

const snap = (clusters: ActivityCluster[], mode: "live" | "fixture" = "live"): ActivitySnapshot => ({
  generated_at: new Date().toISOString(),
  data_mode: mode,
  window_days: 2,
  sources: [{ source: "NASA FIRMS", source_url: "https://firms.modaps.eosdis.nasa.gov/" }],
  limitations: ["Satellite heat detections are not confirmed fires."],
  clusters,
});

const noop = () => undefined;

describe("ActivityPanel", () => {
  it("lists clusters with honest labels, counts and limitations", () => {
    const official = cluster({
      id: "c2",
      rank: 2,
      label: "officially_reported",
      official: { incident_name: "Second Flat", gis_acres: 105854, percent_contained: 30, incident_type: "wildfire", source: "NIFC" },
    });
    render(<ActivityPanel snapshot={snap([cluster(), official])} error={null} selected={null} onSelect={noop} onAnalyse={noop} />);
    expect(screen.getAllByTestId("activity-cluster")).toHaveLength(2);
    expect(screen.getByText("1. Unnamed heat cluster")).toBeTruthy();
    expect(screen.getByText("Unverified detection")).toBeTruthy();
    expect(screen.getByText("2. Second Flat")).toBeTruthy();
    expect(screen.getByText(/105,854 acres, 30% contained/)).toBeTruthy();
    expect(screen.getByText(/not confirmed fires/)).toBeTruthy();
    expect(screen.queryByText("recorded data")).toBeNull();
  });

  it("selecting a cluster offers 'Analyse this area' with its suggested area", () => {
    const onAnalyse = vi.fn();
    const onSelect = vi.fn();
    const { rerender } = render(<ActivityPanel snapshot={snap([cluster()])} error={null} selected={null} onSelect={onSelect} onAnalyse={onAnalyse} />);
    fireEvent.click(screen.getByTestId("activity-cluster"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
    rerender(<ActivityPanel snapshot={snap([cluster()])} error={null} selected="c1" onSelect={onSelect} onAnalyse={onAnalyse} />);
    fireEvent.click(screen.getByText("Analyse this area"));
    expect(onAnalyse.mock.calls[0][0].suggested_area.type).toBe("Polygon");
  });

  it("empty window never says nothing is burning; recorded data is badged; errors are shown", () => {
    render(<ActivityPanel snapshot={snap([], "fixture")} error={null} selected={null} onSelect={noop} onAnalyse={noop} />);
    expect(screen.getByTestId("no-activity").textContent).toMatch(/doesn.t mean nothing is burning/);
    expect(screen.getByText("recorded data")).toBeTruthy();
    cleanup();
    render(<ActivityPanel snapshot={null} error="Couldn't load recent activity." selected={null} onSelect={noop} onAnalyse={noop} />);
    expect(screen.getByText("Couldn't load recent activity.")).toBeTruthy();
  });

  it("labels prescribed burns and formats times", () => {
    expect(clusterTitle(cluster({ official: { incident_name: "Unit 7", incident_type: "prescribed burn", source: "NIFC" } }))).toBe(
      "Unit 7 (prescribed burn)",
    );
    const now = Date.parse("2026-10-03T09:00:00Z");
    expect(ago("2026-10-03T08:30:00Z", now)).toBe("30 min ago");
    expect(ago("2026-10-03T06:00:00Z", now)).toBe("3 h ago");
    expect(ago("2026-09-23T09:00:00Z", now)).toBe("10 days ago");
  });
});
