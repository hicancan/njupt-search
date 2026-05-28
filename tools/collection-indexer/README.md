# Collection Indexer

This tool builds and validates generated collection runtime artifacts.

Near-term migration purpose:

- consume one or more audited source package paths through CLI arguments instead of implicit sibling paths;
- produce generated collection runtime artifacts for `collection_id: njupt-public`;

CLI:

```powershell
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-kind sitegraph --source-package <jwc-index> --source-package <xsc-index> --source-package <cxcy-index> --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package <jwc-index> --source-package <xsc-index> --source-package <cxcy-index> --collection apps\web\public\generated\collections\njupt-public
```
