# HyTask-RAG v1.0 Product Freeze

Status: in progress until the current CI/evaluation run proves the generated artifacts.

## Freeze Criteria

- `config/source_channels.json` is the production source graph.
- `channel_count >= 60` and `production_channel_count >= 50`.
- P0 sources are split into task-oriented channels.
- P1 sources have audited or probed production skeletons.
- `public/index/` contains documents with notice cards and typed search terms, task frames, aliases, ontology, and manifest.
- Frontend renders source, channel, domain, intent, lifecycle, task frames, action, deadline, materials, evidence, risk, and score reason.
- Query smoke test covers the 25 required student queries.
- CI-equivalent commands pass locally.

## Product Principles

- Official public-source notices are recalled when their original text, notice card, typed terms, aliases, or TaskFrame fields match the query.
- GitHub and learning resources are useful supplements, not replacements for official notices.
- Restricted pages are metadata-only and do not generate concrete tasks.
- Sensitive pages do not expose sensitive body text.
- Search must not return a full unfiltered list for a no-match query.
- Every recalled item should have a concise recall reason.
- The product must display: `本项目为非官方工具，请以官网原文为准。`

## Current v1 Scope

Included:

- Source-Channel Graph;
- CanonicalDocument;
- RuleGuard;
- LLM/Rule TaskFrame;
- Notice cards, typed search terms, synonyms, and TaskFrames;
- Query aliases and ontology;
- route-aware recall with strict chronological display;
- static React/Vite UI;
- exam vertical channel;
- evaluation and query smoke scripts;
- GitHub Pages / Cloudflare deployment path.

Excluded:

- small-model training;
- Hugging Face integration;
- user login;
- database service;
- long-running backend;
- private or restricted school systems;
- non-public APIs.

## Dataset Freeze Readiness

Small-model distillation can begin only after:

- `eval/reports/latest.json` is generated from the v1 artifacts;
- query smoke passes;
- evidence coverage is reported honestly;
- source audits and channel graph are stable enough to avoid moving-label churn.
