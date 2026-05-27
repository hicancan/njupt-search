# Testing Strategy

## Local Gate

Use these commands from the repository root:

```powershell
npm test
npm run typecheck
npm run build
npm run lint
uv run python -m pytest
```

Generated artifact and search quality checks use:

```powershell
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --skip-output
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package <path-to-njupt-site-graph-jwc-index> --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```

## Unit And Contract Tests

Current tests must remain passing as code migrates:

- search index contract, tokenization, ranking, shard filtering, progressive phases, and coverage;
- generated sitegraph artifact parity and manifest contracts;
- exam data contract validation;
- class/course search behavior;
- `.ics` calendar/export behavior;
- URL-safe download filename behavior.

When logic moves across `packages/*` or `tools/*`, move or add tests with the logic.

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

## Tool Commands

```powershell
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package <path> --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --collection apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m pytest
npm test
npm run typecheck
npm run build
```
