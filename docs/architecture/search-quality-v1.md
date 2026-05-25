# Search Quality v1 Architecture

## Overview

Search Quality v1.3 validates a static recall architecture. Offline indexing preserves public-source text and extracts evidence-backed notice cards, typed search terms, synonyms, TaskFrames, materials, locations, attachments, and risk fields. Runtime search only recalls route-valid candidates and displays matches by `published_at` descending.

## Key Components

1. **Query Router v2.1**
   - Uses explicit route evidence to infer broad query type, target domains/intents, blockers, and required terms.
   - Routes decide candidate eligibility. They do not assign display rank.

2. **Source Coverage Gates**
   - Checks critical source/channel coverage such as `jwc_exam` and `xsc_scholarship`.
   - Statuses like `warning_filtered_all` explain why a channel might have zero documents while preserving data-gap accounting.

3. **Offline Evidence Extraction**
   - `documents.json` carries original text, evidence, `notice_card`, `typed_search_terms`, `synonyms`, and TaskFrame data.
   - Semantic verifier removes ungrounded deadline/action/material/location fields before data reaches the frontend.

4. **Frontend-as-Truth Gate**
   - `eval_frontend_search.ts` runs the same TypeScript recall path used by the browser.
   - `eval_product_search.py --mode both` reports Python and frontend pass/fail fields, but blocks on frontend results.
   - `eval_search_parity.py --ts-results ...` quantifies Python/TS recall drift.

5. **Data Gap Classification**
   - Search cases can declare `coverage_channels`.
   - If those channels are empty, filtered out, or contain no relevant public document for the query terms, the case is `data_gap` instead of a false strict pass.

## Current Claim Boundary

v1.3 does not claim dense retrieval, BM25, cross-encoder reranking, learning-to-rank, click feedback, online personalization, or semantic ranking. It claims frontend-real candidate recall, strict chronological display, and explicit data-gap accounting.
