# Proof of concept: Line Fire 2024 burn severity without Earth Engine

Run on Sep 24, 2026 to check [ADR-009](../../adr/ADR-009-imagery-without-earth-engine.md) before committing to it.

![Line Fire: Sentinel-2 dNBR vs official BAER](line-fire-2024-dnbr-vs-baer.png)

**What it does:** finds the least-cloudy Sentinel-2 L2A scenes before (Aug 20, 2024) and after (Oct 19, 2024) the fire through Earth Search (no account); reads only the fire area from the image files; masks clouds with SCL; computes NBR and dNBR; classifies severity; and compares that pixel-by-pixel with the official USFS BAER soil burn severity map on the same 20 m grid.

**Result** ([results.json](results.json)): 100% cloud-free pixels inside the perimeter, about 30–45 s end to end, dNBR median 0.63 inside the fire vs 0.002 outside, **54.9% exact class agreement, 98.5% within one class** (the first prototype reported 54.5% / 98.2%; the kit's exact 20 m grid aligns the BAER download more precisely). Our "High" is larger than BAER's because dNBR measures vegetation loss while BAER measures soil damage. The thresholds are the standard USGS forest values and need calibrating for chaparral.

**Lessons, now built into `kit/imagery.py` and the `earth_search_s2` connector:**
1. **Scaling:** apply the −0.1 BOA offset **only when** `earthsearch:boa_offset_applied` is false, checked per item. Asset metadata advertises the offset either way. Getting it wrong produced impossible dNBR values (> 2) in the first run.
2. **Duplicates:** the same tile can appear twice on one date (e.g. Sentinel-2A and 2C passing the same day: `S2A_…_0_L2A` / `S2C_…_1_L2A`); keep one per tile (the least cloudy).
3. **Geometry:** the CAL FIRE Line Fire perimeter is invalid (self-touching ring); repair it (`make_valid`) before use.
4. **BAER** `exportImage` works on our own grid (`bboxSR`/`imageSR` 32611, nearest neighbour); pixel values 1–4 = Unburned-very low / Low / Moderate / High.

## Run it yourself

```bash
make demo-line-fire     # Docker, no keys: writes output/results.json + the figure (~30 s)
```
or without Docker: `cd apps/worker && uv run --group research python research/line_fire_2024.py --out /tmp/line-fire`.

The script is [`apps/worker/research/line_fire_2024.py`](../../../apps/worker/research/line_fire_2024.py): it runs the worker's real pipeline (the `earth_search_s2` connector finds scenes, `kit/imagery.py` reads pixels) and adds the comparison and figure on top. Research code, not production code.

Contains modified Copernicus Sentinel data 2024.
