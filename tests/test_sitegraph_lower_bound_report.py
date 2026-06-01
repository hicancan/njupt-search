from __future__ import annotations

from njupt_search_eval.sitegraph_search import shard_filter_proves_no_match
from njupt_search_eval.sitegraph_lower_bound_report import build_lower_bound_report, render_markdown_report
from njupt_search_indexer.sitegraph_shards import build_filter_bitset


def test_shard_filter_proves_no_match_when_phrase_token_is_absent() -> None:
    payload = {
        "shard-1": {
            **build_filter_bitset(["材料"], bit_count=2048, hash_count=1),
            "hash_algorithm": "bloom-fnv1a32-utf8",
        }
    }

    assert shard_filter_proves_no_match("shard-1", payload, ["材料提交"]) is True
    assert shard_filter_proves_no_match("shard-1", payload, ["材料"]) is False


def test_lower_bound_report_contains_rerunnable_evidence() -> None:
    report = build_lower_bound_report(
        baseline_ref="1a0996e",
        queries=["校历"],
        cache_queries=["校历"],
        include_quality=False,
        include_task=False,
        include_cache=True,
        include_local_body_benchmark=False,
        parse_runs=3,
    )

    assert report["report"] == "njupt-search-lower-bound-evidence-v1"
    assert report["runtime_contract"]["legacy_global_first_screen"] is False
    assert report["runtime_contract"]["startup_loads_local_indexes"] is False
    assert report["runtime_contract"]["completion_requires_ledger"] is True
    assert report["byte_comparison"]["routed_first_screen_total_bytes"]["current"] > 0
    assert report["parse_decode_benchmark"]["source_manifests"]["current"]["bytes"] > 0

    measurement = report["query_measurements"][0]
    assert measurement["query"] == "校历"
    assert measurement["coverage"]["exhaustive_complete"] is True
    assert measurement["coverage"]["pending_shards"] == 0
    assert measurement["planner"]["selected_local_index_count"] > 0
    assert measurement["planner"]["phase_local_index_ids"]["first_trusted_results"]
    assert measurement["retrieval"]["dynamic_pruning"] is True
    assert measurement["phase_measurements"]["first_trusted_results"]["uncached_loaded_bytes"] <= 5 * 1024 * 1024
    assert measurement["phase_gate"]["passed"] is True
    assert report["query_measurement_summary"]["phase_gates_passed"] is True
    assert report["query_path_parse_decode_benchmark"]["summary"]["passed"] is True

    assert report["cache_benchmark"]["summary"]["passed"] is True
    assert report["cache_benchmark"]["summary"]["max_warm_uncached_bytes"] == 0
    assert report["dod_audit"]["6"]["status"] == "evidence_present"

    markdown = render_markdown_report(report)
    assert "NJUPT Search Lower-Bound Evidence Report" in markdown
    assert "DoD items remain unmet" in markdown
