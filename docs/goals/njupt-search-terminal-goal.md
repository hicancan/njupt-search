# Goal: Refactor `njupt-search` into the terminal top-tier collection-search architecture

This document is the **single terminal goal** for Codex. It is intended to be referenced from Goal mode, not copied into a short prompt.

Use it with:

```text
/goal Execute docs/goals/njupt-search-terminal-goal.md. Work milestone by milestone. Preserve user-visible behavior. Do not mark any milestone complete unless the required local checks, browser acceptance, and GitHub Actions/cloud CI checks pass or are explicitly blocked with evidence.
```

---

## 0. First principles

`njupt-search` is not merely a Vite/React app. It is the downstream search product in a three-repository ecosystem.

The ecosystem must remain:

```text
static-site-graph
  Generic framework/template/rules for modeling static or semi-static websites into auditable site graphs.

njupt-site-graph
  NJUPT source-truth producer. It may produce many audited source packages, not only JWC.

njupt-search
  Downstream public information search product. It consumes audited source packages, compiles browser runtime artifacts, runs progressive static search in the browser, and provides the user-facing Web/PWA experience.
```

The terminal architecture is governed by this rule:

```text
Source truth is upstream.
Search index is compiled.
Browser runtime is formal.
Product experience is downstream.
CI/CD verifies the whole loop.
```

This repository must become a clean downstream product repository with internal boundaries. It must not absorb upstream source-truth ownership.

---

## 1. Terminal mission

Refactor `njupt-search` from the current mixed shape:

```text
src/
scripts/
public/
tests/
.github/workflows/
```

into a durable product repository with explicit layers:

```text
apps/web
packages/contracts
packages/search-core
packages/exam-core
tools/collection-indexer
tools/exam-pipeline
tools/search-eval
tools/quality-gates
tests/integration
tests/e2e
docs/architecture
docs/adr
docs/goals
.github/workflows
```

The final product must still work as the current product works, unless an ADR explicitly changes behavior.

The terminal outcome is:

```text
Audited source packages from njupt-site-graph
  -> tools/collection-indexer
  -> generated collection runtime artifacts
  -> packages/search-core browser runtime
  -> apps/web React/PWA product
  -> browser acceptance
  -> GitHub Actions/cloud CI/CD validation
```

---

## 2. Non-negotiable boundaries

### 2.1 Do not merge the three repositories

Do not move these into `njupt-search`:

```text
static-site-graph internals
njupt-site-graph configs/sites/*
upstream site crawling logic
upstream site modeling logic
upstream source-truth audit notes
JWC/NJUPT page-family exploration notes as product code
```

`njupt-search` consumes `njupt-site-graph` outputs; it does not own upstream source discovery or crawling.

### 2.2 Do not design around only JWC

Current production may compile only JWC, but the terminal abstraction must be:

```text
collection_id: njupt-public
sources:
  - jwc
  - future source packages from njupt-site-graph
```

Use `collection` as the product abstraction, not `jwc` or `site`.

### 2.3 Separate source from vertical

Sources are origin packages.

Verticals are product experiences.

```text
Sources:
  jwc, yjs, lib, xgc, tw, job, news, future site packages

Verticals:
  exam, calendar, forms, systems, policy, workflow, downloads
```

The exam channel is a structured product vertical, not a sitegraph source.

### 2.4 Do not reintroduce legacy production search concepts

Production non-exam search must remain:

```text
audited source package
-> collection index compiler
-> hash-addressed static artifacts
-> browser Worker progressive static search
-> React/PWA UI
```

Do not add production dependence on:

```text
LLM search
task-frame search
model provider fields
semantic_mode
source_channel_production_enabled
github_resource_production_enabled
server-side search runtime
```

Legacy-field rejection may remain as a quality gate.

### 2.5 Contract, not path convention

Do not make the architecture depend on local sibling paths such as:

```text
../njupt-site-graph/data/sites/jwc/index
D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index
```

Final tools must use explicit CLI inputs and outputs:

```text
collection-indexer build \
  --collection-id njupt-public \
  --source-kind sitegraph \
  --source-package <path-to-source-package> \
  --out apps/web/public/generated/collections/njupt-public
```

All cross-layer boundaries must be expressed through:

```text
schemas
manifests
CLI arguments
tests
quality gates
CI/CD workflows
browser acceptance
```

### 2.6 Preserve behavior unless an ADR explicitly changes it

Preserve existing behavior:

```text
home page
quick search entries
URL query behavior
current JWC/current collection search
progressive search phases
coverage panel
exam/class query behavior
exam data availability
PWA update notification
GitHub Pages deployment behavior
Android release compatibility if still supported
```

### 2.7 Generated artifacts are compiled runtime data

Generated JSON artifacts are not hand-written source.

Never manually edit generated artifacts. Update the generator or source input and regenerate.

### 2.8 Avoid architecture theater

Do not create empty target directories just to make the tree look right.

A new directory is allowed only if it contains at least one of:

```text
migrated production code
migrated tests
immediately used config
scoped AGENTS.md
README explaining a near-term migration purpose
CI/tooling used by the current milestone
```

### 2.9 Do not add Codex GitHub Action

Do **not** add a Codex GitHub Action, Codex review workflow, or `.github/codex/prompts` as part of this terminal architecture.

Codex is the refactoring tool. It is not part of the product architecture or final CI/CD gate.

The terminal CI/CD requirement means deterministic GitHub Actions such as tests, builds, generated artifact validation, deployment checks, and release checks.

### 2.10 Avoid premature `packages/ui`

Do not extract `packages/ui` early.

Start with:

```text
apps/web/src/shared/ui
```

Create `packages/ui` only if shared UI primitives are stable, reused across multiple features, and extracting them reduces complexity.

### 2.11 Public URL migration must be two-phase

Current runtime paths must not break abruptly:

```text
data/all_exams.json
data/data_summary.json
index/manifest.json
index/sitegraph/jwc/artifacts/*
index/sitegraph/jwc/shards/*
```

Required migration:

```text
Phase 1: add new generated layout while preserving old URLs
Phase 2: update app config, Worker config, PWA runtimeCaching, deployment, and browser tests
Phase 3: remove old URLs only after browser acceptance and GitHub Actions pass
```

---

## 3. Target repository shape

Converge toward this structure with real code, tests, docs, and workflows.

```text
njupt-search/
  AGENTS.md
  README.md
  package.json
  tsconfig.base.json
  eslint.config.js
  vitest.workspace.ts
  pyproject.toml
  uv.lock

  .github/
    workflows/
      ci.yml
      update-exam-data.yml
      update-collection-index.yml
      validate-generated-artifacts.yml
      deploy-web.yml
      release-android.yml

  apps/
    web/
      README.md
      package.json
      index.html
      vite.config.ts
      tsconfig.json
      public/
        assets/
          logo.png
          icon-192x192.png
          icon-512x512.png
        generated/
          README.md
          collections/
            njupt-public/
              manifest.json
              artifacts/
              shards/
          exam/
            all_exams.json
            data_summary.json
        legacy/
          README.md
      src/
        main.tsx
        app/
          App.tsx
          providers/
          routing/
          config/
        pages/
          home/
          results/
          not-found/
        widgets/
          app-shell/
          search-box/
          update-notifier/
        features/
          query-router/
          exam-search/
          collection-search/
        shared/
          ui/
          lib/
          styles/
          testing/

  packages/
    contracts/
      README.md
      package.json
      tsconfig.json
      src/
        exam/
        source-sitegraph/
        search-collection/
        search-index/
        generated/json-schema/
      tests/

    search-core/
      README.md
      package.json
      tsconfig.json
      src/
        contract/
        collection/
        text/
        retrieval/
        ranking/
        shards/
        verification/
        progressive/
        formatting/
      tests/

    exam-core/
      README.md
      package.json
      tsconfig.json
      src/
        model/
        contract/
        search/
        calendar/
      tests/

    ui/  # optional late-stage extraction only

  tools/
    collection-indexer/
      README.md
      pyproject.toml
      src/njupt_search_indexer/
        input/
        normalize/
        compile/
        index/
        output/
      tests/

    exam-pipeline/
      README.md
      pyproject.toml
      src/njupt_exam_pipeline/
      tests/

    search-eval/
      README.md
      pyproject.toml
      src/njupt_search_eval/
      queries/
        representative_queries.yaml
      tests/

    quality-gates/
      README.md
      scripts/

  tests/
    integration/
    e2e/

  docs/
    goals/
      njupt-search-terminal-goal.md
    architecture/
      current-state-analysis.md
      target-architecture.md
      data-flow.md
      collection-index-contract.md
      browser-runtime.md
      frontend-architecture.md
      pipeline-architecture.md
      testing-strategy.md
      ci-cd-acceptance.md
    adr/
      0001-keep-three-repository-ecosystem-boundary.md
      0002-use-product-repo-monorepo-layout.md
      0003-separate-search-core-from-web-ui.md
      0004-version-search-index-contract.md
      0005-use-collection-not-single-site-as-product-abstraction.md
      0006-keep-generated-artifacts-explicit.md
      0007-browser-acceptance-is-required.md
      0008-cloud-ci-is-required-for-final-acceptance.md
      0009-no-llm-task-framework-in-production-non-exam-search.md
    operations/
      local-development.md
      update-exam-data.md
      update-collection-index.md
      release-process.md
      android-release.md
      rollback-generated-index.md
    codex/
      milestone-prompts.md
      review-checklist.md
```

---

## 4. Initial migration map

Use this map to avoid ambiguous moves.

```text
src/App.tsx
  -> apps/web/src/app/App.tsx
  -> apps/web/src/app/routing/*
  -> apps/web/src/pages/*

src/views/HomeView.tsx
  -> apps/web/src/pages/home/HomePage.tsx
  -> apps/web/src/features/query-router/model/searchPresets.ts

src/views/ResultsView.tsx
  -> apps/web/src/pages/results/ResultsPage.tsx
  -> apps/web/src/features/exam-search/ui/*
  -> apps/web/src/features/collection-search/ui/*

src/components/SearchInput.tsx
  -> apps/web/src/widgets/search-box/SearchInput.tsx

src/components/Header.tsx
src/components/ThemeToggle.tsx
src/components/UptimeDisplay.tsx
src/components/ResultsSkeleton.tsx
  -> apps/web/src/widgets/*
  -> apps/web/src/shared/ui/* where appropriate

src/workers/searchWorker.ts
  -> apps/web/src/features/collection-search/worker/collectionSearch.worker.ts

src/hooks/useSearchIndex.ts
  -> apps/web/src/features/collection-search/model/useSearchIndexWorker.ts

src/hooks/useSearchEngine.ts
  -> apps/web/src/features/collection-search/model/useProgressiveSearch.ts

src/hooks/useExamData.ts
src/hooks/useClassSearch.ts
src/hooks/useSelectedExamIds.ts
  -> apps/web/src/features/exam-search/model/*
  -> packages/exam-core/* for pure logic

src/utils/searchIndex.ts
  -> packages/search-core/src/contract/*
  -> packages/search-core/src/text/*
  -> packages/search-core/src/retrieval/*
  -> packages/search-core/src/ranking/*
  -> packages/search-core/src/shards/*
  -> packages/search-core/src/verification/*
  -> packages/search-core/src/progressive/*
  -> packages/search-core/src/formatting/*

src/types/index.ts
  -> packages/contracts/src/exam/*
  -> packages/contracts/src/source-sitegraph/*
  -> packages/contracts/src/search-collection/*
  -> packages/contracts/src/search-index/*

src/utils/examDataContract.ts
  -> packages/exam-core/src/contract/*
  -> packages/contracts/src/exam/*

src/utils/examQuery.ts
  -> packages/exam-core/src/search/*

src/utils/icsGenerator.ts
  -> packages/exam-core/src/calendar/*

scripts/build_sitegraph_index.py
  -> tools/collection-indexer/src/njupt_search_indexer/*

scripts/validate_sitegraph_index.py
  -> tools/collection-indexer/src/njupt_search_indexer/input/validate_upstream.py
  -> tools/quality-gates/scripts/check_collection_manifest.py

scripts/sitegraph_search.py
scripts/eval/sitegraph_query_smoke_test.py
  -> tools/search-eval/src/njupt_search_eval/*
  -> tools/search-eval/queries/representative_queries.yaml

scripts/auto_update_exam_data.py
scripts/analyze_and_update.py
  -> tools/exam-pipeline/src/njupt_exam_pipeline/*

scripts/utils/validate_search_index.py
  -> tools/quality-gates/scripts/*

public/data/*
  -> apps/web/public/generated/exam/*
  -> keep legacy compatibility until public URL migration is complete

public/index/*
  -> apps/web/public/generated/collections/njupt-public/*
  -> keep legacy compatibility until public URL migration is complete

.github/workflows/auto-update.yml
  -> update-exam-data.yml
  -> update-collection-index.yml
  -> validate-generated-artifacts.yml

.github/workflows/deploy.yml
  -> deploy-web.yml

.github/workflows/build-apk.yml
  -> release-android.yml
```

---

## 5. Milestones

Work milestone by milestone. Do not start the next milestone until the current milestone is reported and accepted.

### Milestone 0: Goal, AGENTS, docs, and acceptance standards only

Create/update:

```text
AGENTS.md
docs/goals/njupt-search-terminal-goal.md
docs/architecture/current-state-analysis.md
docs/architecture/target-architecture.md
docs/architecture/testing-strategy.md
docs/architecture/ci-cd-acceptance.md
docs/adr/0001-keep-three-repository-ecosystem-boundary.md
docs/adr/0002-use-product-repo-monorepo-layout.md
docs/adr/0005-use-collection-not-single-site-as-product-abstraction.md
docs/adr/0007-browser-acceptance-is-required.md
docs/adr/0008-cloud-ci-is-required-for-final-acceptance.md
docs/codex/milestone-prompts.md
docs/codex/review-checklist.md
```

Do not move production source code in this milestone.

Done only when:

```text
the terminal goal exists in docs/goals
AGENTS.md exists
current-state analysis documents actual current problems
target architecture is documented
testing and CI/CD acceptance are documented
no production code moved
```

### Milestone 1: Add only useful skeleton

Add target directories only when immediately useful.

Done only when no empty theater directories are created.

### Milestone 2: Extract contracts

Move contracts to `packages/contracts`.

Keep compatibility re-exports until imports are migrated.

Done only when:

```text
contract tests exist
current imports still work
npm test passes
typecheck passes
build passes
```

### Milestone 3: Extract search-core

Move browser-safe search logic into `packages/search-core`.

Keep `src/utils/searchIndex.ts` as a temporary facade until migration is complete.

Done only when:

```text
tokenizer tests pass
ranking tests pass
coverage tests pass
shard filter tests pass
progressive search tests pass
current Worker still works
representative query smoke still passes
```

### Milestone 4: Extract exam-core

Move pure exam parsing/search/calendar logic into `packages/exam-core`.

Done only when exam data contract tests, class search tests, and calendar/export tests pass.

### Milestone 5: Move web app to `apps/web`

Move React/Vite app into `apps/web`.

Preserve build, deployment output, public paths, and user behavior.

Done only when local checks and browser smoke pass.

### Milestone 6: Split web features

Refactor app into:

```text
app
pages
features/query-router
features/exam-search
features/collection-search
widgets
shared
```

`App.tsx` must become a thin composition root.

Done only when browser acceptance passes for home, collection search, exam, coverage, and mobile.

### Milestone 7: Package collection-indexer

Move sitegraph index-building logic into `tools/collection-indexer`.

Rename mental model from single-site indexer to collection compiler.

Done only when it can compile the current JWC source package into artifacts compatible with current product behavior.

### Milestone 8: Package exam-pipeline

Move exam data pipeline into `tools/exam-pipeline`.

Done only when generated exam artifacts validate and current exam vertical still works.

### Milestone 9: Package search-eval and quality-gates

Move representative queries and validation scripts into:

```text
tools/search-eval
tools/quality-gates
```

Done only when representative query smoke tests and generated artifact quality gates pass.

### Milestone 10: Generated artifact layout migration

Move toward:

```text
apps/web/public/generated/collections/njupt-public/
apps/web/public/generated/exam/
```

Use two-phase compatibility.

Done only when old paths remain compatible or removal is proven safe by browser acceptance and CI.

### Milestone 11: CI/CD workflow refactor

Refactor deterministic GitHub Actions into:

```text
ci.yml
update-exam-data.yml
update-collection-index.yml
validate-generated-artifacts.yml
deploy-web.yml
release-android.yml
```

Do not add Codex GitHub Action.

Done only when cloud CI passes or exact human action is reported.

### Milestone 12: Final cleanup

Remove obsolete compatibility facades, stale scripts, stale docs, stale imports, and old path assumptions.

Done only when full local checks, browser acceptance, and GitHub Actions/cloud CI pass.

---

## 6. Required local validation

Use current equivalent commands until final tools exist.

### 6.1 TypeScript / React / Web / Worker

```bash
npm test
npm run typecheck
npm run build
```

If lint exists:

```bash
npm run lint
```

### 6.2 Python

```bash
python -m pytest
```

Current equivalent quality commands:

```bash
uv run python scripts/validate_sitegraph_index.py --sitegraph-index <path> --skip-output
uv run python scripts/build_sitegraph_index.py --sitegraph-index <path>
uv run python scripts/validate_sitegraph_index.py --sitegraph-index <path>
uv run python scripts/utils/validate_search_index.py
uv run python scripts/eval/sitegraph_query_smoke_test.py
uv run python -m pytest
```

Future target quality commands:

```bash
python -m njupt_search_indexer build --collection-id njupt-public --source-package <path> --out apps/web/public/generated/collections/njupt-public
python -m njupt_search_indexer validate --collection apps/web/public/generated/collections/njupt-public
python -m njupt_search_eval run-smoke-queries --collection apps/web/public/generated/collections/njupt-public
python tools/quality-gates/scripts/check_no_legacy_fields.py
python tools/quality-gates/scripts/check_public_artifact_sizes.py
python -m pytest
npm test
npm run typecheck
npm run build
```

---

## 7. Required browser acceptance

Browser validation is mandatory for milestones touching:

```text
routing
App.tsx
home/results pages
SearchInput/Header/Footer
exam UI/data
collection search UI
Worker location
Worker protocol
public URLs
manifest/artifact/shard loading
PWA/service worker/cache config
generated artifact layout
deployment output paths
final acceptance
```

Minimum browser smoke:

```text
1. Start local dev server.
2. Open home route.
3. Verify no initial console errors.
4. Search `校历`.
5. Search `期末考试`.
6. Search `教务管理系统`.
7. Search `学生相关文件及表格`.
8. Search `xlsx`.
9. Verify results appear.
10. Verify progressive phase/coverage UI appears.
11. Verify no manifest/artifact/shard/data 404.
12. Verify Worker reaches ready state and emits search phases.
13. Verify query URL state works.
14. Query an exam class route if exam data is available.
15. Verify mobile viewport 375x812 has no critical overflow.
16. Verify desktop viewport 1440x900 works.
```

Browser report format:

```text
Browser Validation Report
- Local URL:
- Dev server command:
- Browser tool used:
- Viewports:
- Queries tested:
- Routes tested:
- Worker ready observed: yes/no
- Search phases observed:
- Coverage observed:
- Console error count:
- Network 404 count:
- PWA/cache notes:
- Pass/fail:
```

---

## 8. Required GitHub Actions / cloud CI acceptance

Final acceptance requires deterministic GitHub Actions/cloud CI to pass in a clean runner.

Required final workflows:

```text
pull_request:
  ci.yml
  validate-generated-artifacts.yml
  browser/e2e smoke if configured

push to main:
  ci.yml
  update-exam-data.yml or equivalent
  update-collection-index.yml or equivalent
  validate-generated-artifacts.yml
  deploy-web.yml

release/tag/manual:
  release-android.yml if Android remains supported
```

Final workflows must:

```text
install Node dependencies cleanly
install Python dependencies cleanly
run TypeScript tests
run typecheck
run build
run Python tests
run generated artifact quality gates
run representative query smoke tests
validate generated artifact contracts
upload useful artifacts on failure
separate exam update failures from collection-index failures
prevent deployment if validation fails
```

If Codex cannot access GitHub Actions from the current environment, it must report:

```text
exact workflow names to run
expected success criteria
local commands already run
what remains unverified
```

---

## 9. Canonical representative queries

Use one canonical list for quick searches, placeholders, search evaluation, browser smoke, and docs.

Initial list:

```text
校历
期末考试
慕课考试
转专业
规章制度
办事流程
学生相关文件及表格
教务管理系统
大创
推免
成绩
附件1
xlsx
考试安排
B250403
```

Do not duplicate this list independently across files.

---

## 10. Milestone report format

After each milestone, report exactly:

```text
Milestone:
Problem fixed:
Files changed:
Architecture boundary improved:
Compatibility wrappers added/removed:
Local commands run:
Local command results:
Browser validation required: yes/no
Browser validation result:
GitHub Actions/cloud CI required now: yes/no
GitHub Actions/cloud CI result or exact human action needed:
Risks:
Rollback notes:
Next recommended milestone:
```

Do not start the next milestone automatically.

---

## 11. Final Definition of Done

The terminal goal is complete only when all are true:

```text
1. The repository has real apps/packages/tools/docs/tests structure, not empty theater.
2. `apps/web` owns UI and browser integration.
3. `packages/contracts` owns runtime and generated artifact contracts.
4. `packages/search-core` owns browser-safe progressive static search logic.
5. `packages/exam-core` owns pure exam domain logic.
6. `tools/collection-indexer` compiles audited source packages into collection runtime artifacts.
7. `tools/exam-pipeline` produces exam generated artifacts.
8. `tools/search-eval` owns representative query smoke tests.
9. `tools/quality-gates` owns generated artifact and contract gates.
10. Generated artifact layout is explicit and documented.
11. Current product behavior is preserved or explicitly ADR-changed.
12. Architecture is ready for multiple future source packages in `njupt-public`.
13. Old production LLM/task-framework concepts do not return.
14. Local tests pass.
15. Browser acceptance passes.
16. GitHub Actions/cloud CI passes.
17. Deploy does not run if validation fails.
18. Android release workflow is preserved or explicitly ADR-changed.
19. Docs and ADRs explain the final architecture.
20. No Codex GitHub Action or AI review workflow is required for completion.
```
