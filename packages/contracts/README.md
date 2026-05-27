# Contracts Package Migration Target

This directory is the Milestone 2 target for runtime and generated-artifact contracts. It is README-only until contracts are moved with compatibility re-exports and tests.

Near-term migration purpose:

- own exam data contracts currently in `src/utils/examDataContract.ts` and shared types currently in `src/types/index.ts`;
- own source-sitegraph input contracts, search collection manifests, and search index artifact contracts;
- provide a stable package boundary used by the web app, search core, exam core, tools, tests, and quality gates.

Milestone 2 must keep current imports working while contract consumers are migrated.

