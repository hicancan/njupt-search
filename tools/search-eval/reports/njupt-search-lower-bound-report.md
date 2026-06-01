# NJUPT Search Lower-Bound Evidence Report

- Generated at: `2026-06-01T05:51:09.106325+00:00`
- Collection: `apps/web/public/generated/collections/njupt-public`
- Baseline ref: `1a0996e`
- Current artifact generation: `2026-06-01T03:48:46.586213+00:00`

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
| `routed_first_screen_total_bytes` | 217,034 | 218,304 | 1,270 | 0.585% |
| `bootstrap_manifest_bytes` | 12,790 | 13,713 | 923 | 7.217% |
| `source_registry_bytes` | 4,405 | 4,804 | 399 | 9.058% |
| `global_query_directory_bytes` | 197,030 | 196,978 | -52 | -0.026% |
| `query_aliases_bytes` | 2,809 | 2,809 | 0 | 0.000% |
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
| `artifact_total_bytes` | 122,264,702 | 77,279,110 | -44,985,592 | -36.794% |
| `binary_artifact_total_bytes` | None | 25,857,276 | 25,857,276 |  |
| `runtime_artifact_total_bytes` | None | 103,136,386 | 103,136,386 |  |
| `artifact_count` | 1,465 | 1,219 | -246 | -16.792% |
| `binary_artifact_count` | None | 492 | 492 |  |
| `local_index_count` | 246 | 246 | 0 | 0.000% |
| `full_shard_count` | 942 | 942 | 0 | 0.000% |
| `max_full_shard_bytes` | 485,346 | 499,697 | 14,351 | 2.957% |
| `avg_full_shard_bytes` | 47,539 | 48,510 | 970 | 2.042% |

## Parse And Decode

| Family | Baseline bytes | Current bytes | Baseline mean ms | Current mean ms |
| --- | ---: | ---: | ---: | ---: |
| `bootstrap_json` | 217,034 | 218,304 | 0.940 | 1.046 |
| `source_manifests` | 1,066,061 | 686,225 | 3.859 | 2.136 |
| `shard_filters_json_and_bitsets` | 2,843,792 | 2,843,792 | 8.540 | 8.474 |
| `local_light_json` | 28,563,086 | 0 | 271.419 | 0.000 |
| `local_light_meta_json` | 0 | 11,962,895 | 0.000 | 44.478 |
| `local_light_packed` | 0 | 9,006,665 | 0.000 | 831.848 |
| `local_light_packed_query_terms` | 0 | 9,006,665 | 0.000 | 213.944 |
| `local_body_json` | 30,920,155 | 0 | 437.222 | 0.000 |
| `local_body_packed` | 0 | 16,850,611 | 0.000 | 1676.294 |
| `local_body_packed_query_terms` | 0 | 16,850,611 | 0.000 | 422.771 |

## Runtime Query-Term Decode Summary

- Baseline local-index runtime bytes: `59,483,241`
- Current local-index runtime bytes: `37,820,171`
- Runtime byte change: `-36.419%`
- Baseline local-index parse/decode mean: `708.641` ms
- Current query-term parse/decode mean: `681.193` ms
- Parse/decode change: `-3.873%`
- Light decode mode: `metadata_json_plus_packed_query_term_selective`
- Body decode mode: `packed_query_term_selective`

## Rust/WASM Decision

- Decision: `typescript_better_for_current_runtime`
- Winner for current runtime: `typescript_runtime_decoder`
- TypeScript decode mean ms: `636.351`
- WASM materialized decode mean ms: `689.802`
- WASM stats-only decode mean ms: `39.948`
- Reason: The current browser runtime consumes a JavaScript SitegraphLocalBodyIndex object. On the full packed body workload, Rust/WASM decode plus JSON bridge was 1.084x the TypeScript decoder, so replacing only the decoder would increase current runtime decode cost. The stats-only WASM path is recorded as a lower-bound signal for a future full WASM retrieval core that avoids JS object materialization.

## Query Measurements

| Query | ms | Results | Candidate shards | Loaded shards | Uncached bytes | Pruned postings | Complete | Top result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `校历` | 1650.148 | 12 | 32 | 474 | 52,362,058 | 8 | `True` | 2025-2026学年校历 |
| `慕课考试` | 2019.865 | 12 | 32 | 569 | 60,195,348 | 78 | `True` | 【教务管理办公室】2025-2026学年第二学期在线开放课程（慕课）线下考试报名通知 |
| `学生相关文件及表格` | 2440.457 | 12 | 32 | 628 | 54,763,613 | 257 | `True` | 南京邮电大学学生毕业申请表 2026-04-16 |
| `教务管理系统` | 2178.573 | 12 | 32 | 470 | 58,035,908 | 613 | `True` | 教务管理系统 |
| `附件1` | 2413.229 | 12 | 32 | 601 | 54,584,482 | 250 | `True` | 【科创竞赛】第九届“外教社杯”全国高校学生跨文化能力大赛南京邮电大学校园赛通知 |
| `不存在的查询词` | 1194.109 | 0 | 32 | 154 | 44,130,320 | 0 | `True` |  |

## Cache Benchmark

- Query count: `8`
- Max cold uncached bytes: `60,195,348`
- Max warm uncached bytes: `0`
- Total warm cached bytes: `477,243,404`
- Passed: `True`

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
| 2 | `evidence_present` | Planner telemetry includes route expected_cost_bytes, selected expected_uncached bytes, and cache state per local index. |
| 3 | `evidence_present` | {"any_dynamic_pruning": true, "total_postings_pruned": 1206} |
| 4 | `evidence_present` | Measured queries report proof ledger complete with zero pending/failed shards; runtime tests cover no-match proof, failed shard refusal, and cancelled pending-ledger refusal. |
| 5 | `evidence_present` | {"artifact_total_bytes_current": 77279110, "artifact_total_bytes_baseline": 122264702, "runtime_parse_decode_summary": {"baseline_local_index_runtime_bytes": 59483241, "current_local_index_runtime_bytes": 37820171, "bytes_delta": -21663070, |
| 6 | `evidence_present` | {"light_json_bytes": 0, "light_split_runtime_bytes": 20969560, "body_json_bytes": 0, "body_packed_runtime_bytes": 16850611, "note": "Packed binary light terms plus metadata JSON are used for query planning; packed binary body indexes are us |
| 7 | `evidence_present` | {"artifact_count": 246, "benchmark": "packed-impact-decoder-wasm-vs-typescript-v1", "collection": "apps/web/public/generated/collections/njupt-public", "decision": {"reason": "The current browser runtime consumes a JavaScript SitegraphLocal |
| 8 | `evidence_present` | {"query_count": 8, "max_cold_uncached_bytes": 60195348, "max_warm_uncached_bytes": 0, "total_warm_cached_bytes": 477243404, "max_warm_ms": 2057.844, "passed": true, "failure_count": 0, "cache_invalidation_test": "Changed content-hash artifa |
| 9 | `evidence_present` | {"policy": "metadata_and_filename_only_no_extracted_attachment_content", "levels": ["metadata_only", "filename_only", "text_extracted", "snippet", "full_content"], "coverage": {"total": 8094, "metadata_only": 8094, "filename_only": 8094, "t |
| 10 | `evidence_present` | Smoke queries, task queries, measured cold queries, warm cache queries, and a negative query are represented when full report mode is used. |
| 11 | `external_browser_evidence_required` | Browser verification is not performed by this CLI report; use the in-app browser evidence from the goal run. |
| 12 | `external_ci_deploy_required` | Local validators/tests/builds can be recorded separately; CI/deployment status is outside this local report. |
| 13 | `evidence_present` | This report includes byte, time, quality, cache, pruning, parse/decode, and coverage sections. |
| 14 | `unmet` | Commit, push, CI, and deployment checks are intentionally not claimed by this report. |

## Reproduction

```powershell
uv run --python 3.13 python -m njupt_search_eval run-lower-bound-report --baseline-ref 1a0996e --collection apps\web\public\generated\collections\njupt-public --output tools\search-eval\reports\njupt-search-lower-bound-report.json --markdown tools\search-eval\reports\njupt-search-lower-bound-report.md
```

This report is evidence for the active lower-bound goal. It does not claim final completion while DoD items remain unmet.
