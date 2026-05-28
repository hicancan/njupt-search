<div align="center">

# 🔍 njupt-search

**Progressive Verifiable Static Search**

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-blue.svg)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React-19.2-61DAFB.svg)](https://react.dev/)
[![Python](https://img.shields.io/badge/Python-3.10+-FFD43B.svg)](https://www.python.org/)

南邮本科生教务信息与考试查询的 Serverless 静态搜索引擎。<br>
彻底摒弃传统后端数据库，将检索算力下放至浏览器端，实现 **0成本、免运维、毫秒级响应、全离线可用** 的极致搜索体验。

🌍 **[在线体验 (njupt.hicancan.top)](https://njupt.hicancan.top)**

</div>

---

## ✨ 核心特性

- ⚡️ **Progressive Search (渐进式搜索引擎)**
  首屏仅下载极轻量的局部倒排索引 (`light_inverted_index`) 瞬间命中标题；后台 Web Worker 静默加载完整哈希分片 (Full Shards) 补全正文深度扫描。快与深，二者兼得。
- 📱 **Offline-First & PWA**
  深度集成的 Progressive Web App。核心索引一旦被浏览器缓存，即便是**断网/弱网环境**下，依然可以快速查考表、查文件。
- 🛡️ **Zero-Cost Serverless (零成本与免运维)**
  全量数据通过 CI 构建为高度优化的静态 JSON 树，直接托管于静态 CDN。没有 MySQL，没有 ElasticSearch，将服务器成本永远降至 0。
- 🧩 **Web Worker 计算隔离**
  前端基于 React 19 + Vite 7 构建，所有高负荷的文本扫描、分词合并与相关性重排均在独立 Worker 线程执行，保障主线程 UI (60 FPS) 丝滑流畅。
- 🔐 **Strict Index Contract (严格的索引契约)**
  依托 Python 工具链提供强大的静态检查：从源头数据审计到哈希校验，再加上 `quality-gates`（质量门禁）和端到端搜索评估 (`search-eval`)，确保呈现给学生的每一条结果都准确无误。

## 🏗️ 架构与数据流 (Architecture)

项目作为 `njupt-site-graph` (上游爬虫与真相源) 的下游应用，形成了极度克制的单向数据流：

```text
[上游: njupt-site-graph] (提供已审计的源数据包)
         │
         ▼
[Python Indexer] (离线编译)
 uv run python -m njupt_search_indexer build
         │
         ├──> manifest.json (稳定入口声明)
         ├──> light_inverted_index.json (首屏极速召回)
         └──> full.*.<hash>.json (静态全文分片)
         │
         ▼
[CDN / Github Pages] (静态资源分发)
         │
         ▼
[浏览器 React + Web Worker] (渐进式加载与计算)
 执行阶段: quick_results -> body_results -> hydrate_results -> verify -> exhaustive_complete
```

## 📦 项目目录结构 (Monorepo)

本项目采用 NPM Workspaces + Python `uv` 混合 Monorepo 管理，边界清晰：

```text
njupt-search/
├── apps/web/               # React 19 / Vite / Tailwind 纯前端应用与 Web Worker
├── packages/               # TypeScript 公共逻辑库
│   ├── contracts/          # 静态资源的 Schema 与接口契约
│   ├── exam-core/          # 考试日历、结构解析核心逻辑
│   └── search-core/        # 浏览器端搜索执行引擎
├── tools/                  # Python 离线数据管道 (uv 管理)
│   ├── collection-indexer/ # 将源数据编译为浏览器可用的 Hash Shards
│   ├── exam-pipeline/      # 考试数据构建流水线
│   ├── quality-gates/      # 索引体积与结构质量门禁
│   └── search-eval/        # 搜索结果评估与回归测试
├── android/                # 基于 Trusted Web Activity (TWA) 封装的原生安卓客户端
└── tests/                  # Python 核心逻辑测试
```

## 🚀 本地开发指南

### 1. 启动前端 UI

确保本地已安装 Node.js (>=20) 并启用 NPM Workspaces。

```powershell
npm ci
npm run dev
```

### 2. 完整的数据构建与校验流程

本项目使用 `uv` 管理 Python 依赖 (`pyproject.toml` + `uv.lock`)，不使用传统的 `requirements.txt`。请在根目录执行以下 PowerShell 指令进行完整的数据校验：

```powershell
# 1. 验证上游数据源
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --skip-output

# 2. 编译并生成前端静态索引 (Collection)
uv run python -m njupt_search_indexer build --collection-id njupt-public --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --out apps\web\public\generated\collections\njupt-public

# 3. 验证生成的产物
uv run python -m njupt_search_indexer validate --source-package D:\code\github\hicancan\njupt-site-graph\data\sites\jwc\index --collection apps\web\public\generated\collections\njupt-public

# 4. 质量门禁检查 (索引体积与结构规范)
uv run python tools\quality-gates\scripts\validate_search_index.py
uv run python tools\quality-gates\scripts\check_public_artifact_sizes.py

# 5. 回归与评估测试 (Smoke Queries)
uv run python -m njupt_search_eval run-smoke-queries --collection apps\web\public\generated\collections\njupt-public
```
> **Smoke Queries 代表性测试词：**
> 校历、慕课考试、期末考试、转专业、规章制度、办事流程、学生相关文件及表格、教务管理系统、大创、推免、成绩、附件1、xlsx。

### 3. 代码质量与格式化

```powershell
uv run python -m pytest   # Python 单元测试
npm test                  # TS/JS 单元测试 (Vitest)
npm run typecheck         # TS 类型检查
npm run lint              # ESLint 代码规范
npm run build             # 前端生产环境构建
```

## 🤖 自动化工作流 (CI/CD)

通过 GitHub Actions 实现全自动化更新：
- `.github/workflows/update-exam-data.yml`: 考试数据更新流。
- `.github/workflows/update-collection-index.yml`: 消费 `njupt-site-graph` 源数据，生成最新静态索引。
- `.github/workflows/validate-generated-artifacts.yml`: 执行 Quality Gates。
- `.github/workflows/deploy-web.yml`: 构建并发布至 GitHub Pages。

## 📄 License

本项目基于 [AGPL-3.0 License](LICENSE) 协议开源。
