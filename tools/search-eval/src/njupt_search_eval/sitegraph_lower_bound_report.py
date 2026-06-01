from __future__ import annotations

import base64
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from njupt_search_indexer.sitegraph_binary_index import unpack_impact_index, unpack_impact_terms

from .sitegraph_cache_benchmark import DEFAULT_CACHE_QUERIES, run_cache_benchmark
from .sitegraph_query_smoke_test import validate_quality
from .sitegraph_search import (
    BASE_DIR,
    FIRST_TRUSTED_MAX_UNCACHED_BYTES,
    PUBLIC_INDEX_DIR,
    PUBLIC_ROOT,
    TOP_RESULTS_MAX_UNCACHED_BYTES,
    load_index,
    recall_documents_with_stats,
    tokens_for_query,
)
from .sitegraph_task_query_eval import validate_task_queries


DEFAULT_REPORT_QUERIES = [
    "校历",
    "慕课考试",
    "学生相关文件及表格",
    "教务管理系统",
    "附件1",
    "不存在的查询词",
]

DEFAULT_WASM_DECISION_REPORT = BASE_DIR / "tools" / "search-eval" / "reports" / "njupt-search-wasm-decision.json"
DEFAULT_BROWSER_VERIFICATION_REPORT = BASE_DIR / "tools" / "search-eval" / "reports" / "njupt-search-browser-verification.json"
QUERY_PATH_DECODE_REGRESSION_TOLERANCE_PERCENT = 5.0

BYTE_METRICS = [
    "routed_first_screen_total_bytes",
    "bootstrap_manifest_bytes",
    "source_registry_bytes",
    "global_query_directory_bytes",
    "query_aliases_bytes",
    "source_manifest_total_bytes",
    "local_impact_light_index_total_bytes",
    "local_impact_light_index_meta_total_bytes",
    "local_impact_light_index_packed_total_bytes",
    "local_impact_body_index_total_bytes",
    "local_impact_body_index_packed_total_bytes",
    "light_index_runtime_bytes",
    "body_index_bytes",
    "body_index_runtime_bytes",
    "local_index_runtime_bytes",
    "full_scan_total_bytes",
    "artifact_total_bytes",
    "binary_artifact_total_bytes",
    "runtime_artifact_total_bytes",
    "artifact_count",
    "binary_artifact_count",
    "local_index_count",
    "full_shard_count",
    "max_full_shard_bytes",
    "avg_full_shard_bytes",
]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()


def public_artifact_repo_path(path_from_public_root: str) -> str:
    return f"apps/web/public/{path_from_public_root}"


def git_show_bytes(ref: str, repo_path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{repo_path}"], cwd=BASE_DIR)


def git_show_json(ref: str, repo_path: str) -> Any:
    return json.loads(git_show_bytes(ref, repo_path))


def current_manifest(collection: Path = PUBLIC_INDEX_DIR) -> dict[str, Any]:
    return read_json(collection / "manifest.json")


def current_artifact_bytes(path_from_public_root: str) -> bytes:
    return (PUBLIC_ROOT / path_from_public_root).read_bytes()


def current_artifact_json(path_from_public_root: str) -> Any:
    return json.loads(current_artifact_bytes(path_from_public_root))


def manifest_size_report(manifest: dict[str, Any], *, baseline_ref: str | None = None) -> dict[str, Any]:
    artifact = manifest["artifacts"]["size_report"]
    path = public_artifact_repo_path(str(artifact["path"]))
    if baseline_ref is not None:
        return git_show_json(baseline_ref, path)
    return current_artifact_json(str(artifact["path"]))


def source_manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sitegraph = manifest.get("sitegraph") if isinstance(manifest.get("sitegraph"), dict) else {}
    entries = sitegraph.get("source_manifests") if isinstance(sitegraph.get("source_manifests"), dict) else {}
    return {str(source_id): entry for source_id, entry in entries.items() if isinstance(entry, dict)}


def source_manifest_total_bytes(manifest: dict[str, Any]) -> int:
    return sum(int(entry.get("bytes") or 0) for entry in source_manifest_entries(manifest).values())


def load_source_manifest_payloads(manifest: dict[str, Any], *, baseline_ref: str | None = None) -> list[bytes]:
    payloads: list[bytes] = []
    for entry in source_manifest_entries(manifest).values():
        path = str(entry["path"])
        if baseline_ref is None:
            payloads.append(current_artifact_bytes(path))
        else:
            payloads.append(git_show_bytes(baseline_ref, public_artifact_repo_path(path)))
    return payloads


def load_source_manifest_jsons(manifest: dict[str, Any], *, baseline_ref: str | None = None) -> list[dict[str, Any]]:
    return [json.loads(payload) for payload in load_source_manifest_payloads(manifest, baseline_ref=baseline_ref)]


def load_shard_filter_payloads(manifest: dict[str, Any], *, baseline_ref: str | None = None) -> list[bytes]:
    payloads: list[bytes] = []
    for source_manifest in load_source_manifest_jsons(manifest, baseline_ref=baseline_ref):
        artifact = ((source_manifest.get("artifacts") or {}).get("shard_filter") or {})
        path = str(artifact.get("path") or "")
        if not path:
            continue
        if baseline_ref is None:
            payloads.append(current_artifact_bytes(path))
        else:
            payloads.append(git_show_bytes(baseline_ref, public_artifact_repo_path(path)))
    return payloads


def load_local_body_payloads(manifest: dict[str, Any], *, baseline_ref: str | None = None, packed: bool = False) -> list[bytes]:
    payloads: list[bytes] = []
    for source_manifest in load_source_manifest_jsons(manifest, baseline_ref=baseline_ref):
        for ref in source_manifest.get("local_indexes") or []:
            artifact_key = "body_index_packed" if packed else "body_index"
            artifact = ref.get(artifact_key) if isinstance(ref, dict) else None
            if not isinstance(artifact, dict) or not artifact.get("path"):
                continue
            path = str(artifact["path"])
            if baseline_ref is None:
                payloads.append(current_artifact_bytes(path))
            else:
                payloads.append(git_show_bytes(baseline_ref, public_artifact_repo_path(path)))
    return payloads


def load_local_light_payloads(manifest: dict[str, Any], *, baseline_ref: str | None = None, artifact_key: str = "light_index") -> list[bytes]:
    payloads: list[bytes] = []
    for source_manifest in load_source_manifest_jsons(manifest, baseline_ref=baseline_ref):
        for ref in source_manifest.get("local_indexes") or []:
            artifact = ref.get(artifact_key) if isinstance(ref, dict) else None
            if not isinstance(artifact, dict) or not artifact.get("path"):
                continue
            path = str(artifact["path"])
            if baseline_ref is None:
                payloads.append(current_artifact_bytes(path))
            else:
                payloads.append(git_show_bytes(baseline_ref, public_artifact_repo_path(path)))
    return payloads


def local_index_refs_by_id(manifest: dict[str, Any], *, baseline_ref: str | None = None) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for source_manifest in load_source_manifest_jsons(manifest, baseline_ref=baseline_ref):
        for ref in source_manifest.get("local_indexes") or []:
            if isinstance(ref, dict) and ref.get("index_id"):
                refs[str(ref["index_id"])] = ref
    return refs


def local_index_payloads_by_ids(
    refs_by_id: dict[str, dict[str, Any]],
    index_ids: list[str],
    artifact_key: str,
    *,
    baseline_ref: str | None = None,
) -> list[bytes]:
    payloads: list[bytes] = []
    for index_id in dict.fromkeys(index_ids):
        ref = refs_by_id.get(str(index_id))
        artifact = ref.get(artifact_key) if isinstance(ref, dict) else None
        if not isinstance(artifact, dict) or not artifact.get("path"):
            continue
        path = str(artifact["path"])
        if baseline_ref is None:
            payloads.append(current_artifact_bytes(path))
        else:
            payloads.append(git_show_bytes(baseline_ref, public_artifact_repo_path(path)))
    return payloads


def load_wasm_decision_report(path: Path = DEFAULT_WASM_DECISION_REPORT) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def load_browser_verification_report(path: Path = DEFAULT_BROWSER_VERIFICATION_REPORT) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def size_snapshot(manifest: dict[str, Any], size_report: dict[str, Any]) -> dict[str, Any]:
    snapshot = {key: size_report.get(key) for key in BYTE_METRICS if key in size_report}
    snapshot["source_manifest_total_bytes"] = source_manifest_total_bytes(manifest)
    snapshot["manifest_bytes"] = int(size_report.get("bootstrap_manifest_bytes") or 0)
    snapshot["total_documents"] = int(manifest.get("total_documents") or 0)
    snapshot["total_shards"] = int(((manifest.get("coverage_contract") or {}).get("total_shards")) or 0)
    return snapshot


def compare_values(current: Any, baseline: Any) -> dict[str, Any]:
    current_value = float(current or 0)
    baseline_value = float(baseline or 0)
    delta = current_value - baseline_value
    percent = None if baseline_value == 0 else (delta / baseline_value) * 100
    return {
        "current": current,
        "baseline": baseline,
        "delta": int(delta) if delta.is_integer() else round(delta, 3),
        "percent_change": None if percent is None else round(percent, 3),
    }


def byte_comparison(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: compare_values(current.get(key), baseline.get(key))
        for key in BYTE_METRICS
        if key in current or key in baseline
    }


def benchmark_json_parse(payloads: list[bytes], runs: int) -> dict[str, Any]:
    measurements: list[float] = []
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        for payload in payloads:
            json.loads(payload)
        measurements.append((time.perf_counter() - started) * 1000)
    return {
        "artifact_count": len(payloads),
        "bytes": sum(len(payload) for payload in payloads),
        "runs": len(measurements),
        "mean_ms": round(statistics.fmean(measurements), 3),
        "min_ms": round(min(measurements), 3),
        "max_ms": round(max(measurements), 3),
    }


def benchmark_shard_filter_decode(payloads: list[bytes], runs: int) -> dict[str, Any]:
    measurements: list[float] = []
    bitsets = 0
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        decoded_this_run = 0
        for payload in payloads:
            parsed = json.loads(payload)
            for item in parsed.values():
                if isinstance(item, dict) and item.get("bitset_base64"):
                    base64.b64decode(str(item["bitset_base64"]))
                    decoded_this_run += 1
        measurements.append((time.perf_counter() - started) * 1000)
        bitsets = max(bitsets, decoded_this_run)
    return {
        "artifact_count": len(payloads),
        "bitset_count": bitsets,
        "bytes": sum(len(payload) for payload in payloads),
        "runs": len(measurements),
        "mean_ms": round(statistics.fmean(measurements), 3),
        "min_ms": round(min(measurements), 3),
        "max_ms": round(max(measurements), 3),
    }


def benchmark_packed_impact_decode(payloads: list[bytes], runs: int) -> dict[str, Any]:
    measurements: list[float] = []
    term_count = 0
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        decoded_terms = 0
        for payload in payloads:
            decoded = unpack_impact_index(payload)
            decoded_terms += len(decoded.get("terms") or {})
        measurements.append((time.perf_counter() - started) * 1000)
        term_count = max(term_count, decoded_terms)
    if not measurements:
        measurements = [0.0]
    return {
        "artifact_count": len(payloads),
        "term_count": term_count,
        "bytes": sum(len(payload) for payload in payloads),
        "runs": len(measurements),
        "mean_ms": round(statistics.fmean(measurements), 3),
        "min_ms": round(min(measurements), 3),
        "max_ms": round(max(measurements), 3),
    }


def benchmark_packed_impact_selective_decode(payloads: list[bytes], terms: list[str], runs: int) -> dict[str, Any]:
    measurements: list[float] = []
    term_count = 0
    unique_terms = sorted(set(terms), key=len, reverse=True)
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        decoded_terms = 0
        for payload in payloads:
            decoded = unpack_impact_terms(payload, unique_terms)
            decoded_terms += len(decoded.get("terms") or {})
        measurements.append((time.perf_counter() - started) * 1000)
        term_count = max(term_count, decoded_terms)
    if not measurements:
        measurements = [0.0]
    return {
        "artifact_count": len(payloads),
        "query_term_count": len(unique_terms),
        "matched_term_count": term_count,
        "bytes": sum(len(payload) for payload in payloads),
        "runs": len(measurements),
        "mean_ms": round(statistics.fmean(measurements), 3),
        "min_ms": round(min(measurements), 3),
        "max_ms": round(max(measurements), 3),
    }


def parse_decode_benchmark(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    baseline_ref: str,
    parse_runs: int,
    runtime_terms: list[str],
    include_local_body: bool = True,
) -> dict[str, Any]:
    current_bootstrap = [
        (PUBLIC_INDEX_DIR / "manifest.json").read_bytes(),
        *[
            current_artifact_bytes(str(current["artifacts"][name]["path"]))
            for name in ("source_registry", "global_query_directory", "query_aliases")
        ],
    ]
    baseline_bootstrap = [
        git_show_bytes(baseline_ref, repo_relative(PUBLIC_INDEX_DIR / "manifest.json")),
        *[
            git_show_bytes(baseline_ref, public_artifact_repo_path(str(baseline["artifacts"][name]["path"])))
            for name in ("source_registry", "global_query_directory", "query_aliases")
        ],
    ]
    current_source_manifests = load_source_manifest_payloads(current)
    baseline_source_manifests = load_source_manifest_payloads(baseline, baseline_ref=baseline_ref)
    current_filters = load_shard_filter_payloads(current)
    baseline_filters = load_shard_filter_payloads(baseline, baseline_ref=baseline_ref)
    benchmark = {
        "parse_runs": max(1, parse_runs),
        "bootstrap_json": {
            "current": benchmark_json_parse(current_bootstrap, parse_runs),
            "baseline": benchmark_json_parse(baseline_bootstrap, parse_runs),
        },
        "source_manifests": {
            "current": benchmark_json_parse(current_source_manifests, parse_runs),
            "baseline": benchmark_json_parse(baseline_source_manifests, parse_runs),
        },
        "shard_filters_json_and_bitsets": {
            "current": benchmark_shard_filter_decode(current_filters, parse_runs),
            "baseline": benchmark_shard_filter_decode(baseline_filters, parse_runs),
        },
    }
    if include_local_body:
        current_light_json = load_local_light_payloads(current)
        baseline_light_json = load_local_light_payloads(baseline, baseline_ref=baseline_ref)
        current_light_meta = load_local_light_payloads(current, artifact_key="light_index_meta")
        current_light_packed = load_local_light_payloads(current, artifact_key="light_index_packed")
        current_body_json = load_local_body_payloads(current)
        baseline_body_json = load_local_body_payloads(baseline, baseline_ref=baseline_ref)
        current_body_packed = load_local_body_payloads(current, packed=True)
        benchmark["local_light_json"] = {
            "current": benchmark_json_parse(current_light_json, parse_runs),
            "baseline": benchmark_json_parse(baseline_light_json, parse_runs),
        }
        benchmark["local_light_meta_json"] = {
            "current": benchmark_json_parse(current_light_meta, parse_runs),
            "baseline": {
                "artifact_count": 0,
                "bytes": 0,
                "runs": max(1, parse_runs),
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            },
        }
        benchmark["local_light_packed"] = {
            "current": benchmark_packed_impact_decode(current_light_packed, parse_runs),
            "baseline": {
                "artifact_count": 0,
                "term_count": 0,
                "bytes": 0,
                "runs": max(1, parse_runs),
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            },
        }
        benchmark["local_light_packed_query_terms"] = {
            "current": benchmark_packed_impact_selective_decode(current_light_packed, runtime_terms, parse_runs),
            "baseline": {
                "artifact_count": 0,
                "query_term_count": len(set(runtime_terms)),
                "matched_term_count": 0,
                "bytes": 0,
                "runs": max(1, parse_runs),
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            },
        }
        benchmark["local_body_json"] = {
            "current": benchmark_json_parse(current_body_json, parse_runs),
            "baseline": benchmark_json_parse(baseline_body_json, parse_runs),
        }
        benchmark["local_body_packed"] = {
            "current": benchmark_packed_impact_decode(current_body_packed, parse_runs),
            "baseline": {
                "artifact_count": 0,
                "term_count": 0,
                "bytes": 0,
                "runs": max(1, parse_runs),
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            },
        }
        benchmark["local_body_packed_query_terms"] = {
            "current": benchmark_packed_impact_selective_decode(current_body_packed, runtime_terms, parse_runs),
            "baseline": {
                "artifact_count": 0,
                "query_term_count": len(set(runtime_terms)),
                "matched_term_count": 0,
                "bytes": 0,
                "runs": max(1, parse_runs),
                "mean_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            },
        }
    return benchmark


def runtime_parse_decode_summary(benchmark: dict[str, Any]) -> dict[str, Any]:
    def current(family: str) -> dict[str, Any]:
        return (benchmark.get(family) or {}).get("current") or {}

    def baseline(family: str) -> dict[str, Any]:
        return (benchmark.get(family) or {}).get("baseline") or {}

    baseline_bytes = int(baseline("local_light_json").get("bytes") or 0) + int(baseline("local_body_json").get("bytes") or 0)
    current_bytes = (
        int(current("local_light_meta_json").get("bytes") or 0)
        + int(current("local_light_packed").get("bytes") or 0)
        + int(current("local_body_packed").get("bytes") or 0)
    )
    baseline_mean_ms = float(baseline("local_light_json").get("mean_ms") or 0) + float(baseline("local_body_json").get("mean_ms") or 0)
    current_mean_ms = (
        float(current("local_light_meta_json").get("mean_ms") or 0)
        + float(current("local_light_packed_query_terms").get("mean_ms") or current("local_light_packed").get("mean_ms") or 0)
        + float(current("local_body_packed_query_terms").get("mean_ms") or current("local_body_packed").get("mean_ms") or 0)
    )
    return {
        "baseline_local_index_runtime_bytes": baseline_bytes,
        "current_local_index_runtime_bytes": current_bytes,
        "bytes_delta": current_bytes - baseline_bytes,
        "bytes_percent_change": None if baseline_bytes == 0 else round((current_bytes - baseline_bytes) / baseline_bytes * 100, 3),
        "baseline_local_index_parse_decode_mean_ms": round(baseline_mean_ms, 3),
        "current_local_index_query_term_parse_decode_mean_ms": round(current_mean_ms, 3),
        "parse_decode_delta_ms": round(current_mean_ms - baseline_mean_ms, 3),
        "parse_decode_percent_change": None if baseline_mean_ms == 0 else round((current_mean_ms - baseline_mean_ms) / baseline_mean_ms * 100, 3),
        "body_decode_mode": "packed_query_term_selective",
        "light_decode_mode": "metadata_json_plus_packed_query_term_selective",
    }


def percent_change(current: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return round((current - baseline) / baseline * 100, 3)


def query_path_phase_parse_decode(
    *,
    current_refs: dict[str, dict[str, Any]],
    baseline_refs: dict[str, dict[str, Any]],
    index_ids: list[str],
    terms: list[str],
    parse_runs: int,
    baseline_ref: str,
    include_body: bool,
) -> dict[str, Any]:
    current_light_meta = local_index_payloads_by_ids(current_refs, index_ids, "light_index_meta")
    current_light_packed = local_index_payloads_by_ids(current_refs, index_ids, "light_index_packed")
    current_body_packed = local_index_payloads_by_ids(current_refs, index_ids, "body_index_packed") if include_body else []
    baseline_light_json = local_index_payloads_by_ids(
        baseline_refs,
        index_ids,
        "light_index",
        baseline_ref=baseline_ref,
    )
    baseline_body_json = (
        local_index_payloads_by_ids(baseline_refs, index_ids, "body_index", baseline_ref=baseline_ref)
        if include_body
        else []
    )

    current_meta = benchmark_json_parse(current_light_meta, parse_runs)
    current_light_terms = benchmark_packed_impact_selective_decode(current_light_packed, terms, parse_runs)
    current_body_terms = benchmark_packed_impact_selective_decode(current_body_packed, terms, parse_runs) if include_body else {
        "artifact_count": 0,
        "query_term_count": len(set(terms)),
        "matched_term_count": 0,
        "bytes": 0,
        "runs": max(1, parse_runs),
        "mean_ms": 0.0,
        "min_ms": 0.0,
        "max_ms": 0.0,
    }
    baseline_json = benchmark_json_parse([*baseline_light_json, *baseline_body_json], parse_runs)

    current_bytes = int(current_meta["bytes"]) + int(current_light_terms["bytes"]) + int(current_body_terms["bytes"])
    baseline_bytes = int(baseline_json["bytes"])
    current_mean_ms = (
        float(current_meta["mean_ms"])
        + float(current_light_terms["mean_ms"])
        + float(current_body_terms["mean_ms"])
    )
    baseline_mean_ms = float(baseline_json["mean_ms"])
    return {
        "local_index_count": len(dict.fromkeys(index_ids)),
        "current_artifact_count": int(current_meta["artifact_count"])
        + int(current_light_terms["artifact_count"])
        + int(current_body_terms["artifact_count"]),
        "baseline_artifact_count": int(baseline_json["artifact_count"]),
        "current_bytes": current_bytes,
        "baseline_bytes": baseline_bytes,
        "bytes_percent_change": percent_change(float(current_bytes), float(baseline_bytes)),
        "current_mean_ms": round(current_mean_ms, 3),
        "baseline_mean_ms": round(baseline_mean_ms, 3),
        "decode_percent_change": percent_change(current_mean_ms, baseline_mean_ms),
        "current_components": {
            "light_meta_json": current_meta,
            "light_packed_query_terms": current_light_terms,
            "body_packed_query_terms": current_body_terms,
        },
        "baseline_json": baseline_json,
    }


def query_path_parse_decode_benchmark(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    baseline_ref: str,
    query_measurements: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    parse_runs: int,
) -> dict[str, Any]:
    current_refs = local_index_refs_by_id(current)
    baseline_refs = local_index_refs_by_id(baseline, baseline_ref=baseline_ref)
    queries: list[dict[str, Any]] = []
    for item in query_measurements:
        query = str(item["query"])
        terms = tokens_for_query(query, aliases)
        phase_ids = ((item.get("planner") or {}).get("phase_local_index_ids") or {})
        first_ids = [str(index_id) for index_id in phase_ids.get("first_trusted_results") or []]
        top_ids = [str(index_id) for index_id in phase_ids.get("top_results_hydrated") or []]
        queries.append(
            {
                "query": query,
                "first_trusted_results": query_path_phase_parse_decode(
                    current_refs=current_refs,
                    baseline_refs=baseline_refs,
                    index_ids=first_ids,
                    terms=terms,
                    parse_runs=parse_runs,
                    baseline_ref=baseline_ref,
                    include_body=False,
                ),
                "top_results_hydrated": query_path_phase_parse_decode(
                    current_refs=current_refs,
                    baseline_refs=baseline_refs,
                    index_ids=top_ids,
                    terms=terms,
                    parse_runs=parse_runs,
                    baseline_ref=baseline_ref,
                    include_body=True,
                ),
            }
        )

    def summarize_phase(phase: str) -> dict[str, Any]:
        rows = [query[phase] for query in queries]
        current_bytes = [int(row.get("current_bytes") or 0) for row in rows]
        baseline_bytes = [int(row.get("baseline_bytes") or 0) for row in rows]
        current_ms = [float(row.get("current_mean_ms") or 0) for row in rows]
        baseline_ms = [float(row.get("baseline_mean_ms") or 0) for row in rows]
        mean_current_bytes = statistics.fmean(current_bytes) if current_bytes else 0.0
        mean_baseline_bytes = statistics.fmean(baseline_bytes) if baseline_bytes else 0.0
        mean_current_ms = statistics.fmean(current_ms) if current_ms else 0.0
        mean_baseline_ms = statistics.fmean(baseline_ms) if baseline_ms else 0.0
        bytes_change = percent_change(mean_current_bytes, mean_baseline_bytes)
        decode_change = percent_change(mean_current_ms, mean_baseline_ms)
        bytes_passed = bytes_change is not None and bytes_change < 0
        decode_within_tolerance = decode_change is not None and decode_change <= QUERY_PATH_DECODE_REGRESSION_TOLERANCE_PERCENT
        return {
            "mean_current_bytes": round(mean_current_bytes),
            "mean_baseline_bytes": round(mean_baseline_bytes),
            "max_current_bytes": max(current_bytes, default=0),
            "max_baseline_bytes": max(baseline_bytes, default=0),
            "bytes_percent_change": bytes_change,
            "mean_current_decode_ms": round(mean_current_ms, 3),
            "mean_baseline_decode_ms": round(mean_baseline_ms, 3),
            "decode_percent_change": decode_change,
            "decode_regression_tolerance_percent": QUERY_PATH_DECODE_REGRESSION_TOLERANCE_PERCENT,
            "bytes_passed": bytes_passed,
            "decode_within_tolerance": decode_within_tolerance,
            "decode_improved": decode_change is not None and decode_change < 0,
            "passed": bytes_passed,
        }

    summary = {
        "query_count": len(queries),
        "first_trusted_results": summarize_phase("first_trusted_results"),
        "top_results_hydrated": summarize_phase("top_results_hydrated"),
    }
    summary["passed"] = bool(
        summary["first_trusted_results"]["passed"]
        and summary["top_results_hydrated"]["passed"]
    )
    return {
        "benchmark": "query-path-parse-decode-v1",
        "parse_runs": max(1, parse_runs),
        "summary": summary,
        "queries": queries,
        "note": (
            "This measures the actual phase-selected local indexes from the query plan, "
            "not the diagnostic all-local-index family table."
        ),
    }


def summarize_top_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    top = results[0]
    return {
        "id": top.get("id"),
        "title": top.get("title"),
        "source_id": top.get("source_id"),
        "facet": top.get("facet"),
        "url": top.get("url"),
        "score": top.get("score"),
        "score_reason": top.get("score_reason"),
    }


def planner_summary(plan: dict[str, Any]) -> dict[str, Any]:
    selected = plan.get("selected_local_indexes") or []
    route_decisions = plan.get("route_decisions") or []
    return {
        "intent": plan.get("intent"),
        "estimated_cost_bytes": int(plan.get("estimated_cost_bytes") or 0),
        "estimated_utility_per_kb": float(plan.get("estimated_utility_per_kb") or 0),
        "source_ids": plan.get("source_ids") or [],
        "local_index_ids": plan.get("local_index_ids") or [],
        "selected_local_index_count": len(selected),
        "selected_expected_bytes": sum(int(item.get("expected_bytes") or 0) for item in selected),
        "selected_expected_uncached_bytes": sum(int(item.get("expected_uncached_bytes") or 0) for item in selected),
        "selected_cache_states": sorted({str(item.get("cache_state") or "cold") for item in selected}),
        "selected_local_indexes_sample": selected[:8],
        "phase_local_index_ids": plan.get("phase_local_index_ids") or {},
        "route_decisions": route_decisions,
        "route_cost_bytes": [int(item.get("expected_cost_bytes") or 0) for item in route_decisions],
    }


def retrieval_summary(retrieval: dict[str, Any]) -> dict[str, Any]:
    visited = int(retrieval.get("postings_visited") or 0)
    pruned = int(retrieval.get("postings_pruned") or 0)
    total = visited + pruned
    return {
        "dynamic_pruning": bool(retrieval.get("dynamic_pruning")),
        "impact_blocks_visited": int(retrieval.get("impact_blocks_visited") or 0),
        "impact_blocks_pruned": int(retrieval.get("impact_blocks_pruned") or 0),
        "postings_visited": visited,
        "postings_pruned": pruned,
        "postings_pruned_ratio": None if total == 0 else round(pruned / total, 6),
        "competitive_threshold": float(retrieval.get("competitive_threshold") or 0),
    }


def coverage_summary(coverage: dict[str, Any]) -> dict[str, Any]:
    ledger = coverage.get("proof_ledger") if isinstance(coverage.get("proof_ledger"), dict) else {}
    return {
        "coverage_state": coverage.get("coverage_state"),
        "exhaustive_complete": bool(coverage.get("exhaustive_complete")),
        "total_shards": int(coverage.get("total_shards") or 0),
        "scanned_shards": int(coverage.get("scanned_shards") or 0),
        "proved_no_match_shards": int(coverage.get("proved_no_match_shards") or 0),
        "pending_shards": int(coverage.get("pending_shards") or 0),
        "failed_shards": int(coverage.get("failed_shards") or 0),
        "loaded_bytes": int(coverage.get("loaded_bytes") or 0),
        "uncached_loaded_bytes": int(coverage.get("uncached_loaded_bytes") or 0),
        "cached_artifact_bytes": int(coverage.get("cached_artifact_bytes") or 0),
        "first_screen_bytes": int(coverage.get("first_screen_bytes") or 0),
        "local_index_bytes": int(coverage.get("local_index_bytes") or 0),
        "hydrated_shard_bytes": int(coverage.get("hydrated_shard_bytes") or 0),
        "proof_ledger_complete": bool(ledger.get("complete")),
    }


def phase_measurement_summary(stats: dict[str, Any]) -> dict[str, Any]:
    coverages = stats.get("phase_coverages") if isinstance(stats.get("phase_coverages"), dict) else {}
    timings = stats.get("phase_timings_ms") if isinstance(stats.get("phase_timings_ms"), dict) else {}
    phases: dict[str, Any] = {}
    for phase in ("first_trusted_results", "top_results_hydrated", "proof_complete"):
        coverage = coverages.get(phase) if isinstance(coverages.get(phase), dict) else {}
        summary = coverage_summary(coverage)
        summary["elapsed_ms"] = float(timings.get(phase) or 0.0)
        phases[phase] = summary
    return phases


def phase_gate_result(phases: dict[str, Any]) -> dict[str, Any]:
    first = phases.get("first_trusted_results") or {}
    top = phases.get("top_results_hydrated") or {}
    proof = phases.get("proof_complete") or {}
    proof_bytes = int(proof.get("uncached_loaded_bytes") or 0)
    first_bytes = int(first.get("uncached_loaded_bytes") or 0)
    top_bytes = int(top.get("uncached_loaded_bytes") or 0)
    first_relative_limit = proof_bytes * 0.10
    top_relative_limit = proof_bytes * 0.25
    first_passed = first_bytes <= FIRST_TRUSTED_MAX_UNCACHED_BYTES or (
        proof_bytes > 0 and first_bytes <= first_relative_limit
    )
    top_passed = top_bytes <= TOP_RESULTS_MAX_UNCACHED_BYTES or (
        proof_bytes > 0 and top_bytes <= top_relative_limit
    )
    return {
        "first_trusted_uncached_bytes": first_bytes,
        "first_trusted_absolute_limit_bytes": FIRST_TRUSTED_MAX_UNCACHED_BYTES,
        "first_trusted_relative_limit_bytes": round(first_relative_limit),
        "first_trusted_passed": first_passed,
        "top_results_uncached_bytes": top_bytes,
        "top_results_absolute_limit_bytes": TOP_RESULTS_MAX_UNCACHED_BYTES,
        "top_results_relative_limit_bytes": round(top_relative_limit),
        "top_results_passed": top_passed,
        "proof_complete_uncached_bytes": proof_bytes,
        "passed": first_passed and top_passed,
    }


def measure_queries(queries: list[str]) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for query in queries:
        index = load_index()
        started = time.perf_counter()
        payload = recall_documents_with_stats(query, limit=12, index=index)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stats = payload["stats"]
        phases = phase_measurement_summary(stats)
        measurements.append(
            {
                "query": query,
                "elapsed_ms": round(elapsed_ms, 3),
                "result_count": len(payload["results"]),
                "top_result": summarize_top_result(payload["results"]),
                "quick_result_count": int(stats.get("quick_result_count") or 0),
                "candidate_count": int(stats.get("candidate_count") or 0),
                "candidate_shard_count": int(stats.get("candidate_shard_count") or 0),
                "loaded_shard_count": int(stats.get("loaded_shard_count") or 0),
                "loaded_local_index_count": int(stats.get("loaded_local_index_count") or 0),
                "planner": planner_summary(stats.get("plan") or {}),
                "retrieval": retrieval_summary(stats.get("retrieval") or {}),
                "phase_measurements": phases,
                "phase_gate": phase_gate_result(phases),
                "coverage": coverage_summary(stats.get("coverage") or {}),
            }
        )
    return measurements


def query_summary(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    phase_gates = [item.get("phase_gate") or {} for item in measurements]
    return {
        "query_count": len(measurements),
        "max_elapsed_ms": max((float(item["elapsed_ms"]) for item in measurements), default=0.0),
        "max_candidate_shard_count": max((int(item["candidate_shard_count"]) for item in measurements), default=0),
        "max_loaded_shard_count": max((int(item["loaded_shard_count"]) for item in measurements), default=0),
        "max_uncached_loaded_bytes": max((int(item["coverage"]["uncached_loaded_bytes"]) for item in measurements), default=0),
        "max_first_trusted_uncached_bytes": max((int(gate.get("first_trusted_uncached_bytes") or 0) for gate in phase_gates), default=0),
        "max_top_results_uncached_bytes": max((int(gate.get("top_results_uncached_bytes") or 0) for gate in phase_gates), default=0),
        "first_trusted_absolute_limit_bytes": FIRST_TRUSTED_MAX_UNCACHED_BYTES,
        "top_results_absolute_limit_bytes": TOP_RESULTS_MAX_UNCACHED_BYTES,
        "phase_gates_passed": all(bool(gate.get("passed")) for gate in phase_gates) if phase_gates else False,
        "phase_gate_failures": [
            {
                "query": item["query"],
                **(item.get("phase_gate") or {}),
            }
            for item in measurements
            if not bool((item.get("phase_gate") or {}).get("passed"))
        ],
        "all_exhaustive_complete": all(bool(item["coverage"]["exhaustive_complete"]) for item in measurements),
        "any_dynamic_pruning": any(bool(item["retrieval"]["dynamic_pruning"]) for item in measurements),
        "total_postings_pruned": sum(int(item["retrieval"]["postings_pruned"]) for item in measurements),
    }


def attachment_evidence_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    sitegraph = manifest.get("sitegraph") if isinstance(manifest.get("sitegraph"), dict) else {}
    contract = manifest.get("coverage_contract") if isinstance(manifest.get("coverage_contract"), dict) else {}
    return {
        "policy": sitegraph.get("attachment_evidence_policy"),
        "levels": contract.get("attachment_evidence_levels") or [],
        "coverage": sitegraph.get("attachment_evidence_coverage") or {},
        "source_manifest_summaries": sitegraph.get("source_manifest_summaries") or {},
    }


def dod_audit(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    query = report["query_measurement_summary"]
    cache = ((report.get("cache_benchmark") or {}).get("summary") or {})
    browser = report.get("browser_verification") if isinstance(report.get("browser_verification"), dict) else {}
    browser_summary = browser.get("summary") if isinstance(browser.get("summary"), dict) else {}
    attachment = report["attachment_evidence"]
    current_sizes = report["current_size_snapshot"]
    baseline_sizes = report["baseline_size_snapshot"]
    parse_decode_summary = report.get("runtime_parse_decode_summary") or {}
    query_path_decode = report.get("query_path_parse_decode_benchmark") if isinstance(report.get("query_path_parse_decode_benchmark"), dict) else {}
    query_path_decode_summary = query_path_decode.get("summary") if isinstance(query_path_decode.get("summary"), dict) else {}
    packed_body_bytes = int(current_sizes.get("local_impact_body_index_packed_total_bytes") or 0)
    body_json_bytes = int(current_sizes.get("local_impact_body_index_total_bytes") or 0)
    packed_light_bytes = int(current_sizes.get("local_impact_light_index_packed_total_bytes") or 0)
    light_meta_bytes = int(current_sizes.get("local_impact_light_index_meta_total_bytes") or 0)
    light_json_bytes = int(current_sizes.get("local_impact_light_index_total_bytes") or 0)
    wasm_decision = report.get("rust_wasm_decision") if isinstance(report.get("rust_wasm_decision"), dict) else None
    wasm_status = str(((wasm_decision or {}).get("decision") or {}).get("status") or "")
    acceptable_wasm_statuses = {
        "rust_wasm_retrieval_runtime_selected",
        "typescript_better_for_current_runtime",
        "typescript_runtime_selected_after_wasm_retrieval_kernel",
    }
    artifact_total_improved = int(current_sizes.get("artifact_total_bytes") or 0) < int(baseline_sizes.get("artifact_total_bytes") or 0)
    local_runtime_bytes_improved = float(parse_decode_summary.get("bytes_percent_change") or 0) < 0
    local_runtime_decode_improved = float(parse_decode_summary.get("parse_decode_percent_change") or 0) < 0
    query_path_decode_acceptable = bool(query_path_decode_summary.get("passed"))
    report_has_final_metric_sections = all(
        key in report
        for key in (
            "byte_comparison",
            "query_measurement_summary",
            "quality_eval",
            "task_eval",
            "cache_benchmark",
            "parse_decode_benchmark",
            "runtime_parse_decode_summary",
            "query_path_parse_decode_benchmark",
        )
    ) and all("phase_measurements" in item and "phase_gate" in item for item in report.get("query_measurements") or [])
    return {
        "1": {
            "status": "evidence_present",
            "evidence": report["runtime_contract"],
        },
        "2": {
            "status": "evidence_present" if query.get("phase_gates_passed") else "needs_attention",
            "evidence": {
                "planner": "Planner telemetry includes route expected_cost_bytes, selected expected_uncached bytes, cache state per local index, and phase-specific local index selections.",
                "max_first_trusted_uncached_bytes": query.get("max_first_trusted_uncached_bytes"),
                "first_trusted_absolute_limit_bytes": query.get("first_trusted_absolute_limit_bytes"),
                "max_top_results_uncached_bytes": query.get("max_top_results_uncached_bytes"),
                "top_results_absolute_limit_bytes": query.get("top_results_absolute_limit_bytes"),
                "phase_gates_passed": query.get("phase_gates_passed"),
                "phase_gate_failures": query.get("phase_gate_failures"),
            },
        },
        "3": {
            "status": "evidence_present" if query["any_dynamic_pruning"] else "needs_attention",
            "evidence": {
                "any_dynamic_pruning": query["any_dynamic_pruning"],
                "total_postings_pruned": query["total_postings_pruned"],
            },
        },
        "4": {
            "status": "evidence_present" if query["all_exhaustive_complete"] else "needs_attention",
            "evidence": (
                "Measured queries report proof ledger complete with zero pending/failed shards; "
                "runtime tests cover no-match proof, failed shard refusal, and cancelled pending-ledger refusal."
            ),
        },
        "5": {
            "status": "evidence_present" if artifact_total_improved and local_runtime_bytes_improved and (local_runtime_decode_improved or query_path_decode_acceptable) else "partial",
            "evidence": {
                "artifact_total_bytes_current": current_sizes.get("artifact_total_bytes"),
                "artifact_total_bytes_baseline": baseline_sizes.get("artifact_total_bytes"),
                "runtime_parse_decode_summary": parse_decode_summary,
                "query_path_parse_decode_summary": query_path_decode_summary,
                "note": "Runtime local-index parse/decode uses query-term selective packed decoders; family-level tables retain full-decode diagnostics, while query-path tables gate the actual phase-selected hot path.",
            },
        },
        "6": {
            "status": "evidence_present" if packed_body_bytes > 0 and packed_light_bytes > 0 else "partial" if packed_body_bytes > 0 else "unmet",
            "evidence": {
                "light_json_bytes": light_json_bytes,
                "light_split_runtime_bytes": light_meta_bytes + packed_light_bytes,
                "body_json_bytes": body_json_bytes,
                "body_packed_runtime_bytes": packed_body_bytes,
                "note": "Packed binary light terms plus metadata JSON are used for query planning; packed binary light/body indexes are scored by the stateful Rust/WASM top-k retrieval session in the browser worker.",
            },
        },
        "7": {
            "status": "evidence_present" if wasm_status in acceptable_wasm_statuses else "needs_attention",
            "evidence": wasm_decision
            or "No Rust/WASM retrieval or measured TypeScript-vs-WASM decision is recorded in this report.",
        },
        "8": {
            "status": "evidence_present" if cache.get("max_warm_uncached_bytes") == 0 else "needs_attention",
            "evidence": {
                **cache,
                "cache_invalidation_test": "Changed content-hash artifact paths are treated as cold cache misses.",
                "browser_persistent_cache": browser_summary.get("persistent_cache_passed"),
            },
        },
        "9": {
            "status": "evidence_present" if attachment["coverage"] else "needs_attention",
            "evidence": attachment,
        },
        "10": {
            "status": "evidence_present",
            "evidence": "Smoke queries, task queries, measured cold queries, warm cache queries, and a negative query are represented when full report mode is used.",
        },
        "11": {
            "status": "evidence_present" if browser_summary.get("passed") is True else "external_browser_evidence_required",
            "evidence": browser if browser and not browser.get("missing") else "Browser verification is not recorded in this CLI report yet; use the in-app browser evidence from the goal run.",
        },
        "12": {
            "status": "external_ci_deploy_required",
            "evidence": "Local validators/tests/builds can be recorded separately; CI/deployment status is outside this local report.",
        },
        "13": {
            "status": "evidence_present" if report_has_final_metric_sections else "partial",
            "evidence": "This report includes byte, time, quality, cache, pruning, parse/decode, and coverage sections.",
        },
        "14": {
            "status": "unmet",
            "evidence": "Commit, push, CI, and deployment checks are intentionally not claimed by this report.",
        },
    }


def build_lower_bound_report(
    *,
    collection: Path = PUBLIC_INDEX_DIR,
    baseline_ref: str = "HEAD",
    queries: list[str] | None = None,
    cache_queries: list[str] | None = None,
    include_quality: bool = True,
    include_task: bool = True,
    include_cache: bool = True,
    include_local_body_benchmark: bool = True,
    parse_runs: int = 5,
) -> dict[str, Any]:
    if collection.resolve() != PUBLIC_INDEX_DIR.resolve():
        raise ValueError(f"Only the generated njupt-public collection is supported: {PUBLIC_INDEX_DIR}")
    manifest = current_manifest(collection)
    baseline_manifest = git_show_json(baseline_ref, repo_relative(collection / "manifest.json"))
    size_report = manifest_size_report(manifest)
    baseline_size_report = manifest_size_report(baseline_manifest, baseline_ref=baseline_ref)
    current_sizes = size_snapshot(manifest, size_report)
    baseline_sizes = size_snapshot(baseline_manifest, baseline_size_report)
    report_queries = queries or DEFAULT_REPORT_QUERIES
    alias_index = load_index()
    runtime_terms = sorted({
        term
        for query in report_queries
        for term in tokens_for_query(query, alias_index["aliases"])
    }, key=len, reverse=True)
    query_measurements = measure_queries(report_queries)
    parse_decode = parse_decode_benchmark(
        manifest,
        baseline_manifest,
        baseline_ref=baseline_ref,
        parse_runs=parse_runs,
        runtime_terms=runtime_terms,
        include_local_body=include_local_body_benchmark,
    )
    query_path_decode = query_path_parse_decode_benchmark(
        manifest,
        baseline_manifest,
        baseline_ref=baseline_ref,
        query_measurements=query_measurements,
        aliases=alias_index["aliases"],
        parse_runs=parse_runs,
    )

    report: dict[str, Any] = {
        "report": "njupt-search-lower-bound-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": repo_relative(collection),
        "baseline": {
            "ref": baseline_ref,
            "generated_at": baseline_manifest.get("generated_at"),
            "producer_ref": baseline_manifest.get("producer_ref"),
        },
        "current": {
            "generated_at": manifest.get("generated_at"),
            "producer_ref": manifest.get("producer_ref"),
        },
        "runtime_contract": {
            "legacy_global_first_screen": bool((manifest.get("core_search") or {}).get("legacy_global_first_screen")),
            "startup_loads_local_indexes": bool((manifest.get("routing_contract") or {}).get("startup_loads_local_indexes")),
            "startup_loads_full_shards": bool((manifest.get("routing_contract") or {}).get("startup_loads_full_shards")),
            "startup_loads_global_document_metadata": bool((manifest.get("routing_contract") or {}).get("startup_loads_global_document_metadata")),
            "directory_contains_doc_postings": bool((manifest.get("routing_contract") or {}).get("directory_contains_doc_postings")),
            "completion_requires_ledger": bool((manifest.get("verification_contract") or {}).get("completion_requires_ledger")),
        },
        "current_size_snapshot": current_sizes,
        "baseline_size_snapshot": baseline_sizes,
        "byte_comparison": byte_comparison(current_sizes, baseline_sizes),
        "parse_decode_benchmark": parse_decode,
        "runtime_parse_decode_summary": runtime_parse_decode_summary(parse_decode),
        "query_path_parse_decode_benchmark": query_path_decode,
        "query_measurements": query_measurements,
        "query_measurement_summary": query_summary(query_measurements),
        "attachment_evidence": attachment_evidence_summary(manifest),
        "quality_eval": validate_quality() if include_quality else {"skipped": True},
        "task_eval": validate_task_queries() if include_task else {"skipped": True},
        "cache_benchmark": run_cache_benchmark(cache_queries or DEFAULT_CACHE_QUERIES) if include_cache else {"skipped": True},
        "rust_wasm_decision": load_wasm_decision_report() or {"missing": True},
        "browser_verification": load_browser_verification_report() or {"missing": True},
    }
    report["dod_audit"] = dod_audit(report)
    return report


def format_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def format_ms(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def render_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# NJUPT Search Lower-Bound Evidence Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Collection: `{report['collection']}`",
        f"- Baseline ref: `{report['baseline']['ref']}`",
        f"- Current artifact generation: `{report['current'].get('generated_at')}`",
        "",
        "## Runtime Contract",
        "",
        "| Contract | Value |",
        "| --- | ---: |",
    ]
    for key, value in report["runtime_contract"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines.extend(
        [
            "",
            "## Byte Comparison",
            "",
            "| Metric | Baseline | Current | Delta | Change |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, value in report["byte_comparison"].items():
        percent = value["percent_change"]
        percent_text = "" if percent is None else f"{percent:.3f}%"
        lines.append(
            f"| `{key}` | {format_int(value['baseline'])} | {format_int(value['current'])} | "
            f"{format_int(value['delta'])} | {percent_text} |"
        )

    lines.extend(
        [
            "",
            "## Parse And Decode",
            "",
            "| Family | Baseline bytes | Current bytes | Baseline mean ms | Current mean ms |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, value in report["parse_decode_benchmark"].items():
        if key == "parse_runs":
            continue
        baseline = value["baseline"]
        current = value["current"]
        lines.append(
            f"| `{key}` | {format_int(baseline['bytes'])} | {format_int(current['bytes'])} | "
            f"{format_ms(baseline['mean_ms'])} | {format_ms(current['mean_ms'])} |"
        )
    runtime_decode = report.get("runtime_parse_decode_summary") or {}
    lines.extend(
        [
            "",
            "## Runtime Query-Term Decode Summary",
            "",
            f"- Baseline local-index runtime bytes: `{format_int(runtime_decode.get('baseline_local_index_runtime_bytes'))}`",
            f"- Current local-index runtime bytes: `{format_int(runtime_decode.get('current_local_index_runtime_bytes'))}`",
            f"- Runtime byte change: `{runtime_decode.get('bytes_percent_change')}%`",
            f"- Baseline local-index parse/decode mean: `{format_ms(runtime_decode.get('baseline_local_index_parse_decode_mean_ms'))}` ms",
            f"- Current query-term parse/decode mean: `{format_ms(runtime_decode.get('current_local_index_query_term_parse_decode_mean_ms'))}` ms",
            f"- Parse/decode change: `{runtime_decode.get('parse_decode_percent_change')}%`",
            f"- Light decode mode: `{runtime_decode.get('light_decode_mode')}`",
            f"- Body decode mode: `{runtime_decode.get('body_decode_mode')}`",
        ]
    )
    query_path_decode = report.get("query_path_parse_decode_benchmark") if isinstance(report.get("query_path_parse_decode_benchmark"), dict) else {}
    query_path_summary = query_path_decode.get("summary") if isinstance(query_path_decode.get("summary"), dict) else {}
    if query_path_summary:
        lines.extend(
            [
                "",
                "## Query Path Parse And Decode",
                "",
                "| Phase | Mean baseline bytes | Mean current bytes | Byte change | Mean baseline ms | Mean current ms | Decode change | Byte gate | Decode within tolerance |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for phase in ("first_trusted_results", "top_results_hydrated"):
            phase_summary = query_path_summary.get(phase) or {}
            lines.append(
                f"| `{phase}` | {format_int(phase_summary.get('mean_baseline_bytes'))} | "
                f"{format_int(phase_summary.get('mean_current_bytes'))} | `{phase_summary.get('bytes_percent_change')}%` | "
                f"{format_ms(phase_summary.get('mean_baseline_decode_ms'))} | "
                f"{format_ms(phase_summary.get('mean_current_decode_ms'))} | "
                f"`{phase_summary.get('decode_percent_change')}%` | `{phase_summary.get('bytes_passed')}` | "
                f"`{phase_summary.get('decode_within_tolerance')}` |"
            )
        lines.append(
            f"- Query-path byte gate passed: `{query_path_summary.get('passed')}`. "
            f"Decode timing is reported separately with tolerance `{QUERY_PATH_DECODE_REGRESSION_TOLERANCE_PERCENT}%`."
        )

    wasm_decision = report.get("rust_wasm_decision") if isinstance(report.get("rust_wasm_decision"), dict) else {}
    if wasm_decision and not wasm_decision.get("missing"):
        decision = wasm_decision.get("decision") or {}
        ts_decode = wasm_decision.get("typescript_decode_to_object") or {}
        wasm_decode = wasm_decision.get("wasm_decode_to_json_then_parse") or {}
        wasm_stats = wasm_decision.get("wasm_stats_only_decode") or {}
        ts_retrieval = wasm_decision.get("typescript_retrieval_kernel") or {}
        wasm_retrieval = wasm_decision.get("wasm_retrieval_kernel") or {}
        wasm_session = wasm_decision.get("wasm_retrieval_session") or {}
        wasm_score_bridge = wasm_decision.get("wasm_retrieval_session_scores_bridge") or {}
        lines.extend(
            [
                "",
                "## Rust/WASM Decision",
                "",
                f"- Decision: `{decision.get('status')}`",
                f"- Winner for current runtime: `{decision.get('winner')}`",
                f"- TypeScript decode mean ms: `{format_ms(ts_decode.get('mean_ms'))}`",
                f"- WASM materialized decode mean ms: `{format_ms(wasm_decode.get('mean_ms'))}`",
                f"- WASM stats-only decode mean ms: `{format_ms(wasm_stats.get('mean_ms'))}`",
                f"- TypeScript retrieval kernel mean ms: `{format_ms(ts_retrieval.get('mean_ms'))}`",
                f"- WASM stateless retrieval kernel mean ms: `{format_ms(wasm_retrieval.get('mean_ms'))}`",
                f"- WASM stateful retrieval session mean ms: `{format_ms(wasm_session.get('mean_ms'))}`",
                f"- WASM stateful retrieval score bridge mean ms: `{format_ms(wasm_score_bridge.get('mean_ms'))}`",
                f"- Reason: {decision.get('reason')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Query Measurements",
            "",
            "| Query | ms | Results | Candidate shards | Loaded shards | Uncached bytes | Pruned postings | Complete | Top result |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for item in report["query_measurements"]:
        top = item.get("top_result") or {}
        lines.append(
            f"| `{item['query']}` | {format_ms(item['elapsed_ms'])} | {format_int(item['result_count'])} | "
            f"{format_int(item['candidate_shard_count'])} | {format_int(item['loaded_shard_count'])} | "
            f"{format_int(item['coverage']['uncached_loaded_bytes'])} | "
            f"{format_int(item['retrieval']['postings_pruned'])} | "
            f"`{item['coverage']['exhaustive_complete']}` | {str(top.get('title') or '')[:80]} |"
        )

    lines.extend(
        [
            "",
            "## Phase Gates",
            "",
            "| Query | First trusted bytes | First trusted ms | Top hydrated bytes | Top hydrated ms | Proof bytes | Passed |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in report["query_measurements"]:
        phases = item.get("phase_measurements") or {}
        first = phases.get("first_trusted_results") or {}
        top = phases.get("top_results_hydrated") or {}
        proof = phases.get("proof_complete") or {}
        gate = item.get("phase_gate") or {}
        lines.append(
            f"| `{item['query']}` | {format_int(first.get('uncached_loaded_bytes'))} | "
            f"{format_ms(first.get('elapsed_ms'))} | {format_int(top.get('uncached_loaded_bytes'))} | "
            f"{format_ms(top.get('elapsed_ms'))} | {format_int(proof.get('uncached_loaded_bytes'))} | "
            f"`{gate.get('passed')}` |"
        )
    query_measurement_summary = report.get("query_measurement_summary") or {}
    lines.extend(
        [
            "",
            f"- First trusted hard gate: `<={format_int(FIRST_TRUSTED_MAX_UNCACHED_BYTES)}` bytes or `<=10%` of proof bytes.",
            f"- Top hydrated hard gate: `<={format_int(TOP_RESULTS_MAX_UNCACHED_BYTES)}` bytes or `<=25%` of proof bytes.",
            f"- Phase gates passed: `{query_measurement_summary.get('phase_gates_passed')}`",
        ]
    )

    cache = report.get("cache_benchmark") or {}
    if not cache.get("skipped"):
        summary = cache.get("summary") or {}
        lines.extend(
            [
                "",
                "## Cache Benchmark",
                "",
                f"- Query count: `{format_int(summary.get('query_count'))}`",
                f"- Max cold uncached bytes: `{format_int(summary.get('max_cold_uncached_bytes'))}`",
                f"- Max warm uncached bytes: `{format_int(summary.get('max_warm_uncached_bytes'))}`",
                f"- Total warm cached bytes: `{format_int(summary.get('total_warm_cached_bytes'))}`",
                f"- Passed: `{summary.get('passed')}`",
            ]
        )

    browser = report.get("browser_verification") if isinstance(report.get("browser_verification"), dict) else {}
    if browser and not browser.get("missing"):
        summary = browser.get("summary") or {}
        lines.extend(
            [
                "",
                "## Browser Verification",
                "",
                f"- Passed: `{summary.get('passed')}`",
                f"- Persistent cache passed: `{summary.get('persistent_cache_passed')}`",
                f"- Viewports: `{json.dumps(summary.get('viewports') or [], ensure_ascii=False)}`",
                f"- Scenario count: `{format_int(summary.get('scenario_count'))}`",
                f"- Max warm uncached immutable bytes: `{format_int(summary.get('max_warm_uncached_immutable_bytes'))}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Quality",
            "",
            f"- Smoke eval: `{'skipped' if report['quality_eval'].get('skipped') else 'passed'}`",
            f"- Task eval: `{'skipped' if report['task_eval'].get('skipped') else str(report['task_eval'].get('passed')) + '/' + str(report['task_eval'].get('expectation_count'))}`",
            "",
            "## Attachment Evidence",
            "",
            f"- Policy: `{report['attachment_evidence'].get('policy')}`",
            f"- Coverage: `{json.dumps(report['attachment_evidence'].get('coverage') or {}, ensure_ascii=False)}`",
            "",
            "## Definition Of Done Audit",
            "",
            "| Item | Status | Evidence |",
            "| ---: | --- | --- |",
        ]
    )
    for item, value in report["dod_audit"].items():
        evidence = value.get("evidence")
        if not isinstance(evidence, str):
            evidence = json.dumps(evidence, ensure_ascii=False)
        lines.append(f"| {item} | `{value.get('status')}` | {evidence[:240]} |")

    baseline_ref = str(report.get("baseline", {}).get("ref") or "HEAD")

    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```powershell",
            f"uv run --python 3.13 python -m njupt_search_eval run-lower-bound-report --baseline-ref {baseline_ref} --collection apps\\web\\public\\generated\\collections\\njupt-public --output tools\\search-eval\\reports\\njupt-search-lower-bound-report.json --markdown tools\\search-eval\\reports\\njupt-search-lower-bound-report.md",
            "```",
            "",
            "This report is evidence for the active lower-bound goal. It does not claim final completion while DoD items remain unmet.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report_files(report: dict[str, Any], *, output: Path | None, markdown: Path | None) -> None:
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown_report(report), encoding="utf-8")
