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
    law-v2.56.6-20260522.yaml   # Phase 2 Round 1 生产 prompt（六维锚定规则）
    law-v2.55-cross-review.yaml # 交叉评审版本（Round 2 用）
    law-v2.50.2-20260514.yaml   # 嵌入评分步骤（历史基线）
docs/
  requirements/    # 需求文档
  architecture/    # ADR（架构决策记录）
  evaluation/      # 评价方法论文档
    concept-operationalization-v1.0.md  # 概念操作化定义
    v0.15-phase1-test-report-20260511.md # v0.15 第一阶段测试报告
    law-ai-assisted-review-rules-v0.17.md # 当前活跃规程
  discussion/      # 设计讨论记录
tests/             # 测试（镜像 src/ 结构）
alembic/           # 数据库迁移脚本
scripts/           # 工具脚本
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
  fullevaluation/  # Phase 2 全量评审结果
  e2-pool/         # E2 候选池（ranking/Top50/评测数据 round1+round2）
  report_*.json/csv # 当前报告统计派生文件
  autoresearch/    # 当前活跃的自动研究测试
```

> 归档目录（如 `archive/`、`docs/**/archive/`、`results/**/archive/`、`scripts/archive/`、`configs/frameworks/archive/`）只作为本地保留区使用，已被 `.gitignore` 忽略，不再作为仓库内容维护。

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
- 📌 **Prompt/契约真源**：评价 prompt、`output_template`、JSON 输出契约与量化映射优先以 `configs/frameworks/*.yaml` 为真源（实现层）；评审方法论、流程规则和复核条件以 `docs/evaluation/law-ai-assisted-review-rules-v0.17.md` 为真源（规程层）。业务代码只负责渲染、适配、校验和兼容 fallback，不得新增硬编码评价口径

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

### Paper ID 映射（关键数据源）

**⚠️ 警告**：项目中存在多个 Paper ID 映射文件，使用不当会导致分析错误。

**权威数据源**：
- ✅ `results/datasets/three-journals/metadata.csv`（1920 条）：论文元数据（标题、期刊、年份、作者等），**这是权威来源**
- ✅ `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-{id}.json`（1920 个文件）：评审结果，ID 与 CSV 一致
- ✅ `results/rankings/e2-ccb-v5/ranking.json`（105 条）：E2 候选池真源；五轴≥9 且 E1(core_ceiling_bonus)≥80，Top80 + 学科保底 max(5,Top50配额) + 年≥5；E1 候选选取与 E2 重排名均用 core_ceiling_bonus

**常见错误**：
- ❌ **错误示例**：使用错误的 ID 映射导致 paper-1238（"债权人代位权的类型化构造"，2024年）的分数被标到"党政体制如何塑造基层执法"（paper-1244，2017年）上
- ❌ **根因**：从中间文件、缓存或手动构建的映射表中读取 ID，导致 +1~+7 的偏移
- ✅ **正确做法**：始终从 `results/datasets/three-journals/metadata.csv` 读取 `编号` 字段作为 Paper ID，不要从其他来源构建映射

**验证方法**：
```bash
# 检查特定论文的 ID 和标题
python3 -c "
import csv
with open('results/datasets/three-journals/metadata.csv', 'r', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        if '党政体制' in row['题目']:
            print(f\"ID={row['编号']}, 年份={row['年份']}, 标题={row['题目']}\")
"
```

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

- `raw/fullpaper/`：全量评审集。当前 1920 篇 PDF，用于 Phase 2 大规模评审。元数据见 `results/datasets/three-journals/metadata.csv`（1920 条记录，列：期刊/年份/卷/期/题目/作者/作者机构/页数/主题词）。

---

## 评价框架快速参考

### 权威真源

- **方法论规程**：`docs/evaluation/law-ai-assisted-review-rules-v0.17.md`（六维 R1/R2、五轴、CCB、复核与审计规则）
- **实现框架**：`configs/frameworks/law-v2.56.6-20260522.yaml`（Phase 2 Round 1 生产 prompt、输出模板、JSON 契约、量化映射）
- **概念操作化**：`docs/evaluation/concept-operationalization-v1.0.md`
- **架构决策**：`docs/architecture/20260414_ADR-001_evaluation-framework-v2.md`

### 当前活跃版本

| 版本 | 状态 | 说明 |
|------|------|------|
| v2.50.2 | 嵌入评分步骤（历史基线） | 负样本均值 76.1；正样本 91.1；正负差距 15.0；识别率 44% |
| v2.55 | 交叉评审版本（Round 2 用） | 基于 v2.50.2，维度命名已更新为标准命名 |
| v2.56.6 | **Phase 2 Round 1 生产 prompt** | v2.56 + 6 轮锚定规则优化，std 28.16→6.22（-77.9%） |

历史版本（v1.0 ~ v2.54）保留在本地忽略归档区，不进入 Git。

**维度命名更新**（2026-05-22）：
- 统一六维度中文名称：研究创新性、现状洞察度、理论建构力、逻辑连贯性、学术共识度、前瞻延展性
- v2.50.2 和 v2.55 已更新为标准命名
- 历史版本归档前已同步更新 v2.47、v2.52、v2.53、v2.54 的命名

**v2.56 Prompt 语义对齐**（2026-05-22）：
- ❌ **问题诊断**：v2.55 维度 name_zh 已更新，但 prompt_template 仍使用旧名称（问题创新性、分析框架建构力、逻辑严密性、结论可接受性）
- ✅ **修复内容**：
  1. 研究创新性（原：问题创新性）：扩展评价范围，不只看问题，还看方法、材料、理论贡献
  2. 现状洞察度：保持不变
  3. 理论建构力（原：分析框架建构力）：扩展评价范围，不只看框架可操作性，还看理论体系完整性
  4. 逻辑连贯性（原：逻辑严密性）：调整评价标准，从"无漏洞"改为"前后一致、论证流畅"
  5. 学术共识度（原：结论可接受性）：保持不变
  6. 前瞻延展性：保持不变

**v2.56.6 锚定规则迭代**（2026-05-22，autoresearch 6 轮）：
- ✅ 每轮针对 std 最高的维度添加强制锚定规则（针对法哲学/理论型论文）
- ✅ 迭代路径：AF→PO→LI→LC→CC→FE，逐维度收敛
- ✅ 最终结果：整体 avg std 6.22（从 28.16 降低 77.9%）
- ✅ Holdout 验证通过（iter1h: 13.59 ≈ 13.57，无过拟合）
- 📋 **定位**：Phase 2 Round 1 生产 prompt
- 📋 **文件**：`configs/frameworks/law-v2.56.6-20260522.yaml`

**v2.51 Phase 0 失败总结**（2026-05-15 ~ 2026-05-17）：
- ❌ Stage A 负面模式检测器无法达到生产要求（命中率 22% vs 目标 70%，误报率 50% vs 目标 10%）
- ❌ Pattern 定义过于抽象，AI 无法区分"正常学术表述"和"空泛表述"
- ❌ 短 prompt 无法提供足够上下文判断论证质量
- 📋 详细报告：`docs/evaluation/v2.51-phase0-failure-report.md`
- 📋 建议：暂停 Phase 0，重新设计 pattern 定义（基于可观察指标，避免依赖论证质量判断）

**v2.50.2 测试结果**（2026-05-14，9 篇负样本 + 1 篇正样本）：
- ✅ 正样本稳定性：蒋红珍 91.1 分（未误伤）
- ✅ 有效识别（< 75）：邵莉莉 68.6、杨清望 63.5、李姝卉 69.4、张涛 74.7
- ⚠️ 边界样本（75-80）：娄金炜 75.8、伍德志 77.3、崔聪聪 79.0
- ❌ 未识别（> 80）：李雪 86.8、包晓丽 89.4
- ✅ 正负样本差距：91.1 - 76.1 = 15.0 分（全部负样本）；91.1 - 69.1 = 22.0 分（有效识别的 4 篇）
- 结论：问题创新性维度扣分制有效；分析框架/结论维度仍是优化瓶颈

**v2.50.x 迭代经验**（2026-05-14）：
- ❌ ceiling_rules 路线失败：AI 倾向于宽松解释触发条件（v2.49，0% 触发率）
- ✅ 前置扣分对问题创新性有效：权重 0.3，是主要降分来源
- ⚠️ 分析框架/结论维度的扣分指令被长 prompt 淹没：无论放在开头、中间还是锚定表中，AI 仍按既有评分标准给分
- 📋 下一步方向：缩短 prompt 长度、简化评分标准、或重构分析框架维度的评分流程

**v2.50.2 设计要点**：
- 基于 v2.47（生产推荐版本）
- 问题创新性：前置扣分指令（3 个检查项，扣 15-30 分）
- 分析框架：将负面模式检测嵌入"第一步：框架可操作性检查"的评分流程
- 结论可接受性：将负面模式检测嵌入"轨道A/B"的评分流程
- 使用量化标准减少 AI 主观判断空间

**v2.47 推荐理由**：
- 经过 14 篇样本验证，表现稳定
- 修正了 v2.46 的前瞻延展性系统性低分问题
- 适合作为当前生产环境使用

### 四阶段流程

预检（项目口径判断）→ 六维评分（0-100）→ 自主知识体系信号校验（0-8，不入基础分）→ 评价层复核判断

### 总分计算公式（final_score）

`final_score = min(base + bonus, ceiling)`

- **base**（基础分）：核心四维加权平均 = (研究创新性×0.3 + 现状洞察度×0.2 + 理论建构力×0.15 + 逻辑连贯性×0.2) / 0.85
- **ceiling**（学术共识度封顶）：<60→最高65；60-74→最高75；≥75→不限
- **bonus**（前瞻延展性加分）：0-5分，前提：逻辑连贯性≥60、学术共识度≥60、核心四维均≥50
- 实现真源：`src/reporting/scoring.py` → `calculate_weighted_total()`

### 五轴位置归属度评价

独立于六维质量评价的"中国法学自主知识体系位置归属度"结构化评估（v0.2）：

- **五轴**：对象归属度、材料归属度、范畴自主度、解释目标归属度、体系映射度
- **量尺**：每轴 0-2 分，总分 0-10（0=无证据，1=局部证据，2=核心结构证据）
- **强度分档**：strong=8-10，medium=5-7，weak=2-4，absent=0-1
- **不与六维加总**：只用于候选分层、专家复核优先级、知识体系覆盖分析
- **方法论真源**：`docs/evaluation/autonomous-knowledge-system-position-assessment-v0.2.md`
- **旧四信号**（中国问题中心性/中国实践解释/外部理论转化/可复核概念）降级为兼容字段，不再作为位置归属度主结构

**两轮评估流程（R1→R2）**：
- R1：deepseek-v4-pro + qwen3.6-plus 独立五轴评估
- R2 按分歧条件触发：skip（完全一致，~33%）、light（路径/节点分歧，~45%）、full（轴分/置信度分歧，~23%）
- 历史 Top101 实测：R1 两模型平均总分差 0.53，严重分歧（≥4）仅 4%；R2 实际触发率 67%
- 实现脚本：
  - Top101 兼容入口：`scripts/evaluate_top101_position_assessment_two_rounds.py`；共用实现位于 `src/evaluation/position/`
  - 交大法学期刊：`scripts/evaluate_jiaodafaxue_position.py`（311 篇 final_score > 55，R1+R2）

**交大法学期刊评估**：
- 原始论文：`raw/jiaodafaxue/`（642 篇 .md 文件，期刊：交大法学）
- 论文列表：`results/datasets/jiaodafaxue/metadata.json`（ID 1-642，独立于三大刊元数据）
- 六维评审：`results/datasets/jiaodafaxue/six-dimension/phase2-r2-v2.55/per-paper/paper-{id}.json`（642 篇已完成）
- 五轴评估输出：`results/datasets/jiaodafaxue/five-axis/position-v0.2/`
- 分数阈值可调：`--min-score 55`（默认，311 篇）、`--min-score 60`（280 篇）、`--min-score 70`（175 篇）

### 推荐模型配置

- **主力模型**：Qwen3.6-Plus / GLM-5.1（阿里百炼平台），Temperature 0.3
- **分歧处理**：六维 R2 后单维度 std > 8 时进入专家复核，不自动调用 GPT 仲裁
- **不推荐**：Gemini 3.1 Pro（评分波动 ±35 分）

### 可靠性阈值

- High：std ≤ 5 | Medium：5 < std ≤ 8 | Low：8 < std ≤ 12 | Critical：std > 12

### Phase 2 测试结果（10 篇，2026-05-22）

**测试配置**：
- 框架：v2.55（交叉评审版本）
- 模型：4 个（deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus）
- 模型分组：A 组（glm-5.1, qwen3.6-plus，宽松）、B 组（deepseek-v4-pro, kimi-k2.6，严格）
- 交叉评审机制：A 组看 B 组的严格评价后重新评分，B 组看 A 组的宽松评价后重新评分
- 并发策略：论文级（3 篇）+ 维度级（6 维度）+ 模型级（4 模型）

**关键发现**：
- Round 1 完成率：10/10 篇
- Round 2 完成率：9/10 篇（论文 7 因内容审查问题未完成）
- Round 1 平均 std：29.06（高于前 100 篇的 17.59）
- Round 2 平均 std：14.43（显著下降，进入可接受范围）
- std > 8 的维度比例：75.0% → 20.4%（Round 1 → Round 2）
- 收敛率：100%（所有完成 Round 2 的论文均收敛）
- 平均 std 下降：14.71 分

**内容审查处理**：
- 阿里云 API 对部分法学论文触发内容审查（`data_inspection_failed`）
- 自动追踪机制：记录到 `content_inspection_issues.jsonl` 和 markdown 报告
- 容错策略：当对方组全部失败时，自动复用 Round 1 结果

**验证结论**：
- ✅ 测试通过：Round 2 交叉评审机制非常有效
- ✅ Round 1 标准差偏高可接受：交叉评审后显著收敛
- ✅ 可进入 Phase 2 完整评审

**对比前 100 篇**：
- 前 100 篇：Round 1 平均 std 17.59，Round 2 部分维度收敛率 80%+
- 10 篇测试：Round 1 平均 std 29.06（+65%），Round 2 收敛率 100%
- 分析：10 篇样本可能包含更多争议性论文，但交叉评审机制依然有效

**脚本位置**：
- 论文选择：`scripts/select_10_papers_for_test.py`
- 评审执行：`scripts/phase2_test_10_papers.py`
- 结果分析：`scripts/analyze_test_10_results.py`
- 测试报告：`results/phase2-test-10/test-report.md`

### Round 2 机制单篇验证（2026-05-22）

对 `032_我国民事庭审阶段化构造再认识` 执行完整 R1→R2 流程，验证脚本正确性。

**收敛效果**：

| 指标 | R1 | R2 |
|------|----|----|
| 平均 std | 9.3 | 4.62（↓50%）|
| 收敛维度（≤8）| 1/6 | 5/6 |
| 最大 std | 16.0 | 10.3 |

**模型行为差异（R2 变化幅度）**：

| 模型 | 组别 | R2 平均变化 | 行为特征 |
|------|------|------------|----------|
| deepseek-v4-pro | B（严格）| +1.0 | 高度锚定，3/6 维度分数不变 |
| glm-5.1 | A（宽松）| -5.0 | 向 B 组意见靠拢，普遍下调 |
| kimi-k2.6 | B（严格）| +7.8 | 愿意上调，变化最大 |
| qwen3.6-plus | A（宽松）| -4.3 | 普遍下调，与 glm 行为一致 |

**DeepSeek 顽固性的根因（已确认，非 bug）**：
- 属于 B 组（严格组），R2 中看到 A 组的宽松评价后，系统性地认为 A 组"过于宽松"，拒绝调整
- `rejected_points` 质量高：能给出具体理由（如"论文是制度介绍而非理论争辩"），不是无脑拒绝
- 这是**锚定效应**，是交叉评审设计的预期行为——防止所有模型向均值漂移
- 对比 kimi（同 B 组）平均上调 +7.8，说明是模型特性而非 prompt 问题

**未收敛维度（研究创新性，std 10.3）**：
- DeepSeek 给出实质性学术分歧（论文是否提出可争辩的法学理论问题），不是评分随机波动
- 属于**真实学术判断差异**，prompt 无法修复，应由专家终审介入

**不需要 autoresearch 迭代 R2 的理由**：
1. Phase 2 的 10 篇测试已验证 R2 收敛率 100%（R1 avg std 29 → R2 14.43）
2. 单篇验证进一步确认 R2 机制工作正常，50% std 降幅是实打实的
3. 剩余分歧是真实学术分歧，不是 prompt 问题
4. autoresearch 迭代的是 Round 1 的锚定规则（v2.56.6），R2 机制是独立的

**R2 耗时**：1103s ≈ 18分钟/篇（4 模型 × 6 维度 = 24 次 API 调用，每次需读全文）。全量运行时需考虑此成本。

**脚本位置**：`scripts/test_single_paper_two_rounds.py`，结果：`results/single-paper-test-032/`

### Phase 2 全量评审完成情况（2026-05-27）

全量评审已完成，当前结果登记在 `results/catalog.yaml`。

**执行配置**：
- 框架：v2.55（交叉评审版本）
- 模型：4 个（deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus）
- 原始论文：`raw/fullpaper/`（1920 篇 PDF）
- 元数据：`results/datasets/three-journals/metadata.csv`（1920 条，列：期刊/年份/卷/期/题目/作者/作者机构/页数/主题词）

**结果目录结构**：

```
results/datasets/three-journals/six-dimension/phase2-r2-v2.55/
├── summary.csv        # Git 保留的 1920 篇六维摘要与 CCB 总分
├── per-paper/         # 本地忽略；1920 篇完整 R1+R2 结果
└── audit/round1-errors/ # Round 1 问题论文分类（64 篇，已排除空状态）
    ├── 2-all-reject/      # 4 模型全拒（5 篇）
    ├── 3-majority-reject/ # 多数拒绝（19 篇）
    ├── 4-single-reject/   # 单模型拒绝（15 篇）
    ├── 5-boundary-only/   # 仅边界判断（25 篇）
    └── error-summary.json # 错误汇总
```

**单篇结果 JSON 字段**：
- `paper`：论文 PDF 路径
- `framework`：使用的框架版本（configs/frameworks/law-v2.55-cross-review.yaml）
- `models`：参与评审的模型列表
- `dimensions`：六维度评分，每维度含 round1_scores, round2_scores, changes, raw_outputs
- `overall`：汇总指标（round1_avg_std, round2_avg_std, std_improvement, dimensions_converged 等）

**问题论文处理**：
- ~~空状态（90 篇）~~：已全部补测完成，结果已纳入 round2，原始文件已清理
- 全拒论文（5 篇）：可直接排除，不进入后续评审
- 多数/单模型拒绝（34 篇）：需人工复核决定是否纳入
- 边界论文（25 篇）：需人工确认项目口径归属

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
- **分歧处理**：六维 R2 后单维度 std > 8 时进入专家复核
- **供应商策略**：国内模型→DashScope 百炼，仲裁模型→Fucheers
- **AI 定位**：辅助初筛，不替代专家终审

当前口径见 `docs/evaluation/law-ai-assisted-review-rules-v0.17.md`。

### 来自 Round 2 机制验证（2026-05-22，已冻结）

- **框架版本**：v2.55（交叉评审版本）+ R2 逻辑，不再用 autoresearch 迭代 R2 prompt
- **DeepSeek 顽固性是设计正确行为**：B 组严格模型看到 A 组宽松评价后系统性拒绝调整，属锚定效应，防止模型向均值漂移；不是 bug，不需要修
- **未收敛维度（std > 8）的处理**：剩余分歧多为真实学术判断差异（如"论文是否提出可争辩理论问题"），prompt 无法修复，交由专家终审
- **Phase 2 大规模执行**：已完成（2026-05-27）。v2.55 + R2 逻辑，1920 篇完整结果存于 `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/`；64 篇 Round 1 问题论文已分类存于 `round1-err/`（空状态 90 篇已全部补测完成并清理）

详细分析见 `results/single-paper-test-032/`

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

- `expert-audit-report`：把单篇论文的六维、五轴与 E2 原始数据整理为专家审计报告；内容真源位于 `agent-skills/expert-audit-report/`。

### 已废弃

- `socialeval-project-context`（2026-06-13 归档）
  - 原因：本文件已完整承载项目上下文，继续保留 skill 会造成重复维护和额外读取成本
  - 归档位置：本地忽略归档区 `agent-skills/archive/deprecated-20260613/socialeval-project-context/`

- `socialeval-convergence-report-export`（2026-06-01 归档）
  - 原因：convergence-test 格式已被 Phase 2 fullevaluation 替代
  - 归档位置：本地忽略归档区 `agent-skills/archive/deprecated-20260601/`

### 使用约定

- 项目通用上下文优先维护在本文件，避免与 skill 重复维护
- 只有当某个项目工作流需要独立触发规则、脚本或参考材料时，才在 `agent-skills/` 下新增独立 skill
- 若重新启用项目专属 skill，可运行 `python3 scripts/install_project_skills.py`，默认同时软链接到 Codex 的 `~/.codex/skills/` 与 Claude Code 的 `~/.claude/skills/`；`agent-skills/` 始终是唯一内容真源

---

## 归档管理

### 归档策略（2026-07-16 更新）

为保持仓库边界清晰，归档文件只保留在本地忽略区，不再进入 Git。当前 Git 只保留活跃代码、当前报告/摘要、核心元数据、必要 manifest 和可复现生成脚本。

#### 当前 Git 保留范围

1. **配置文件**：3 个六维生产/基线版本 + 五轴 v0.2 + `registry.yaml` + 独立 CCB v0.8 协议
2. **原始数据指针**：`results/datasets/three-journals/metadata.csv` 和必要说明；大语料、逐篇原始输出保留本地
3. **评审结果摘要**：`results/datasets/`、`results/rankings/`、`results/reports/current/` 与 `results/catalog.yaml`
4. **脚本**：当前可复跑、可维护的核心工具脚本
5. **文档**：当前活跃规程、当前报告、README/CLAUDE/manifest

#### 本地忽略范围

- `archive/` 与所有 `**/archive/`
- `results/datasets/**/per-paper/`、`results/datasets/**/audit/`、`results/rankings/**/per-paper/` 等逐篇 AI 原始输出
- `results/retest-*/`、旧候选/Top50 诊断文件、补测中间产物
- `raw/review_comments/`、`raw/fullpaper/`、`法学三大刊论文/`
- 缓存、虚拟环境、系统文件和临时日志

历史制品统一放在仓库同级 `../SocialEval-archive/2026-07-16-deep-clean/`；归档清单记录原路径、字节数与 SHA-256。逐篇活动数据仍留在上述本地忽略目录。

#### E2 候选池（v5，2026-06-15 选入；2026-07-12 口径切 core_ceiling_bonus）

**入池规则**：

| 层级 | 规则 | 说明 |
|------|------|------|
| 硬条件 | 五轴 ≥ 9 **且** E1(core_ceiling_bonus 总分) ≥ 80 | 不满足则不入池 |
| 选入 | Top 80（按 E1 ccb 降序） | 前 80 名直接入选 |
| 学科保底 | 每学科 ≥ max(5, Top50 配额) | 只从满足两项硬条件的候选补入；不足时接受缺口 |
| 年度保底 | 每年（2015–2025）≥ 5 篇 | 只从满足两项硬条件的候选补入；不足时接受缺口 |
| 不足容忍 | 学科/年度保底可不满 | 如果池内该学科/年度论文不足，接受缺口 |

**E1 总分口径（E1 候选选取）**：`calculate_weighted_total(scoring_protocol=core_ceiling_bonus)`，即
`min(base + bonus, ceiling, 100)`——base=核心四维加权平均(0.85归一化)、bonus=前瞻分档弱加分(0–5)、ceiling=学术共识度封顶，并执行最终 100 分封顶。
**E2 重排名口径**：同样 core_ceiling_bonus，作用于 E1+E2 median 池化的六维 pooled_avg。
两层均用 ccb，口径一致。实现真源 `src/reporting/scoring.py`，协议真源 `configs/scoring/core-ceiling-bonus-v0.8.yaml`。
**不再用**六维简单算术平均或简单加权和（旧 v5 池口径）。**E3 选择性补测已弃用**（E1+E2 median(8) 对 92% 论文已收敛；剩余高分歧多为真实学术判断差异，多轮同模型补测无法修复，交专家终审）。

**学科分类口径**：`results/datasets/three-journals/classification.csv` 的 **专家分类（33 篇专家纠正）优先 → 否则原分类**。
AI 主分类（6 轮迭代产物）因过度归并到法学理论等可疑归类，已被弃用并从该文件删除相关列。

**实际结果**（2026-07-16 严格门槛重建，原分类+专家分类）：

- 全库满足硬条件（五轴≥9 且 ccb≥80）：**638 篇**（旧简单均值口径 421 篇 → ccb 拯救核心四维强但前瞻/共识一般的论文）
- Top 80 直接入选：80 篇
- 学科保底补入：21 篇
- 年度保底补入：4 篇
- **最终池：105 篇**（相对 2026-07-12 的 110 篇池新增 4、剔除 9）
- 池内 ranking：`weighted_score` = core_ceiling_bonus(median 池化六维)，区间 83.59–94.32

**Top50 比例配额**（按全库 1920 篇学科比例分配，池内按 ccb 选取）：

- 配额：民商12/刑法9/宪法6/诉讼6/法理6/知产2/国际2/环境2/经济2/法律史2/党内1 = 50
- Top50 score 区间 86.24–94.32，**无 underflow**

**关键文件**：

- 候选池 ranking：`results/rankings/e2-ccb-v5/ranking.json`（105 篇，E1+E2 median 聚合 + ccb 总分）
- 入池选择清单：`results/rankings/e2-ccb-v5/pool.json`（105 篇，e1_score=E1-only ccb）
- E2 评测原始数据：`results/rankings/e2-ccb-v5/per-paper/round1/` + `round2/`（当前池 105 篇；目录另保留 9 篇已出池历史结果，本地忽略）
- 学科分类：`results/datasets/three-journals/classification.csv`（原分类 + 专家分类）
- 重选/重建脚本：`scripts/reselect_e2_pool_ccb.py`（E1 ccb 重选）、`scripts/rebuild_ranking_v5_ccb.py`（E2 ccb 重排名）、`scripts/rebuild_top50_proportional_ccb.py`（Top50）
- E2 补跑脚本：`scripts/e2_new_supplement.py`（默认 4 论文并发、API 全局并发上限 5、断点续传）
- 专家审阅展示清单：`results/rankings/e2-ccb-v5/top50-proportional.json` + `results/rankings/e2-ccb-v5/top50-ccb-list.md`

**历史口径（已废弃）**：

- 旧 E2-Top102（v5，2026-06-15）：102 篇，E1 用六维简单算术平均；2026-07-12 切 ccb 后调整为 110 篇，2026-07-16 严格门槛重建为 105 篇
- 旧 Top102/Top101 目录：旧 E2 数据与候选池，已迁入冷归档并由当前排名目录取代
- v3/v4 旧候选池 ranking：101 篇，使用旧分类与简单加权和，仅供冷归档追溯
- E3 选择性补测（45 篇）：已弃用（E1+E2 已收敛，高分歧交专家终审）

#### 查找本地归档文件
```bash
# 查看冷归档及校验清单
tree -L 2 ../SocialEval-archive/2026-07-16-deep-clean/
wc -l ../SocialEval-archive/2026-07-16-deep-clean/manifest.jsonl
```
