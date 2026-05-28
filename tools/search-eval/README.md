# Search Eval

This tool owns deterministic representative query evaluation.

Near-term migration purpose:

- validate progressive search recall, bounded candidate hydration, coverage, and exhaustive verification for generated collection artifacts.
- report candidate shard cost separately from loaded/scanned shards, because exhaustive verification may load many shards to prove complete coverage.

```powershell
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```

```powershell
uv run python -m njupt_search_eval run-task-queries --collection apps\web\public\generated\collections\njupt-public
```

`run-task-queries` validates the data-backed student task matrix in `queries/expected_results.json`, including routed exam-vertical class queries such as `B250403`.
