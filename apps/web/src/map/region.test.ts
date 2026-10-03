import { describe, expect, it } from "vitest";
import type { Polygon } from "../api/types";
import outline from "../../public/region.geojson?raw";
import { areaKm2, box, checkArea, PRESETS, selfIntersects, setRegion } from "./region";

setRegion(JSON.parse(outline));

describe("area checks", () => {
  it("accepts the demo areas", () => {
    expect(checkArea(PRESETS.lineFire.area as Polygon)).toBeNull();
    expect(checkArea(PRESETS.recent.area as Polygon)).toBeNull();
    expect(checkArea(PRESETS.thompson.area as Polygon)).toBeNull();
    expect(checkArea(PRESETS.alexander.area as Polygon)).toBeNull();
    expect(checkArea(box(-150.0, 61.1, -149.8, 61.25))).toBeNull(); // Anchorage
    expect(checkArea(box(-157.95, 21.28, -157.8, 21.35))).toBeNull(); // Honolulu
    expect(checkArea(box(-118.4, 34.0, -118.2, 34.1))).toBeNull(); // Los Angeles is in scope statewide
  });
  it("rejects missing, outside-county, too-large and self-intersecting areas", () => {
    expect(checkArea(null)).toMatch(/Draw an area/);
    expect(checkArea(box(-112.2, 33.3, -111.9, 33.6))).toBeNull(); // Phoenix is in scope now
    expect(checkArea(box(-117.1, 32.45, -116.9, 32.52))).toMatch(/inside the United States/); // Tijuana
    expect(checkArea(box(-123.2, 49.2, -123.0, 49.3))).toMatch(/inside the United States/); // Vancouver
    expect(checkArea(box(-121.5, 36, -119, 37.5))).toMatch(/too large/);
    const bowtie: Polygon = { type: "Polygon", coordinates: [[[-117, 34], [-116.9, 34.1], [-116.9, 34], [-117, 34.1], [-117, 34]]] };
    expect(selfIntersects(bowtie)).toBe(true);
    expect(checkArea(bowtie)).toMatch(/cross/);
  });
  it("computes area roughly right", () => {
    // 0.1° x 0.1° near 34°N ≈ 11.1 km x 9.2 km ≈ 102 km²
    expect(areaKm2(box(-117, 34, -116.9, 34.1))).toBeGreaterThan(95);
    expect(areaKm2(box(-117, 34, -116.9, 34.1))).toBeLessThan(110);
  });
});
