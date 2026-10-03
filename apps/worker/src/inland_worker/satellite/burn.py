"""Burn-ratio maths on reflectance arrays from kit/imagery.read_bands().

BASELINE by the lead so the agent's burn-severity tool works end to end. Section 6 owns this module and will
extend it (NDVI, calibrated chaparral thresholds, overlays): see docs/sections/06-satellite-analysis.md.
"""

from __future__ import annotations

import numpy as np

# USGS / Key & Benson (2006) dNBR thresholds collapsed to 4 classes (forest-calibrated; S6/S8 to calibrate)
DNBR_EDGES = (0.10, 0.27, 0.66)
CLASS_NAMES = ("Unburned/very low", "Low", "Moderate", "High")
M2_PER_ACRE = 4046.8564224


def nbr(nir: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    """Normalized Burn Ratio; NaN where masked or where the denominator is not positive."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(nir + swir2 > 0, (nir - swir2) / (nir + swir2), np.nan).astype(np.float32)


def dnbr(nbr_before: np.ndarray, nbr_after: np.ndarray) -> np.ndarray:
    return (nbr_before - nbr_after).astype(np.float32)


def classify(d: np.ndarray) -> np.ndarray:
    """0 = no data, 1..4 = CLASS_NAMES."""
    return np.where(np.isnan(d), 0, np.digitize(d, DNBR_EDGES) + 1).astype(np.uint8)


def class_acres(classes: np.ndarray, inside: np.ndarray, pixel_area_m2: float) -> dict[str, float]:
    return {
        name: round(float(((classes == i + 1) & inside).sum()) * pixel_area_m2 / M2_PER_ACRE, 1)
        for i, name in enumerate(CLASS_NAMES)
    }
