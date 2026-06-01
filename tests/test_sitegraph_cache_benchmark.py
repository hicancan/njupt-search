from __future__ import annotations

from njupt_search_eval.sitegraph_cache_benchmark import run_cache_benchmark


def test_warm_cache_benchmark_reuses_content_hash_artifacts() -> None:
    report = run_cache_benchmark(["校历"])
    assert report["summary"]["passed"] is True
    assert report["summary"]["max_warm_uncached_bytes"] == 0
    assert report["summary"]["total_warm_cached_bytes"] > 0
    row = report["queries"][0]
    assert row["warm_cache"]["artifact_misses"] == 0
    assert row["warm_cache"]["artifact_hits"] > 0
    assert row["cold_top_id"] == row["warm_top_id"]
    assert row["warm_selected_cache_states"]["warm"] > 0
