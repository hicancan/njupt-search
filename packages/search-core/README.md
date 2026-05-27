# Search Core

This package owns the browser-safe progressive static search runtime.

Current responsibilities:

- tokenizer and query alias expansion;
- generated sitegraph/search-index contract parsing;
- retrieval and ranking;
- full-shard loading and hydration;
- shard-filter proof and scan fallback;
- progressive search phases and coverage accounting;
- non-React result formatting.

The web app imports this runtime through `apps/web/src/features/collection-search`.

Package checks:

```powershell
node ./node_modules/typescript/bin/tsc -p packages/search-core/tsconfig.json --noEmit
node ./node_modules/vitest/vitest.mjs run packages/search-core/tests/searchIndex.test.ts
```
