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

```powershell
uv run python -m njupt_search_eval run-cache-benchmark --collection apps\web\public\generated\collections\njupt-public
```

`run-cache-benchmark` runs each query cold, then repeats it against the same in-process content-hash artifact cache. It fails if a warm repeat changes the top result, loses exhaustive coverage, or performs any uncached immutable artifact reads.

```powershell
node --import tsx tools\search-eval\scripts\benchmarkPackedDecoder.mjs --build-wasm --collection apps\web\public\generated\collections\njupt-public --runs 5 --output tools\search-eval\reports\njupt-search-wasm-decision.json --markdown tools\search-eval\reports\njupt-search-wasm-decision.md
```

`benchmarkPackedDecoder.mjs` builds the Rust/WASM packed impact decoder and compares it with the TypeScript runtime decoder on the generated packed body-index artifacts. The output is consumed by the lower-bound report as the Rust/WASM decision evidence.

```powershell
uv run python -m njupt_search_eval run-lower-bound-report --collection apps\web\public\generated\collections\njupt-public --output docs\reports\njupt-search-lower-bound-report.json --markdown docs\reports\njupt-search-lower-bound-report.md
```

`run-lower-bound-report` compares the current generated collection with a git baseline ref, measures byte deltas, JSON parse/decode costs, deterministic query telemetry, cold/warm cache behavior, attachment evidence semantics, and DoD audit status. It is an evidence report, not a final completion claim.
