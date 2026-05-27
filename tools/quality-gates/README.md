# Quality Gates

This directory owns deterministic generated-artifact and contract gates.

Near-term migration purpose:

- own obsolete-field rejection and public artifact size checks as explicit gates;
- keep deployment blocked when generated artifacts or contracts fail validation.

Quality gates must remain deterministic and must not depend on Codex or other AI review workflows.

```powershell
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
```
