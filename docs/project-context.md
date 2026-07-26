# SocialEval 系统与成果上下文

本文件记录 SocialEval 的系统定位、架构、评价方法、历史实验、数据成果和归档状态。
代理执行规则与不可破坏约束见项目根目录的 [AGENTS.md](../AGENTS.md)。

## 项目简介

**中国自主知识创新（法学论文）评价系统**（SocialEval）是一套面向自主知识体系的
AI 辅助学术评价系统，以法学论文评审为切入点，支持拓展至人文社科各学科。

核心机制：

```text
多模型并发评价 → 一致性验证 → 专家复核 → 标准化报告输出
```

主系统需求：
`docs/requirements/SocialEval-requirements-v0.5.md`。

### 编辑辅助预审阶段

编辑辅助预审系统面向《交大法学》《学术月刊》等编辑部的未发表法学投稿，目标是产出：

- 六维评分；
- AI 期刊风格综合审稿意见；
- 基于优、良、中、差组合的细分决定建议；
- 供编辑确认、覆盖和审计的综合预审报告。

编辑预审是当前重点；投稿人可通过邮箱注册和验证，向正式启用期刊投稿、查看本人
稿件进度、接收编辑发布的作者结果并申请撤稿。预审决定不使用 CCB 阈值。业务扩展
放在 `src/editorial/`，复用六维引擎、providers、报告、认证和摄取能力。

本地 `raw/label/` 中的真实审稿意见只作为评估基准和输出格式参考，不进入 Git。
编辑辅助预审的当前设计入口为 `docs/editorial/README.md`，需求基线为
`docs/requirements/editorial-pre-review-requirements-v1.2.md`。初始编辑单元包括
《交大法学》、《学术月刊》法学板块和《东方法学》，均从“试运行”开始。

## 系统架构

### 技术栈

- 后端：Python 3.10+、FastAPI，依赖管理使用 `uv`。
- 前端：React + TypeScript。
- 数据库：PostgreSQL，存储论文、评分和审计日志。
- 缓存与队列：Redis + Celery。
- AI 接入：统一 provider 抽象层，支持直连与兼容 OpenAI API 的多供应商网关。

### 目录结构

```text
src/
  api/             RESTful API（FastAPI）
  core/            核心配置与工具
  evaluation/      AI 评价引擎（六维、五轴、多模型）
  ingestion/       文档摄取与预处理
  knowledge/       知识体系配置动态加载
  models/          SQLAlchemy 数据模型
  reliability/     可靠性、标准差与置信度
  reporting/       评分、PDF 与 JSON 报告
  review/          专家复核工作流
  web/             Web 相关后端
configs/
  frameworks/      评价框架、Prompt 和输出契约
  scoring/         评分协议
docs/
  requirements/    产品需求
  architecture/    ADR
  evaluation/      评价方法与实验报告
  discussion/      设计讨论
frontend/          React + TypeScript 前端
tests/             测试（镜像 src/）
alembic/           数据库迁移
scripts/           评估、分析、验证与维护脚本
results/
  catalog.yaml     结果总目录
  datasets/        三大刊、交大法学、学术月刊数据摘要
  rankings/        CCB 与 E2 排名
  reports/         当前诊断与完整性报告
```

归档目录和逐篇原始输出保留在本地忽略区，不作为当前 Git 仓库内容维护。

## 运行环境

环境变量清单以 `.env.example` 为准，主要分为：

- `DATABASE_URL`：PostgreSQL 连接；
- `REDIS_URL`：Redis 和 Celery；
- `SECRET_KEY`：JWT/Session 签名，生产环境必须更换；
- 直连供应商：`OPENAI_*`、`ANTHROPIC_*`、`DEEPSEEK_*`；
- 网关供应商：`ZENMUX_*`、`OPENROUTER_*`、`DASHSCOPE_*`、`KETAN_*`、
  `FUCHEERS_*`、`YUNYI_*`、`SSS_*`；
- `SMTP_*`：专家复核邮件通知。

每个网关需要同时配置对应的 `*_BASE_URL` 与 `*_API_KEY`。历史主力国内模型通过
DashScope 百炼调用，历史仲裁模型通过 Fucheers 调用。所有业务调用均应经过
`src/evaluation/providers/`，不直接依赖供应商 SDK。

当前本机 Docker 状态、生产化完成项和交大 jCloud 后续步骤见
[部署与当前进展交接](deployment/CURRENT-HANDOFF.md)。该文件不记录任何真实凭据。

## 评价体系

### 权威真源

- 方法论规程：
  `docs/evaluation/law-ai-assisted-review-rules-v0.17.md`。
- Round 1 生产框架：
  `configs/frameworks/law-v2.56.6-20260522.yaml`。
- Round 2 交叉评审框架：
  `configs/frameworks/law-v2.55-cross-review.yaml`。
- 概念操作化：
  `docs/evaluation/concept-operationalization-v1.0.md`。
- 架构决策：
  `docs/architecture/20260414_ADR-001_evaluation-framework-v2.md`。

### 四阶段流程

```text
预检（项目口径判断）
  → 六维评分（0–100）
  → 自主知识体系信号校验（0–8，不进入基础分）
  → 评价层复核判断
```

六维标准名称为：

1. 研究创新性；
2. 现状洞察度；
3. 理论建构力；
4. 逻辑连贯性；
5. 学术共识度；
6. 前瞻延展性。

### CCB 总分

`final_score = min(base + bonus, ceiling)`

- `base`：核心四维加权平均，即
  `(研究创新性×0.3 + 现状洞察度×0.2 + 理论建构力×0.15 + 逻辑连贯性×0.2) / 0.85`。
- `ceiling`：学术共识度 `<60` 时最高 65，`60–74` 时最高 75，`≥75` 不额外封顶。
- `bonus`：前瞻延展性提供 0–5 分弱加分，前提是逻辑连贯性与学术共识度均
  `≥60`，核心四维均 `≥50`。
- 实现真源：`src/reporting/scoring.py` 的 `calculate_weighted_total()`。
- 协议真源：`configs/scoring/core-ceiling-bonus-v0.8.yaml`。

### 五轴位置归属度

五轴用于评估“中国法学自主知识体系位置归属度”，独立于六维质量评价：

- 对象归属度；
- 材料归属度；
- 范畴自主度；
- 解释目标归属度；
- 体系映射度。

每轴 0–2 分，总分 0–10；`strong=8–10`、`medium=5–7`、`weak=2–4`、
`absent=0–1`。五轴不与六维加总，只用于候选分层、复核优先级和知识体系覆盖分析。
方法论真源为
`docs/evaluation/autonomous-knowledge-system-position-assessment-v0.2.md`。
旧四信号字段仅作兼容，不再作为位置归属度主结构。

当前两轮流程：

- R1：`deepseek-v4-pro` 与 `qwen3.7-max-2026-06-08` 独立评估；
- R2：按分歧触发 `skip`、`light` 或 `full`；
- 2026-07-26 起未来任务直接使用 Qwen3.7-Max；既有 Qwen3.6-Plus 逐篇结果
  保持历史版本，不重跑、不回写；
- Top101 历史实测中，R1 两模型平均总分差 0.53，严重分歧（差值 ≥4）约 4%，
  R2 实际触发率约 67%；
- 共用实现位于 `src/evaluation/position/`；
- Top101 兼容入口：
  `scripts/evaluate_top101_position_assessment_two_rounds.py`；
- 交大法学入口：
  `scripts/evaluate_jiaodafaxue_position.py`。

### 可靠性阈值

| 等级 | 标准差 |
|---|---:|
| High | `std ≤ 5` |
| Medium | `5 < std ≤ 8` |
| Low | `8 < std ≤ 12` |
| Critical | `std > 12` |

R2 后单维度 `std > 8` 进入专家复核，不自动调用 GPT 仲裁。

## 框架版本与迭代经验

### 当前活跃版本

| 版本 | 状态 | 说明 |
|---|---|---|
| v2.50.2 | 历史基线 | 嵌入评分步骤；负样本均值 76.1、正样本 91.1 |
| v2.55 | R2 使用 | 交叉评审版本，维度名已标准化 |
| v2.56.6 | R1 生产 Prompt | 六轮锚定优化，std 28.16 → 6.22 |

历史版本 v1.0–v2.54 保留在本地忽略归档区。

### v2.56 语义对齐

v2.55 已更新维度 `name_zh`，但当时 `prompt_template` 仍使用旧名称。v2.56 完成：

- “问题创新性”扩展为“研究创新性”，覆盖问题、方法、材料和理论贡献；
- “分析框架建构力”扩展为“理论建构力”，覆盖理论体系完整性；
- “逻辑严密性”调整为“逻辑连贯性”，强调前后一致和论证流畅；
- 现状洞察度、学术共识度、前瞻延展性保持连续口径。

### v2.56.6 锚定规则

2026-05-22 使用 `autoresearch` 完成六轮 R1 锚定规则迭代：

- 迭代顺序：AF → PO → LI → LC → CC → FE；
- 每轮处理标准差最高维度，重点覆盖法哲学和理论型论文；
- 整体平均 std 从 28.16 降至 6.22，下降 77.9%；
- Holdout 结果 13.59，接近基线 13.57，未观察到明显过拟合。

该工具只用于历史 R1 迭代，不用于继续调整已经冻结的 R2 机制。

### v2.51 Phase 0 失败经验

2026-05-15 至 2026-05-17 的 Stage A 负面模式检测器未达到生产要求：

- 命中率 22%，目标 70%；
- 误报率 50%，目标 10%；
- Pattern 定义过于抽象，模型难以区分正常学术表述与空泛表述；
- 短 Prompt 缺少判断论证质量所需上下文。

详细报告：
`docs/evaluation/v2.51-phase0-failure-report.md`。后续如重启该方向，应使用可观察指标
重构 Pattern，而不是继续抽象描述“论证质量”。

### v2.50.x 经验

9 篇负样本与 1 篇正样本的 v2.50.2 测试中：

- 正样本 91.1，未被误伤；
- 4 篇负样本低于 75，3 篇处于 75–80，2 篇仍高于 80；
- 全部负样本均值 76.1，与正样本差 15.0；
- 有效识别的 4 篇均值 69.1，与正样本差 22.0。

结论与经验：

- `ceiling_rules` 路线在 v2.49 中触发率为 0%，失败；
- 前置扣分对研究创新性有效；
- 长 Prompt 会淹没理论建构力和学术共识度的扣分指令；
- 后续方向应优先缩短 Prompt、简化标准或重构维度流程。

v2.50.2 基于 v2.47。v2.47 曾在 14 篇样本上表现稳定，并修复 v2.46 对前瞻
延展性的系统性低分。

## Phase 2 验证与全量成果

### 10 篇测试（2026-05-22）

配置：

- 框架：v2.55；
- 模型：`deepseek-v4-pro`、`glm-5.1`、`kimi-k2.6`、`qwen3.6-plus`；
- A 组宽松模型：GLM、Qwen；
- B 组严格模型：DeepSeek、Kimi；
- A/B 两组在 R2 互看对方意见后重新评分。

结果：

- R1 完成 10/10，R2 完成 9/10；论文 7 因内容审查未完成；
- 平均 std 从 29.06 降至 14.43；
- `std > 8` 的维度比例从 75.0% 降至 20.4%；
- 已完成 R2 的论文收敛率 100%；
- 平均 std 下降 14.71。

阿里云对部分法学论文会返回 `data_inspection_failed`。历史流程将问题写入
`content_inspection_issues.jsonl` 和 Markdown 报告；对方组全部失败时复用 R1，
同时保留失败记录。

相关脚本：

- `scripts/select_10_papers_for_test.py`；
- `scripts/phase2_test_10_papers.py`；
- `scripts/analyze_test_10_results.py`；
- 报告位于 `results/phase2-test-10/test-report.md`。

### 单篇 R2 验证

对 `032_我国民事庭审阶段化构造再认识` 的完整验证结果：

| 指标 | R1 | R2 |
|---|---:|---:|
| 平均 std | 9.3 | 4.62 |
| 收敛维度（≤8） | 1/6 | 5/6 |
| 最大 std | 16.0 | 10.3 |

模型平均变化：

- DeepSeek（严格组）：`+1.0`，高度锚定；
- GLM（宽松组）：`-5.0`；
- Kimi（严格组）：`+7.8`；
- Qwen（宽松组）：`-4.3`。

DeepSeek 拒绝向宽松意见靠拢属于有理由的严格锚定，不是代码缺陷。研究创新性仍有
`std=10.3`，体现“是否提出可争辩法学理论问题”的真实学术分歧，应交由专家终审。

单篇 R2 历史耗时约 1103 秒，即 18 分钟（4 模型 × 6 维度，共 24 次全文调用）。
脚本为 `scripts/test_single_paper_two_rounds.py`，结果位于
`results/single-paper-test-032/`。

### 1920 篇全量评审

Phase 2 全量评审于 2026-05-27 完成，登记在 `results/catalog.yaml`：

- 框架：v2.55 R2；
- 模型：DeepSeek、GLM、Kimi、Qwen；
- 原始论文：`raw/fullpaper/`；
- 权威元数据：`results/datasets/three-journals/metadata.csv`；
- 摘要：
  `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/summary.csv`；
- 逐篇完整结果：
  `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/`。

问题论文分类：

- 5 篇四模型全拒，可直接排除；
- 19 篇多数拒绝；
- 15 篇单模型拒绝；
- 25 篇仅边界判断；
- 曾有 90 篇空状态，均已补测完成并清理原空状态文件。

多数拒绝、单模型拒绝和边界论文需要人工复核。

## 数据集与 ID 边界

### 三大刊

- `results/datasets/three-journals/metadata.csv`：1920 条元数据，是 Paper ID 唯一权威来源；
- `编号` 字段与逐篇 `paper-{id}.json` 一致；
- 不得从中间文件、缓存或文件顺序重建 ID；
- 已知错误案例曾将 paper-1238 的分数错配到 paper-1244，根因是自建映射出现偏移。

核验示例：

```bash
python3 -c "
import csv
with open('results/datasets/three-journals/metadata.csv', 'r', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        if '党政体制' in row['题目']:
            print(f\"ID={row['编号']}, 年份={row['年份']}, 标题={row['题目']}\")
"
```

### 交大法学

- 原始论文：`raw/jiaodafaxue/`，642 篇 Markdown；
- 元数据：`results/datasets/jiaodafaxue/metadata.json`，独立 ID 1–642；
- 六维结果：
  `results/datasets/jiaodafaxue/six-dimension/phase2-r2-v2.55/per-paper/`；
- 五轴结果：
  `results/datasets/jiaodafaxue/five-axis/position-v0.2/`；
- 五轴历史运行默认 `final_score > 55`，共 311 篇；阈值 60 时 280 篇，
  阈值 70 时 175 篇。

### 框架这代样本

- `raw/calibration-regression/`：3 篇校准/回归样本，可用于调参；
- `raw/holdout-test/`：4 篇冻结测试样本，只允许修复可归因问题；
- `raw/validation/`：8 篇最终验证样本，应在规则冻结后一次性运行；
- `raw/fullpaper/`：1920 篇全量评审语料。

顺序必须是校准回归 → 冻结测试 → 最终验证。参与过调参的样本不能重新标记为验证集。

## E2 候选池与排名

当前 E2 候选池为 v5，2026-06-15 初选，2026-07-12 切换到
`core_ceiling_bonus`，2026-07-16 按严格门槛重建。

### 入池规则

| 层级 | 规则 |
|---|---|
| 硬条件 | 五轴 ≥9 且 E1 CCB ≥80 |
| 直接选入 | 按 E1 CCB 排名前 80 |
| 学科保底 | 每学科 ≥ `max(5, Top50 配额)` |
| 年度保底 | 2015–2025 每年 ≥5 篇 |
| 不足容忍 | 硬条件内样本不足时接受保底缺口 |

E1 候选选取与 E2 重排名都使用 CCB。E2 对 E1+E2 的六维结果取 median 池化后再计算
CCB，不再使用六维简单算术平均或旧简单加权和。

学科分类使用
`results/datasets/three-journals/classification.csv`，按“33 篇专家纠正优先，否则原分类”。
历史 AI 主分类因过度归并而弃用。

### 当前结果

- 满足硬条件：638 篇；
- Top80 直接选入：80 篇；
- 学科保底补入：21 篇；
- 年度保底补入：4 篇；
- 最终池：105 篇；
- `weighted_score` 区间：83.59–94.32。

Top50 学科配额：

```text
民商12 / 刑法9 / 宪法6 / 诉讼6 / 法理6 /
知产2 / 国际2 / 环境2 / 经济2 / 法律史2 / 党内1
```

Top50 分数区间 86.24–94.32，无 underflow。

关键文件：

- `results/rankings/e2-ccb-v5/ranking.json`：105 篇 E2 CCB 排名；
- `results/rankings/e2-ccb-v5/pool.json`：入池清单；
- `results/rankings/e2-ccb-v5/per-paper/`：本地忽略的 E2 原始结果；
- `results/rankings/e2-ccb-v5/top50-proportional.json`；
- `results/rankings/e2-ccb-v5/top50-ccb-list.md`；
- `scripts/reselect_e2_pool_ccb.py`；
- `scripts/rebuild_ranking_v5_ccb.py`；
- `scripts/rebuild_top50_proportional_ccb.py`；
- `scripts/e2_new_supplement.py`。

E3 选择性补测已经弃用：E1+E2 median(8) 对 92% 论文已经收敛，剩余高分歧主要是
真实学术判断差异，应交专家终审。旧 Top102/Top101、v3/v4 候选池和 E3 结果仅在
冷归档中用于追溯。

## 已确认决策与遗留事项

来自主需求 v0.5：

- v1 不支持扫描 PDF OCR，疑似扫描件应提示重新上传；
- 多模型并发默认 3，上限 5；
- 进入复核队列且指定专家后自动发送邮件，编辑可手动追加复核；
- 投稿人邮箱自助注册并验证；编辑、专家和管理员由管理员邀请；
- Web 使用 Session，API 使用 API Key。

来自评价验证：

- 历史主力模型为 Qwen3.6-Plus / GLM-5.1，Temperature 0.3；
- 国内模型历史上主要走 DashScope，历史仲裁模型走 Fucheers；
- R2 后 `std > 8` 交专家复核；
- AI 只辅助初筛，不替代专家终审；
- v2.55 R2 已冻结；
- 新模型候选集取消宽松组与严格组，第二轮每个模型匿名参考另外三个
  模型的完整第一轮意见；该候选协议不追溯改写 v2.55 历史结果；
- DeepSeek 的严格锚定是设计行为；
- 未收敛维度代表可能的真实学术分歧，不通过继续调 Prompt 强行消除。

仍待需求层确认：

- 外部期刊系统接入方式、签名机制和幂等策略；
- MinerU 后续采用自动通道还是管理员手动启用。

## 项目级 Skills

项目专属 Skill 的内容真源在 `agent-skills/`，当前只有：

- `expert-audit-report`：把单篇论文六维、五轴与 E2 原始数据整理为专家审计报告；
  由 Claude Code 在本项目内使用，不注册为全局 Codex Skill。

`scripts/install_project_skills.py` 默认将项目 Skill 软链接到本仓库
`.claude/skills/`；如需安装到其他目录，可重复传入 `--target-dir`。
`.agents/skills/` 是本地忽略的第三方/全局 Skill 目录，不属于项目维护范围。

已归档项目 Skill：

- `socialeval-project-context`：上下文已由项目文档承载；
- `socialeval-convergence-report-export`：旧 convergence-test 格式已被 Phase 2
  全量评价取代。

`autoresearch` 位于本地忽略的 `.agents/skills/autoresearch`，仅作为 v2.56.6 R1
锚定迭代历史工具，当前不主动安装。

## 归档与 Git 边界

### 当前 Git 保留

- 活跃框架与评分配置；
- 必要原始数据指针和元数据；
- `results/datasets/`、`results/rankings/`、`results/reports/current/` 摘要；
- 当前可复跑、可维护的脚本；
- 当前规程、报告、README、AGENTS、CLAUDE 和 manifest。

### 本地忽略

- `archive/` 和所有 `**/archive/`；
- `results/datasets/**/per-paper/`、`audit/`、排名逐篇原始输出；
- 旧候选池诊断、补测中间产物和临时日志；
- `raw/review_comments/`、`raw/fullpaper/`、`raw/label/`；
- 虚拟环境、缓存和系统文件。

历史制品集中在：

```text
../SocialEval-archive/2026-07-16-deep-clean/
```

归档 manifest 记录原路径、字节数和 SHA-256。逐篇活动数据仍保留在项目内相应的本地
忽略目录。

查看归档：

```bash
tree -L 2 ../SocialEval-archive/2026-07-16-deep-clean/
wc -l ../SocialEval-archive/2026-07-16-deep-clean/manifest.jsonl
```

## 参考资料

| 文件 | 说明 |
|---|---|
| `ref/法学论文的人工评价逻辑.pptx` | 法学论文人工评价方法论 |
| `ref/AI_Legal_Paper_Evaluation_System.pptx` | AI 评价系统方案演示 |
| `ref/lecture_citation_quality.pdf` | 引用质量相关学术参考 |
| `ref/【会议纪要V2】...研讨会.docx` | 专家研讨会纪要 |
