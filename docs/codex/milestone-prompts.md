# Milestone Prompts

Use these prompts to continue the terminal migration without compressing the objective into a smaller task.

## General Continuation

```text
/goal Execute docs/goals/njupt-search-terminal-goal.md. Work milestone by milestone. Preserve user-visible behavior. Do not mark any milestone complete unless the required local checks, browser acceptance, and GitHub Actions/cloud CI checks pass or are explicitly blocked with evidence.
```

## Milestone 0

```text
Complete Milestone 0 only. Create or update AGENTS.md, the canonical terminal goal, architecture docs, ADRs, and Codex review docs. Do not move production code. Run the local checks appropriate for documentation-only work and report using the required milestone format.
```

## Milestone 1

```text
Complete Milestone 1 only. Add useful skeleton directories only where they contain immediately useful README, config, tests, or scoped instructions. Do not create empty theater directories. Preserve user-visible behavior.
```

## Milestone 2

```text
Complete Milestone 2 only. Extract contracts into packages/contracts with compatibility re-exports until imports are migrated. Add contract tests. Verify npm test, typecheck, and build.
```

## Milestone 3

```text
Complete Milestone 3 only. Extract browser-safe search logic into packages/search-core. Keep src/utils/searchIndex.ts as a temporary facade. Verify tokenizer, ranking, coverage, shard filter, progressive search, Worker behavior, and representative query smoke tests.
```

## Milestone Report

Every milestone report must use the format in `docs/goals/njupt-search-terminal-goal.md`.

