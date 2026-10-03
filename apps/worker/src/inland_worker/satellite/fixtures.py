"""Recorded imagery for fixture mode (scripts/record_imagery_fixture.py).

Each case holds Sentinel-2 scene evidence whose asset hrefs point at small local GeoTIFFs of raw DN values, so
fixture mode runs the same kit/imagery.read_bands → burn maths as live mode, on the user's own area. An area or
date window the recording doesn't cover gets no scene: the tool reports it as missing, never a substitute result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from inland_worker.contracts.models import Evidence

IMAGERY_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "imagery"


@dataclass(frozen=True)
class ImageryCase:
    name: str
    extent: BaseGeometry
    scenes: tuple[Evidence, ...]


@lru_cache
def load_cases(root: Path = IMAGERY_FIXTURES) -> tuple[ImageryCase, ...]:
    cases = []
    for path in sorted(root.glob("*/scenes.json")):
        raw = json.loads(path.read_text())
        scenes = []
        for rec in raw["scenes"]:
            for s in rec["properties"]["scenes"]:
                for asset in s["assets"].values():
                    asset["href"] = str((path.parent / asset["href"]).resolve())
            scenes.append(Evidence.model_validate(rec))
        cases.append(ImageryCase(path.parent.name, box(*raw["extent"]), tuple(scenes)))
    return tuple(cases)


def recorded_scenes(area: BaseGeometry, start: date, end: date) -> list[Evidence]:
    """Recorded scenes whose extent fully contains `area` and whose date falls in [start, end]."""
    return [
        s
        for case in load_cases()
        if case.extent.contains(area)
        for s in case.scenes
        if start <= date.fromisoformat(s.properties["date"]) <= end
    ]
