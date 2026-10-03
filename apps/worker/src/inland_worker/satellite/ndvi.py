"""NDVI maths on reflectance arrays from kit/imagery.read_bands() (Section 6 owns and extends this)."""

from __future__ import annotations

import numpy as np


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index; NaN where masked or where the denominator is not positive."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(nir + red > 0, (nir - red) / (nir + red), np.nan).astype(np.float32)


def ndvi_change(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """after - before: negative values mean vegetation loss."""
    return (after - before).astype(np.float32)


def summarize(change: np.ndarray, inside: np.ndarray) -> dict[str, float] | None:
    vals = change[inside & np.isfinite(change)]
    if vals.size == 0:
        return None
    return {
        "ndvi_change_median": round(float(np.median(vals)), 3),
        "ndvi_change_p25": round(float(np.percentile(vals, 25)), 3),
        "ndvi_change_p75": round(float(np.percentile(vals, 75)), 3),
        "loss_share": round(float((vals <= -0.1).sum()) / vals.size, 3),  # share of pixels losing ≥0.1 NDVI
    }
