# HyTask-RAG Architecture

HyTask-RAG is the njupt-search v1 architecture before small-model training:

```text
公开网站集合
-> Source-Channel Graph
-> CanonicalDocument
-> RuleGuard
-> LLM/Rule SemanticResult
-> Semantic Verifier
-> TaskFrame
-> NoticeCard / TypedSearchTerms
-> Query Understanding
-> Candidate Recall
-> Chronological Display
-> Product UI
-> Self Evaluation
-> Static Deploy
```

## Source-Channel Graph

`config/source_channels.json` is the production graph. A source is an authority origin; a channel is the audited crawl and coverage unit. Runtime code does not use `campus_sources.json` as a main path.

Channel fields include:

- `list_urls`;
- `student_value`;
- `expected_domains`;
- `expected_intents`;
- `priority`;
- `crawl_depth`;
- `pagination`;
- `selectors`;
- `sensitive_risks`;
- `positive_keywords`;
- `negative_keywords`.

The v1 freeze target is source_count >= 30 and channel_count >= 60.

## CanonicalDocument

`scripts/models/canonical_document.py` normalizes raw crawler output into a stable document contract:

- canonical URL;
- clean text;
- attachments;
- published_at;
- content_hash;
- dedupe_key;
- source_id;
- channel_id.

All LLM and retrieval stages consume the canonicalized shape.

## RuleGuard

`scripts/core/rule_guard.py` runs before LLM. It decides whether a document may be sent to LLM and whether full text may be displayed.

Guard outputs include:

- `restricted`;
- `sensitive`;
- `low_evidence`;
- `duplicate`;
- `expired`;
- `evergreen`;
- `risk_flags`;
- `allow_llm`;
- `allow_full_text_display`;
- `review_required`.

Restricted pages do not generate TaskFrames. Sensitive pages do not expose sensitive body text.

## Semantic Verifier

`scripts/core/semantic_verifier.py` is the deterministic gate between LLM/heuristic semantic extraction and production SearchDocument output.

It removes or downgrades:

- deadlines without date/deadline evidence;
- student actions that are not grounded in source text;
- department-only actions incorrectly interpreted as student tasks;
- required materials not present in source text or attachment metadata;
- TaskFrame deadlines/actions/materials/location/contact that are not grounded;
- all concrete TaskFrames for restricted, sensitive, low-evidence, or LLM-disallowed documents.

Removal counts are written into document `semantic_verifier` metadata and summarized in the manifest on the next indexing run.

## TaskFrame

`scripts/models/task_frame.py` and `scripts/core/task_extractor.py` convert documents into student task frames:

- who: audience, college, grade, major, class_name;
- what;
- action: required, verb, object, summary;
- time: published_at, deadline, lifecycle, urgency_days;
- materials;
- location;
- source;
- evidence;
- risk;
- confidence.

Evidence must be grounded in extracted page text, attachment names, or trusted structured data. Missing fields stay null/empty and reviewable.

## Notice Cards And Recall

`scripts/update_search_index.py` writes notice cards, typed search terms, synonyms, TaskFrame fields, materials, locations, attachments, evidence, and risk directly into `public/index/documents.json`.

Runtime search does not build a BM25 or hybrid index. Python and TypeScript both perform candidate recall from the same document fields and route rules, then display recalled candidates by `published_at` descending. `score = 1` is retained only as a result-card compatibility field.

## Query Understanding

`config/query_aliases.json` maps student language to canonical aliases, target domains, target intents, and semantic queries. Examples:

- 保研 -> 推免 / 推荐免试 / 免试研究生;
- 大创 -> 大学生创新创业训练计划 / 创新创业项目申报;
- 校园网 -> VPN / 统一身份认证 / 邮箱 / 信息化.

## Static Artifacts

The deployable frontend consumes:

```text
public/index/documents.json
public/index/task_frames.json
public/index/query_aliases.json
public/index/ontology.json
public/index/manifest.json
public/data/all_exams.json
```

No long-running backend is required.

## Evaluation

Automated checks:

- `scripts/utils/validate_search_index.py`: schema, safety, source/channel counts, manifest invariants;
- `scripts/eval/eval_search.py`: P@5, R@10, MRR@10, NDCG@10 and artifact statistics;
- `scripts/eval/query_smoke_test.py`: product-level query checks for official priority, exam channel, no-match behavior, risk hints, and score reasons.

## Safety Boundaries

- no login;
- no campus-network bypass;
- no non-public API scraping;
- no private chat ingestion;
- no sensitive body text sent to LLM;
- API keys stay in environment variables or Actions secrets;
- always keep the non-official disclaimer visible in the product.
