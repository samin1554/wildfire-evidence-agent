import { describe, expect, it } from "vitest";
import type { Polygon } from "../api/types";
import { areaKm2, box, checkArea, PRESETS, selfIntersects } from "./region";

describe("area checks", () => {
  it("accepts the demo areas", () => {
    expect(checkArea(PRESETS.lineFire.area as Polygon)).toBeNull();
    expect(checkArea(PRESETS.recent.area as Polygon)).toBeNull();
  });
  it("rejects missing, outside-county, too-large and self-intersecting areas", () => {
    expect(checkArea(null)).toMatch(/Draw an area/);
    expect(checkArea(box(-118.5, 34, -118.2, 34.2))).toMatch(/San Bernardino/);
    expect(checkArea(box(-117.5, 34, -115, 35.5))).toMatch(/too large/);
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
