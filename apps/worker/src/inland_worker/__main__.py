"""Command line for the worker.

python -m inland_worker providers                       list configured data sources
python -m inland_worker fetch wfigs_current --bbox -124.5,32.5,-114.1,42.0
python -m inland_worker fetch firms --fixture           use recorded data (no keys, no network)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from inland_worker.connectors.registry import CONNECTORS
from inland_worker.data import DataService
from inland_worker.kit import load_providers


def _providers() -> int:
    reg = load_providers()
    for pid, cfg in reg.providers.items():
        status = "ready" if pid in CONNECTORS else "no connector yet"
        key = f"needs {cfg.auth.env}" if cfg.auth.env else "no key"
        print(f"{pid:<16} {cfg.ingestion.class_:<15} {key:<24} {status}  ({cfg.display_name})")
    return 0


def _fetch(args: argparse.Namespace) -> int:
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    date_range = None
    if args.date_range:
        start, end = args.date_range.split("/")
        date_range = {"start": start, "end": end}
    svc = DataService(mode="fixture" if args.fixture else None)
    try:
        result = asyncio.run(
            svc.get_evidence(args.provider, bbox=bbox, date_range=date_range, params=json.loads(args.params))
        )
    except (KeyError, ValueError) as exc:  # bad input: say what's wrong, no traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = {
        "provider_id": result.provider_id,
        "origin": result.origin,
        "freshness": result.freshness.model_dump(),
        "count": len(result.items),
        "first": result.items[0].model_dump(mode="json") if result.items else None,
    }
    if summary["first"] and summary["first"]["geometry"]:
        summary["first"]["geometry"] = {"type": summary["first"]["geometry"]["type"], "coordinates": "…"}
    print(json.dumps(summary, indent=2, default=str))
    return 0 if result.ok else 2


def _ask(args: argparse.Namespace) -> int:
    from inland_worker.agent import OpenRouterLLM, run_analysis

    w, s, e, n = (float(v) for v in args.bbox.split(","))
    area = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    start, end = args.date_range.split("/")
    use_llm = not args.no_llm and bool(os.environ.get("OPENROUTER_API_KEY"))
    llm = OpenRouterLLM() if use_llm else None
    data = DataService(mode="fixture" if args.fixture else None)
    result = asyncio.run(run_analysis(args.question, area, {"start": start, "end": end}, llm=llm, data=data))
    if result.declined:
        print(f"Declined ({result.decline_code}): {result.message}")
        return 3
    print(result.report.markdown())
    print(
        f"---\nplan: {[s['name'] for s in result.plan]} ({result.plan_source}) · explanation: "
        f"{result.explanation_source} · models: {result.models_used or 'none'} · evidence items: {len(result.evidence)}"
    )
    if not use_llm and not args.no_llm:
        print("(no OPENROUTER_API_KEY set: used the rule-based planner and wording)")
    if args.json:
        Path(args.json).write_text(result.model_dump_json(indent=2))
        print(f"full result written to {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="inland_worker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("providers", help="list configured data sources")
    f = sub.add_parser("fetch", help="get evidence from one provider and print a summary")
    f.add_argument("provider")
    f.add_argument("--bbox", help="west,south,east,north (default: the provider's default area)")
    f.add_argument("--date-range", help="YYYY-MM-DD/YYYY-MM-DD (needed by earth_search_s2)")
    f.add_argument("--params", default="{}", help="connector params as JSON")
    f.add_argument("--fixture", action="store_true", help="use recorded fixtures instead of the network")
    a = sub.add_parser("ask", help="run the agent on a question for an area and dates")
    a.add_argument("question")
    a.add_argument("--bbox", required=True, help="west,south,east,north")
    a.add_argument("--date-range", required=True, help="YYYY-MM-DD/YYYY-MM-DD")
    a.add_argument("--fixture", action="store_true", help="use recorded data (no network for data)")
    a.add_argument("--no-llm", action="store_true", help="rule-based planner and wording, no AI calls")
    a.add_argument("--json", help="also write the full result (report + evidence + trace) to this file")
    args = ap.parse_args(argv)
    return {"providers": lambda: _providers(), "fetch": lambda: _fetch(args), "ask": lambda: _ask(args)}[
        args.cmd
    ]()


if __name__ == "__main__":
    sys.exit(main())
