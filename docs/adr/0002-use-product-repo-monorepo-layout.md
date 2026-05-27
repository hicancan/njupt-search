# ADR 0002: Use Product Repository Monorepo Layout

## Status

Accepted.

## Context

The current flat layout mixes React UI, browser search runtime, exam logic, Python generation tools, generated artifacts, and tests.

## Decision

Migrate toward a product monorepo layout:

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
```

Introduce directories only when they contain useful migrated code, tests, config, scoped instructions, or documentation tied to the active milestone.

## Consequences

- Package boundaries become explicit and testable.
- The web app remains the only browser product.
- Early empty architecture directories are avoided.

