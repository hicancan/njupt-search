# ADR 0007: Browser Acceptance Is Required

## Status

Accepted.

## Context

Many important product requirements are browser/runtime behaviors: Worker loading, progressive search events, public artifact URLs, PWA caching, URL query state, responsive layout, and exam data loading.

## Decision

Require browser acceptance for milestones that touch browser-facing behavior, public URLs, generated artifact layout, deployment output, or final acceptance.

Use the report template in `docs/architecture/testing-strategy.md`.

## Consequences

- Unit tests and builds are necessary but not sufficient for browser-facing milestones.
- Console errors, network 404s, Worker readiness, progressive phases, coverage display, mobile viewport, and desktop viewport are explicit evidence.
- Milestones that only update architecture docs can record browser acceptance as not required.

