# NJUPT Search Rust/WASM Retrieval Decision

- Generated at: `2026-06-01T07:10:51.619Z`
- Artifact count: `246`
- Packed body bytes: `16,850,611`
- Runs: `5`

## Results

| Path | Mean ms | Min ms | Max ms |
| --- | ---: | ---: | ---: |
| TypeScript runtime decoder to JS object | 645.327 | 609.692 | 737.170 |
| Rust/WASM decode to JSON string, then JS parse | 685.090 | 677.183 | 702.058 |
| Rust/WASM stats-only decode lower bound | 43.046 | 37.650 | 46.110 |
| TypeScript selective retrieval kernel | 3360.691 | 3307.103 | 3422.653 |
| Rust/WASM stateless retrieval kernel | 470.565 | 442.374 | 518.326 |
| Rust/WASM stateful retrieval session | 587.936 | 537.360 | 626.321 |
| Rust/WASM stateful retrieval with score bridge | 587.416 | 574.691 | 597.751 |

## Decision

- Status: `rust_wasm_retrieval_runtime_selected`
- Winner for current runtime: `wasm_retrieval_session_scores_bridge`
- WASM materialized path ratio vs TypeScript: `1.062x`
- WASM stats-only lower-bound ratio vs TypeScript: `0.067x`
- WASM stateful retrieval ratio vs TypeScript retrieval kernel: `0.175x`
- WASM stateful score bridge ratio vs TypeScript retrieval kernel: `0.175x`
- Reason: The browser runtime can consume Rust/WASM stateful score entries directly. On the full packed body workload, the Rust/WASM session score bridge was 0.175x the TypeScript selective retrieval kernel for the same artifact format, query set, and global top-k pruning state.

## Reproduction

```powershell
node --import tsx tools\search-eval\scripts\benchmarkPackedDecoder.mjs --build-wasm --collection apps\web\public\generated\collections\njupt-public --runs 5 --output docs\reports\njupt-search-wasm-decision.json --markdown docs\reports\njupt-search-wasm-decision.md
```
