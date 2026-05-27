# ADR 0009: Terminal Generated Layout Only

## Status

Accepted

## Context

The terminal architecture now requires a clean top-tier layout with only generated artifact entrypoints under `apps/web/public/generated`.

## Decision

Generated runtime artifacts are served only from:

```text
apps/web/public/generated/collections/njupt-public/
apps/web/public/generated/exam/
```

The old root `public/`, `/index/*`, `/data/*`, and root `scripts/` entrypoints are removed. Tooling must use the packaged Python modules under `tools/*`.

## Consequences

- Existing production URLs for generated data change to `/generated/...`.
- Browser acceptance and GitHub Actions must prove that the new paths load without manifest, artifact, shard, or exam data 404s.
- Quality gates fail if obsolete generated artifact directories reappear.
