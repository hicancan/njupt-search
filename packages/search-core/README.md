# Search Core

This package owns the browser-safe progressive static search runtime extracted in Milestone 3.

Current responsibilities:

- tokenizer and query alias expansion;
- generated sitegraph/search-index contract parsing;
- retrieval and ranking;
- full-shard loading and hydration;
- shard-filter proof and scan fallback;
- progressive search phases and coverage accounting;
- non-React result formatting.

`src/utils/searchIndex.ts` remains as a temporary compatibility facade until imports are migrated in later milestones. The current Worker protocol and user-visible search behavior must stay compatible while this package becomes the runtime owner.

Package checks:

```powershell
node ./node_modules/typescript/bin/tsc -p packages/search-core/tsconfig.json --noEmit
node ./node_modules/vitest/vitest.mjs run packages/search-core/tests/searchIndex.test.ts
```
