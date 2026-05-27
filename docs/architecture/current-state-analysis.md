# Current State Analysis

## Summary

The repository is a working Vite/React/PWA product with two production data paths:

```text
JWC audited sitegraph package -> scripts/build_sitegraph_index.py -> public/index -> browser Worker -> React UI
exam Excel/data update scripts -> public/data -> exam React UI
```

The current product already implements progressive static search with hash-addressed JWC artifacts, browser Worker search phases, coverage reporting, exam data loading, and GitHub Pages deployment. The main architectural problem is not missing behavior; it is that product, contracts, generated artifacts, tools, and domain logic still share a flat application repository layout.

## Current Repository Shape

Current production code is organized under:

```text
src/
scripts/
public/
tests/
.github/workflows/
```

Important current files:

- `src/App.tsx` owns top-level routing and application composition.
- `src/views/HomeView.tsx` and `src/views/ResultsView.tsx` own page-level UI.
- `src/workers/searchWorker.ts` owns browser search Worker integration.
- `src/utils/searchIndex.ts` mixes runtime contracts, tokenization, retrieval, ranking, shard handling, verification, and formatting.
- `src/utils/examDataContract.ts`, `src/utils/examQuery.ts`, and `src/utils/icsGenerator.ts` own pure exam-domain logic inside the web app.
- `scripts/build_sitegraph_index.py`, `scripts/validate_sitegraph_index.py`, and `scripts/sitegraph_search.py` own current JWC index build/validation/evaluation logic.
- `scripts/auto_update_exam_data.py` and `scripts/analyze_and_update.py` own exam data update and processing.
- `public/index/` contains generated JWC search runtime artifacts.
- `public/data/` contains generated exam artifacts and source spreadsheets.

## Actual Problems

1. Cross-layer contracts are implicit in path conventions and TypeScript/Python structures rather than isolated package boundaries.
2. Search-core logic is browser-safe but not yet packaged separately from React UI code.
3. Exam pure logic is tested but still located inside the web app source tree.
4. The collection compiler is still named and shaped around the current JWC sitegraph implementation.
5. Current public URLs are production dependencies, so generated artifact layout migration must be two-phase.
6. GitHub Actions combine exam update, JWC index update, validation, and frontend checks in one update workflow, making failure ownership less clear.
7. Documentation describes the current progressive search path but does not yet record the terminal monorepo architecture and milestone gates.
8. The target docs directories were previously ignored by `.gitignore`, so canonical goal and ADR files could exist locally without being tracked.

## Existing Strengths To Preserve

- Public behavior: home page, quick search entries, query URL state, results page, exam/class search, `.ics` export, coverage panel, and PWA update behavior.
- Progressive Worker phases: quick, body, hydrate, verify, and exhaustive completion.
- Hash-addressed large artifacts under `public/index/sitegraph/jwc/`.
- Python contract tests for upstream/generated artifact parity.
- Frontend unit tests for exam query, class search, download naming, generated data contracts, calendar export, and search index behavior.
- Deployment to GitHub Pages and Android release workflow.

## Constraints For Migration

- Do not move production source code during Milestone 0.
- Do not break legacy public URLs before a documented two-phase migration.
- Do not make local sibling paths the final architecture contract.
- Do not merge upstream crawler/modeling/audit ownership into this repository.
- Do not create empty target directories without immediately useful contents.

