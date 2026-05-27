# Integration Test Migration Target

This directory is the target for cross-package integration tests once packages and tools exist. It is README-only during Milestone 1 to avoid empty test structure.

Near-term migration purpose:

- hold tests that verify package/tool boundaries, generated artifact contracts, and compatibility facades across layers;
- complement existing root Python contract tests while production code is gradually moved.

Do not move current tests here until the milestone that changes the code boundary they cover.

