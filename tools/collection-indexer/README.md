# Collection Indexer Tool Migration Target

This directory is the Milestone 7 target for the collection compiler. It is README-only until current sitegraph build and validation logic is packaged.

Near-term migration purpose:

- move from the current JWC-oriented scripts toward an explicit collection compiler;
- consume audited source package paths through CLI arguments instead of implicit sibling paths;
- produce generated collection runtime artifacts for `collection_id: njupt-public`;
- preserve current generated artifact compatibility until the public URL migration is complete.

Initial target CLI shape:

```powershell
python -m njupt_search_indexer build --collection-id njupt-public --source-kind sitegraph --source-package <path> --out apps/web/public/generated/collections/njupt-public
```

