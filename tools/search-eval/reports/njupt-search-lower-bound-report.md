# NJUPT Search Lower-Bound Evidence Report

- Generated at: `2026-06-01T01:22:22.847710+00:00`
- Collection: `apps/web/public/generated/collections/njupt-public`
- Baseline ref: `HEAD`
- Current artifact generation: `2026-06-01T01:21:18.715612+00:00`

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
| `routed_first_screen_total_bytes` | 217,006 | 218,333 | 1,327 | 0.612% |
| `bootstrap_manifest_bytes` | 12,762 | 13,746 | 984 | 7.710% |
| `source_registry_bytes` | 4,405 | 4,804 | 399 | 9.058% |
| `global_query_directory_bytes` | 197,030 | 196,974 | -56 | -0.028% |
| `query_aliases_bytes` | 2,809 | 2,809 | 0 | 0.000% |
| `source_manifest_total_bytes` | 1,066,061 | 776,801 | -289,260 | -27.134% |
| `local_impact_light_index_total_bytes` | 28,563,086 | 0 | -28,563,086 | -100.000% |
| `local_impact_light_index_meta_total_bytes` | None | 11,962,895 | 11,962,895 |  |
| `local_impact_light_index_packed_total_bytes` | None | 8,565,618 | 8,565,618 |  |
| `local_impact_body_index_total_bytes` | 30,920,155 | 30,920,155 | 0 | 0.000% |
| `local_impact_body_index_packed_total_bytes` | None | 15,970,965 | 15,970,965 |  |
| `light_index_runtime_bytes` | None | 20,528,513 | 20,528,513 |  |
| `body_index_bytes` | 30,920,155 | 30,920,155 | 0 | 0.000% |
| `body_index_runtime_bytes` | None | 15,970,965 | 15,970,965 |  |
| `local_index_runtime_bytes` | None | 36,499,478 | 36,499,478 |  |
| `full_scan_total_bytes` | 44,782,519 | 45,697,141 | 914,622 | 2.042% |
| `artifact_total_bytes` | 122,264,702 | 108,289,852 | -13,974,850 | -11.430% |
| `binary_artifact_total_bytes` | None | 24,536,583 | 24,536,583 |  |
| `runtime_artifact_total_bytes` | None | 132,826,435 | 132,826,435 |  |
| `artifact_count` | 1,465 | 1,465 | 0 | 0.000% |
| `binary_artifact_count` | None | 492 | 492 |  |
| `local_index_count` | 246 | 246 | 0 | 0.000% |
| `full_shard_count` | 942 | 942 | 0 | 0.000% |
| `max_full_shard_bytes` | 485,346 | 499,697 | 14,351 | 2.957% |
| `avg_full_shard_bytes` | 47,539 | 48,510 | 970 | 2.042% |

## Parse And Decode

| Family | Baseline bytes | Current bytes | Baseline mean ms | Current mean ms |
| --- | ---: | ---: | ---: | ---: |
| `bootstrap_json` | 217,006 | 218,333 | 0.722 | 0.773 |
| `source_manifests` | 1,066,061 | 776,801 | 3.324 | 1.791 |
| `shard_filters_json_and_bitsets` | 2,843,792 | 2,843,792 | 10.951 | 12.599 |
| `local_light_json` | 28,563,086 | 0 | 270.082 | 0.000 |
| `local_light_meta_json` | 0 | 11,962,895 | 0.000 | 52.306 |
| `local_light_packed` | 0 | 8,565,618 | 0.000 | 955.126 |
| `local_body_json` | 30,920,155 | 30,920,155 | 588.496 | 584.467 |
| `local_body_packed` | 0 | 15,970,965 | 0.000 | 1876.366 |

## Rust/WASM Decision

- Decision: `typescript_better_for_current_runtime`
- Winner for current runtime: `typescript_runtime_decoder`
- TypeScript decode mean ms: `566.902`
- WASM materialized decode mean ms: `641.194`
- WASM stats-only decode mean ms: `18.890`
- Reason: The current browser runtime consumes a JavaScript SitegraphLocalBodyIndex object. On the full packed body workload, Rust/WASM decode plus JSON bridge was 1.131x the TypeScript decoder, so replacing only the decoder would increase current runtime decode cost. The stats-only WASM path is recorded as a lower-bound signal for a future full WASM retrieval core that avoids JS object materialization.

## Query Measurements

| Query | ms | Results | Candidate shards | Loaded shards | Uncached bytes | Pruned postings | Complete | Top result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `校历` | 2555.105 | 12 | 32 | 775 | 57,694,250 | 8 | `True` | 2025-2026学年校历 |
| `慕课考试` | 3084.260 | 12 | 32 | 778 | 62,783,026 | 78 | `True` | 【教务管理办公室】2025-2026学年第二学期在线开放课程（慕课）线下考试报名通知 |
| `学生相关文件及表格` | 2355.224 | 12 | 32 | 876 | 56,751,778 | 257 | `True` | 南京邮电大学学生毕业申请表 2026-04-16 |
| `教务管理系统` | 2707.087 | 12 | 32 | 835 | 62,588,132 | 613 | `True` | 教务管理系统 |
| `附件1` | 2763.549 | 12 | 32 | 700 | 57,169,551 | 275 | `True` | 【科创竞赛】第九届“外教社杯”全国高校学生跨文化能力大赛南京邮电大学校园赛通知 |
| `不存在的查询词` | 2698.840 | 0 | 32 | 671 | 62,783,599 | 0 | `True` |  |

## Cache Benchmark

- Query count: `8`
- Max cold uncached bytes: `64,878,472`
- Max warm uncached bytes: `0`
- Total warm cached bytes: `527,831,068`
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
| 3 | `evidence_present` | {"any_dynamic_pruning": true, "total_postings_pruned": 1231} |
| 4 | `evidence_present` | Measured queries report proof ledger complete with zero pending/failed shards. |
| 5 | `partial` | Before/after byte and parse/decode metrics are present; not every artifact family improved. |
| 6 | `evidence_present` | {"light_json_bytes": 0, "light_split_runtime_bytes": 20528513, "body_json_bytes": 30920155, "body_packed_runtime_bytes": 15970965, "note": "Packed binary light terms plus metadata JSON are used for query planning; packed binary body indexes |
| 7 | `evidence_present` | {"artifact_count": 246, "benchmark": "packed-impact-decoder-wasm-vs-typescript-v1", "collection": "apps/web/public/generated/collections/njupt-public", "decision": {"reason": "The current browser runtime consumes a JavaScript SitegraphLocal |
| 8 | `evidence_present` | {"query_count": 8, "max_cold_uncached_bytes": 64878472, "max_warm_uncached_bytes": 0, "total_warm_cached_bytes": 527831068, "max_warm_ms": 2439.024, "passed": true, "failure_count": 0} |
| 9 | `evidence_present` | {"policy": "metadata_and_filename_only_no_extracted_attachment_content", "levels": ["metadata_only", "filename_only", "text_extracted", "snippet", "full_content"], "coverage": {"total": 8094, "metadata_only": 8094, "filename_only": 8094, "t |
| 10 | `evidence_present` | Smoke queries, task queries, measured cold queries, warm cache queries, and a negative query are represented when full report mode is used. |
| 11 | `external_browser_evidence_required` | Browser verification is not performed by this CLI report; use the in-app browser evidence from the goal run. |
| 12 | `external_ci_deploy_required` | Local validators/tests/builds can be recorded separately; CI/deployment status is outside this local report. |
| 13 | `partial` | This report includes byte, time, quality, cache, pruning, parse/decode, and coverage sections. |
| 14 | `unmet` | Commit, push, CI, and deployment checks are intentionally not claimed by this report. |

## Reproduction

```powershell
uv run --python 3.13 python -m njupt_search_eval run-lower-bound-report --collection apps\web\public\generated\collections\njupt-public --output tools\search-eval\reports\njupt-search-lower-bound-report.json --markdown tools\search-eval\reports\njupt-search-lower-bound-report.md
```

This report is evidence for the active lower-bound goal. It does not claim final completion while DoD items remain unmet.
