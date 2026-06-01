from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sitegraph_search import PUBLIC_INDEX_DIR
from .sitegraph_cache_benchmark import run_cache_benchmark
from .sitegraph_lower_bound_report import build_lower_bound_report, write_report_files
from .sitegraph_query_smoke_test import validate_quality
from .sitegraph_task_query_eval import validate_task_queries


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic njupt-search representative query evaluation.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke_parser = subparsers.add_parser("run-smoke-queries", help="Run the representative query smoke suite.")
    smoke_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory. Reserved for the layout migration.")
    task_parser = subparsers.add_parser("run-task-queries", help="Run data-driven student task query expectations.")
    task_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory. Reserved for the layout migration.")
    task_parser.add_argument("--expectations", type=Path, default=None, help="Path to expected_results.json.")
    cache_parser = subparsers.add_parser("run-cache-benchmark", help="Run cold/warm content-hash artifact cache benchmarks.")
    cache_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory. Reserved for the layout migration.")
    cache_parser.add_argument("--query", action="append", default=None, help="Query to include. Can be passed more than once.")
    report_parser = subparsers.add_parser("run-lower-bound-report", help="Write a lower-bound evidence report with byte, query, cache, and parse/decode metrics.")
    report_parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory. Reserved for the layout migration.")
    report_parser.add_argument("--baseline-ref", default="HEAD", help="Git ref used as the before/baseline artifact set.")
    report_parser.add_argument("--query", action="append", default=None, help="Measured query to include. Can be passed more than once.")
    report_parser.add_argument("--cache-query", action="append", default=None, help="Cache benchmark query to include. Can be passed more than once.")
    report_parser.add_argument("--parse-runs", type=int, default=5, help="Number of JSON parse/decode benchmark runs.")
    report_parser.add_argument("--output", type=Path, default=None, help="Optional JSON report output path.")
    report_parser.add_argument("--markdown", type=Path, default=None, help="Optional Markdown report output path.")
    report_parser.add_argument("--skip-quality", action="store_true", help="Skip representative smoke query evals.")
    report_parser.add_argument("--skip-task", action="store_true", help="Skip data-backed task query evals.")
    report_parser.add_argument("--skip-cache", action="store_true", help="Skip cold/warm cache benchmark.")
    report_parser.add_argument("--skip-local-body-benchmark", action="store_true", help="Skip full local body JSON-vs-packed parse/decode benchmark.")
    args = parser.parse_args()

    if args.collection is not None and args.collection.resolve() != PUBLIC_INDEX_DIR.resolve():
        raise SystemExit(f"Only the generated njupt-public collection is supported: {PUBLIC_INDEX_DIR}")
    if args.command == "run-smoke-queries":
        print(json.dumps(validate_quality(), ensure_ascii=False, indent=2))
    elif args.command == "run-task-queries":
        print(json.dumps(validate_task_queries(args.expectations) if args.expectations else validate_task_queries(), ensure_ascii=False, indent=2))
    elif args.command == "run-cache-benchmark":
        result = run_cache_benchmark(args.query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["summary"]["passed"]:
            raise SystemExit(1)
    elif args.command == "run-lower-bound-report":
        report = build_lower_bound_report(
            collection=args.collection or PUBLIC_INDEX_DIR,
            baseline_ref=args.baseline_ref,
            queries=args.query,
            cache_queries=args.cache_query,
            include_quality=not args.skip_quality,
            include_task=not args.skip_task,
            include_cache=not args.skip_cache,
            include_local_body_benchmark=not args.skip_local_body_benchmark,
            parse_runs=args.parse_runs,
        )
        write_report_files(report, output=args.output, markdown=args.markdown)
        print(json.dumps(report, ensure_ascii=False, indent=2))
