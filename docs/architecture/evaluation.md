# Evaluation

Production non-exam search is evaluated as Progressive Verifiable Static Search over the JWC sitegraph package.

```powershell
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```

The gate verifies:

- quick phase returns results for every representative query;
- body index can be loaded after quick results;
- candidate full shards can be hydrated and ranked;
- shard filter proves no-match shards can be skipped;
- scan fallback covers shards that cannot be proved no-match;
- verification reaches `coverage.exhaustive_complete=true`;
- final coverage has proved or scanned every shard declared by manifest;
- expected title, facet, nav path, URL, and score reason are present.

Representative queries:

```text
校历、慕课考试、期末考试、转专业、规章制度、办事流程、学生相关文件及表格、教务管理系统、大创、推免、成绩、附件1、xlsx
```

`tests/test_sitegraph_contract.py` additionally proves upstream count parity, hash artifact paths, manifest coverage declarations, required full-shard fields, and absence of stale fixed-name artifacts.
