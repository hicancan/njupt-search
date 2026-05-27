# Exam Pipeline

This tool fetches exam spreadsheets and transforms them into generated exam artifacts.

Near-term migration purpose:

- generate exam artifacts under `apps/web/public/generated/exam`;
- keep generated exam data separate from collection source packages.

The exam vertical is a product experience, not a sitegraph source.

```powershell
uv run python -m njupt_exam_pipeline run
```
