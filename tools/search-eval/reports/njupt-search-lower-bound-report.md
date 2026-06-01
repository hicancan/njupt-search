# NJUPT Search Lower-Bound Evidence Report

- Generated at: `2026-06-01T12:53:28.579289+00:00`
- Collection: `apps/web/public/generated/collections/njupt-public`
- Baseline ref: `1a0996e`
- Current artifact generation: `2026-06-01T11:41:42.782193+00:00`

## Runtime Contract

| Contract | Value |
| --- | ---: |
| `legacy_global_first_screen` | `False` |
| `startup_loads_local_indexes` | `False` |
| `startup_loads_full_shards` | `False` |
| `startup_loads_global_document_metadata` | `False` |
| `directory_contains_doc_postings` | `False` |
| `completion_requires_ledger` | `True` |

## Byte Comparison

| Metric | Baseline | Current | Delta | Change |
| --- | ---: | ---: | ---: | ---: |
| `routed_first_screen_total_bytes` | 217,034 | 219,564 | 2,530 | 1.166% |
| `bootstrap_manifest_bytes` | 12,790 | 14,259 | 1,469 | 11.486% |
| `source_registry_bytes` | 4,405 | 4,804 | 399 | 9.058% |
| `global_query_directory_bytes` | 197,030 | 197,600 | 570 | 0.289% |
| `query_aliases_bytes` | 2,809 | 2,901 | 92 | 3.275% |
| `source_manifest_total_bytes` | 1,066,061 | 686,225 | -379,836 | -35.630% |
| `local_impact_light_index_total_bytes` | 28,563,086 | 0 | -28,563,086 | -100.000% |
| `local_impact_light_index_meta_total_bytes` | None | 11,962,895 | 11,962,895 |  |
| `local_impact_light_index_packed_total_bytes` | None | 9,006,665 | 9,006,665 |  |
| `local_impact_body_index_total_bytes` | 30,920,155 | 0 | -30,920,155 | -100.000% |
| `local_impact_body_index_packed_total_bytes` | None | 16,850,611 | 16,850,611 |  |
| `light_index_runtime_bytes` | None | 20,969,560 | 20,969,560 |  |
| `body_index_bytes` | 30,920,155 | 0 | -30,920,155 | -100.000% |
| `body_index_runtime_bytes` | None | 16,850,611 | 16,850,611 |  |
| `local_index_runtime_bytes` | None | 37,820,171 | 37,820,171 |  |
| `full_scan_total_bytes` | 44,782,519 | 45,697,141 | 914,622 | 2.042% |
| `artifact_total_bytes` | 122,264,702 | 77,279,822 | -44,984,880 | -36.793% |
| `binary_artifact_total_bytes` | None | 25,857,276 | 25,857,276 |  |
| `runtime_artifact_total_bytes` | None | 103,137,098 | 103,137,098 |  |
| `artifact_count` | 1,465 | 1,219 | -246 | -16.792% |
| `binary_artifact_count` | None | 492 | 492 |  |
| `local_index_count` | 246 | 246 | 0 | 0.000% |
| `full_shard_count` | 942 | 942 | 0 | 0.000% |
| `max_full_shard_bytes` | 485,346 | 499,697 | 14,351 | 2.957% |
| `avg_full_shard_bytes` | 47,539 | 48,510 | 970 | 2.042% |

## Parse And Decode

| Family | Baseline bytes | Current bytes | Baseline mean ms | Current mean ms |
| --- | ---: | ---: | ---: | ---: |
| `bootstrap_json` | 217,034 | 219,564 | 0.901 | 0.967 |
| `source_manifests` | 1,066,061 | 686,225 | 4.486 | 1.962 |
| `shard_filters_json_and_bitsets` | 2,843,792 | 2,843,792 | 8.269 | 8.388 |
| `local_light_json` | 28,563,086 | 0 | 262.079 | 0.000 |
| `local_light_meta_json` | 0 | 11,962,895 | 0.000 | 41.042 |
| `local_light_packed` | 0 | 9,006,665 | 0.000 | 833.850 |
| `local_light_packed_query_terms` | 0 | 9,006,665 | 0.000 | 208.363 |
| `local_body_json` | 30,920,155 | 0 | 428.641 | 0.000 |
| `local_body_packed` | 0 | 16,850,611 | 0.000 | 1697.137 |
| `local_body_packed_query_terms` | 0 | 16,850,611 | 0.000 | 384.721 |

## Runtime Query-Term Decode Summary

- Baseline local-index runtime bytes: `59,483,241`
- Current local-index runtime bytes: `37,820,171`
- Runtime byte change: `-36.419%`
- Baseline local-index parse/decode mean: `690.720` ms
- Current query-term parse/decode mean: `634.126` ms
- Parse/decode change: `-8.193%`
- Light decode mode: `metadata_json_plus_packed_query_term_selective`
- Body decode mode: `packed_query_term_selective`

## Query Path Parse And Decode

| Phase | Mean baseline bytes | Mean current bytes | Byte change | Mean baseline ms | Mean current ms | Decode change | Byte gate | Decode within tolerance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `first_trusted_results` | 3,594,643 | 2,695,326 | `-25.018%` | 31.636 | 26.563 | `-16.038%` | `True` | `True` |
| `top_results_hydrated` | 10,938,208 | 7,004,252 | `-35.965%` | 125.469 | 111.247 | `-11.335%` | `True` | `True` |
- Query-path byte gate passed: `True`. Decode timing is reported separately with tolerance `5.0%`.

## Rust/WASM Decision

- Decision: `rust_wasm_retrieval_runtime_selected`
- Winner for current runtime: `wasm_retrieval_session_scores_bridge`
- TypeScript decode mean ms: `645.327`
- WASM materialized decode mean ms: `685.090`
- WASM stats-only decode mean ms: `43.046`
- TypeScript retrieval kernel mean ms: `3360.691`
- WASM stateless retrieval kernel mean ms: `470.565`
- WASM stateful retrieval session mean ms: `587.936`
- WASM stateful retrieval score bridge mean ms: `587.416`
- Reason: The browser runtime can consume Rust/WASM stateful score entries directly. On the full packed body workload, the Rust/WASM session score bridge was 0.175x the TypeScript selective retrieval kernel for the same artifact format, query set, and global top-k pruning state.

## Query Measurements

| Query | ms | Results | Candidate shards | Loaded shards | Uncached bytes | Pruned postings | Complete | Top result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `校历` | 1409.170 | 12 | 18 | 472 | 50,246,788 | 265 | `True` | 2025-2026学年校历 |
| `慕课考试` | 1636.469 | 12 | 18 | 569 | 53,223,215 | 70 | `True` | 【教务管理办公室】2025-2026学年第二学期在线开放课程（慕课）线下考试报名通知 |
| `学生相关文件及表格` | 2320.912 | 12 | 18 | 628 | 54,178,693 | 250 | `True` | 南京邮电大学学生毕业申请表 2026-04-16 |
| `教务管理系统` | 2132.762 | 12 | 18 | 483 | 51,723,971 | 309 | `True` | 教务管理系统 |
| `附件1` | 2250.969 | 12 | 18 | 601 | 52,191,611 | 189 | `True` | 【科创竞赛】第九届“外教社杯”全国高校学生跨文化能力大赛南京邮电大学校园赛通知 |
| `不存在的查询词` | 1091.161 | 0 | 8 | 148 | 34,775,972 | 0 | `True` |  |

## Phase Gates

| Query | First trusted bytes | First trusted ms | Top hydrated bytes | Top hydrated ms | Proof bytes | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `校历` | 4,014,830 | 45.628 | 9,315,740 | 140.361 | 50,246,788 | `True` |
| `慕课考试` | 4,386,232 | 60.009 | 10,366,630 | 201.469 | 53,223,215 | `True` |
| `学生相关文件及表格` | 3,505,996 | 57.218 | 7,750,789 | 192.708 | 54,178,693 | `True` |
| `教务管理系统` | 4,118,978 | 58.000 | 9,923,870 | 245.895 | 51,723,971 | `True` |
| `附件1` | 4,219,284 | 57.528 | 9,755,672 | 185.460 | 52,191,611 | `True` |
| `不存在的查询词` | 3,440,203 | 43.324 | 8,743,962 | 146.242 | 34,775,972 | `True` |

- First trusted hard gate: `<=5,242,880` bytes or `<=10%` of proof bytes.
- Top hydrated hard gate: `<=10,485,760` bytes or `<=25%` of proof bytes.
- Phase gates passed: `True`

## Cache Benchmark

- Query count: `8`
- Max cold uncached bytes: `54,178,693`
- Max warm uncached bytes: `0`
- Total warm cached bytes: `412,248,327`
- Passed: `True`

## Browser Verification

- Passed: `True`
- Persistent cache passed: `True`
- Viewports: `["desktop-default", "390x844"]`
- Scenario count: `8`
- Max warm uncached immutable bytes: `None`

## Quality

- Smoke eval: `passed`
- Task eval: `29/29`

## Attachment Evidence

- Policy: `metadata_and_filename_only_no_extracted_attachment_content`
- Coverage: `{"total": 8094, "metadata_only": 8094, "filename_only": 8094, "text_extracted": 0, "snippet": 0, "full_content": 0}`

## Definition Of Done Audit

| Item | Status | Evidence |
| ---: | --- | --- |
| 1 | `evidence_present` | {"legacy_global_first_screen": false, "startup_loads_local_indexes": false, "startup_loads_full_shards": false, "startup_loads_global_document_metadata": false, "directory_contains_doc_postings": false, "completion_requires_ledger": true} |
| 2 | `evidence_present` | {"planner": "Planner telemetry includes route expected_cost_bytes, selected expected_uncached bytes, cache state per local index, and phase-specific local index selections.", "max_first_trusted_uncached_bytes": 4386232, "first_trusted_absol |
| 3 | `evidence_present` | {"any_dynamic_pruning": true, "total_postings_pruned": 1083} |
| 4 | `evidence_present` | Measured queries report proof ledger complete with zero pending/failed shards; runtime tests cover no-match proof, failed shard refusal, and cancelled pending-ledger refusal. |
| 5 | `evidence_present` | {"artifact_total_bytes_current": 77279822, "artifact_total_bytes_baseline": 122264702, "runtime_parse_decode_summary": {"baseline_local_index_runtime_bytes": 59483241, "current_local_index_runtime_bytes": 37820171, "bytes_delta": -21663070, |
| 6 | `evidence_present` | {"light_json_bytes": 0, "light_split_runtime_bytes": 20969560, "body_json_bytes": 0, "body_packed_runtime_bytes": 16850611, "note": "Packed binary light terms plus metadata JSON are used for query planning; packed binary light/body indexes  |
| 7 | `evidence_present` | {"artifact_count": 246, "benchmark": "packed-impact-retrieval-wasm-vs-typescript-v2", "collection": "apps/web/public/generated/collections/njupt-public", "decision": {"reason": "The browser runtime can consume Rust/WASM stateful score entri |
| 8 | `evidence_present` | {"query_count": 8, "max_cold_uncached_bytes": 54178693, "max_warm_uncached_bytes": 0, "total_warm_cached_bytes": 412248327, "max_warm_ms": 1747.481, "passed": true, "failure_count": 0, "cache_invalidation_test": "Changed content-hash artifa |
| 9 | `evidence_present` | {"policy": "metadata_and_filename_only_no_extracted_attachment_content", "levels": ["metadata_only", "filename_only", "text_extracted", "snippet", "full_content"], "coverage": {"total": 8094, "metadata_only": 8094, "filename_only": 8094, "t |
| 10 | `evidence_present` | Smoke queries, task queries, measured cold queries, warm cache queries, and a negative query are represented when full report mode is used. |
| 11 | `evidence_present` | {"report": "njupt-search-browser-verification-v3", "generated_at": "2026-06-01T11:58:52.526Z", "target": "http://127.0.0.1:4177", "summary": {"passed": true, "persistent_cache_passed": true, "wasm_runtime_passed": true, "dynamic_pruning_pas |
| 12 | `external_ci_deploy_required` | Local validators/tests/builds can be recorded separately; CI/deployment status is outside this local report. |
| 13 | `evidence_present` | This report includes byte, time, quality, cache, pruning, parse/decode, and coverage sections. |
| 14 | `unmet` | Commit, push, CI, and deployment checks are intentionally not claimed by this report. |

## Reproduction

```powershell
uv run --python 3.13 python -m njupt_search_eval run-lower-bound-report --baseline-ref 1a0996e --collection apps\web\public\generated\collections\njupt-public --output tools\search-eval\reports\njupt-search-lower-bound-report.json --markdown tools\search-eval\reports\njupt-search-lower-bound-report.md
```

This report is evidence for the active lower-bound goal. It does not claim final completion while DoD items remain unmet.
