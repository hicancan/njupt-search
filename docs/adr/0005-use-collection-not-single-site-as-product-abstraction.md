# ADR 0005: Use Collection, Not Single Site, As Product Abstraction

## Status

Accepted.

## Context

Current production compiles the JWC sitegraph package, but the product must be able to consume future audited NJUPT source packages.

## Decision

Use collection-level language and contracts:

```text
collection_id: njupt-public
sources:
  - jwc
  - future audited source packages
```

Keep source packages separate from product verticals. `exam` is a structured product vertical, not a `sitegraph` source.

## Consequences

- The collection compiler replaces single-site mental models over time.
- Current JWC behavior remains compatible while contracts prepare for additional sources.
- UI and docs should not hard-code the terminal architecture as JWC-only.

