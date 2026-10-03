"""Snapshot building on recorded data, and an honest result when a source is down."""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from inland_worker.activity.snapshot import build_snapshot
from inland_worker.data import DataService
from inland_worker.kit.errors import ProviderError

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"


def validator():
    resources = []
    for name in ("evidence.schema.json", "analysis-job.schema.json", "job-event.schema.json"):
        contents = json.loads((CONTRACTS / name).read_text())
        res = Resource.from_contents(contents, default_specification=DRAFT202012)
        resources += [((CONTRACTS / name).as_uri(), res), (contents["$id"], res)]
    openapi = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text())
    resources.append(((CONTRACTS / "openapi.yaml").as_uri(), DRAFT202012.create_resource(openapi)))
    return Draft202012Validator(
        {"$ref": f"{(CONTRACTS / 'openapi.yaml').as_uri()}#/components/schemas/ActivitySnapshot"},
        registry=Registry().with_resources(resources),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


async def test_fixture_snapshot_has_ranked_clusters_and_matches_the_contract():
    snap = await build_snapshot(DataService(mode="fixture"))
    assert snap["data_mode"] == "fixture" and snap["clusters"]
    assert [c["rank"] for c in snap["clusters"]] == list(range(1, len(snap["clusters"]) + 1))
    assert any("not confirmed fires" in lim for lim in snap["limitations"])
    errors = list(validator().iter_errors(snap))
    assert not errors, errors[0].message


async def test_firms_outage_gives_an_empty_snapshot_that_says_why(monkeypatch):
    svc = DataService(mode="live")

    async def boom(*args, **kwargs):
        raise ProviderError("firms", "simulated outage")

    monkeypatch.setattr("inland_worker.data.service.fetch", boom)
    snap = await build_snapshot(svc)
    assert snap["clusters"] == []
    assert any("FIRMS was unavailable" in lim for lim in snap["limitations"])
    assert any("perimeters" in lim and "unavailable" in lim for lim in snap["limitations"])
    assert not list(validator().iter_errors(snap))
