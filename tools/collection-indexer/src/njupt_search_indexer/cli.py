from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .build_sitegraph_index import DEFAULT_SITEGRAPH_INDEX, build_sitegraph_index, configure_collection_output
from .validate_sitegraph_index import validate_generated_index, validate_sitegraph_package


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and validate njupt-search collection artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build collection runtime artifacts from an audited source package.")
    build_parser.add_argument("--collection-id", default="njupt-public")
    build_parser.add_argument("--source-kind", default="sitegraph", choices=("sitegraph",))
    build_parser.add_argument("--source-package", dest="source_package", type=Path, default=DEFAULT_SITEGRAPH_INDEX)
    build_parser.add_argument("--out", type=Path, default=None, help="Target output collection directory. Defaults to the configured public collection path.")
    build_parser.add_argument("--shard-size", type=int, default=1000)

    validate_parser = subparsers.add_parser("validate", help="Validate upstream and generated collection artifacts.")
    validate_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory to validate.")
    validate_parser.add_argument("--source-package", dest="source_package", type=Path, default=DEFAULT_SITEGRAPH_INDEX)
    validate_parser.add_argument("--skip-output", action="store_true", help="Only validate the upstream source package.")

    args = parser.parse_args()
    if args.command == "build":
        configure_collection_output(args.collection_id, args.out)
        summary = build_sitegraph_index(args.source_package.resolve(), shard_size=args.shard_size)
        summary["collection_id"] = args.collection_id
        summary["source_kind"] = args.source_kind
        _print_json(summary)
        return

    configure_collection_output(output_dir=args.collection)
    package = validate_sitegraph_package(args.source_package.resolve())
    summary: dict[str, Any] = {
        "collection_id": "njupt-public",
        "sitegraph_index": str(args.source_package.resolve()),
        "package_valid": True,
        "truth_counts": package["actual_counts"],
        "quality": package["manifest"].get("quality"),
    }
    if not args.skip_output:
        summary["generated_index"] = validate_generated_index(package)
    _print_json(summary)
