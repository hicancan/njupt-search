# Product Search Quality Gate

The product gate protects the JWC progressive static search path and the separate exam vertical.

## Required Commands

```powershell
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --skip-output
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
uv run python -m pytest
npm test
npm run typecheck
npm run build
```

## Blocking Invariants

- upstream JWC package has no quality errors and every discovered URL has an outcome;
- attachment binaries are not saved; attachment records are metadata only;
- external links are recorded only and are not recursively crawled;
- generated detail, attachment, external link, and edge counts match upstream truth counts;
- manifest declares `progressive_search`, `coverage_contract`, and `verification_contract`;
- manifest provides `shard_catalog` plus `shard_filter` proof metadata;
- large artifacts are hash-addressed under `apps/web/public/generated/collections/njupt-public/sitegraph/jwc/`;
- stale fixed-name public index artifacts are absent;
- Worker emits progressive events and final exhaustive coverage;
- representative queries have quick results and complete exhaustive verification;
- exam data remains available through the exam vertical.
