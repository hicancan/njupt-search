from __future__ import annotations

import time
from typing import Any

from .sitegraph_search import load_index, recall_documents_with_stats


DEFAULT_CACHE_QUERIES = [
    "校历",
    "慕课考试",
    "转专业",
    "学生相关文件及表格",
    "教务管理系统",
    "奖学金",
    "大创",
    "不存在的查询词",
]


def top_id(result: dict[str, Any]) -> str | None:
    results = result.get("results") or []
    if not results:
        return None
    return str(results[0].get("id") or "")


def timed_query(index: dict[str, Any], query: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    result = recall_documents_with_stats(query, limit=20, index=index)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms


def cache_state_counts(result: dict[str, Any]) -> dict[str, int]:
    selected = ((result.get("stats") or {}).get("plan") or {}).get("selected_local_indexes") or []
    counts = {"cold": 0, "partial": 0, "warm": 0}
    for item in selected:
        state = str(item.get("cache_state") or "cold")
        if state not in counts:
            counts[state] = 0
        counts[state] += 1
    return counts


def cache_summary(stats: dict[str, Any]) -> dict[str, Any]:
    cache = dict(stats.get("cache") or {})
    return {
        "scope": str(cache.get("scope") or "memory_content_hash"),
        "artifact_hits": int(cache.get("artifact_hits") or 0),
        "artifact_misses": int(cache.get("artifact_misses") or 0),
        "cached_bytes": int(cache.get("cached_bytes") or 0),
        "uncached_bytes": int(cache.get("uncached_bytes") or 0),
        "cacheable_bytes": int(cache.get("cacheable_bytes") or 0),
        "memory_hits": int(cache.get("memory_hits") or 0),
        "persistent_hits": int(cache.get("persistent_hits") or 0),
        "network_misses": int(cache.get("network_misses") or 0),
    }


def validate_warm_run(query: str, cold: dict[str, Any], warm: dict[str, Any]) -> dict[str, Any] | None:
    cold_stats = cold.get("stats") or {}
    warm_stats = warm.get("stats") or {}
    warm_cache = cache_summary(warm_stats)
    failures: dict[str, Any] = {}
    if ((cold_stats.get("coverage") or {}).get("exhaustive_complete")) is not True:
        failures["cold_exhaustive_complete"] = cold_stats.get("coverage")
    if ((warm_stats.get("coverage") or {}).get("exhaustive_complete")) is not True:
        failures["warm_exhaustive_complete"] = warm_stats.get("coverage")
    if top_id(cold) != top_id(warm):
        failures["top_result_changed"] = {"cold": top_id(cold), "warm": top_id(warm)}
    if warm_cache["artifact_misses"] != 0 or warm_cache["uncached_bytes"] != 0:
        failures["warm_cache_miss"] = warm_cache
    if failures:
        return {"query": query, "failures": failures}
    return None


def run_cache_benchmark(queries: list[str] | None = None) -> dict[str, Any]:
    query_list = queries or DEFAULT_CACHE_QUERIES
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for query in query_list:
        index = load_index()
        cold, cold_ms = timed_query(index, query)
        warm, warm_ms = timed_query(index, query)
        cold_stats = cold["stats"]
        warm_stats = warm["stats"]
        failure = validate_warm_run(query, cold, warm)
        if failure:
            failures.append(failure)
        rows.append(
            {
                "query": query,
                "cold_ms": round(cold_ms, 3),
                "warm_ms": round(warm_ms, 3),
                "cold_uncached_bytes": cold_stats["uncached_loaded_bytes"],
                "warm_uncached_bytes": warm_stats["uncached_loaded_bytes"],
                "warm_cached_bytes": warm_stats["cached_artifact_bytes"],
                "cold_cache": cache_summary(cold_stats),
                "warm_cache": cache_summary(warm_stats),
                "cold_selected_cache_states": cache_state_counts(cold),
                "warm_selected_cache_states": cache_state_counts(warm),
                "cold_loaded_shard_count": cold_stats["loaded_shard_count"],
                "warm_loaded_shard_count": warm_stats["loaded_shard_count"],
                "cold_top_id": top_id(cold),
                "warm_top_id": top_id(warm),
                "exhaustive_complete": bool((warm_stats.get("coverage") or {}).get("exhaustive_complete")),
            }
        )
    summary = {
        "query_count": len(rows),
        "max_cold_uncached_bytes": max((int(row["cold_uncached_bytes"]) for row in rows), default=0),
        "max_warm_uncached_bytes": max((int(row["warm_uncached_bytes"]) for row in rows), default=0),
        "total_warm_cached_bytes": sum(int(row["warm_cached_bytes"]) for row in rows),
        "max_warm_ms": max((float(row["warm_ms"]) for row in rows), default=0.0),
        "passed": len(failures) == 0,
        "failure_count": len(failures),
    }
    return {
        "benchmark": "sitegraph-memory-content-hash-cache-v2",
        "evidence_scope": "deterministic in-process cache simulation; browser persistent cache is measured by browser verification",
        "queries": rows,
        "summary": summary,
        "failures": failures,
    }
