# SocialEval 项目清理归档计划

## 当前状态分析

### 1. 配置文件（configs/frameworks/）
**保留（生产版本）：**
- `law-v2.56.6-20260522.yaml` - Phase 2 Round 1 生产 prompt（六维锚定规则）
- `law-v2.55-cross-review.yaml` - 交叉评审版本（Round 2 用）
- `law-v2.50.2-20260514.yaml` - 嵌入评分步骤（历史基线）
- `schema_v2.json` - 生产 schema

**已归档：**
- `archive/v2.0-v2.54-20260522/` - 59 个历史版本
- `archive/schemas/` - 历史 schema

### 2. 原始数据（raw/）
**保留（全部真源）：**
- `fullpaper/` - 1920 篇 PDF（Phase 2 全量评审）
- `calibration-regression/` - 3 篇校准/回归集
- `holdout-test/` - 4 篇冻结测试集
- `validation/` - 8 篇最终验证集
- `top30_paper/` - 30 篇 top 论文
- `sample/` - 样本论文

**可归档：**
- `phase1-100-papers/` - 已被 results/phase1-100-papers/ 评审完成
- `phase1-30-papers/` - 已被 results/phase1-30-papers/ 评审完成

### 3. 评审结果（results/）
**保留（最新成果）：**
- `fullevaluation/` - Phase 2 全量评审结果（1913 篇 round2 + 64 篇 round1-err）
- `merged-metadata.csv` - 1962 条论文元数据
- `phase1-100-papers-strictest/` - Phase 1 最严格版本评审
- `autoresearch/v2.56/` - v2.56 迭代结果
- `retest-top60/` - Top 60 重测结果
- `phase3-evaluation/` - Phase 3 评估结果

**可归档：**
- `phase1-100-papers/` - 被 phase1-100-papers-strictest 替代
- `phase1-100-papers-cross-review/` - 交叉评审测试（已完成）
- `phase1-30-papers/` - 早期 30 篇测试
- `phase1-30-papers-backup/` - 备份
- `phase1-cross-review-test/` - 交叉评审测试
- `phase2-test-10/` - 10 篇测试（已完成）
- `phase2-1849-papers/` - 被 fullevaluation 替代
- `phase2-1849-papers-test/` - 测试目录
- `retest-7papers/` - 7 篇重测
- `autoresearch/` 下的历史测试文件（v2.47 相关）
- `autoresearch-v2.51/` - v2.51 失败版本
- 根目录下的 PDF 评价报告（6 个）
- 各种临时分析 JSON 文件

**已归档：**
- `archive/` - 251M 历史测试结果

### 4. 脚本（scripts/）
**保留（核心工具）：**
- `analyze_*.py` - 分析脚本（10+ 个）
- `generate_*.py` - 生成脚本（10+ 个）
- `dashboard.py` - 仪表板
- `export_*.py` - 导出脚本
- `full_verify.sh` / `quick_verify.sh` - 验证脚本
- `evaluate_top30_signals.py` - Top 30 评估
- `phase2_*.py` - Phase 2 相关脚本
- `rubric_reflector.py` - Rubric 反思工具

**可归档：**
- 所有 `apply_v2.*.py` - 历史版本应用脚本
- 所有 `test_*.py` - 测试脚本（非核心）
- 所有 `compare_v2.*.py` - 版本对比脚本
- 所有 `run_v0.14_*.py` - v0.14 测试脚本
- 所有 `run_convergence_test_*.py` - 收敛性测试脚本
- `batch_*.py` - 批量测试脚本
- `debug_*.py` - 调试脚本
- `diagnose_*.py` - 诊断脚本
- `check_*.py` - 检查脚本（非核心）
- `find_*.py` - 查找脚本（非核心）
- `extract_*.py` - 提取脚本（非核心）
- `benchmark_*.py` - 基准测试脚本
- `clean_paper_list.py` - 一次性清理脚本
- `regression_*.py` - 回归测试脚本

**已归档：**
- `archive/experiments-20260601/` - 15 个实验脚本
- `archive/model-tests/` - 7 个模型测试脚本
- `archive/provider-tests/` - 11 个供应商测试脚本

### 5. 文档（docs/）
**保留（当前活跃）：**
- `requirements/SocialEval-requirements-v0.4.md` - 当前需求文档
- `architecture/` - 架构决策记录
- `evaluation/law-ai-assisted-review-rules-v0.16-large-scale-candidate.md` - 当前评审规则
- `evaluation/concept-operationalization-v1.0.md` - 概念操作化
- `evaluation/std-analysis-summary-20260423.md` - 标准差分析
- `evaluation/v0.15-phase1-test-report-20260511.md` - v0.15 测试报告
- `evaluation/v2.51-phase0-failure-report.md` - v2.51 失败报告
- `evaluation/v2.56.6-20260522.yaml` 相关文档
- `deployment/` - 部署文档
- `usage/` - 使用指南

**可归档：**
- `evaluation/law-ai-assisted-review-rules-v0.1-v0.7.md` - 历史评审规则（v0.8-v0.14 已归档）
- `evaluation/law-ai-assisted-review-rules-v0.10-v0.12.md` - 中间版本
- `evaluation/law-ai-assisted-review-rules-v0.15-expert-edition.md` - 专家版（非当前）
- `evaluation/law-scoring-rules-v0.1-v0.2.md` - 历史评分规则
- `evaluation/v2.19-vs-v2.20-comparison.md` - 历史版本对比
- `evaluation/v2.42-to-v2.43-alignment-20260508.md` - 历史对齐文档
- `evaluation/v2.47-*.md` - v2.47 相关文档（非当前）
- `evaluation/v2.48-*.md` - v2.48 相关文档（非当前）
- `evaluation/v2.49-*.md` - v2.49 相关文档（非当前）
- `evaluation/v0.14-*.md` - v0.14 相关文档
- `evaluation/autoresearch-*.md` - autoresearch 配置文档（已完成）
- `evaluation/consistency-verification-v2.19-v0.6.md` - 历史一致性验证
- `evaluation/convergence-test-history-20260423.md` - 收敛性测试历史
- `evaluation/holdout-v2.40-stability-test-20260426.md` - v2.40 稳定性测试
- `evaluation/validation-sample-plan-20260425.md` - 验证样本计划（已完成）
- `evaluation/pattern-redesign-analysis.md` - 模式重设计分析
- `evaluation/citalaw-paper-analysis.md` - 引用分析
- `evaluation/scite-api-evaluation.md` - Scite API 评估
- `evaluation/sample-papers-database-schema.md` - 样本论文数据库 schema
- `evaluation/legal-paper-six-dimensions-guide.md` - 六维度指南（已被 v0.16 替代）
- `evaluation/law-framework-v2.2-research-notes.md` - v2.2 研究笔记
- `evaluation/how-to-use-law-v2-config.md` - 配置使用指南（已过时）
- `evaluation/README-20260423.md` - 历史 README
- `design/` - 设计文档（已完成）
- `discussion/` - 讨论记录（已完成）
- `presentations/` - 演示文档（历史）
- `specs/` - 规格文档（已完成）
- `superpowers/` - Superpowers 配置（已完成）
- `SocialEval-current-user-manual-2026-04-21.md` - 历史用户手册

**已归档：**
- `archive/` - 历史需求、规划、分析文档
- `evaluation/archive/v0.8-v0.14/` - v0.8-v0.14 评审规则

---

## 清理归档方案

### 阶段 1：删除系统生成物
- `.DS_Store`
- `__pycache__/`
- `*.pyc`
- `.pytest_cache/`
- `.ruff_cache/`
- `.cache/`
- macOS 冲突副本（`* 2.*` / `* 2`）

### 阶段 2：归档原始数据
创建 `raw/archive/phase1-papers-20260601/`：
- `phase1-100-papers/` → `raw/archive/phase1-papers-20260601/phase1-100-papers/`
- `phase1-30-papers/` → `raw/archive/phase1-papers-20260601/phase1-30-papers/`

### 阶段 3：归档评审结果
创建 `results/archive/phase1-phase2-tests-20260601/`：
- `phase1-100-papers/` → `results/archive/phase1-phase2-tests-20260601/phase1-100-papers/`
- `phase1-100-papers-cross-review/` → `results/archive/phase1-phase2-tests-20260601/phase1-100-papers-cross-review/`
- `phase1-30-papers/` → `results/archive/phase1-phase2-tests-20260601/phase1-30-papers/`
- `phase1-30-papers-backup/` → `results/archive/phase1-phase2-tests-20260601/phase1-30-papers-backup/`
- `phase1-cross-review-test/` → `results/archive/phase1-phase2-tests-20260601/phase1-cross-review-test/`
- `phase2-test-10/` → `results/archive/phase1-phase2-tests-20260601/phase2-test-10/`
- `phase2-1849-papers/` → `results/archive/phase1-phase2-tests-20260601/phase2-1849-papers/`
- `phase2-1849-papers-test/` → `results/archive/phase1-phase2-tests-20260601/phase2-1849-papers-test/`
- `retest-7papers/` → `results/archive/phase1-phase2-tests-20260601/retest-7papers/`
- `autoresearch-v2.51/` → `results/archive/phase1-phase2-tests-20260601/autoresearch-v2.51/`

创建 `results/archive/autoresearch-v2.47-20260601/`：
- `autoresearch/v2.47-*.json` → `results/archive/autoresearch-v2.47-20260601/`
- `autoresearch/quick-verify-*.json` → `results/archive/autoresearch-v2.47-20260601/`
- `autoresearch/verify-v2.41-*.json` → `results/archive/autoresearch-v2.47-20260601/`
- `autoresearch/verify-v2.42-*.json` → `results/archive/autoresearch-v2.47-20260601/`
- `autoresearch/autoresearch-log-*.tsv` → `results/archive/autoresearch-v2.47-20260601/`
- `autoresearch/stability-test/` → `results/archive/autoresearch-v2.47-20260601/stability-test/`

删除根目录 PDF 评价报告（已过时）：
- `国体的起源、构造和选择_中西暗合与差异_佀化强_评价*.pdf`
- `司法公正与同理心正义_杜宴林_评价*.pdf`
- `比例原则在民法上的适用及展开_郑晓剑_评价*.pdf`

删除临时分析文件：
- `cross-review-test-analysis.json`
- `cross-review-enhanced-analysis.json`
- `paper-list-cleaning-report.md`
- `phase2-paper-list.json`
- `phase2-paper-list-cleaned.json`
- `phase3-paper-list.json`
- `phase3-paper-list-cleaned.json`
- `phase3-paper-list-cleaning-report.md`
- `reflection-report-v2.17.0-20260424-080450.md`
- `round2-full-report.md`
- `phase2-paper-metadata-summary.md`
- `merge_cache/`

### 阶段 4：归档脚本
创建 `scripts/archive/framework-tests-20260601/`：
- 所有 `apply_v2.*.py`
- 所有 `test_*.py`（除了核心测试）
- 所有 `compare_v2.*.py`
- 所有 `run_v0.14_*.py`
- 所有 `run_convergence_test_*.py`
- `batch_*.py`
- `debug_*.py`
- `diagnose_*.py`
- `check_phase2_failures.py`
- `check_round1_err_dimensions.py`
- `find_all_reject_papers.py`
- `extract_top20_round2.py`
- `benchmark_matching_optimization.py`
- `clean_paper_list.py`
- `regression_*.py`
- `analyze_precheck_*.py`
- `analyze_high_*.py`
- `analyze_round2_distribution.py`
- `analyze_autoresearch_progress.py`
- `analyze_cross_review*.py`
- `compare_phase1_results.py`
- `compare_v2.55_v2.56.py`

### 阶段 5：归档文档
创建 `docs/evaluation/archive/v0.1-v0.15-20260601/`：
- `law-ai-assisted-review-rules-v0.1-v0.7.md`
- `law-ai-assisted-review-rules-v0.10-v0.12.md`
- `law-ai-assisted-review-rules-v0.15-expert-edition.md`
- `law-scoring-rules-v0.1-v0.2.md`

创建 `docs/evaluation/archive/v2.19-v2.51-20260601/`：
- `v2.19-vs-v2.20-comparison.md`
- `v2.42-to-v2.43-alignment-20260508.md`
- `v2.47-*.md`
- `v2.48-*.md`
- `v2.49-*.md`
- `v0.14-*.md`
- `consistency-verification-v2.19-v0.6.md`
- `convergence-test-history-20260423.md`
- `holdout-v2.40-stability-test-20260426.md`

创建 `docs/evaluation/archive/reference-20260601/`：
- `validation-sample-plan-20260425.md`
- `pattern-redesign-analysis.md`
- `citalaw-paper-analysis.md`
- `scite-api-evaluation.md`
- `sample-papers-database-schema.md`
- `legal-paper-six-dimensions-guide.md`
- `law-framework-v2.2-research-notes.md`
- `how-to-use-law-v2-config.md`
- `README-20260423.md`

创建 `docs/evaluation/archive/autoresearch-20260601/`：
- `autoresearch-*.md`

创建 `docs/archive/completed-20260601/`：
- `design/`
- `discussion/`
- `presentations/`
- `specs/`
- `superpowers/`
- `SocialEval-current-user-manual-2026-04-21.md`

---

## 保留的最终结构

### configs/frameworks/
```
law-v2.56.6-20260522.yaml
law-v2.55-cross-review.yaml
law-v2.50.2-20260514.yaml
schema_v2.json
archive/
  v2.0-v2.54-20260522/
  schemas/
```

### raw/
```
fullpaper/
calibration-regression/
holdout-test/
validation/
top30_paper/
sample/
archive/
  phase1-papers-20260601/
```

### results/
```
fullevaluation/
merged-metadata.csv
phase1-100-papers-strictest/
phase3-evaluation/
retest-top60/
paper-list.json
phase2-metadata-*.csv
autoresearch/
  v2.56/
  archive/
archive/
  phase1-phase2-tests-20260601/
  autoresearch-v2.47-20260601/
  (existing archives)
```

### scripts/
```
analyze_strictest_results.py
analyze_test_10_results.py
dashboard.py
evaluate_top30_signals.py
export_convergence_reports.py
export_phase1_100_report.py
full_verify.sh
generate_final_top20.py
generate_paper_list.py
generate_paper_metadata.py
generate_phase2_summary.py
generate_phase3_summary.py
generate_round1_err_2_5_report.py
generate_round2_markdown_report.py
install_project_skills.py
phase2_*.py
rubric_reflector.py
select_10_papers_for_test.py
test_single_paper_two_rounds.py
archive/
  framework-tests-20260601/
  experiments-20260601/
  model-tests/
  provider-tests/
```

### docs/
```
requirements/
  SocialEval-requirements-v0.4.md
architecture/
deployment/
usage/
evaluation/
  law-ai-assisted-review-rules-v0.16-large-scale-candidate.md
  concept-operationalization-v1.0.md
  std-analysis-summary-20260423.md
  v0.15-phase1-test-report-20260511.md
  v2.51-phase0-failure-report.md
  archive/
    v0.8-v0.14/
    v0.1-v0.15-20260601/
    v2.19-v2.51-20260601/
    reference-20260601/
    autoresearch-20260601/
archive/
  completed-20260601/
  (existing archives)
```

---

## 执行步骤

1. **删除系统生成物**（安全，可恢复）
2. **归档原始数据**（移动到 raw/archive/）
3. **归档评审结果**（移动到 results/archive/）
4. **归档脚本**（移动到 scripts/archive/）
5. **归档文档**（移动到 docs/evaluation/archive/ 和 docs/archive/）
6. **更新 CLAUDE.md**（更新归档说明）
7. **生成归档报告**（记录本次清理内容）

---

## 风险评估

### 低风险（可直接执行）
- 删除系统生成物
- 归档 Phase 1 原始论文（已有评审结果）
- 归档历史测试结果（已被新版本替代）
- 归档实验脚本（已完成实验）
- 归档历史文档（已被新版本替代）

### 中风险（需确认）
- 删除根目录 PDF 评价报告（确认无引用）
- 删除临时分析文件（确认无引用）
- 归档 autoresearch v2.47 结果（确认 v2.56 已替代）

### 高风险（需用户确认）
- 无

---

## 预期效果

### 空间节省
- 删除系统生成物：~50MB
- 归档原始数据：~100MB
- 归档评审结果：~50MB
- 归档脚本：~5MB
- 归档文档：~10MB
- **总计：~215MB**

### 目录简化
- scripts/：110 个文件 → ~20 个核心工具
- docs/evaluation/：55 个文件 → ~10 个当前文档
- results/：45 个目录/文件 → ~15 个当前成果

### 可维护性提升
- 清晰的"当前活跃"vs"历史归档"边界
- 更容易找到最新成果
- 更容易理解项目当前状态
