# NJUPT Search Rust/WASM Decoder Decision

- Generated at: `2026-06-01T03:52:59.270Z`
- Artifact count: `246`
- Packed body bytes: `16,850,611`
- Runs: `5`

## Results

| Path | Mean ms | Min ms | Max ms |
| --- | ---: | ---: | ---: |
| TypeScript runtime decoder to JS object | 636.351 | 602.181 | 688.527 |
| Rust/WASM decode to JSON string, then JS parse | 689.802 | 659.382 | 705.837 |
| Rust/WASM stats-only decode lower bound | 39.948 | 37.004 | 42.998 |

## Decision

- Status: `typescript_better_for_current_runtime`
- Winner for current runtime: `typescript_runtime_decoder`
- WASM materialized path ratio vs TypeScript: `1.084x`
- WASM stats-only lower-bound ratio vs TypeScript: `0.063x`
- Reason: The current browser runtime consumes a JavaScript SitegraphLocalBodyIndex object. On the full packed body workload, Rust/WASM decode plus JSON bridge was 1.084x the TypeScript decoder, so replacing only the decoder would increase current runtime decode cost. The stats-only WASM path is recorded as a lower-bound signal for a future full WASM retrieval core that avoids JS object materialization.

## Reproduction

```powershell
node --import tsx tools\search-eval\scripts\benchmarkPackedDecoder.mjs --build-wasm --collection apps\web\public\generated\collections\njupt-public --runs 5 --output docs\reports\njupt-search-wasm-decision.json --markdown docs\reports\njupt-search-wasm-decision.md
```
