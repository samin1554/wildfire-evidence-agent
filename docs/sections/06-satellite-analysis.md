# Section 6: Satellite analysis

**Stack:** Python 3.12 · NumPy · rasterio · a STAC client (pystac-client) · Shapely/pyproj · pytest
**Pair partner:** Section 2 (analysis UI): your numbers become charts and evidence cards people can understand.
**Read first:** [Start here](../guides/start-here.md) · [ADR-009](../adr/ADR-009-imagery-without-earth-engine.md) · [Sentinel-2 provider spec](../connectors/providers/earth-search-s2.md) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **`kit/imagery.py` + the `earth_search_s2` connector (merged):** find images for any area and dates, and read reflectance with clouds masked. See [What's built § imagery](../platform-status.md#6-kitimagerypy-satellite-pixels).
> - **The whole pipeline in one script:** `apps/worker/research/line_fire_2024.py`. Run it with `make demo-line-fire`.
> - `rasterio`, `numpy` and `pyproj` are already in the worker and its Docker image. No account or key is needed.
>
> **Your part of Milestone 1:** Not on the critical path. Start S6-1 (formula tests) now, then build on `read_bands()`.


## 1. Your job in plain English

You do **the science**. You use satellite images to measure how the land changed: how much vegetation was lost, and how badly an area burned.

The European **Sentinel-2** satellites photograph the Earth every few days in many "colours" (bands), including infrared that our eyes can't see. Healthy plants reflect lots of near-infrared light; burned ground doesn't. By comparing images from **before** and **after** a fire, you calculate:
- **NDVI** (vegetation index): how green and healthy the vegetation is.
- **NBR / dNBR** (burn ratio and its change): how severely an area burned.

The images are free public data on Amazon's servers. **Earth Search** is a free search service (no account, no key) that finds the right images. You then read **only the pixels inside the user's area** from those files and do the math with NumPy. We chose this over Google Earth Engine to avoid account setup ([ADR-009](../adr/ADR-009-imagery-without-earth-engine.md)).

**Analogy:** you're a doctor comparing an X-ray from before and after an injury. You pick clear images (no clouds, like no motion blur), measure the same spot the same way both times, and report your numbers with how much of the image was usable.

![Agent workflow](../diagrams/agent-workflow.svg)

**Start by reading** the [Line Fire proof of concept](../research/line-fire-2024/README.md): it's the whole pipeline in one script, and its four lessons will save you days.

**Done looks like:** given an area and two date windows, your functions return before/after values, the change, the dates and scenes used, the percentage of usable pixels and the units, plus a map overlay image. The same historical fire gives the same numbers every time. S8 then compares your burn severity with the official BAER/MTBS maps (built by S4).

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/satellite/**` | `kit/**` incl. `kit/imagery.py`, `data/**`, `agent/**` (lead) |
| `apps/worker/tests/satellite/**` | `contracts/**` (lead) |
| `docs/connectors/providers/earth-search-s2.md` (science sections) | connectors (S4/S5), evidence rules (S8) |

The lead's `kit/imagery.py` handles **finding scenes and reading pixels** (search, choosing the least-cloudy scene, windowed reads, cloud mask, tracing). You build **the science on top**: indices, change, statistics, severity classes and overlays. The agent calls your functions as **tools**; the AI model never does the math.

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Band** | One "colour" channel. We use `red` (B04), `nir` (B08), `swir22` (B12), `scl` (scene classification) and `visual` (true colour). |
| **Surface reflectance (L2A)** | Brightness already corrected for the atmosphere. Earth Search's `sentinel-2-l2a` is this product. |
| **STAC** | A standard way to search satellite catalogues: "images over this box, between these dates, sorted by cloud cover". |
| **COG** | Cloud-Optimized GeoTIFF: an image file built so you can read just one small window over the internet instead of downloading the whole file. |
| **NDVI** | (NIR − Red) / (NIR + Red). Ranges −1 to 1; higher = greener. |
| **NBR / dNBR** | NBR = (NIR − SWIR2)/(NIR + SWIR2); dNBR = NBR_before − NBR_after. Bigger dNBR = more severe burn. |
| **Cloud mask (SCL)** | The `scl` band labels each pixel (cloud, shadow, water, vegetation…). Remove cloud, shadow and no-data pixels **before** averaging. |
| **Resolution** | Pixel size: 10 m for red/nir, 20 m for swir22/scl. Resample to one grid and say which. |
| **Projected CRS** | Sentinel-2 files are in UTM (metres). Areas must be computed in metres, never in lat/long degrees. |
| **Deterministic** | Same inputs → same outputs: fixed scenes, fixed area, fixed method. |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| NumPy | Array math | [NumPy: absolute beginners](https://numpy.org/doc/stable/user/absolute_beginners.html) | NDVI on two 3×3 arrays, handling divide-by-zero and NaN. |
| STAC + pystac-client | Find scenes | [STAC intro](https://stacspec.org/en/tutorials/intro-to-stac/) · [pystac-client docs](https://pystac-client.readthedocs.io/) | Search `sentinel-2-l2a` on `https://earth-search.aws.element84.com/v1` for the Line Fire box in Oct 2024, sorted by cloud cover. |
| rasterio | Read a window from a COG | [rasterio docs](https://rasterio.readthedocs.io/en/stable/) (Windowed reading) | Read a 200×200 window of the `red` band from one scene and print its shape and CRS. |
| Sentinel-2 L2A | The data | [Earth Search](https://element84.com/earth-search/) | Find the SCL class numbers for cloud and shadow in the product documentation. |
| Burn severity background | The science | [USGS: Landsat Normalized Burn Ratio](https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio) | Explain dNBR thresholds in your own words. |
| pyproj / CRS | Correct areas | [pyproj docs](https://pyproj4.github.io/pyproj/stable/) | Convert a lon/lat polygon to UTM zone 11N and compute its area in acres. |
| pytest | Tests | [docs.pytest.org](https://docs.pytest.org/en/stable/getting-started.html) | Test your NDVI function with hand-computed values. |

**Learn it with AI:**
```text
Explain Cloud-Optimized GeoTIFFs and windowed reads with rasterio to a Python programmer: how can I read
only a small area from a 100 MB Sentinel-2 band over HTTP, what is a "window", and how do I convert my
lon/lat polygon to pixel coordinates when the file is in UTM? Use a tiny example.
```

## 5. Set up your machine

Nothing to sign up for: the data needs no account or key.
```bash
make worker-install                       # the worker's Python environment
cd apps/worker && uv run python -c "import numpy; print(numpy.__version__)"
```
`rasterio`, `numpy` and `pyproj` are already in the worker. Try the real pipeline: `make demo-line-fire` (Docker) or read `apps/worker/research/line_fire_2024.py`.

## 6. Build it step by step

### S6-1 Formula functions + unit tests (start now, no network)
- **Goal:** NDVI, NBR and dNBR are correct and tested.
- **Steps:** NumPy functions with masking (NaN for masked or no-data pixels); means ignore masked pixels; divide-by-zero gives NaN, never a crash.
- **AI prompt:**
  ```text
  Plan NumPy functions ndvi(nir, red), nbr(nir, swir2), dnbr(nbr_before, nbr_after) with masking
  support in apps/worker/src/inland_worker/satellite, plus pytest cases with hand-computed values,
  divide-by-zero, and fully masked arrays. Tests first.
  ```
- **Done when:** values are correct to 1e-6. These tests are the ground truth for everything after.

### S6-2 Severity classes and statistics
- **Goal:** turn a dNBR array into class areas.
- **Steps:** classify dNBR with documented thresholds (cite the source in code); count valid pixels per class; convert to acres using the pixel size in metres; report `valid_pixel_pct`.
- **Tests:** a synthetic array with known class counts; a fully masked array → `Missing` with a reason.

### S6-3 NDVI before/after on real imagery (after `kit/imagery.py` lands)
- **Goal:** two date windows + a polygon → mean NDVI before, after and % change, plus scene IDs, acquisition dates, valid-pixel %, resolution and units.
- **Steps:** ask `kit/imagery.py` for the least-cloudy scene per window and the masked AOI arrays → your NDVI functions → package as `deterministic_calculation` evidence with the method and inputs recorded.
- **AI prompt:**
  ```text
  Plan calculate_ndvi_change(before_window, after_window, area) using kit/imagery.py (scene search,
  windowed reads, SCL mask) and my NumPy functions from S6-1. Return values, scene ids, dates,
  valid_pixel_pct, resolution and units as Evidence. How do we make the result repeatable?
  ```
- **Check yourself:** run it twice on the Line Fire and get the same numbers. Compare with your NumPy tests on a tiny area.
- **Done when:** the Line Fire result is saved as a fixture (small `.npz` arrays + recorded search JSON).

### S6-4 dNBR burn severity
- **Goal:** dNBR statistics and burned-area estimates by severity class for the same windows.
- **Steps:** as S6-3 with NBR; resample `swir22` (20 m) and `nir` (10 m) to one grid and say which; areas in the UTM CRS.
- **Hand-off:** S8 compares your burned area and classes with the official BAER/MTBS assessments (S4) and the CAL FIRE perimeter.

### S6-5 Map overlays
Render NDVI-change and dNBR-class PNGs plus before/after true-colour thumbnails, with their bounds, for object storage. The API serves them ([ADR-009](../adr/ADR-009-imagery-without-earth-engine.md)). Keep a colour legend consistent with S1.

**Common mistakes:** averaging before masking clouds; mixing 10 m and 20 m bands without saying how; computing areas in degrees; reading whole scenes instead of the AOI window; reporting a number without scene dates or units.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| `kit/imagery.py` (search, windowed reads, SCL mask) | Lead | Your own practice script in a throwaway folder |
| Evidence schema | Lead (`contracts/evidence.schema.json`) | The examples in `contracts/examples/evidence/` |
| Fire perimeters for test areas | S4 / `California_Historic_Fire_Perimeters` | The Line Fire polygon from a browser query |

| Others need from you | Who |
|---|---|
| Numbers + units + dates for charts | S2 |
| Measured severity to compare with official maps | S8 |
| Tools the agent can call | Lead |

## 8. When you're stuck

rasterio and STAC docs → OpenCode Plan mode (ask it to explain windows and CRS, not to write everything) → S2 (your pair) for presentation → the lead for `kit/imagery.py` → team chat with the snippet, the error, and the area and dates you used.

## 9. Coming from the lead

- [x] A **baseline** `satellite/burn.py` (NBR, dNBR, 4-class thresholds, acres) so the agent's `burn_severity` tool works end to end. It's your module: extend it (NDVI, chaparral calibration, overlays) and keep its function names or update the tool with the lead.

- [x] `kit/imagery.py` + the `earth_search_s2` connector: scene search, `pick_scene()` (least-cloudy full-coverage date), `read_bands()` (windowed reads, per-scene offset rule, SCL mask, tile merging, tracing), `true_colour()`. Usage:
  ```python
  scenes = (await get_evidence("earth_search_s2", area=aoi, date_range={"start": "2024-10-01", "end": "2024-10-31"})).items
  grid = aoi_grid(aoi)
  stack = read_bands(pick_scene(scenes), grid, bands=("nir", "swir22"))   # your NBR/dNBR go on top
  ```
- [x] `rasterio`, `numpy`, `pyproj` in the worker and its Docker image
- [ ] The chosen historical test fire(s) and before/after date windows (proposed: Line Fire 2024, Aug vs Oct)
- [ ] Cloud-limit and minimum valid-pixel thresholds
- [ ] Overlay storage and the API route for serving overlays (with S3/S7)
