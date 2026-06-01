---
name: socialeval-convergence-report-export
description: 在 SocialEval 仓库内，将 results/convergence-test-*.json 评审结果按 results/论文评价格式.md 抽取并导出为 PDF；也用于调整这类 PDF 的横向排版、边距、页眉摘要、模型表格和字段显示。
---

# SocialEval Convergence Report Export

用于把 convergence test 结果 JSON 转成可阅读、可打印的论文评审 PDF。

## 触发场景

- 用户要求将 `convergence-test-*.json` 转换为 PDF。
- 用户提到“按 `论文评价格式.md` 抽取”“评审结果 PDF”“convergence report export”。
- 用户要求调整这类 PDF 的版式，例如 `landscape`、右侧留空、删除来源文件、摘要字段、表格列宽。

## 核心文件

- 输入模板参考：`results/论文评价格式.md`
- 输入数据：`results/convergence-test-*.json`
- 导出脚本：`scripts/export_convergence_reports.py`
- 默认输出：与输入同名的 `results/*.pdf`

## 工作流

1. 先确认输入 JSON 是否存在：

   ```bash
   rg --files results | rg 'convergence-test.*\.json$|论文评价格式\.md$'
   ```

2. 如仅需生成 PDF，直接运行：

   ```bash
   uv run python scripts/export_convergence_reports.py \
     results/convergence-test-full-v214.json \
     results/convergence-test-v214-biyuanze.json \
     results/convergence-test-v214-guoti.json
   ```

3. 如用户要求调整版式，只改 `scripts/export_convergence_reports.py` 中的 HTML/CSS 模板，避免改动 JSON 抽取逻辑，除非字段结构确实变化。

4. 生成后验证 PDF：

   ```bash
   uv run python - <<'PY'
   from pathlib import Path
   import fitz

   for path in Path("results").glob("convergence-test*.pdf"):
       doc = fitz.open(path)
       rect = doc[0].rect
       print(path.name, "pages=", doc.page_count, "size=", round(rect.width, 1), "x", round(rect.height, 1), "landscape=", rect.width > rect.height)
       print(doc[0].get_text("text").splitlines()[:8])
   PY
   ```

## 默认排版约定

- 使用 A4 横向：`size: A4 landscape`。
- 右侧页边距应明显留空，当前推荐 `22mm`。
- 首页只显示报告标题、论文题目、版本、总分、平均标准差。
- 不显示“来源文件”和“原始论文”，除非用户明确要求。
- 预检与六维度评分保留三模型横向对照表。

## 字段映射

- 预检字段：`status`、`issues`、`review_flags`、`recommendation`
- 维度字段：`score`、`summary`、`core_judgment`、`score_rationale`、`evidence_quotes`、`strengths`、`weaknesses`
- 维度顺序应使用法学评价六维度：
  `problem_originality`、`literature_insight`、`analytical_framework`、`logical_coherence`、`conclusion_consensus`、`forward_extension`

## 注意事项

- 保持最小改动；不要重构现有 API 报告链路。
- 不要把导出脚本复制进 skill 目录，脚本属于项目资产，skill 只记录触发和操作流程。
- 若用户要求批量导出其他 JSON，优先复用同一脚本并传入新文件路径。
- 如果 PDF 中文显示异常，优先检查本机字体；当前脚本使用 `"Songti SC", "STSong", "Hiragino Sans GB", "Arial Unicode MS"`。
