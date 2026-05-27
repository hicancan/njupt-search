# Progressive Verifiable Static Search

The browser search path has one non-exam source: the audited JWC sitegraph package from `njupt-site-graph`.

## Data Flow

```text
JWC sitegraph package
-> tools/collection-indexer
-> apps/web/public/generated/collections/njupt-public/manifest.json
-> hash artifacts
-> Search Worker event stream
-> React display
```

## Artifacts

- `manifest.json`: stable entrypoint and contract.
- `doc_meta_light`: lightweight metadata for first-screen recall.
- `light_inverted_index`: title, section, nav path, tag, attachment, external, and system postings.
- `body_inverted_index`: summary and content postings.
- `shard_catalog`: per-shard id, hash path, byte size, count, facet, section, year, and record-type ranges.
- `shard_filter`: Bloom-style proof data for proving that a query cannot match a shard before full-field scanning.
- `full.*.<hash>.json`: full shards used for candidate hydration and exhaustive verification.
- `outcomes`: upstream URL outcome summary used to audit source coverage.
- `size_report`: first-screen bytes, body bytes, full scan bytes, shard sizes, and representative phase timings.

## Worker Events

```text
quick_started
quick_results
body_started
body_results
hydrate_started
hydrate_results
verify_started
verify_progress
verify_results
exhaustive_complete
cancelled
error
```

Every event includes coverage:

```json
{
  "phase": "verify_progress",
  "searched_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
  "proved_no_match_shards": 320,
  "scanned_shards": 120,
  "total_shards": 481,
  "searched_documents": 1880,
  "total_documents": 7534,
  "loaded_bytes": 18350000,
  "used_body_index": true,
  "exhaustive_complete": false
}
```

`exhaustive_complete=true` is proof that every manifest full shard has either been proved no-match by `shard_filter` or scanned for the declared coverage fields.
