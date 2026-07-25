# SocialEval 项目执行指南

本文件只规定代理在本项目中的工作方式、不可破坏约束和权威真源。系统背景、
历史实验、数据成果与归档说明见
[项目上下文](docs/project-context.md)。

## 开始工作前

- 先检查 `git status --short`，保留用户未提交的改动；不要回滚、覆盖或清理无关文件。
- 先读与任务直接相关的代码、配置和文档；能从仓库验证的事实不要反问用户。
- 默认推进到可验证闭环：实现最小必要改动、运行相称检查、说明结果和剩余风险。
- 未公开论文、真实审稿意见、逐篇模型输出、API Key 与 `.env` 均按敏感信息处理。

### 项目文档入口

- [系统与成果上下文](docs/project-context.md)：架构、评价方法、历史实验、数据集与归档。
- [主系统需求 v0.4](docs/requirements/SocialEval-requirements-v0.4.md)。
- [编辑辅助预审设计索引](docs/editorial/README.md)：当前活文档入口。
- [编辑辅助预审需求 v1.1](docs/requirements/editorial-pre-review-requirements-v1.1.md)。
- [法学 AI 辅助评审规程 v0.17](docs/evaluation/law-ai-assisted-review-rules-v0.17.md)。
- [概念操作化定义](docs/evaluation/concept-operationalization-v1.0.md)。
- [评价框架 ADR](docs/architecture/20260414_ADR-001_evaluation-framework-v2.md)。

## 快速开始

```bash
uv sync --extra dev
cp .env.example .env
docker compose up -d
uv run alembic upgrade head
uv run uvicorn src.api.main:app --reload --port 8000
```

使用 `.env.example` 作为环境变量清单；不得在文档、日志、提交或回复中输出真实凭据。
生产环境 `SECRET_KEY` 必须使用强随机值。

### 常用验证命令

```bash
uv lock --check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pytest
uv run pytest tests/test_evaluation/
uv run pytest --cov=src
```

只在用户要求或改动范围确有需要时运行会改写文件的格式化命令：

```bash
uv run ruff format src/ tests/
```

### 数据库迁移

```bash
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic history
```

生成迁移后必须人工检查 `alembic/versions/`，确认升级和降级路径正确。

## 架构索引

```text
src/
  api/             FastAPI 接口
  core/            配置与公共工具
  evaluation/      六维、五轴与多模型评价引擎
  ingestion/       PDF/DOCX/TXT/Markdown 摄取
  knowledge/       知识体系配置加载
  models/          SQLAlchemy 模型
  reliability/     一致性与置信度
  reporting/       评分与报告输出
  review/          专家复核流程
  web/             Web 相关后端
configs/
  frameworks/      评价 Prompt、输出契约与框架配置
  scoring/         评分协议
frontend/          React + TypeScript 前端
tests/             与 src/ 对应的测试
```

编辑辅助预审在本项目内扩展，业务代码放入 `src/editorial/`；当前阶段以法学稿件、
编辑预审为主，不能把尚未确认的作者端或其他学科能力当作已实现功能。

## 权威真源与当前版本

- 方法论与复核规则：
  `docs/evaluation/law-ai-assisted-review-rules-v0.17.md`。
- 六维 R1 生产 Prompt：
  `configs/frameworks/law-v2.56.6-20260522.yaml`。
- 六维 R2 交叉评审：
  `configs/frameworks/law-v2.55-cross-review.yaml`。
- Prompt、`output_template`、JSON 契约和量化映射：
  `configs/frameworks/*.yaml`，并符合 `configs/frameworks/schema_v2.json`。
- 总分实现：`src/reporting/scoring.py` 的 `calculate_weighted_total()`。
- CCB 协议：`configs/scoring/core-ceiling-bonus-v0.8.yaml`。
- 结果登记：`results/catalog.yaml`。

评价维度、字段枚举、量化规则和新评价口径不得在业务代码中硬编码为唯一来源。
代码只负责配置加载、渲染、适配、校验和兼容 fallback。

## 不可破坏约束

### AI 调用

- 所有模型调用必须经过 `src/evaluation/providers/` 统一抽象层；业务代码不得直接
  `import openai`、`anthropic` 等供应商 SDK。
- `raw/label/`、未发表投稿和真实审稿意见不得发送给 Web Search、Firecrawl、
  浏览器/普通连接器或无审计的外部工具；经授权的模型评审仍须通过上述 providers
  抽象层，并按本节要求持久化调用记录。
- 每次调用均须持久化输入、原始输出、时间戳、模型、供应商与失败信息；不能只存最终分数。
- R2 后单维度 `std > 8` 表示需要专家复核，不得自动用仲裁模型覆盖真实学术分歧。
- v2.55 R2 机制已经冻结；不要用 `autoresearch` 继续调整 R2 Prompt。

### API、认证与上传

- 业务 API 必须执行 Token/Session/API Key 认证；只有显式登记的健康检查等公开端点可例外。
- Web 端使用 Session，API 调用使用 API Key；用户采用邀请制，不开放自注册。
- 上传文件必须校验类型和可解析性；当前允许 PDF、DOCX、TXT，已有 Markdown 数据通道按
  现有实现处理。
- v1 不提供扫描 PDF OCR；疑似扫描件应提示重新上传可解析版本。

### 数据与样本

- `.env` 必须保持在 `.gitignore` 中；不得提交 API Key。
- `raw/label/` 的真实审稿意见只作本地评估基准和格式参考，不进入 Git。
- 校准、冻结测试、最终验证三组样本不得混用：
  `raw/calibration-regression/` → `raw/holdout-test/` → `raw/validation/`。
- 已参与调参的样本不得重新标记为最终验证集；新增样本必须先声明用途。
- 多模型并发默认 3，上限 5。

## Paper ID 映射红线

三大刊论文 ID 的唯一权威元数据是：
`results/datasets/three-journals/metadata.csv` 的 `编号` 字段。

- 不得从缓存、中间文件或文件排序重新生成 Paper ID。
- 六维逐篇结果路径：
  `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-{id}.json`。
- E2 候选池真源：`results/rankings/e2-ccb-v5/ranking.json`。
- 交大法学数据使用独立的 ID 1–642，真源为
  `results/datasets/jiaodafaxue/metadata.json`，不得与三大刊 ID 混用。

分析特定论文时，至少用权威元数据交叉核对 ID、题目和年份。

## 开发规范

- Python 3.10+，依赖管理使用 `uv`；遵循 `uv.lock`。
- Python 使用 Ruff，行长 88；公共函数必须有类型注解和 docstring。
- 前端使用 React + TypeScript，禁止 `any` 和 `@ts-ignore`；使用 ESLint + Prettier。
- 测试目录镜像 `src/`；异步测试使用 `pytest-asyncio`。
- 核心逻辑，尤其 `evaluation`、`knowledge`、`reliability` 和新增的 `editorial`，
  应有相称的自动化测试。
- 修改数据库模型时生成并检查 Alembic 迁移，不能只修改 ORM。
- Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`。
- 每个 commit 只包含一个逻辑变更；PR 原则上不超过 400 行，较大功能按可验证阶段拆分。

## 已冻结的项目决策

- AI 定位是辅助初筛，不替代编辑或专家终审。
- 六维与五轴相互独立；五轴不与六维加总。
- CCB 使用核心四维、学术共识度封顶和前瞻延展性弱加分。
- Phase 2 全量 1920 篇评审已经完成；历史逐篇原始数据不得因重构被删除。
- DeepSeek 在 R2 中保持严格锚定属于预期模型行为，不作为需要“修复”的缺陷。
- 未收敛分歧交由专家复核；不得通过增加同模型轮次伪造一致性。
- 外部期刊接入的签名、幂等策略和 MinerU 启用方式仍未确定，实施前需回到需求层确认。

详细依据、指标和结果位置见
[项目上下文](docs/project-context.md)。

## 项目级 Skills

项目专属 Skill 的唯一内容真源是 `agent-skills/`，当前仅：

- `expert-audit-report`：将单篇论文六维、五轴和 E2 数据整理为专家审计报告；
  由 Claude Code 在本项目内使用，不注册为全局 Codex Skill。

`scripts/install_project_skills.py` 扫描 `agent-skills/*/SKILL.md`，默认软链接到
本仓库 `.claude/skills/`。如确需其他引擎或目录，显式传入可重复的
`--target-dir`；不要分别维护多份内容副本。

`.agents/skills/` 是本地忽略的第三方/全局 Skill 区，不属于项目真源。
`autoresearch` 仅是 v2.56.6 R1 锚定规则迭代的历史工具，当前不主动安装；
除非用户明确启动新的框架迭代，否则不要使用。

## 归档边界

- `archive/`、`docs/**/archive/`、`results/**/archive/`、逐篇 AI 输出和原始语料为本地忽略内容。
- 当前 Git 只维护活跃代码、配置、规程、必要元数据、结果摘要和可复现脚本。
- 历史制品位于仓库同级
  `../SocialEval-archive/2026-07-16-deep-clean/`，清单包含原路径、字节数和 SHA-256。
- 不得因为文件被忽略就擅自删除、移动或重建本地归档与原始数据。
