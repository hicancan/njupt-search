# Top-Tier Upgrade Audit

Generated during the one-shot production hardening pass.

## Architecture Map

- `config/source_channels.json` is the source/channel graph. It defines official sources, channel URLs, selectors, expected domains/intents, priority, and audit status.
- `scripts/update_search_index.py` crawls campus sources, prepares canonical documents, runs rule guards, optional LLM enrichment, semantic verification, TaskFrame extraction, offline notice-card/typed-term enrichment, and manifest writing.
- `scripts/models/*` defines canonical documents, source graph nodes, TaskFrames, and the shared search contract loader.
- `public/index/*.json` is the static production search index consumed by the React app.
- `src/types/index.ts` validates production JSON in the browser. Production enum fields are now strict.
- `src/utils/searchIndex.ts` recalls route-valid candidates from `public/index/documents.json` and displays matches by `published_at` descending.
- `scripts/search/vertical_ranker.py` mirrors frontend recall for offline evaluation and parity checks.
- `scripts/eval/*` runs search quality, frontend search, product acceptance, and Python/TypeScript parity gates.
- `.github/workflows/auto-update.yml` crawls, validates, evaluates, and commits generated artifacts.

## Data Flow

1. `config/source_channels.json` -> `read_source_channel_configs()`
2. Channel list URLs -> `collect_candidates()`
3. Candidate detail pages -> `prepare_notice_candidate()`
4. Raw HTML/text/attachments -> `CanonicalDocument`
5. `rule_guard` determines restricted, sensitive, low-evidence, duplicate, and LLM-allowed state
6. LLM or heuristic semantic extraction -> `SemanticResult`
7. `semantic_verifier` removes ungrounded deadline/action/material/location/task fields
8. `extract_task_frames()` normalizes concrete student tasks
9. `finalize_hytask_documents()` normalizes contract fields and verifies cached/generated documents
10. `attach_notice_card_and_terms()` writes evidence-backed cards, typed search terms, synonyms, objects, actions, deadlines, materials, locations, attachments, and risk fields
11. Frontend parses strict documents, recalls route-valid candidates, and displays matches in strict chronological order

## Confirmed Weaknesses Fixed

- TypeScript production enum parsing silently used `.catch()` defaults.
- Guarded semantic fallback emitted invalid `campus_life` / `information`.
- Python/TypeScript route validation had duplicated enum lists.
- Ranking weights were not fully consumed by either runtime.
- The `bm25` component was effectively a term-frequency proxy in the frontend ranker.
- Campus crawling used global `verify=False` and suppressed TLS warnings.
- Channel selectors existed in config but were not represented in runtime channel config.
- Optional frontend index files loaded all-or-nothing.
- CI workflow built shell args as one unquoted string and committed LLM cache by default.

## Remaining Weaknesses

- The generated production index was validated, but not fully regenerated in this run; crawler changes apply on the next indexing run.
- The source graph still depends on heuristic WordPress-like extraction for many legacy pages.
- Medical insurance has only one strong current public document in the local index; product gate passes after blocking unrelated campus-network/resource candidates, but source coverage should be improved.
- CET, specific competition notices, and degree-defense queries remain documented data gaps.

## Files Changed

- Contracts: `config/search_contract.json`, `scripts/models/search_contract.py`, `src/types/index.ts`
- Validation: `scripts/utils/validate_search_index.py`, `scripts/utils/validate_query_routes.py`
- Semantics: `scripts/core/semantic_verifier.py`, `scripts/core/semantic_pipeline.py`, `scripts/models/task_frame.py`
- Crawler/network: `scripts/update_search_index.py`, `scripts/config/indexer_config.py`, `scripts/models/source_graph.py`, `scripts/auto_update_exam_data.py`
- Recall: `src/utils/searchIndex.ts`, `scripts/search/vertical_ranker.py`, `config/query_routes.json`, `config/query_aliases.json`
- Frontend resilience: `src/hooks/useSearchIndex.ts`, `src/App.tsx`
- CI/eval/docs/tests: `.github/workflows/auto-update.yml`, `eval/queries/search_gold.json`, `tests/*`, architecture docs
