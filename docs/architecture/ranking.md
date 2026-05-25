# Recall And Chronological Display

The production search path is no longer a ranker. It is route-aware candidate recall followed by strict chronological display.

Shared inputs:

- `config/query_routes.json`
- `config/query_aliases.json`
- `public/index/documents.json`
- `public/index/query_aliases.json`

Runtime implementations:

- Frontend: `src/utils/searchIndex.ts`
- Python eval: `scripts/search/vertical_ranker.py`

The parity gate is `scripts/eval/eval_search_parity.py`.

## Components

- `query_terms`: raw query tokens plus configured aliases.
- `route_gating`: target domains/intents and explicit route blockers.
- `notice_card`: offline evidence-backed objects, actions, deadlines, materials, locations, attachments, and risk.
- `typed_search_terms`: offline searchable terms tagged by source field.
- `synonyms`: alias terms attached offline from `config/query_aliases.json`.
- `chronology`: every recalled candidate is displayed by `published_at` descending, with source/id only as deterministic tie-breakers.

The runtime assigns `score = 1` only as a compatibility shape for result cards. It does not compute BM25, hybrid score components, semantic utility, tier scores, or degraded fallback results.

## Route Gating

Routes can define target domains/intents, blocked domains/sources, required top-result terms, bad-result terms, and whether resource documents are allowed. These fields decide whether a document is a valid candidate, not how high it ranks.

If official sources do not contain a relevant public document, product gates may classify the miss as a data gap when the case declares coverage channels and those channels are empty or missing the expected relevant item.

## Commands

```powershell
npm exec -- tsx --tsconfig tsconfig.app.json scripts/eval/eval_frontend_search.ts --out eval/reports/ts_search_results.json
uv run python scripts/eval/eval_search_parity.py --ts-results eval/reports/ts_search_results.json
```
