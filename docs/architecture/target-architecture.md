# Target Architecture

## Mission

`njupt-search` becomes a downstream product repository with explicit app, package, tool, test, documentation, and CI/CD boundaries.

The terminal data path is:

```text
audited source packages from njupt-site-graph
-> tools/collection-indexer
-> generated collection runtime artifacts
-> packages/search-core browser runtime
-> apps/web React/PWA product
-> browser acceptance
-> GitHub Actions/cloud CI/CD validation
```

## Repository Layers

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
docs/architecture
docs/adr
docs/goals
.github/workflows
```

Directories are introduced only when they contain migrated production code, migrated tests, immediately used config, scoped instructions, or useful README documentation.

## Ownership Boundaries

### `apps/web`

Owns the browser product:

- React/PWA composition.
- Routing and URL query state.
- Home and results pages.
- Search box, app shell, update notifier, coverage display, and responsive UI.
- Worker loading and browser integration.
- Generated static assets served to users.

### `packages/contracts`

Owns shared TypeScript runtime contracts and generated artifact schemas:

- exam data contracts;
- source-sitegraph input contracts;
- collection manifest contracts;
- search index artifact contracts;
- generated JSON schema where useful.

### `packages/search-core`

Owns browser-safe non-exam search logic:

- tokenization and normalization;
- retrieval and ranking;
- shard catalog/filter logic;
- progressive search phase orchestration;
- coverage and verification;
- result formatting that is not React-specific.

### `packages/exam-core`

Owns pure exam-domain logic:

- exam model and contract validation helpers;
- class/course search;
- exam schedule grouping;
- calendar export logic.

### `tools/collection-indexer`

Owns the collection compiler. It consumes explicit source package paths and writes explicit output paths. The target CLI shape is:

```powershell
python -m njupt_search_indexer build --collection-id njupt-public --source-kind sitegraph --source-package <path> --out apps/web/public/generated/collections/njupt-public
```

### `tools/exam-pipeline`

Owns exam data acquisition and transformation into generated exam artifacts.

### `tools/search-eval`

Owns representative query smoke tests and evaluation fixtures.

### `tools/quality-gates`

Owns deterministic artifact and contract gates such as legacy-field rejection, generated artifact size checks, and public artifact validation.

## Collection Abstraction

The product abstraction is a collection, not a single site:

```text
collection_id: njupt-public
sources:
  - jwc
  - future audited source packages
```

Sources are origin packages. Verticals are product experiences. `exam` is a vertical, not a `sitegraph` source.

## Compatibility Strategy

The migration must preserve current public URLs until browser acceptance and CI prove a replacement layout is safe:

```text
public/data/*
public/index/manifest.json
public/index/sitegraph/jwc/artifacts/*
public/index/sitegraph/jwc/shards/*
```

The target generated layout is introduced alongside legacy URLs before any removal:

```text
apps/web/public/generated/collections/njupt-public/
apps/web/public/generated/exam/
```

