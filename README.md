# njupt-search

<div align="center">

<img src="public/assets/logo.png" height="80" alt="njupt-search logo" />

**南邮学生事务的源审计、任务理解、混合检索与静态信息入口。**

[在线使用](https://njupt.hicancan.top) · [报告 Bug](https://github.com/hicancan/njupt-search/issues)

</div>

## 项目定位

`njupt-search` 不是普通公告聚合站，也不是单纯考试查询工具。当前主架构是 HyTask-RAG：Hybrid Student Task Retrieval-Augmented Graph。

```text
Source-Channel Graph
-> Canonical Document
-> Rule Guard
-> LLM/Heuristic Semantic Result
-> Semantic Verifier
-> TaskFrame
-> Hybrid Index
-> Query Understanding
-> Hybrid Retrieval
-> Student Utility Ranking
-> Product UI
-> Self Evaluation
-> Static Deploy
```

考试查询保留为 `exam_vertical` 垂直频道：输入班级号可查看期末考试安排、勾选课程并导出 `.ics` 日历。公告、通知、就业、图书馆、后勤、保卫、档案、体育、国际交流、学院通知和 GitHub 学习资料进入统一搜索。

## 主配置

生产主链路只使用 Source-Channel Graph：

```text
config/source_channels.json
```

每个 source 可以包含多个 channel。channel 是抓取、审计、过滤和排序的基本单位。`campus_sources.json` 不再作为运行主链路。

辅助配置：

```text
config/query_aliases.json
config/ontology.json
config/search_contract.json
config/github_search_sources.json
```

生成索引：

```text
public/index/documents.json
public/index/task_frames.json
public/index/query_aliases.json
public/index/ontology.json
public/index/manifest.json
```

考试数据：

```text
public/data/all_exams.json
public/data/data_summary.json
```

## HyTask-RAG 组件

- Source-Channel Graph：记录公开源站、栏目、学生价值、预期领域/意图、选择器、分页、风险和关键词。
- Canonical Document：统一 URL、正文、附件、发布时间、hash、dedupe key、source_id 和 channel_id。
- Rule Guard：在 LLM 前检测 restricted、sensitive、low_evidence、duplicate、expired、evergreen、附件风险和行政噪声。
- Semantic Verifier：在写入 SearchDocument 前移除未由原文或附件元数据支撑的 deadline、action、materials、location/contact 和 TaskFrame 字段。
- TaskFrame：把通知建模为学生任务，包含对象、任务、动作、截止、材料、地点、证据、风险和置信度。
- Notice Card / Typed Terms：离线把公开原文和证据抽取为通知卡片、typed_search_terms、synonyms、objects、actions、deadlines、materials、locations、attachments 和 risk。
- Search Contract：`config/search_contract.json` 约束 kind、category、domain、intent、source_type、lifecycle、semantic_mode 和 TaskFrame 枚举，生产验证严格失败。
- Query Aliases：把“保研/推免”“大创”“校园网”等学生自然语言映射到领域、意图和语义扩展。
- Query Intent Router: 识别查询模式并将其路由到特定垂类意图（如考试查询、资源搜索、事务通知等）。
- Recall Search：搜索阶段只用查询、同义词、路由阻断和离线结构化字段做候选召回；命中候选严格按 `published_at` 倒序展示，不做语义排序或权重重排。
- Self Evaluation：`scripts/eval/eval_frontend_search.ts` 先生成浏览器真实 TypeScript top-5，`scripts/eval/eval_product_search.py --mode both` 以 frontend 结果作为产品真相，同时报告 Python 召回结果；`scripts/eval/eval_search_parity.py --ts-results ...` 量化 Python/TS drift。

## 安全边界

- 只抓公开网页和公开接口。
- 不登录学校系统。
- 不绕过校园网或统一身份认证限制。
- restricted 页面不生成具体任务。
- sensitive 页面不向 LLM 发送敏感正文，不展示敏感正文片段。
- LLM/规则输出不是事实源；deadline、action、materials 和 TaskFrame 必须经过 deterministic verifier。
- API key 只来自环境变量或 GitHub Actions secrets，不写入仓库。
- 本项目为非官方工具，请以官网原文为准。

## 本地开发

需要 Node.js >= 20，Windows 建议 PowerShell 7。

```powershell
npm ci
npm run dev
```

质量检查：

```powershell
npm run lint
npm test
npm run typecheck
npm run build
```

Python 依赖：

```powershell
uv pip install -r requirements.txt
```

更新考试数据：

```powershell
uv run python scripts\auto_update_exam_data.py
uv run python scripts\analyze_and_update.py
```

更新 HyTask-RAG 搜索索引：

```powershell
uv run python scripts\update_search_index.py
```

常用参数：

```powershell
uv run python scripts\update_search_index.py --dry-run --no-llm
uv run python scripts\update_search_index.py --source jwc --force-llm --limit 20
uv run python scripts\update_search_index.py --llm-provider deepseek --llm-batch-size 32
uv run python scripts\update_search_index.py --no-github
```

校验与自评：

```powershell
uv run python scripts\utils\validate_search_index.py
uv run python scripts\utils\validate_query_routes.py
uv run python scripts\eval\eval_search.py --write-report
uv run python scripts\eval\query_smoke_test.py
& .\node_modules\.bin\tsx.ps1 --tsconfig tsconfig.app.json scripts\eval\eval_frontend_search.ts --out eval\reports\ts_search_results.json
uv run python scripts\eval\eval_product_search.py --mode both --ts-results eval\reports\ts_search_results.json
uv run python scripts\eval\eval_search_parity.py --ts-results eval\reports\ts_search_results.json
```

Search Quality v1.3 使用 `strict_pass / data_gap / fail` 三类状态。`data_gap` 只表示 Source-Channel 覆盖证明当前索引不能回答该 query，不计入 strict pass。当前 durable gold map 在 `eval/queries/search_gold.json`，可执行 gate 在 `eval/search_cases.json`。

## 自动更新

`.github/workflows/auto-update.yml` 每 6 小时更新考试数据、公开校园索引和 GitHub 资料源，并运行索引契约、产品搜索和 Python/TypeScript parity 校验。workflow inputs 以 shell array 传递；LLM cache 只有在 `commit_llm_cache=true` 时才提交。`.github/workflows/deploy.yml` 负责 lint、test、build 与 GitHub Pages 部署。

LLM 增强只在离线索引构建阶段运行。未配置 Key 时使用规则抽取，不影响静态搜索可用性。

可选环境变量：

```powershell
$env:DEEPSEEK_API_KEY="..."
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
$env:GEMINI_API_KEYS="key1,key2,key3"
$env:NJUPT_SEARCH_GITHUB_TOKEN="..."
```

## 项目结构

```text
config/                 # source-channel graph, ontology, aliases, contract
docs/architecture/      # HyTask-RAG, contract, recall, eval, source adapters
docs/operations/        # update/deploy runbook
docs/source-audit/      # Chrome DevTools MCP 公开源审计
docs/product/           # 产品冻结报告
eval/                   # 自动 query 集与报告
public/data/            # 考试垂直频道数据
public/index/           # 静态 HyTask-RAG 索引
scripts/core/           # Rule Guard, tokenizer, query expansion, task extraction
scripts/models/         # CanonicalDocument, SourceGraph, TaskFrame, search contract
scripts/eval/           # eval_search and query smoke tests
src/                    # React/Vite/PWA 前端
```

## License

[AGPL-3.0](LICENSE)
