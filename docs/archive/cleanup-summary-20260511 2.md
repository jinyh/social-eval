# SocialEval 项目清理总结

## 清理时间
2026-05-11

## 归档文件统计

### 1. results/archive/
- **convergence-tests/** (56 个文件)
  - 收敛性测试结果 (v2.8 - v2.31)
  - 诊断测试文件 (diag-zhang-v217-*.json)
  - 基线测试文件 (baseline-v2.20.json)
  - 单维度测试 (v2.15-*.json)

- **model-tests/** (11 个文件)
  - DeepSeek、GPT-5.4、Kimi 等模型测试
  - 端到端管道测试 (e2e-real-pipeline-*.json)
  - 回归测试 (regression-v2.42-sample1.json)
  - 组合模型测试 (test-4models.json, test-composite.json)

- **v0.14-tests/** (8 个文件/目录)
  - v0.14 版本批量测试 (v0.14-batch-test/)
  - 烟雾测试 (v0.14-smoke-*.json)
  - 分层测试 (v0.14-v2.44-layered-smoke*.json)
  - GLM-Qwen 测试 (v0.14-glm-qwen-v2.44/)

- **v0.15-tests/** (2 个文件/目录)
  - v0.15 版本批量测试 (v0.15-batch/)
  - 烟雾测试 (v0.15-smoke-许可.json)

### 2. scripts/archive/
- **model-tests/** (7 个脚本)
  - compare_model_combinations.py
  - diagnose_glm51.py
  - test_4models.sh
  - test_deepseek_dashscope.py
  - test_deepseek_variants.py
  - test_gpt54_stability.py
  - test_kimi_k26.py

- **provider-tests/** (11 个脚本)
  - diagnose_sss_detailed.py
  - diagnose_sss_provider.py
  - show_sss_config.py
  - test_ketan_provider.py
  - test_sss_final.py
  - test_sss_provider.py
  - test_sss_simple.py
  - test_sss_with_models.py
  - test_yunyi_provider.py
  - trace_sss_api.py
  - verify_sss_sync.py

### 3. docs/evaluation/archive/v0.8-v0.14/
- law-ai-assisted-review-rules-v0.8-20260425.md/pdf
- law-ai-assisted-review-rules-v0.9-20260507.md
- law-ai-assisted-review-rules-v0.13-expert-edition.md/pdf
- law-ai-assisted-review-rules-v0.14-expert-edition.md/pdf
- law-ai-assisted-review-rules-v0.14-expert-response-20260509.md/pdf
- law-ai-assisted-review-rules-v0.14-review-notes-20260508.md

共 10 个文件，包含专家版本和专家反馈文档。

### 4. docs/archive/
- 20260508_harness-engineering-analysis.md（临时分析文档）
- sss-provider-test-summary.md（供应商测试总结）

### 5. results/autoresearch/archive/
- **quick-verify/** (22 个快速验证测试)
  - quick-verify-20260425-*.json (从 001455 到 162722)

- **v2.32-v2.40/** (40 个历史版本测试)
  - v2.32-v2.40 各版本的 full/retest 测试
  - holdout-v2.40-*.json (4 个冻结测试集)

- **日志和计划文档**
  - autoresearch-deepseek-v4-log.tsv
  - iteration-2-plan.md
  - iteration-3-plan.md
  - iteration-log-20260425.md
  - session-summary-20260425.md
  - strategy-summary.md

## 保留的活跃文件

### results/
- 评价报告 PDF (6 个)
  - 国体的起源、构造和选择_佀化强_评价.pdf
  - 司法公正与同理心正义_杜宴林_评价.pdf
  - 比例原则在民法上的适用及展开_郑晓剑_评价.pdf
  - 及其模型匿名版本
- 论文评价格式.md
- autoresearch/ (当前活跃测试)
  - autoresearch-log-20260425-090828.tsv
  - autoresearch-log.tsv
  - verify-v2.41-jiangge.json
  - verify-v2.42-jiangge.json
  - stability-test/
- reflection-report-v2.17.0-20260424-080450.md

### scripts/
- analyze_iteration.py
- dashboard.py
- export_convergence_reports.py
- full_verify.sh / quick_verify.sh
- generate_legal_ai_review_retro_deck.py
- generate_socialeval_presentation.js
- install_project_skills.py
- regression_v2.42_vs_v2.43.py
- rubric_reflector.py
- run_convergence_test.py
- run_v0.14_multi_model_test.py
- run_v0.14_test.sh
- codex-review-v246-framework.md

### docs/evaluation/
- 当前活跃版本：
  - law-ai-assisted-review-rules-v0.15-phase1-test-report.md
  - law-ai-assisted-review-rules-v0.16-large-scale-candidate.md
- 方法论文档：
  - concept-operationalization-v1.0.md
  - std-analysis-summary-20260423.md
  - v0.15-phase1-test-report-20260511.md

## 归档原则

1. **测试结果**：v2.8 - v2.40 的历史测试结果全部归档
2. **临时脚本**：供应商和模型诊断脚本归档，保留核心工具脚本
3. **文档版本**：v0.8 - v0.14 的评审规则归档，保留当前活跃版本（v0.15, v0.16）
4. **保留标准**：
   - 当前活跃版本 (v0.15, v0.16, v2.45, v2.46)
   - 核心工具脚本（analyze, dashboard, export, verify, run）
   - 最终评价报告 PDF

## 清理效果

- **归档文件总数**：约 182 个
- **results/ 目录**：从 163 个 JSON 文件减少到 0 个（活跃测试在 autoresearch/）
- **scripts/ 目录**：从 32 个脚本减少到 14 个核心脚本
- **文档目录**：结构更清晰，历史版本统一归档

## 查找归档文件

```bash
# 查看归档目录结构
tree -L 2 results/archive/ scripts/archive/ docs/evaluation/archive/

# 搜索特定版本的测试结果
find results/archive/ -name "*v2.30*"

# 搜索特定模型的测试脚本
find scripts/archive/ -name "*deepseek*"

# 查看某个归档目录的文件列表
ls -lh results/archive/convergence-tests/

# 统计归档文件数量
find results/archive/ -type f | wc -l
find scripts/archive/ -type f | wc -l
```

## 注意事项

1. **归档文件不删除**：所有归档文件仍保留在仓库中，只是移动到 archive/ 目录
2. **Git 历史保留**：归档操作不影响 Git 历史，可以通过 git log 追溯文件变更
3. **恢复方法**：如需恢复某个归档文件，直接从 archive/ 目录移回原位置即可
4. **定期清理**：建议每个大版本迭代后（如 v0.16 → v0.17）进行一次归档清理

## 后续建议

1. **测试结果命名**：建议统一测试结果文件命名格式，如 `{version}-{test-type}-{sample}-{timestamp}.json`
2. **自动归档**：可考虑编写脚本自动归档 N 天前的测试结果
3. **归档文档**：重要的归档文件应在 CLAUDE.md 中记录归档原因和位置
4. **定期审查**：每季度审查一次归档目录，删除确认不再需要的文件
