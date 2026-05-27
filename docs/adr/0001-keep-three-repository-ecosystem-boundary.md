# ADR 0001: Keep Three-Repository Ecosystem Boundary

## Status

Accepted.

## Context

The search product depends on audited source data, but source discovery, crawling, site modeling, and audit notes belong upstream.

## Decision

Keep the ecosystem boundary:

```text
static-site-graph -> njupt-site-graph -> njupt-search
```

`njupt-search` consumes explicit source packages and generated artifacts. It does not own crawler internals, upstream site configs, or upstream source-truth audit notes.

## Consequences

- Cross-repository integration is expressed through schemas, manifests, CLI arguments, tests, quality gates, and CI.
- Local sibling paths may be used for current developer commands, but must not become the final contract.
- Refactors in this repository must not import upstream internals as product code.
