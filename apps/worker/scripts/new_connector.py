"""Start a new connector by copying the reference connector for its pattern.

    make new-connector NAME=calfire_historical GROUP=fire PATTERN=arcgis

Creates the connector, its test file (with the shared suite), a fixtures folder and a provider spec,
and registers it. Then: fill in the spec, add the providers.yaml entry, record fixtures, adjust parse().
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1]
REPO = WORKER.parents[1]
PKG = WORKER / "src" / "inland_worker"

REFERENCES = {
    "keyed": ("fire/firms.py", "FirmsConnector", "FirmsParams", "firms"),
    "arcgis": ("fire/wfigs.py", "WfigsCurrentConnector", "WfigsParams", "wfigs_current"),
    "follow_link": ("weather/nws_forecast.py", "NwsForecastConnector", "NwsForecastParams", "nws_forecast"),
    "stac": (
        "imagery/earth_search_s2.py",
        "EarthSearchS2Connector",
        "EarthSearchS2Params",
        "earth_search_s2",
    ),
}


def camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="provider_id, snake_case, e.g. calfire_historical")
    ap.add_argument("--group", required=True, choices=["fire", "weather", "imagery"])
    ap.add_argument("--pattern", required=True, choices=sorted(REFERENCES))
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.name):
        ap.error("NAME must be snake_case")

    ref_file, ref_cls, ref_params, ref_id = REFERENCES[args.pattern]
    cls, params = f"{camel(args.name)}Connector", f"{camel(args.name)}Params"
    target = PKG / "connectors" / args.group / f"{args.name}.py"
    test = WORKER / "tests" / "connectors" / f"test_{args.name}.py"
    spec = REPO / "docs" / "connectors" / "providers" / f"{args.name.replace('_', '-')}.md"
    for path in (target, test):
        if path.exists():
            ap.error(f"{path} already exists")

    src = (PKG / "connectors" / ref_file).read_text()
    src = src.replace(ref_cls, cls).replace(ref_params, params).replace(f'"{ref_id}"', f'"{args.name}"')
    header = (
        f'"""{args.name}: TODO one-line description.\n\n'
        f"Copied from the reference connector {ref_file} ({args.pattern} pattern).\n"
        f"TODO: update build_requests/parse for this provider; spec: {spec.relative_to(REPO)}\n"
    )
    src = re.sub(r'^""".*?\n', header, src, count=1, flags=re.S)
    target.write_text(src)

    test.write_text(f"""from inland_worker.connectors.{args.group}.{args.name} import {cls}
from inland_worker.kit.testing import ConnectorContract


class Test{camel(args.name)}(ConnectorContract):
    connector_cls = {cls}
    query_kwargs = {{"bbox": (-117.8, 33.8, -114.1, 35.9)}}  # TODO: a query that matches your success fixture

    # TODO: add provider-specific tests (field mapping, dates, flags)
""")
    (WORKER / "tests" / "fixtures" / args.name).mkdir(parents=True, exist_ok=True)
    if not spec.exists():
        shutil.copy(REPO / "docs" / "connectors" / "provider-spec-template.md", spec)

    reg = PKG / "connectors" / "registry.py"
    text = reg.read_text()
    text = text.replace(
        "# <new-connector-imports>",
        f"from inland_worker.connectors.{args.group}.{args.name} import {cls}\n# <new-connector-imports>",
    )
    text = text.replace(
        "    # <new-connector-entries>", f"    {cls}.provider_id: {cls},\n    # <new-connector-entries>"
    )
    reg.write_text(text)

    print(f"""created
  {target.relative_to(REPO)}
  {test.relative_to(REPO)}
  {spec.relative_to(REPO)}
  apps/worker/tests/fixtures/{args.name}/
registered {cls} in connectors/registry.py

next steps
  1. fill in {spec.relative_to(REPO)}
  2. add a `{args.name}:` block to apps/worker/config/providers.yaml (copy the `{ref_id}:` block)
  3. make record-fixture PROVIDER={args.name} CASE=success ARGS="--bbox ..."   (and CASE=empty)
     make derive-fixtures PROVIDER={args.name}
  4. edit parse() until: make test-connector PROVIDER={args.name}
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
