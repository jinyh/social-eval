# 已废弃的 Agent Skills - 2026-06-01

## socialeval-convergence-report-export

**废弃原因：**
1. 核心文件已归档：`results/convergence-test-*.json` 已全部归档到 `results/archive/convergence-tests/`
2. 功能已被替代：Phase 2 全量评审使用 `fullevaluation/` 的新格式
3. 维度命名已更新：Skill 中使用旧维度名称，当前标准命名是中文
4. 使用场景已消失：convergence-test 格式的 JSON 已不再生成

**脚本状态：**
- `scripts/export_convergence_reports.py` 仍保留在项目中
- 可用于导出归档的 convergence-test JSON（如需要）

**替代方案：**
- 当前使用 `generate_round2_markdown_report.py` 等新脚本
- Phase 2 评审结果在 `results/fullevaluation/`

**归档时间：** 2026-06-01
