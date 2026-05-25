# Evaluation

The executable product gate is `eval/search_cases.json`.

`eval/queries/search_gold.json` is the durable coverage map. It documents query categories, expected routes, data-gap policy, and metric expectations.

## Metrics

- route accuracy
- `strict_pass`
- `data_gap`
- `fail`
- Precision@5
- MRR
- NDCG
- Recall@10
- Python/TypeScript top-5 parity
- restricted/sensitive leakage
- TaskFrame evidence coverage

## Data Gaps

The current accepted data-gap groups are:

- CET / 四六级 notices from `jwc_exam`
- degree-defense notices from `pg_degree` and `pg_graduation`
- specific competition notices from `cxcy_competition`

Do not convert these to passes without source coverage evidence.

## Commands

```powershell
uv run python scripts/eval/eval_search.py --write-report
uv run python scripts/eval/query_smoke_test.py
uv run python scripts/eval/eval_llm_quality.py
npm exec -- tsx --tsconfig tsconfig.app.json scripts/eval/eval_frontend_search.ts --out eval/reports/ts_search_results.json
uv run python scripts/eval/eval_product_search.py --mode both --ts-results eval/reports/ts_search_results.json
uv run python scripts/eval/eval_search_parity.py --ts-results eval/reports/ts_search_results.json
```
