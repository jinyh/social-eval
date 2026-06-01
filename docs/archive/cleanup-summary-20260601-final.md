# SocialEval 项目大规模清理归档总结 - 2026-06-01

## 执行概述

本次清理采用**激进归档策略**：仅保留最终成果，所有中间迭代全部归档。

## 清理成果

### 空间节省
- **预计节省**：~120MB
- **系统生成物**：~50MB（.DS_Store, __pycache__, .pytest_cache, .ruff_cache, .cache）
- **原始数据迭代**：~5MB（phase1-100-papers, phase1-30-papers, sample）
- **评审结果迭代**：~70MB（Phase 1/2/3 所有迭代）
- **autoresearch 历史**：~2.7MB（v2.47 测试结果）
- **脚本**：~5MB（~80 个迭代脚本）
- **文档**：~10MB（~40 个历史文档）
- **PDF 报告**：~1.3MB（6 个根目录评价报告）

### 目录简化

**原始数据（raw/）：10 个目录 → 5 个**
- ✅ 保留：fullpaper, calibration-regression, holdout-test, validation, top30_paper
- 📦 归档：phase1-100-papers, phase1-30-papers, sample

**评审结果（results/）：45 个目录/文件 → 3 个**
- ✅ 保留：fullevaluation, merged-metadata.csv, autoresearch/v2.56
- 📦 归档：所有 Phase 1/2/3 迭代、重测、临时分析文件、PDF 报告

**脚本（scripts/）：110 个文件 → 17 个**
- ✅ 保留：analyze_strictest_results.py, analyze_test_10_results.py, dashboard.py, evaluate_top30_signals.py, export_convergence_reports.py, full_verify.sh, generate_final_top20.py, generate_legal_ai_review_retro_deck.py, generate_paper_list.py, generate_paper_metadata.py, generate_round2_markdown_report.py, generate_socialeval_presentation.js, install_project_skills.py, phase2_batch_two_rounds.py, phase2_evaluate.py, quick_verify.sh, rubric_reflector.py
- 📦 归档：~80 个迭代/测试/诊断脚本

**文档（docs/evaluation/）：55 个文件 → 2 个**
- ✅ 保留：concept-operationalization-v1.0.md, v0.15-phase1-test-report-20260511.md
- 📦 归档：所有历史版本文档、参考文档、autoresearch 配置文档

---

## 归档详情

### 阶段 1：删除系统生成物 ✅
- `.DS_Store` 文件
- `__pycache__/` 和 `*.pyc`
- `.pytest_cache/`, `.ruff_cache/`, `.cache/`
- macOS 冲突副本（已在之前清理）

### 阶段 2：归档原始数据 ✅
**归档位置**：`raw/archive/phase1-papers-20260601/`
- `phase1-100-papers/` - 100 篇论文（已有评审结果）
- `phase1-30-papers/` - 30 篇论文（已有评审结果）
- `sample/` - 样本论文（已完成测试）

### 阶段 3：归档评审结果 ✅
**归档位置 1**：`results/archive/phase1-2-3-iterations-20260601/`
- **Phase 1 迭代（6 个）**：
  - phase1-100-papers (3.2M)
  - phase1-100-papers-cross-review (6.0M)
  - phase1-100-papers-strictest (6.2M)
  - phase1-30-papers (868K)
  - phase1-30-papers-backup (200K)
  - phase1-cross-review-test (188K)

- **Phase 2 迭代（被 fullevaluation 完全替代）**：
  - phase2-1849-papers (21M)
  - phase2-1849-papers-test (340K)
  - phase2-test-10 (1.2M)
  - phase2-test-10-papers.json (4K)
  - phase2-paper-list.json (444K)
  - phase2-paper-list-cleaned.json (440K)
  - phase2-paper-metadata-summary.md (4K)
  - phase2-metadata-*.csv (3 个文件，2.1M)

- **Phase 3 迭代**：
  - phase3-evaluation (12M)
  - phase3-paper-list*.json (56K)
  - phase3-paper-list-cleaning-report.md (4K)

- **重测目录**：
  - retest-7papers (960K)
  - retest-top60 (8.1M)
  - single-paper-test-032 (120K)

- **临时分析文件**：
  - cross-review-enhanced-analysis.json (356K)
  - cross-review-test-analysis.json (8K)
  - round2-full-report.md (18K)
  - paper-list.json (716K)
  - reflection-report-v2.17.0-20260424-080450.md
  - paper-list-cleaning-report.md
  - top30-knowledge-matching-v2.csv
  - top30-signals/

- **根目录 PDF 评价报告（6 个，~1.3MB）**：
  - 国体的起源、构造和选择_中西暗合与差异_佀化强_评价*.pdf (2 个)
  - 司法公正与同理心正义_杜宴林_评价*.pdf (2 个)
  - 比例原则在民法上的适用及展开_郑晓剑_评价*.pdf (2 个)

- **已删除**：
  - merge_cache/

**归档位置 2**：`results/archive/autoresearch-history-20260601/`
- v2.47-*.json (~30 个文件)
- quick-verify-*.json (3 个)
- verify-v2.*.json (2 个)
- autoresearch-log-*.tsv (2 个)
- stability-test/
- autoresearch-v2.51/ - v2.51 失败版本

### 阶段 4：归档脚本 ✅
**归档位置**：`scripts/archive/iterations-and-tests-20260601/`

**分析脚本（~15 个）**：
- analyze_autoresearch_progress.py
- analyze_cross_review*.py (2 个)
- analyze_high_*.py (2 个)
- analyze_precheck_*.py (2 个)
- analyze_round2_distribution.py
- compare_phase1_results.py
- compare_v2.*.py (所有版本对比)

**测试/诊断脚本（~40 个）**：
- test_*.py
- check_*.py
- debug_*.py
- diagnose_*.py
- find_*.py
- extract_*.py
- benchmark_*.py

**Phase/Run 脚本（~15 个）**：
- phase1_*.py (6 个)
- phase2_test_10_papers.py
- run_convergence_test.py
- run_cross_review.py
- run_phase3.fish
- visualize_phase1_model_scores.py

**生成/导出脚本（~10 个）**：
- select_10_papers_for_test.py
- export_phase1_100_report.py
- generate_phase2_summary.py
- generate_phase3_summary.py
- generate_round1_err_2_5_report.py
- clean_paper_list.py

**其他迭代脚本（~20 个）**：
- analyze_iteration.py
- list_papers_with_reject.py
- match_*.py (5 个)
- merge, merge_three_evaluations.py
- organize_round1_errors.py
- patch_*.py (6 个)
- remove_err_papers_from_round1.py
- retest_*.py (2 个)
- selective_retest_top30.py
- test_v2.56.*.sh (2 个)
- visualize_*.py (2 个)
- quick_verify_v2.56.sh
- scripts/ (目录)

### 阶段 5：归档文档 ✅

**归档位置 1**：`docs/evaluation/archive/v2.19-v2.51-iterations-20260601/`
- v2.19-vs-v2.20-comparison.md
- v2.42-to-v2.43-alignment-20260508.md
- v2.47-*.md (3 个)
- v2.48-*.md (4 个)
- v2.49-*.md (4 个)
- v2.51-*.md (2 个)
- v0.14-*.md (4 个)
- consistency-verification-v2.19-v0.6.md
- convergence-test-history-20260423.md
- holdout-v2.40-stability-test-20260426.md

**归档位置 2**：`docs/evaluation/archive/reference-20260601/`
- validation-sample-plan-20260425.md
- pattern-redesign-analysis.md
- citalaw-paper-analysis.md
- scite-api-evaluation.md
- sample-papers-database-schema.md
- legal-paper-six-dimensions-guide.md
- law-framework-v2.2-research-notes.md
- how-to-use-law-v2-config.md
- README-20260423.md

**归档位置 3**：`docs/evaluation/archive/autoresearch-20260601/`
- autoresearch-config-domestic-models.md
- autoresearch-environment-ready.md
- autoresearch-feasibility-analysis.md
- autoresearch-round1-launch.md
- autoresearch-setup-guide.md
- autoresearch-v2.56-config.md

**归档位置 4**：`docs/archive/completed-projects-20260601/`
- design/
- discussion/
- presentations/
- specs/
- superpowers/
- SocialEval-current-user-manual-2026-04-21.md

---

## 保留的最终成果

### 配置文件（configs/frameworks/）
```
law-v2.56.6-20260522.yaml   # Phase 2 Round 1 生产 prompt
law-v2.55-cross-review.yaml  # 交叉评审版本
law-v2.50.2-20260514.yaml    # 历史基线
schema_v2.json               # 生产 schema
archive/                     # 历史版本归档
```

### 原始数据（raw/）
```
fullpaper/              # 1920 篇 PDF（Phase 2 全量评审）
calibration-regression/ # 3 篇校准/回归集
holdout-test/           # 4 篇冻结测试集
validation/             # 8 篇最终验证集
top30_paper/            # 30 篇 top 论文
archive/                # 历史原始数据归档
```

### 评审结果（results/）
```
fullevaluation/         # Phase 2 全量评审最终成果（1913 篇 round2）
merged-metadata.csv     # 1962 条论文元数据
autoresearch/
  v2.56/                # v2.56 迭代结果
  archive/              # 历史 autoresearch 归档
archive/                # 历史评审结果归档
```

### 脚本（scripts/）17 个核心工具
```
analyze_strictest_results.py
analyze_test_10_results.py
dashboard.py
evaluate_top30_signals.py
export_convergence_reports.py
full_verify.sh
generate_final_top20.py
generate_legal_ai_review_retro_deck.py
generate_paper_list.py
generate_paper_metadata.py
generate_round2_markdown_report.py
generate_socialeval_presentation.js
install_project_skills.py
phase2_batch_two_rounds.py
phase2_evaluate.py
quick_verify.sh
rubric_reflector.py
archive/                # 历史脚本归档
```

### 文档（docs/）
```
requirements/
  SocialEval-requirements-v0.4.md
architecture/
  20260414_ADR-001_evaluation-framework-v2.md
  SocialEval-mvp-cloud-sizing.md
deployment/
  (5 个部署文档)
usage/
  phase1-100-papers-strictest-guide.md
evaluation/
  concept-operationalization-v1.0.md
  v0.15-phase1-test-report-20260511.md
  archive/              # 历史文档归档
archive/                # 已完成项目归档
```

---

## 恢复方式

### 恢复历史配置
```bash
# 从归档目录复制回顶层
cp configs/frameworks/archive/v2.0-v2.54-20260522/law-v2.47-20260511.yaml configs/frameworks/
```

### 恢复历史评审结果
```bash
# 查看 Phase 1 迭代
ls results/archive/phase1-2-3-iterations-20260601/phase1-100-papers/

# 查看 autoresearch v2.47 结果
ls results/archive/autoresearch-history-20260601/
```

### 恢复历史脚本
```bash
# 执行归档的脚本
python scripts/archive/iterations-and-tests-20260601/analyze_cross_review.py
```

### 恢复历史文档
```bash
# 查看历史评审规则
cat docs/evaluation/archive/v0.1-v0.15-iterations-20260601/law-ai-assisted-review-rules-v0.12-20260507.md
```

---

## 验证清理结果

```bash
# 查看保留的配置文件
ls -lh configs/frameworks/*.yaml

# 查看保留的原始数据
ls -1 raw/ | grep -v archive

# 查看保留的评审结果
ls -1 results/ | grep -v archive

# 查看保留的脚本
ls -1 scripts/ | grep -v archive | wc -l

# 查看保留的文档
find docs -maxdepth 2 -type f -name "*.md" | grep -v archive | wc -l
```

---

## 注意事项

1. **所有归档操作都是移动而非删除**，可随时恢复
2. **fullevaluation 是 Phase 2 最终成果**，完全替代了所有 Phase 1/2 迭代
3. **v2.56.6 是当前生产 prompt**，v2.55 用于交叉评审，v2.50.2 是历史基线
4. **核心脚本保留 17 个**，足够日常分析、生成、评估、验证使用
5. **文档只保留当前活跃版本**，历史版本全部归档

---

## 后续建议

1. **定期清理**：每次大版本迭代后，及时归档中间版本
2. **命名规范**：新增测试结果使用日期后缀（如 `test-YYYYMMDD`）
3. **归档标准**：只保留最终成果，中间迭代立即归档
4. **文档维护**：更新 CLAUDE.md 的归档策略章节
