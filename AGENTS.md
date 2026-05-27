# AGENTS.md

## Repository Role

`njupt-search` is the downstream public search product in the three-repository ecosystem:

```text
static-site-graph -> njupt-site-graph -> njupt-search
```

This repository consumes audited source packages and generated exam data, compiles browser runtime artifacts, and owns the React/PWA user experience. It must not absorb upstream crawling, source discovery, or source-truth audit ownership from `static-site-graph` or `njupt-site-graph`.

## Current Milestone Discipline

Follow `docs/goals/njupt-search-terminal-goal.md` milestone by milestone.

- Do not start a later milestone until the current milestone has been reported and accepted.
- Preserve user-visible behavior unless an ADR explicitly records the behavior change; the generated artifact URL migration is now ADR-recorded and uses only the terminal `generated` layout.
- Do not mark a milestone complete unless the required local checks, browser acceptance, and GitHub Actions/cloud CI checks pass or are explicitly blocked with evidence.
- Do not create empty target directories for architecture appearance only.
- Do not add a Codex GitHub Action, Codex review workflow, or `.github/codex/prompts`.

## Product Boundaries

- Use `collection` as the product abstraction. Current production may compile only JWC, but target contracts must allow `collection_id: njupt-public` with multiple future source packages.
- Keep source packages separate from vertical product experiences. `jwc` is a source package; `exam` is a product vertical.
- Production non-exam search remains audited source package -> collection compiler -> hash-addressed static artifacts -> browser Worker progressive static search -> React/PWA UI.
- Do not reintroduce LLM search, task-frame search, provider fields, server-side runtime search, or obsolete semantic production fields.
- Generated JSON artifacts are compiled runtime data. Update generators or source inputs; do not manually edit generated artifacts.

## Local Commands

Use PowerShell commands from the repository root.

```powershell
npm test
npm run typecheck
npm run build
npm run lint
uv run python -m pytest
```

Current generated-artifact quality commands:

```powershell
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --skip-output
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package <path-to-njupt-site-graph-jwc-index> --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package <path-to-njupt-site-graph-jwc-index> --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```

## Browser Acceptance

Run browser acceptance for milestones touching routing, React pages, search UI, exam UI/data, Worker behavior, public paths, PWA caching, generated artifact layout, deployment output, or final acceptance.

Minimum queries:

```text
校历
期末考试
教务管理系统
学生相关文件及表格
xlsx
```

Use the full canonical representative query list from `docs/goals/njupt-search-terminal-goal.md` for smoke tests and docs updates. Do not duplicate it independently in production code.
