# ADR 0008: Cloud CI Is Required For Final Acceptance

## Status

Accepted.

## Context

The terminal architecture must be valid in a clean runner, not only on a developer machine with cached dependencies, generated files, and sibling repositories.

## Decision

Final acceptance requires deterministic GitHub Actions/cloud CI to pass or an evidence-backed blocker report when cloud access is unavailable.

Required final workflows are documented in `docs/architecture/ci-cd-acceptance.md`.

## Consequences

- Local checks cannot prove final completion by themselves.
- Deployment must remain gated by validation.
- Update workflows must separate exam and collection-index failures.
- Android release workflow remains supported unless an ADR explicitly changes it.
