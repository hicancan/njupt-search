# CI/CD Acceptance

## Current Workflows

The current workflow set is:

```text
.github/workflows/auto-update.yml
.github/workflows/deploy.yml
.github/workflows/build-apk.yml
```

`auto-update.yml` updates exam data, consumes the JWC package from `njupt-site-graph`, rebuilds generated search artifacts, validates generated artifacts, runs representative query smoke tests, runs Python tests, and runs frontend checks.

`deploy.yml` builds and deploys the Vite app to GitHub Pages after successful pushes or successful auto-update runs.

`build-apk.yml` preserves Android release compatibility for tag/manual releases.

## Target Workflows

The terminal workflow set is:

```text
ci.yml
update-exam-data.yml
update-collection-index.yml
validate-generated-artifacts.yml
deploy-web.yml
release-android.yml
```

Do not add a Codex workflow or AI review workflow.

## Required Pull Request Gates

Pull requests must run deterministic checks:

- clean Node dependency install;
- clean Python dependency install;
- TypeScript tests;
- typecheck;
- frontend build;
- Python tests;
- generated artifact validation;
- representative query smoke tests;
- browser/e2e smoke if configured.

## Required Main/Release Gates

Pushes to `main` must prevent deployment if validation fails. Generated artifact validation must complete before deploy.

Scheduled or manual update workflows must separate exam update failures from collection-index failures, so source ownership and rollback are clear.

Release or tag workflows must preserve Android APK/AAB release compatibility unless an ADR explicitly retires Android.

## Cloud CI Evidence

For a milestone that requires GitHub Actions/cloud CI, acceptable evidence is:

- successful named workflow run on the relevant commit; or
- an exact blocker report listing workflow names, expected success criteria, local commands already run, and what remains unverified.

Local checks alone are not final acceptance for the terminal goal.

