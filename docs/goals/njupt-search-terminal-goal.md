# Goal: Terminal `njupt-search` Collection Search Architecture

## Objective

Bring `njupt-search` to the terminal top-tier architecture as a downstream static product:

```text
static-site-graph -> njupt-site-graph -> njupt-search
```

`njupt-search` consumes audited source packages and generated exam data, compiles browser runtime artifacts, and owns only the React/PWA product experience.

## Boundaries

- Use `collection` as the product abstraction; the current collection id is `njupt-public`.
- Keep `jwc` as a source package, not as the product abstraction.
- Keep `exam` as a product vertical, not as a sitegraph source package.
- Do not add LLM search, task-frame search, provider fields, server runtime search, or semantic production fields.
- Do not add a Codex GitHub Action, Codex review workflow, or `.github/codex/prompts`.
- Generated JSON artifacts are compiled runtime data. Update generators or source inputs, then regenerate.

## Terminal Shape

```text
apps/web/
  public/generated/
    collections/njupt-public/
      manifest.json
      sitegraph/jwc/artifacts/*.json
      sitegraph/jwc/shards/full.*.<hash>.json
    exam/
      all_exams.json
      data_summary.json
      source_metadata.json
  src/
    app/
    pages/
    features/
    widgets/
    shared/

packages/
  contracts/
  search-core/
  exam-core/

tools/
  collection-indexer/
  exam-pipeline/
  search-eval/
  quality-gates/
```

No root `public`, root `scripts`, `/index/*`, or `/data/*` runtime entrypoints remain in the terminal state.

## Milestones

1. Milestone 0: goal, AGENTS, architecture docs, ADRs, and review standards.
2. Milestone 1: useful skeleton only, no empty architecture directories.
3. Milestone 2: `packages/contracts` owns runtime and generated artifact contracts.
4. Milestone 3: `packages/search-core` owns browser-safe search logic.
5. Milestone 4: `packages/exam-core` owns exam parsing, search, and calendar logic.
6. Milestone 5: React/Vite app lives under `apps/web`.
7. Milestone 6: app split into `app`, `pages`, `features`, `widgets`, and `shared`.
8. Milestone 7: `tools/collection-indexer` builds and validates collection artifacts.
9. Milestone 8: `tools/exam-pipeline` produces generated exam artifacts.
10. Milestone 9: `tools/search-eval` and `tools/quality-gates` own deterministic evaluation and artifact gates.
11. Milestone 10: generated artifacts live only under `apps/web/public/generated`.
12. Milestone 11: GitHub Actions are split into deterministic workflow ownership.
13. Milestone 12: stale paths, stale docs, stale imports, and obsolete entrypoints are removed.

## Required Local Validation

```powershell
npm test
npm run typecheck
npm run build
npm run lint
uv run python -m pytest
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --skip-output
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package <path-to-njupt-site-graph-jwc-index> --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```

## Browser Acceptance

Browser acceptance is mandatory for routing, search UI, exam UI/data, Worker behavior, public paths, PWA caching, generated artifact layout, deployment output, and final acceptance.

Minimum checks:

1. Open the built or dev app.
2. Confirm no console errors.
3. Confirm no manifest, artifact, shard, or exam data 404s.
4. Confirm Worker reaches ready state and emits progressive search phases.
5. Confirm coverage UI reaches exhaustive completion.
6. Confirm desktop and mobile viewports render without broken layout.
7. Query the representative list below.

## GitHub Actions / Cloud CI

Terminal workflow ownership:

```text
ci.yml
update-exam-data.yml
update-collection-index.yml
validate-generated-artifacts.yml
deploy-web.yml
release-android.yml
```

Final acceptance requires local checks, browser acceptance, and deterministic GitHub Actions/cloud CI to pass, or an exact evidence-backed external blocker.

## Canonical Representative Queries

```text
校历
慕课考试
期末考试
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
```

## Final Definition of Done

The goal is complete only when:

1. The repository matches the terminal shape above.
2. Generated artifacts exist only under `apps/web/public/generated`.
3. Packaged tools own collection indexing, exam pipeline, search evaluation, and quality gates.
4. The React app loads generated collection and exam artifacts from the terminal paths.
5. Search behavior remains progressive, verifiable, and pure browser Worker based.
6. Exam search and calendar export work against generated exam artifacts.
7. Local validation passes.
8. Browser acceptance passes.
9. GitHub Actions/cloud CI passes.
10. The result is merged to `main` and milestone branches are removed after successful validation.
