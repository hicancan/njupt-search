from __future__ import annotations

import argparse
from .snapshot.build import publish_exam_artifacts
from .history.build import publish_exam_history_artifacts
from .source.discovery import discover_exam_source, materialize_exam_files
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover, materialize, and build ExamSnapshot artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover = subparsers.add_parser(
        "discover", help="Discover one exam source descriptor at an explicit external path."
    )
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--cache", type=Path, help="Reuse downloaded attachments during materialization.")
    discover.add_argument("--insecure", action="store_true")

    materialize = subparsers.add_parser("materialize", help="Materialize an explicit exam source.")
    materialize.add_argument("--source", type=Path, required=True)
    materialize.add_argument("--materialized", type=Path, required=True)
    materialize.add_argument("--cache", type=Path, required=True)

    build = subparsers.add_parser("build", help="Build one ExamSnapshot from materialized input.")
    build.add_argument("--materialized", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    history = subparsers.add_parser(
        "history", help="Build one ExamHistory from current and previous trusted artifacts."
    )
    history.add_argument("--current-snapshot", type=Path, required=True)
    history.add_argument("--output", type=Path, required=True)
    history.add_argument("--previous-history", type=Path)
    history.add_argument("--previous-snapshot", type=Path)
    args = parser.parse_args()

    if args.command == "discover":
        discover_exam_source(args.output, tls_verify=not args.insecure, cache_root=args.cache)
    elif args.command == "materialize":
        materialize_exam_files(
            source_path=args.source,
            exam_dir=args.materialized,
            cache_root=args.cache,
        )
    elif args.command == "build":
        publish_exam_artifacts(input_dir=args.materialized, output_dir=args.output)
    elif args.command == "history":
        publish_exam_history_artifacts(
            current_snapshot_dir=args.current_snapshot,
            output_dir=args.output,
            previous_history_dir=args.previous_history,
            previous_snapshot_dir=args.previous_snapshot,
        )
