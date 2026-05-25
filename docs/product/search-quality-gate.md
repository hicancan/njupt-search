# Product Search Quality Gate

## Objective

Search Quality v1.3 makes the browser-facing TypeScript recall path the product truth. The gate protects the results that users actually see, while still reporting Python recall drift for diagnosis.

## Modes

```powershell
uv run python scripts\eval\eval_product_search.py --mode python
uv run python scripts\eval\eval_product_search.py --mode frontend --ts-results eval\reports\ts_search_results.json
uv run python scripts\eval\eval_product_search.py --mode both --ts-results eval\reports\ts_search_results.json
```

CI uses `--mode both`. In `both`, Python and frontend are both evaluated and reported, but frontend results are the blocking product truth. Python-only failures remain visible through `python_pass=false`, `non_blocking_failure_reasons`, and the parity report.

## Statuses

- `strict_pass`: blocking frontend checks pass.
- `data_gap`: the case fails, but all configured `coverage_channels` are empty, filtered out, or contain no relevant document for the case terms.
- `fail`: blocking frontend checks fail and the failure is not explainable as a configured data gap.

## Case Schema

`eval/search_cases.json` supports v1.3 relevance fields:

```json
{
  "top1_must_include_any_terms": [],
  "top3_min_relevant_count": 2,
  "top5_min_relevant_count": 3,
  "relevance_terms_any": [],
  "relevance_terms_all_groups": [],
  "forbidden_terms": [],
  "forbidden_domains": [],
  "forbidden_sources": [],
  "data_gap_allowed": false,
  "data_gap_group": "optional-group-name",
  "coverage_channels": []
}
```

Use `relevance_terms_all_groups` when a query needs compound meaning. For example, `论文答辩` must match a document containing `答辩` and at least one of `论文 / 学位 / 毕业`.

## Data Gap Policy

Data gaps do not count as strict passes. They are allowed only when `data_gap_allowed=true` and the configured channels prove there is no suitable indexed document. The short-term CI threshold is at most three unique data gap groups.

Known v1.3 data gap groups:

- `cet_notice`: CET / 四六级专项通知 are absent from the current index.
- `degree_defense`: `pg_degree` and `pg_graduation` are filtered to zero usable documents.
- `competition_specific`: `cxcy_competition` has no 蓝桥杯 / 挑战杯 usable document.

`医保` remains a strict case: top1 must be medical-insurance related and top3 must contain at least two documents matching `医保 / 医疗 / 参保 / 报销`.

## Reporting

Reports are persisted to `eval/reports/product_search_latest.json` with `status_counts`, `data_gap_cases`, `data_gap_channels`, `python_top5`, `frontend_top5`, `python_pass`, `frontend_pass`, and blocking/non-blocking failure reasons.
