# Small-Model Distillation Readiness

This directory documents the next phase only. The current v1 product freeze does not train, download, or connect a Hugging Face model.

The distillation substrate is produced by the static HyTask-RAG pipeline:

- `public/index/documents.json`: canonical, rule-guarded search documents;
- `public/index/task_frames.json`: student task frames with evidence and risk;
- `public/index/documents.json` notice cards, typed search terms, synonyms, materials, locations, attachments, and risk fields;
- `public/index/query_aliases.json`: student query expansion;
- `eval/reports/latest.json`: automatic search/evaluation report;
- `scripts/eval/query_smoke_test.py`: product-level query gate.

Do not start small-model training until:

- source-channel graph is stable;
- CI-equivalent checks pass;
- query smoke passes;
- evidence coverage is acceptable without fabricated evidence;
- the user explicitly starts the small-model phase.
