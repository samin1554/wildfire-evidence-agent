import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActivityCluster, ActivitySnapshot } from "../api/types";
import { ActivityPanel, ago, clusterTitle, placeLabel } from "./ActivityPanel";
import { applyFilters, DEFAULT_FILTERS } from "./filters";
import { parseUrl, toSearch } from "../app/url";

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
  nearest_official: null,
  place: { county: "Grant County", state: "OR" },
  trend: { status: "new", detections_24h_ago: 0 },
  persistent_heat_source: false,
  satellites: ["N21", "N20"],
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
const F = { filters: DEFAULT_FILTERS, onFilters: noop };

describe("ActivityPanel", () => {
  it("lists clusters with honest labels, counts and limitations", () => {
    const official = cluster({
      id: "c2",
      rank: 2,
      label: "officially_reported",
      official: { incident_name: "Second Flat", gis_acres: 105854, percent_contained: 30, incident_type: "wildfire", source: "NIFC" },
    });
    render(<ActivityPanel snapshot={snap([cluster(), official])} error={null} selected={null} onSelect={noop} onAnalyse={noop} {...F} />);
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
    const { rerender } = render(<ActivityPanel snapshot={snap([cluster()])} error={null} selected={null} onSelect={onSelect} onAnalyse={onAnalyse} {...F} />);
    fireEvent.click(screen.getByTestId("activity-cluster"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
    rerender(<ActivityPanel snapshot={snap([cluster()])} error={null} selected="c1" onSelect={onSelect} onAnalyse={onAnalyse} {...F} />);
    fireEvent.click(screen.getByText("Analyse this area"));
    expect(onAnalyse.mock.calls[0][0].suggested_area.type).toBe("Polygon");
  });

  it("empty window never says nothing is burning; recorded data is badged; errors are shown", () => {
    render(<ActivityPanel snapshot={snap([], "fixture")} error={null} selected={null} onSelect={noop} onAnalyse={noop} {...F} />);
    expect(screen.getByTestId("no-activity").textContent).toMatch(/doesn.t mean nothing is burning/);
    expect(screen.getByText("recorded data")).toBeTruthy();
    cleanup();
    render(<ActivityPanel snapshot={null} error="Couldn't load recent activity." selected={null} onSelect={noop} onAnalyse={noop} {...F} />);
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


describe("richer cards", () => {
  it("shows place, trend, satellites, nearest official incident and the persistent-source note", () => {
    const flare = cluster({ id: "f", rank: 2, persistent_heat_source: true, days_seen: 9, place: { county: "Eddy County", state: "NM" } });
    const near = cluster({ nearest_official: { incident_name: "Second Flat", distance_km: 40.9 }, trend: { status: "growing", detections_24h_ago: 4 } });
    render(
      <ActivityPanel snapshot={snap([near, flare])} error={null} selected={null} onSelect={noop} onAnalyse={noop} filters={{ ...DEFAULT_FILTERS, hidePersistent: false }} onFilters={noop} />,
    );
    expect(screen.getByText("Grant County, OR")).toBeTruthy();
    expect(screen.getByText("Growing ▲")).toBeTruthy();
    expect(screen.getAllByText(/Seen by NOAA-21, NOAA-20/).length).toBe(2);
    expect(screen.getByText(/nearest official incident: Second Flat, 40.9 km away/)).toBeTruthy();
    expect(screen.getByTestId("persistent").textContent).toMatch(/seen on 9 of the last 14 days/);
  });

  it("hides persistent sources by default and says so", () => {
    render(<ActivityPanel snapshot={snap([cluster(), cluster({ id: "f", rank: 2, persistent_heat_source: true })])} error={null} selected={null} onSelect={noop} onAnalyse={noop} {...F} />);
    expect(screen.getAllByTestId("activity-cluster")).toHaveLength(1);
    expect(screen.getByText("1 persistent heat source(s) hidden.")).toBeTruthy();
  });

  it("place falls back to coordinates offshore", () => {
    expect(placeLabel(cluster({ place: null }))).toBe("near 44.00°N, 119.00°W");
  });
});

describe("filters", () => {
  const cs = [
    cluster({ id: "a", rank: 1, detections: 5, last_seen: "2026-10-03T01:00:00Z" }),
    cluster({ id: "b", rank: 2, detections: 50, label: "officially_reported", place: { county: "Mariposa County", state: "CA" }, last_seen: "2026-10-03T05:00:00Z" }),
    cluster({ id: "c", rank: 3, detections: 9, persistent_heat_source: true, place: { county: "Eddy County", state: "NM" } }),
  ];
  it("filter by state, official, size and persistence; sort", () => {
    const ids = (f: Partial<typeof DEFAULT_FILTERS>) => applyFilters(cs, { ...DEFAULT_FILTERS, ...f }).map((c) => c.id);
    expect(ids({})).toEqual(["a", "b"]);
    expect(ids({ hidePersistent: false })).toEqual(["a", "b", "c"]);
    expect(ids({ state: "CA" })).toEqual(["b"]);
    expect(ids({ officialOnly: true })).toEqual(["b"]);
    expect(ids({ minDetections: 10 })).toEqual(["b"]);
    expect(ids({ sort: "detections", hidePersistent: false })).toEqual(["b", "c", "a"]);
    expect(ids({ sort: "newest" })).toEqual(["b", "a"]);
  });
  it("no match says so", () => {
    render(<ActivityPanel snapshot={snap(cs)} error={null} selected={null} onSelect={noop} onAnalyse={noop} filters={{ ...DEFAULT_FILTERS, state: "TX" }} onFilters={noop} />);
    expect(screen.getByTestId("no-match")).toBeTruthy();
  });
});

describe("shareable URL", () => {
  it("round-trips tab, cluster, job and filters; ignores junk", () => {
    const s = parseUrl("?tab=active&cluster=c-2343_692&state=CA&official=1&min=5&persistent=show&sort=newest");
    expect(s).toEqual({
      tab: "active",
      cluster: "c-2343_692",
      job: null,
      filters: { state: "CA", officialOnly: true, minDetections: 5, hidePersistent: false, sort: "newest" },
    });
    expect(parseUrl(toSearch(s))).toEqual(s);
    expect(parseUrl("?job=abc").tab).toBe("analyse");
    const junk = parseUrl("?state=<script>&min=-3&sort=evil");
    expect(junk.filters).toEqual(DEFAULT_FILTERS);
  });
});
