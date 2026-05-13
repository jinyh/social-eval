# 中国自主知识创新（法学论文）评价系统 — 项目上下文

## 快速开始

### 环境搭建

```bash
# 1. 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入必需的 API Keys（见下方"环境配置")

# 4. 启动依赖服务（PostgreSQL + Redis）
docker-compose up -d

# 5. 初始化数据库
alembic upgrade head

# 6. 启动开发服务器
uvicorn src.api.main:app --reload --port 8000
# API 文档：http://localhost:8000/docs
```

### 开发命令

```bash
# 代码检查与格式化
ruff check src/ tests/        # 检查代码规范
ruff format src/ tests/       # 自动格式化

# 运行测试
pytest                        # 运行所有测试
pytest tests/test_evaluation/ # 运行特定模块测试
pytest -v -s                  # 详细输出模式
pytest --cov=src              # 生成覆盖率报告

# 数据库迁移
alembic revision --autogenerate -m "描述"  # 创建迁移脚本
alembic upgrade head                       # 应用所有迁移
alembic downgrade -1                       # 回滚一步
alembic history                            # 查看迁移历史

# 依赖管理
uv pip install <package>      # 安装新依赖
uv pip list                   # 查看已安装依赖
uv pip freeze > requirements.txt  # 导出依赖（如需要)
```

---

## 项目简介

**中国自主知识创新（法学论文）评价系统**（SocialEval）是一套面向自主知识体系的 AI 辅助学术评价系统，以法学论文评审为切入点，支持拓展至人文社科各学科。

核心机制：多模型并发评价 → 一致性验证 → 专家复核 → 标准化报告输出

需求文档：`docs/requirements/SocialEval-requirements-v0.4.md`

---

## 架构

### 技术栈
- **后端**：Python 3.10+ (FastAPI)，依赖管理用 `uv`
- **前端**：React + TypeScript（开发中)
- **数据库**：PostgreSQL（论文/评分/审计日志)
- **缓存/队列**：Redis（任务队列)
- **任务队列**：Celery + Redis（异步评审任务)
- **AI 接入**：统一抽象层，支持 OpenAI / Anthropic / DeepSeek

### 目录结构

```
src/
  api/             # F8: RESTful API（FastAPI)
  core/            # 核心配置与工具
  evaluation/      # F3: AI 评价引擎（多模型并发)
  ingestion/       # F1: 文档摄取与预处理
  knowledge/       # F2: 知识体系配置（YAML/JSON 动态加载)
  models/          # 数据库模型（SQLAlchemy)
  reliability/     # F4: 可靠性验证层（均值/标准差/置信度)
  reporting/       # F6: 报告生成（PDF / JSON 导出)
  review/          # F5: 专家复核工作流（开发中)
  web/             # F7: Web 前端（开发中)
configs/
  frameworks/      # 各学科知识体系 YAML 配置文件
    law-v2.48-20260512.yaml # 收紧 rubric + 致命缺陷识别（当前活跃）
    law-v2.47-20260511.yaml # forward_extension 纠偏版本
    law-v2.46-20260511.yaml # v0.16 大规模评估候选
    law-v2.45-20260510.yaml # 全链路对齐基线
    archive/                 # 历史版本归档（v2.0 ~ v2.44）
docs/
  requirements/    # 需求文档
  architecture/    # ADR（架构决策记录）
  evaluation/      # 评价方法论文档
    archive/       # 历史版本归档（v0.8-v0.14）
    concept-operationalization-v1.0.md  # 概念操作化定义
    std-analysis-summary-20260423.md    # 标准差分析总结
    v0.15-phase1-test-report-20260511.md # v0.15 第一阶段测试报告
    law-ai-assisted-review-rules-v0.16-large-scale-candidate.md # 当前活跃规程
  discussion/      # 设计讨论记录
  archive/         # 临时分析文档和历史需求归档
tests/             # 测试（镜像 src/ 结构）
alembic/           # 数据库迁移脚本
scripts/           # 工具脚本
  archive/         # 归档的测试脚本（供应商测试、模型测试）
  analyze_iteration.py
  dashboard.py
  export_convergence_reports.py
  full_verify.sh / quick_verify.sh
  generate_*.py/js
  install_project_skills.py
  regression_v2.42_vs_v2.43.py
  rubric_reflector.py
  run_convergence_test.py
  run_v0.14_*.py/sh
results/           # 测试结果与评价报告
  archive/         # 归档的历史测试结果
    convergence-tests/  # v2.8-v2.31 收敛性测试
    model-tests/        # 模型对比和端到端测试
    v0.14-tests/        # v0.14 版本测试
    v0.15-tests/        # v0.15 版本测试
  autoresearch/    # 当前活跃的自动研究测试
    archive/       # 历史版本测试（v2.32-v2.40）
```

---

## 环境配置

### 必需的环境变量（`.env` 文件)

```bash
# 数据库
DATABASE_URL=postgresql://socialeval:socialeval@localhost:5432/socialeval

# Redis
REDIS_URL=redis://localhost:6379/0

# 安全
SECRET_KEY=change-me-in-production  # ⚠️ 生产环境必须修改

# AI 模型 API Keys（多模型评价必需)
OPENAI_API_KEY=sk-...        # OpenAI API 密钥
ANTHROPIC_API_KEY=sk-ant-... # Anthropic API 密钥
DEEPSEEK_API_KEY=...         # DeepSeek API 密钥（可选)

# SMTP 配置（邮件通知)
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@socialeval.local
```

### 配置说明

- **DATABASE_URL**: PostgreSQL 连接字符串，格式 `postgresql://user:password@host:port/dbname`
- **SECRET_KEY**: JWT 签名密钥，生产环境必须使用强随机字符串
- **AI API Keys**: 至少配置 2 个模型的 API Key（用于多模型并发验证)
- **SMTP**: 用于发送专家复核通知邮件，开发环境可使用 Mailtrap

---

## 常见问题（Gotchas)

### AI 模型调用
- ✅ **必须通过统一抽象层**：所有 AI 调用必须通过 `src/evaluation/providers/` 的抽象层
- ❌ **禁止直接 import SDK**：不要在业务代码中直接 `import openai` 或 `import anthropic`
- 📝 **自动持久化**：所有 AI 调用记录（输入/输出/时间戳/模型名）会自动保存到数据库

### 配置文件加载
- 📂 **动态加载**：评价框架配置从 `configs/frameworks/*.yaml` 动态加载
- 🔄 **无需重启**：修改配置后无需重启服务，下次评价时自动生效
- ✅ **Schema 验证**：配置文件必须符合 `configs/frameworks/schema_v2.json` 定义的 schema
- 🚫 **禁止硬编码**：不要在代码中硬编码评价维度，必须从配置文件读取
- 📌 **Prompt/契约真源**：评价 prompt、`output_template`、JSON 输出契约与量化映射优先以 `configs/frameworks/*.yaml` 为真源（实现层）；评审方法论、流程规则和复核条件以 `docs/evaluation/law-ai-assisted-review-rules-v0.16-large-scale-candidate.md` 为真源（规程层）。业务代码只负责渲染、适配、校验和兼容 fallback，不得新增硬编码评价口径

### 数据库迁移
- 📝 **自动生成**：修改 `src/models/` 下的模型后，运行 `alembic revision --autogenerate -m "描述"`
- ⚠️ **检查脚本**：生成后检查 `alembic/versions/` 下的迁移脚本，确认无误后再 `alembic upgrade head`
- 🔙 **可回滚**：使用 `alembic downgrade -1` 回滚上一次迁移

### 安全注意事项
- 🔒 **`.env` 不提交**：`.env` 文件已在 `.gitignore` 中，不要提交任何 API Key
- 🔐 **Token 认证**：所有 API 接口必须 Token 认证，不得暴露未鉴权端点
- 📄 **文件校验**：用户上传文件必须做类型校验（仅允许 PDF/DOCX/TXT)

### 测试相关
- 🧪 **测试结构**：测试目录镜像 `src/` 结构，如 `tests/test_evaluation/` 对应 `src/evaluation/`
- ⚡ **异步测试**：使用 `pytest-asyncio`，测试函数标记 `@pytest.mark.asyncio`
- 📊 **覆盖率**：核心业务逻辑（evaluation, knowledge, reliability）需要测试覆盖

### 评价样本目录

框架迭代样本统一放在 `raw/` 下，按用途分组，避免调参集、测试集和验证集混用：

- `raw/calibration-regression/`：校准/回归集。当前 3 篇，允许用于框架调参和回归检查；不能作为泛化有效性的证据。
- `raw/holdout-test/`：冻结测试集。当前 4 篇，用于调参后测试；运行后只允许修复明确的规则冲突、输出格式或维度错位问题，避免按单篇结果继续调 rubric。
- `raw/validation/`：最终验证集。当前 8 篇，应在规则冻结后一次性运行；验证结果用于判断是否进入下一框架版本，不应边跑边改。

使用顺序：
1. 先用 `raw/calibration-regression/` 检查新框架是否破坏既有判断。
2. 再用 `raw/holdout-test/` 做冻结测试，只修正可归因的问题。
3. 最后用 `raw/validation/` 做验证，并根据整体结果决定是否进入下一版本。

新增样本时必须先说明用途并归入明确分组；不要把已经参与调参的样本重新标记为验证集。

---

## 评价框架快速参考

### 权威真源

- **方法论规程**：`docs/evaluation/law-ai-assisted-review-rules-v0.16-large-scale-candidate.md`（四阶段流程、评分协议、复核规则、大规模评估执行规则）
- **实现框架**：`configs/frameworks/law-v2.48-20260512.yaml`（prompt、输出模板、JSON 契约、量化映射）
- **概念操作化**：`docs/evaluation/concept-operationalization-v1.0.md`
- **标准差分析**：`docs/evaluation/std-analysis-summary-20260423.md`
- **架构决策**：`docs/architecture/20260414_ADR-001_evaluation-framework-v2.md`

### 当前活跃版本

| 版本 | 状态 | 说明 |
|------|------|------|
| v2.47 | **推荐使用**（forward_extension 纠偏版本） | 修正前瞻延展性系统性低分；14 篇样本验证均值 75.7；正样本稳定性好 |
| v2.48 | ⚠️ 测试未通过（暂不推荐） | 致命缺陷识别不稳定；正负样本区分度不足（实测 7.8 分 vs 声称 19.3 分）；需要优化后重新验证 |
| v2.46 | v0.16 大规模评估候选 | 预检分层 + 信号量化 + 聚合层暴露自主信号 |
| v2.45 | 全链路对齐基线 | 代码完整消费四份契约；六维 prompt 与 v2.46 一致 |

历史版本（v2.0 ~ v2.44）见 `configs/frameworks/` 和 `configs/frameworks/archive/`。

**v2.48 测试结果**（2026-05-13，5 篇样本）：
- ✅ 正样本稳定性：3 篇正样本均值 87.9 分，波动 3.4 分
- ❌ 负样本区分度：正负样本平均差距仅 7.8 分（预期 19.3 分）
- ❌ 致命缺陷识别：不稳定（曹俊金 55 分 ✅，陈姿君 82.3 分 ❌）
- ❌ 模型分歧：负样本关键维度 std > 14（qwen 严格，glm 宽松）
- 结论：需要优化致命缺陷检测规则和引入仲裁机制后重新验证

**v2.47 推荐理由**：
- 经过 14 篇样本验证，表现稳定
- 修正了 v2.46 的前瞻延展性系统性低分问题
- 适合作为当前生产环境使用

### 四阶段流程

预检（项目口径判断）→ 六维评分（0-100）→ 自主知识体系信号校验（0-8，不入基础分）→ 评价层复核判断

### 推荐模型配置

- **主力模型**：Qwen3.6-Plus / GLM-5.1（阿里百炼平台），Temperature 0.3
- **分歧仲裁**：当单维度 std > 8 时，引入 GPT-5.5（Fucheers 提供商）作为仲裁模型
- **不推荐**：Gemini 3.1 Pro（评分波动 ±35 分）

### 可靠性阈值

- High：std ≤ 5 | Medium：5 < std ≤ 8 | Low：8 < std ≤ 12 | Critical：std > 12

---

## 开发规范

### 语言与工具
- Python 3.10+，依赖管理用 `uv`
- TypeScript（前端)，禁用 `any` 和 `@ts-ignore`
- Ruff（Python lint/format)，ESLint + Prettier（前端)

### 代码风格
- Python: 遵循 PEP 8，行长度 88（Ruff 默认)
- 类型注解: 所有公共函数必须有类型注解
- 文档字符串: 公共 API 必须有 docstring

### 关键约束
- **AI 模型调用**必须通过统一抽象层，禁止在业务层直接 import SDK
- **知识体系配置**只能通过 `configs/frameworks/` 的 YAML/JSON 文件定义，禁止硬编码维度
- **评价 prompt 与输出契约**必须优先放在 `configs/frameworks/*.yaml`：包括 `precheck.prompt_template`、`dimensions[].prompt_template`、`autonomous_knowledge_signals.prompt_template`、`output_template`、`output_contract`、`aggregate_output_contract`。代码不得把新评价口径、字段枚举或量化规则硬编码为唯一来源
- **所有 AI 调用记录**须持久化（输入/输出/时间戳/模型名），不可只存最终结果
- **API 接口**必须 Token 认证，不得暴露未鉴权端点

### 安全红线
- `.env` 必须在 `.gitignore` 中，不得提交任何 API Key
- 所有用户上传文件须做类型校验（PDF/DOCX/TXT)
- 生产环境 `SECRET_KEY` 必须使用强随机字符串

### 提交规范
- Conventional Commits：`feat:` / `fix:` / `refactor:` / `docs:`
- 每个 PR 不超过 400 行，每次 commit = 一个逻辑变更
- Commit message 必须清晰描述变更内容

---

## 已确认的决策

### 来自需求 v0.4

以下事项在需求文档中已有结论，开发时须遵守：

- **OCR 支持**：v1 默认不支持扫描版 PDF OCR；疑似扫描版需提示用户重新上传可解析版本（F1.5）
- **多模型并发数**：默认值 3，上限 5（F3.4）
- **专家通知触发条件**：进入复核队列且已完成专家指定后，自动发送邮件通知（F5.5）；编辑也可对高置信度论文手动追加复核
- **用户注册方式**：全角色邀请制，不支持开放自注册（U1.1）
- **认证方式**：Web 端使用 Session，API 调用使用 API Key（U1.3, U1.4）

### 来自标准差分析（2026-04-23）

- **推荐模型**：Qwen3.6-Plus / GLM-5.1（阿里百炼平台），Temperature 0.3
- **分歧仲裁**：单维度 std > 8 时引入 GPT-5.5（Fucheers 提供商）
- **供应商策略**：国内模型→DashScope 百炼，仲裁模型→Fucheers
- **AI 定位**：辅助初筛，不替代专家终审

详细分析见 `docs/evaluation/std-analysis-summary-20260423.md`

---

## 待澄清事项（来自需求 v0.4)

以下事项需在后续版本迭代时确认：

- [ ] 外部期刊系统接入方式、签名机制、幂等策略
- [ ] MinerU 纳入后续版本时的启用方式（自动通道 or 管理员手动启用)

---

## 参考资料

| 文件 | 说明 |
|------|------|
| `ref/法学论文的人工评价逻辑.pptx` | 法学论文人工评价方法论 |
| `ref/AI_Legal_Paper_Evaluation_System.pptx` | AI 评价系统方案演示 |
| `ref/lecture_citation_quality.pdf` | 引用质量相关学术参考 |
| `ref/【会议纪要V2】...研讨会.docx` | 专家研讨会纪要 |

---

## 项目级 Skills

项目专属 skill 统一放在 `agent-skills/`，这里是内容真源；不要分别维护 Claude/Codex 两套副本。

### 当前可用

- `socialeval-project-context`
  - 文件：`agent-skills/socialeval-project-context/SKILL.md`
  - 触发场景：在本仓库里做功能开发、修复、测试、方案设计时
  - 作用：统一加载项目背景、领域约束、目录约定与实现边界

### 使用约定

- 需要项目上下文时，优先读取对应的 `agent-skills/<name>/SKILL.md`
- 新增项目专属工作流时，在 `agent-skills/` 下新增独立目录，避免继续扩写本文件
- 若本地代理支持用户级 skill 目录，可用 `scripts/install_project_skills.py` 把仓库内 skill 软链接到本机技能目录，例如 `~/.agents/skills/`

---

## 归档管理

### 归档策略（2026-05-11 更新）

为保持项目目录清晰，历史测试结果和临时脚本已按以下规则归档：

#### 测试结果归档（results/archive/）
- **convergence-tests/**：v2.8 - v2.31 收敛性测试、诊断测试、基线测试（56 个文件）
- **model-tests/**：DeepSeek、GPT-5.4、Kimi 等模型测试、端到端管道测试、回归测试（11 个文件）
- **v0.14-tests/**：v0.14 版本批量测试、烟雾测试、分层测试（8 个文件/目录）
- **v0.15-tests/**：v0.15 版本批量测试、烟雾测试（2 个文件/目录）

#### 脚本归档（scripts/archive/）
- **model-tests/**：模型对比、诊断、稳定性测试脚本（7 个）
- **provider-tests/**：供应商诊断、配置、追踪脚本（11 个）

#### 文档归档
- **docs/evaluation/archive/v0.8-v0.14/**：法学 AI 辅助评审规则 v0.8 - v0.14 版本及专家反馈（10 个文件）
- **docs/archive/**：临时分析文档、供应商测试总结、历史需求文档
- **results/autoresearch/archive/**：快速验证测试（22 个）、v2.32-v2.40 历史版本测试（40 个）

#### 归档原则
1. **测试结果**：v2.8 - v2.40 的历史测试结果全部归档
2. **临时脚本**：供应商和模型诊断脚本归档，保留核心工具脚本
3. **文档版本**：v0.8 - v0.14 的评审规则归档，保留当前活跃版本（v0.15, v0.16）
4. **保留标准**：
   - 当前活跃版本（v0.15, v0.16, v2.45, v2.46）
   - 核心工具脚本（analyze, dashboard, export, verify, run）
   - 最终评价报告 PDF

#### 查找归档文件
```bash
# 查看归档目录结构
tree -L 2 results/archive/ scripts/archive/ docs/evaluation/archive/

# 搜索特定版本的测试结果
find results/archive/ -name "*v2.30*"

# 搜索特定模型的测试脚本
find scripts/archive/ -name "*deepseek*"
```
