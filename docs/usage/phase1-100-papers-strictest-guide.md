# 100 篇论文大规模评测使用说明

## 概述

本次实现了 4 模型单次评测 + 最严格聚合策略，用于从 100 篇论文中选择最好的论文。

## 核心特性

1. **4 模型配置**：`deepseek-v4-pro`, `glm-5.1`, `kimi-k2.6`, `qwen3.6-plus`
2. **双聚合模式**：同时计算 mean（均值）和 strictest（最严格）两种聚合结果
3. **最严格聚合**：各维度取所有模型的最低分，自主信号也取最低值
4. **并发优化**：论文级并发（默认 5）+ 维度级并发（4 个模型）
5. **断点续传**：支持中断后继续运行

## 文件说明

### 核心脚本

1. **`scripts/run_convergence_test.py`**（已修改）
   - 添加 `aggregation_mode` 参数：`mean` | `strictest` | `both`
   - 添加 `aggregate_scores()` 函数实现聚合逻辑
   - 支持同时输出两种聚合结果

2. **`scripts/phase1_100_papers_strictest.py`**（新建）
   - 100 篇论文的批量评测脚本
   - 默认使用 4 模型 + both 聚合模式
   - 支持断点续传和进度跟踪

3. **`scripts/test_strictest_3papers.py`**（新建）
   - 3 篇论文的小规模验证脚本
   - 用于验证聚合逻辑正确性

4. **`scripts/analyze_strictest_results.py`**（新建）
   - 结果分析脚本
   - 生成分数分布、模型贡献、高分论文清单
   - 导出 CSV 排名表

## 使用流程

### Step 1: 小规模验证（3 篇论文）

```bash
# 验证聚合逻辑是否正确
.venv/bin/python scripts/test_strictest_3papers.py
```

**预期输出**：
- 每篇论文的 mean 和 strictest 分数
- 分数差距（gap）
- 各维度的最严格模型
- 验证测试汇总

**验证要点**：
- ✅ strictest 分数 < mean 分数
- ✅ 分数差距合理（预计 3-6 分）
- ✅ 各维度都有 `strictest_model` 字段
- ✅ 输出格式正确

### Step 2: 全量运行（100 篇论文）

```bash
# 运行 100 篇论文评测
.venv/bin/python scripts/phase1_100_papers_strictest.py \
    --framework configs/frameworks/law-v2.50.2-20260514.yaml \
    --models deepseek-v4-pro,glm-5.1,kimi-k2.6,qwen3.6-plus \
    --aggregation-mode both \
    --concurrency 5 \
    --output-dir results/phase1-100-papers-strictest
```

**参数说明**：
- `--framework`：评价框架配置文件（默认 v2.50.2）
- `--models`：4 个模型，逗号分隔
- `--aggregation-mode`：聚合模式（推荐 `both`）
- `--concurrency`：论文级并发数（默认 5）
- `--output-dir`：输出目录

**预计耗时**：2-3 小时（取决于 API 响应速度）

**输出文件**：
- `results/phase1-100-papers-strictest/paper-001.json` ~ `paper-100.json`：每篇论文的详细结果
- `results/phase1-100-papers-strictest/phase1-result-YYYYMMDD-HHMMSS.json`：汇总结果
- `results/phase1-100-papers-strictest/metrics-tracking.jsonl`：进度跟踪日志

### Step 3: 结果分析

```bash
# 分析结果并生成报告
.venv/bin/python scripts/analyze_strictest_results.py \
    --input-dir results/phase1-100-papers-strictest \
    --output-csv results/phase1-100-papers-strictest/ranking.csv \
    --threshold 75.0
```

**输出文件**：
- `ranking.csv`：按 strictest 分数排序的论文清单
- `analysis-report.json`：详细分析报告

**报告内容**：
- Mean 和 Strictest 的分数分布对比
- 分数差异分析（mean - strictest）
- 模型贡献分析（哪个模型最常成为"最严格模型"）
- 高分论文清单（strictest > 75）

## 输出格式

### 单篇论文结果（paper-XXX.json）

```json
{
  "paper": "001_答复类行政解释的行政诉讼法定位及其司法审查.pdf",
  "models": ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"],
  "aggregation_mode": "both",
  "dimensions": {
    "problem_originality": {
      "model_scores": {
        "deepseek-v4-pro": 85,
        "glm-5.1": 82,
        "kimi-k2.6": 80,
        "qwen3.6-plus": 83
      },
      "mean": 82.5,
      "std": 2.1,
      "strictest": 80,
      "strictest_model": "kimi-k2.6",
      "confidence": "high"
    },
    ...
  },
  "overall": {
    "aggregation_mean": {
      "final_score": 82.5,
      "weighted_total": 495.0
    },
    "aggregation_strictest": {
      "final_score": 78.3,
      "weighted_total": 469.8
    },
    "score_gap": 4.2,
    "max_std": 3.2,
    "high_confidence_pct": 83.3
  }
}
```

### 汇总结果（phase1-result-YYYYMMDD-HHMMSS.json）

```json
{
  "test_time": "2026-05-21T10:30:00",
  "framework": "configs/frameworks/law-v2.50.2-20260514.yaml",
  "models": ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"],
  "aggregation_mode": "both",
  "total_papers": 100,
  "all_scores_mean": [82.5, 79.3, ...],
  "all_scores_strictest": [78.3, 75.1, ...],
  "metrics": {
    "mean_aggregation": {
      "overall_avg": 81.2
    },
    "strictest_aggregation": {
      "overall_avg": 76.8,
      "high_candidates": 85,
      "medium_candidates": 12,
      "boundary_candidates": 3
    },
    "std_over_8_ratio": 0.085,
    "critical_std_ratio": 0.012
  },
  "elapsed_seconds": 8538.5
}
```

## 断点续传

如果评测中断，直接重新运行相同命令即可：

```bash
.venv/bin/python scripts/phase1_100_papers_strictest.py
```

脚本会自动跳过已完成的论文，继续评测未完成的部分。

## 分层阈值

根据用户确认，保持原阈值：

- **高分候选**：`final_score_strictest > 75`
- **重点候选**：`final_score_strictest 65-75` 且自主信号强
- **边界候选**：`final_score_strictest 60-65` 且自主信号强

## 注意事项

1. **API 成本**：4 模型 × 100 篇 × 7 阶段（precheck + 6 维度）= 2800 次 API 调用
2. **耗时**：预计 2-3 小时
3. **模型可用性**：确保 4 个模型都已在 `.env` 中配置好 API Key
4. **最严格聚合的影响**：
   - 分数会显著降低（预计降低 4-6 分）
   - 高分论文数量会减少
   - 这是合理的严格筛选策略

## 故障排查

### 问题：模型不可用

**错误信息**：`未知 Provider：xxx`

**解决方案**：
1. 检查 `src/evaluation/providers/factory.py` 中是否已配置该模型
2. 检查 `.env` 文件中是否配置了对应的 API Key

### 问题：API 超时

**错误信息**：`ProviderTimeoutError`

**解决方案**：
1. 降低并发数：`--concurrency 3`
2. 检查网络连接
3. 检查 API Key 是否有效

### 问题：内存不足

**解决方案**：
1. 降低并发数：`--concurrency 3`
2. 分批运行（修改 manifest.json 只包含部分论文）

## 后续步骤

1. ✅ 完成小规模验证（3 篇论文）
2. ⏳ 运行全量评测（100 篇论文）
3. ⏳ 分析结果并生成报告
4. ⏳ 根据 strictest 分数选择高分论文
5. ⏳ 结合自主信号进行最终筛选

## 技术细节

### 聚合逻辑

```python
# Mean 模式
dimension_score = mean(model_scores)
autonomous_signal_score = mean(model_signals)

# Strictest 模式
dimension_score = min(model_scores)
autonomous_signal_score = min(model_signals)

# Both 模式
# 同时计算上述两种，输出两套完整结果
```

### 总分计算

```python
# Mean 模式总分
base_score_mean = sum(dim["mean"] * dim["weight"] for dim in dimensions)
final_score_mean = calculate_weighted_total(dimension_means, scoring_protocol)

# Strictest 模式总分
base_score_strictest = sum(dim["strictest"] * dim["weight"] for dim in dimensions)
final_score_strictest = calculate_weighted_total(dimension_strictest, scoring_protocol)
```

## 联系方式

如有问题，请查看：
- 计划文档：`/Users/jinyh/.claude/plans/100-4-synchronous-glacier.md`
- 项目文档：`CLAUDE.md`
- 当前评审规程：`docs/evaluation/law-ai-assisted-review-rules-v0.17.md`
