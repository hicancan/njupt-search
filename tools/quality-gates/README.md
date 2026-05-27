# Quality Gates Tool Migration Target

This directory is the Milestone 9 target for deterministic generated-artifact and contract gates. It is README-only until current validation scripts are moved.

Near-term migration purpose:

- own generated artifact validation currently in `scripts/utils/validate_search_index.py`;
- own legacy-field rejection and public artifact size checks as explicit gates;
- keep deployment blocked when generated artifacts or contracts fail validation.

Quality gates must remain deterministic and must not depend on Codex or other AI review workflows.

