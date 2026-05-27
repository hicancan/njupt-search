# Review Checklist

Use this checklist before reporting a milestone.

## Scope

- The work matches the active milestone only.
- No later milestone was started before acceptance.
- User-visible behavior is preserved unless an ADR explicitly records a change.
- No production code was moved during Milestone 0.
- No empty target directories were created.

## Boundaries

- Upstream source discovery, crawling, modeling, configs, and audit notes were not moved into this repo.
- Production non-exam search remains static, browser-side, and Worker-driven.
- The product abstraction is moving toward `collection`, not hard-coded single-site ownership.
- Exam remains a product vertical.
- Legacy LLM/task-framework production concepts were not reintroduced.
- Generated artifacts were not manually edited.

## Verification

- Required local commands were run or explicitly blocked with evidence.
- Browser acceptance was run when the milestone touched browser behavior or public URLs.
- GitHub Actions/cloud CI was checked when required, or exact human action needed was recorded.
- The milestone report lists files changed, risks, rollback notes, and next recommended milestone.

## Documentation

- New architecture docs describe actual repository state and target boundaries.
- ADRs explain decisions and consequences.
- Commands use explicit inputs and outputs where possible.
- Canonical representative queries are referenced from the goal instead of duplicated into independent source lists.
