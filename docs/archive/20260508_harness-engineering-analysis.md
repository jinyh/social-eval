---
title: SocialEval Harness Engineering 分析报告
version: 1.0.0
date: 2026-05-08
author: Claude (Opus 4.7)
status: 分析报告
---

# SocialEval Harness Engineering 分析报告

## 1. 背景

本报告基于以下材料：
- 项目代码库结构（`configs/frameworks/`, `src/evaluation/`, `src/knowledge/`, `src/reliability/`）
- 42 个框架迭代版本（v2.0 → v2.42，由 AutoResearch skill 自动迭代）
- 《中国自主知识体系研究论文 AI 辅助评审规程 v0.13》（专家说明版）
- 现有样本集（`raw/calibration-regression/` 3篇、`raw/holdout-test/` 4篇、`raw/validation/` 8篇）

## 2. 核心问题

**用户问题**：`configs/frameworks/` 这个思路是所谓 Harness 吗？Harness Engineering 可以给这个项目带来什么？

## 3. 现状评估

### 3.1 已有的 Harness 核心组件

✅ **配置驱动的评价框架**
- 42 个版本的 YAML 配置（`configs/frameworks/law-v2.0-20260413.yaml` → `law-v2.42-20260507.yaml`）
- Schema 验证（`schema_v2.json`, `schema_v3.json`）
- 动态加载机制（`src/knowledge/loader.py`, `src/knowledge/version_manager.py`）

✅ **多模型并发评价引擎**
- 统一抽象层（`src/evaluation/providers/factory.py`）
- 并发评价器（`src/evaluation/concurrent_evaluator.py`）
- Prompt 构建器（`src/evaluation/prompt_builder.py`）
- 端到端编排器（`src/evaluation/orchestrator.py`）

✅ **可靠性验证层**
- 标准差计算（`src/reliability/calculator.py`）
- 置信度判断（`src/reliability/threshold_checker.py`）

✅ **样本集分层**
- `raw/calibration-regression/`：校准/回归集（3篇）
- `raw/holdout-test/`：冻结测试集（4篇）
- `raw/validation/`：最终验证集（8篇）

✅ **自动化迭代能力**
- AutoResearch skill 已经能自动调整框架配置
- `scripts/run_convergence_test.py` 支持单篇论文的多模型收敛测试

**结论**：`configs/frameworks/` + 现有代码已经构成了一个**评价框架迭代 Harness**。

---

### 3.2 缺失的 Harness Engineering 能力

基于《评审规程 v0.13》的实际需求，以下能力缺失：

#### 缺失 1：大规模批量评价引擎

**需求来源**：规程 1.1 节
> 本规程计划应用于近10年法学三大刊（《中国法学》《法学研究》《中外法学》）约2000篇论文的系统评价

**现状**：
- `scripts/run_convergence_test.py` 只能单篇论文 + 单框架 + 指定模型
- 没有"批量跑 2000 篇 × 1 框架 × 3 模型"的能力
- 没有断点续传机制（跑到一半挂了，需要重新开始）

**影响**：
- 无法高效完成"2000 篇论文的系统评价"
- 手动跑 2000 篇论文不现实

#### 缺失 2：预检门槛校准工具

**需求来源**：规程附录A《预检门槛校准》
> 正式采用"项目口径预检"作为项目门槛前，必须先用现有参考论文做一轮预检分布校准。

**校准目标**（附录A.1）：
- 目标1：预检"明显不适格"的论文中，至少80%应该是"明显不适格"（经人工确认）
- 目标2：边界论文应进入六维评分并被明确标记复核，避免被自动剔除
- 目标3：传统法教义学好论文不应被预检排除
- 目标4：明显不适格但进入六维评分的论文，应在六维评分中被压分或标记风险

**校准指标**（附录A.3）：
- 指标1：预检排除率（明显不适格的比例）
- 指标2：预检误判率（被排除但实际适格的比例，目标<20%）
- 指标3：预检漏判率（未被排除但实际不适格且六维未识别的比例，目标<5%）
- 指标4：边界复核率（边界进入评分并建议复核的比例）

**现状**：
- 没有自动化的"跑全部样本 → 生成分布报告 → 计算校准指标"工具
- 需要手动统计"明显不适格"、"边界进入评分并建议复核"、"进入六维评分"的论文数量和比例

**影响**：
- 无法验证预检门槛是否合理
- 无法快速迭代优化预检规则

#### 缺失 3：三阶段筛选的候选池管理

**需求来源**：规程附录B《三阶段筛选方案说明》

**三阶段流程**：
1. **第一阶段：AI 辅助初筛**
   - 输入：约2000篇三大刊论文
   - 输出：候选论文（规模由最终打分分布确定，150-200篇仅作为初始工作量参考）
   - 分档：高分候选（总分>75）、重点候选（总分65-75且自主知识体系信号强）、边界候选（总分60-65附近且信号非常强）

2. **第二阶段：引文分析**
   - 输入：第一阶段形成的候选论文
   - 输出：深审候选论文（规模依据引文分析、自主知识体系信号和专家质检结果确定）
   - 分析维度：年均引文量、引文质量、引文语境、自主知识体系信号强度

3. **第三阶段：专家终审**
   - 输入：第二阶段形成的深审候选论文
   - 输出：10篇"中国自主知识体系创新"代表性论文

**现状**：
- 没有"候选池管理系统"，无法追踪"哪些论文进入了哪个阶段"
- 没有"按总分 + 自主知识体系信号"自动分档的工具
- 没有"引文分析集成"（需要外部引文数据库）
- 没有"专家复核界面"（Web UI）

**影响**：
- 无法高效执行三阶段筛选流程
- 无法追踪"每篇论文为什么被保留/排除"

#### 缺失 4：质量保障工具

**需求来源**：规程附录B.5《质量保障机制》
> 专家最低抽查不少于20篇被排除论文，并按年份、期刊、领域分层；如发现遗漏风险，应扩大抽查并调整阈值。

**现状**：
- 没有"按年份、期刊、领域分层抽样"的工具
- 没有"自动生成抽查清单"的能力
- 样本集元数据缺失（`raw/` 下的论文没有"年份、期刊、领域"标注）

**影响**：
- 无法快速生成"需要人工确认的 20 篇论文清单"
- 无法验证"是否遗漏了潜在代表性论文"

---

## 4. Harness Engineering 的价值

基于《评审规程 v0.13》的实际需求，Harness Engineering 的核心价值不是"自动化回归测试"（AutoResearch 已经做了），而是：

### 4.1 大规模批量评价引擎

**功能**：
```bash
# 一键跑 2000 篇论文 × 1 框架 × 3 模型
python scripts/harness_batch_run.py \
    --framework configs/frameworks/law-v2.42-20260507.yaml \
    --papers raw/三大刊2000篇/ \
    --models gpt-5.4,kimi-k2.6,glm-5.1 \
    --output results/batch-2000-papers-v2.42.jsonl \
    --parallel 10  # 并发数
```

**收益**：
- 从"手动跑单篇"到"自动跑 2000 篇"
- 支持断点续传（跑到一半挂了，可以继续）
- 自动生成"预检分布报告"（明显不适格 X%、边界 Y%、进入六维 Z%）
- 支持并发控制（避免 API 限流）

**技术要点**：
- 使用 `asyncio` 并发调用多个模型
- 使用 `jsonlines` 格式存储结果（支持流式写入，断点续传）
- 使用 `tqdm` 显示进度条
- 使用 `tenacity` 处理 API 重试

---

### 4.2 预检门槛校准工具

**功能**：
```bash
# 自动生成预检校准报告
python scripts/harness_precheck_calibration.py \
    --input results/batch-2000-papers-v2.42.jsonl \
    --output results/precheck-calibration-report.html
```

**输出报告包含**（对应附录A.3）：
1. **预检排除率**：明显不适格的比例
2. **预检误判率**：被排除但实际适格的比例（目标<20%）
3. **预检漏判率**：未被排除但实际不适格且六维未识别的比例（目标<5%）
4. **边界复核率**：边界进入评分并建议复核的比例

**按"明显不适格原因"分组统计**：
- 完全不涉及中国问题
- 完全没有法学问题
- 缺少转化动作或可复核命题

**按"年份、期刊、领域"分层抽样**：
- 自动生成"需要人工确认的 20 篇论文清单"
- 确保不同年份、期刊、领域都有覆盖

**自动识别误判风险**：
- 仅因"使用西方理论"而被误判"明显不适格"的论文
- 仅因"未直接使用自主知识体系表述"而被误判的论文
- 传统法教义学好论文被误判的情况

**收益**：
- 从"手动统计"到"自动生成报告"
- 快速定位"预检门槛是否过宽或过窄"
- 支持"迭代优化预检规则"

---

### 4.3 候选池管理系统

**功能**：
```bash
# 第一阶段：AI 初筛，生成候选池
python scripts/harness_stage1_filter.py \
    --input results/batch-2000-papers-v2.42.jsonl \
    --output results/stage1-candidates.json \
    --rules "总分>70 或 (总分>60 且自主知识体系信号强)"

# 第二阶段：引文分析（需要外部引文数据）
python scripts/harness_stage2_citation.py \
    --input results/stage1-candidates.json \
    --citation-db data/citations.db \
    --output results/stage2-candidates.json

# 第三阶段：专家终审界面（Web UI）
python scripts/harness_stage3_expert_review.py \
    --input results/stage2-candidates.json \
    --port 8080
```

**收益**：
- 从"手动筛选"到"自动化三阶段流水线"
- 追踪"每篇论文在哪个阶段、为什么被保留/排除"
- 支持"专家调入引文量不高但创新性极强的论文"（对应附录B.3）

**技术要点**：
- 使用 SQLite 存储候选池状态（论文ID、阶段、分数、信号、保留/排除原因）
- 使用 FastAPI 构建专家复核界面
- 支持"按总分 + 自主知识体系信号"自动分档

---

### 4.4 质量保障工具

**功能**：
```bash
# 自动生成"按年份、期刊、领域分层抽样"的 20 篇论文清单
python scripts/harness_quality_check.py \
    --excluded results/stage1-excluded.json \
    --sample-size 20 \
    --stratify-by year,journal,field \
    --output results/quality-check-sample.json
```

**收益**：
- 从"手动分层抽样"到"自动生成清单"
- 确保"不同年份、期刊、领域"都有覆盖
- 支持"如发现遗漏风险，扩大抽查"（对应附录B.5）

**技术要点**：
- 使用 `scikit-learn.StratifiedShuffleSplit` 进行分层抽样
- 需要先给样本集加元数据（`raw/metadata.yaml`）

---

## 5. 实施建议

### 5.1 短期（1-2 周）

**优先级 1：大规模批量评价引擎**
- 实现 `scripts/harness_batch_run.py`
- 支持断点续传、并发控制、进度显示
- 输出格式：JSONL（每行一篇论文的评价结果）

**优先级 2：预检门槛校准工具**
- 实现 `scripts/harness_precheck_calibration.py`
- 自动生成 HTML 报告（对应附录A）
- 支持"按年份、期刊、领域分层抽样"

**优先级 3：样本集元数据**
- 给 `raw/` 下的论文加元数据（`metadata.yaml`）
- 记录：年份、期刊、领域、作者、标题

---

### 5.2 中期（1 个月）

**优先级 4：第一阶段筛选工具**
- 实现 `scripts/harness_stage1_filter.py`
- 支持"按总分 + 自主知识体系信号"自动分档
- 输出：高分候选、重点候选、边界候选

**优先级 5：质量保障工具**
- 实现 `scripts/harness_quality_check.py`
- 自动生成"需要人工确认的 20 篇论文清单"

**优先级 6：集成到 AutoResearch**
- 让 AutoResearch 在迭代框架时，自动跑预检校准
- 自动生成"v2.40 vs v2.42"的对比报告

---

### 5.3 长期（3 个月）

**优先级 7：候选池管理系统**
- 使用 SQLite 存储候选池状态
- 追踪"每篇论文在哪个阶段、为什么被保留/排除"

**优先级 8：专家复核界面**
- 使用 FastAPI + React 构建 Web UI
- 支持"专家调入/调出论文"
- 支持"专家标注、评论、投票"

**优先级 9：引文分析集成**
- 接入外部引文数据库（如 CNKI）
- 计算"年均引文量、引文质量、引文语境"
- 实现 `scripts/harness_stage2_citation.py`

---

## 6. 技术架构建议

### 6.1 目录结构

```
scripts/
  harness/
    __init__.py
    batch_runner.py          # 批量评价引擎
    precheck_calibration.py  # 预检门槛校准
    stage1_filter.py         # 第一阶段筛选
    stage2_citation.py       # 第二阶段引文分析
    stage3_expert_review.py  # 第三阶段专家复核
    quality_check.py         # 质量保障工具
    candidate_pool.py        # 候选池管理（SQLite）
    metadata_manager.py      # 样本集元数据管理

results/
  batch-runs/              # 批量评价结果（JSONL）
  calibration-reports/     # 预检校准报告（HTML）
  candidate-pools/         # 候选池状态（SQLite）
  quality-checks/          # 质量保障清单（JSON）

raw/
  metadata.yaml            # 样本集元数据（年份、期刊、领域）
  calibration-regression/
  holdout-test/
  validation/
  三大刊2000篇/            # 待评价的 2000 篇论文
```

### 6.2 数据格式

**批量评价结果（JSONL）**：
```json
{
  "paper_id": "司法公正与同理心正义_杜宴林",
  "file_path": "raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf",
  "framework_version": "law-v2.42-20260507",
  "models": ["gpt-5.4", "kimi-k2.6", "glm-5.1"],
  "precheck": {
    "conclusion": "enter_six_dimension_review",
    "triggered_signals": {...}
  },
  "dimensions": {
    "problem_originality": {"mean": 75, "std": 4.2, "scores": [73, 75, 77]},
    "literature_insight": {"mean": 70, "std": 3.8, "scores": [68, 70, 72]},
    ...
  },
  "total_score": {"mean": 72, "std": 3.5},
  "autonomous_knowledge_signals": {...},
  "review_status": "no_review_needed",
  "timestamp": "2026-05-08T10:30:00Z"
}
```

**样本集元数据（YAML）**：
```yaml
papers:
  - filename: 司法公正与同理心正义_杜宴林.pdf
    title: 司法公正与同理心正义
    author: 杜宴林
    year: 2020
    journal: 中国法学
    field: 法理学
    tags: [理论型, 跨学科]
    notes: 用于验证"跨学科概念转化"的评分稳定性
```

---

## 7. 总结

### 7.1 核心结论

**`configs/frameworks/` + AutoResearch 已经是一个"评价框架迭代 Harness"。**

但基于《评审规程 v0.13》的实际需求（2000 篇论文 + 三阶段筛选 + 预检校准），你们现在需要的是：

1. **大规模批量评价 Harness**（2000 篇论文）
2. **预检门槛校准 Harness**（对应附录A）
3. **三阶段筛选 Harness**（对应附录B）
4. **质量保障 Harness**（分层抽样、遗漏检测）

### 7.2 Harness Engineering 的核心价值

**把"手动执行规程"变成"自动化工具链"**，让你们能高效完成"2000 篇论文 → 10 篇代表性论文"的三阶段筛选。

### 7.3 下一步行动

建议优先实现：
1. `scripts/harness_batch_run.py`（批量评价引擎）
2. `scripts/harness_precheck_calibration.py`（预检门槛校准）
3. 给样本集加元数据（`raw/metadata.yaml`）

这三个工具能让你们先尝到"批量评价 + 预检校准"的甜头，验证 Harness Engineering 的价值。

---

**文档结束**
