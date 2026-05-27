from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sitegraph_search import PUBLIC_INDEX_DIR
from .sitegraph_query_smoke_test import validate_quality


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic njupt-search representative query evaluation.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke_parser = subparsers.add_parser("run-smoke-queries", help="Run the representative query smoke suite.")
    smoke_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory. Reserved for the layout migration.")
    args = parser.parse_args()

    if args.collection is not None and args.collection.resolve() != PUBLIC_INDEX_DIR.resolve():
        raise SystemExit(f"Only the generated njupt-public collection is supported: {PUBLIC_INDEX_DIR}")
    print(json.dumps(validate_quality(), ensure_ascii=False, indent=2))
