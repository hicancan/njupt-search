# njupt-search

`njupt-search` 是南邮本科生教务搜索和考试查询静态应用。当前生产架构是 Progressive Verifiable Static Search：快速结果先返回，后台继续扩大覆盖，最终证明 JWC 全量公开索引已核查完成。

[在线使用](https://njupt.hicancan.top)

## 项目定位

生产数据路径只有两条：

1. JWC 公开搜索：只消费 `njupt-site-graph` 已审计的 JWC sitegraph 包，生成 hash-addressed 静态索引，由浏览器 Worker 执行纯代码搜索。
2. 考试垂直频道：生成 `apps/web/public/generated/exam/all_exams.json` 和 `apps/web/public/generated/exam/data_summary.json`，支持班级考试查询、课程选择和 `.ics` 日历导出。

非考试搜索不运行其他校园源、不调用模型、不保留任务框架或固定索引文件。

## Progressive Search

```text
njupt-site-graph/data/sites/jwc/index
-> python -m njupt_search_indexer build
-> apps/web/public/generated/collections/njupt-public/manifest.json
-> apps/web/public/generated/collections/njupt-public/sitegraph/jwc/artifacts/*.json
-> apps/web/public/generated/collections/njupt-public/sitegraph/jwc/shards/full.*.<hash>.json
-> apps/web/src/features/collection-search/worker/collectionSearch.worker.ts
-> React UI
```

`manifest.json` 是唯一稳定入口。大 JSON 均使用内容 hash 命名；首屏只加载 `doc_meta_light`、`light_inverted_index` 和 `query_aliases`。搜索阶段：

1. `quick_started` / `quick_results`：用 `light_inverted_index` 召回并返回快速结果。
2. `body_started` / `body_results`：加载 `body_inverted_index` 补充摘要和正文召回。
3. `hydrate_started` / `hydrate_results`：加载候选 full shards 精排。
4. `verify_started` / `verify_progress` / `verify_results` / `exhaustive_complete`：用 shard filter 证明无命中的分片并跳过；不能证明的 full shards 扫描 `title`、`section`、`nav_path`、`summary`、`content`、`attachments`、`url`，增量合并并稳定重排。

每个事件都带 coverage：`phase`、`searched_fields`、`proved_no_match_shards`、`scanned_shards`、`total_shards`、`searched_documents`、`total_documents`、`loaded_bytes`、`used_body_index`、`exhaustive_complete`。只有全部 full shards 被证明跳过或实际扫描后才允许 `exhaustive_complete=true`。

## Index Contract

manifest 声明：

- `progressive_search.full_scan_supported=true`
- `progressive_search.progressive_events=true`
- `progressive_search.total_shards`
- `progressive_search.total_documents`
- `progressive_search.artifact_roles`
- `coverage_contract.coverage_fields`
- `verification_contract.shard_filter_supported=true`

必需 artifacts：`doc_meta_light`、`light_inverted_index`、`body_inverted_index`、`shard_catalog`、`shard_filter`、`outcomes`、`size_report`，以及 `sitegraph.full_shards` 下的 hash-addressed full shard 列表。

full shards 必须包含全量核查字段：`title`、`url`、`section`、`nav_path`、`summary`、`content`、`attachments`、`record_type`、`facet`、`published_at`、`provenance`。

`size_report` 记录 `first_screen_bytes`、`body_index_bytes`、`full_scan_total_bytes`、`shard_count`、`max_shard_bytes`、`avg_shard_bytes` 和 `representative_query_phase_timings`。

## 本地开发

```powershell
npm ci
npm run dev
```

完整验证：

```powershell
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --skip-output
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --out apps\web\public\generated\collections\njupt-public
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --collection apps\web\public\generated\collections\njupt-public
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_no_obsolete_fields.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
uv run python -m pytest
npm test
npm run typecheck
npm run lint
npm run build
```

代表查询覆盖：校历、慕课考试、期末考试、转专业、规章制度、办事流程、学生相关文件及表格、教务管理系统、大创、推免、成绩、附件1、xlsx。

## 自动更新

`.github/workflows/update-exam-data.yml` 更新考试数据，`.github/workflows/update-collection-index.yml` 消费 JWC sitegraph 包并生成 `apps/web/public/generated/collections/njupt-public`。`ci.yml`、`validate-generated-artifacts.yml` 和 `deploy-web.yml` 分别负责通用检查、生成物质量门和 GitHub Pages 部署。

## 目录

```text
apps/web/               # React/Vite/PWA 前端与 Worker
apps/web/public/generated/exam/
apps/web/public/generated/collections/njupt-public/
tools/                  # collection indexer、exam pipeline、search eval、quality gates
tests/                  # Python sitegraph contract tests
```

## License

[AGPL-3.0](LICENSE)
