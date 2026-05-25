# Frontend Search Gate

## Why Frontend Is Truth

Users search through the React frontend, which calls `recallSearchDocuments` and `routeQuery` in TypeScript. A Python-only gate can pass while the browser returns empty or irrelevant results, so v1.3 requires a frontend evaluation artifact before product and parity gates run.

## Evaluation Flow

```powershell
& .\node_modules\.bin\tsx.ps1 --tsconfig tsconfig.app.json scripts\eval\eval_frontend_search.ts --out eval\reports\ts_search_results.json
uv run python scripts\eval\eval_product_search.py --mode both --ts-results eval\reports\ts_search_results.json
uv run python scripts\eval\eval_search_parity.py --ts-results eval\reports\ts_search_results.json
```

The TypeScript report contains the route result and top-5 document ids/titles/domains for every case in `eval/search_cases.json`.

## Parity Thresholds

`eval_search_parity.py` refuses to pass without `--ts-results`. Current short-term thresholds:

- route fixtures: 100%
- critical non-data-gap top1 exact match: `1.00`
- non-data-gap top1 match: at least `0.60`
- critical non-data-gap average Jaccard: at least `0.50`
- critical top1 source/domain compatibility: `1.00`

The parity gate is intentionally not the product truth. It exposes Python/TS drift while the Product Gate blocks on frontend results.
For v1.3, Python `vertical_rank_documents` is a legacy entry point that delegates to the same recall semantics as the frontend.

## Adding A Search Case

1. Add the query to `eval/search_cases.json`.
2. Set `route` to the expected query route.
3. Add `relevance_terms_any` or `relevance_terms_all_groups`.
4. Add top-k requirements for strict journeys.
5. If the index lacks authoritative source coverage, set `data_gap_allowed=true` and list `coverage_channels`.
6. Re-run frontend eval, product gate, and parity gate.

Do not mark a weak or unrelated top-5 result as success. Use `data_gap` when the source graph proves the current index cannot answer the query yet.
