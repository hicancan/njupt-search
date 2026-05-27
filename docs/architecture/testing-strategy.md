# Testing Strategy

## Local Gate

Use the current equivalent commands until target package/tool commands exist:

```powershell
npm test
npm run typecheck
npm run build
npm run lint
uv run python -m pytest
```

Generated artifact and search quality checks currently use:

```powershell
uv run python scripts\validate_sitegraph_index.py --sitegraph-index <path-to-njupt-site-graph-jwc-index> --skip-output
uv run python scripts\build_sitegraph_index.py --sitegraph-index <path-to-njupt-site-graph-jwc-index>
uv run python scripts\validate_sitegraph_index.py --sitegraph-index <path-to-njupt-site-graph-jwc-index>
uv run python scripts\utils\validate_search_index.py
uv run python scripts\eval\sitegraph_query_smoke_test.py
```

## Unit And Contract Tests

Current tests must remain passing as code migrates:

- search index contract, tokenization, ranking, shard filtering, progressive phases, and coverage;
- generated sitegraph artifact parity and manifest contracts;
- exam data contract validation;
- class/course search behavior;
- `.ics` calendar/export behavior;
- URL-safe download filename behavior.

When logic moves to `packages/search-core`, `packages/exam-core`, or `packages/contracts`, move or add tests with the logic. Keep temporary compatibility facades tested until consumers are migrated.

## Browser Acceptance

Browser acceptance is required when a milestone touches:

- routing or `App.tsx`;
- home/results pages;
- search box, header, update notifier, or coverage display;
- exam UI or data loading;
- collection search UI;
- Worker file location or protocol;
- manifest, artifact, shard, or exam data public URLs;
- PWA service worker/cache config;
- generated artifact layout;
- deployment output paths;
- final acceptance.

Minimum browser smoke:

```text
Open home route.
Verify no initial console errors.
Search 校历.
Search 期末考试.
Search 教务管理系统.
Search 学生相关文件及表格.
Search xlsx.
Verify results appear.
Verify progressive phase and coverage UI appear.
Verify no manifest/artifact/shard/data 404.
Verify Worker reaches ready state and emits search phases.
Verify query URL state works.
Query an exam class route if exam data is available.
Verify mobile viewport 375x812.
Verify desktop viewport 1440x900.
```

## Browser Report Template

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

## Future Target Commands

```powershell
python -m njupt_search_indexer build --collection-id njupt-public --source-package <path> --out apps/web/public/generated/collections/njupt-public
python -m njupt_search_indexer validate --collection apps/web/public/generated/collections/njupt-public
python -m njupt_search_eval run-smoke-queries --collection apps/web/public/generated/collections/njupt-public
python tools\quality-gates\scripts\check_no_legacy_fields.py
python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m pytest
npm test
npm run typecheck
npm run build
```

