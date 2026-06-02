# Top 71 补测执行计划

## 背景

经过诊断发现，之前的 E2/E3 评测存在两个问题：
1. 使用了简单均值而非加权分来筛选 Top 60
2. 没有考虑年份覆盖（每年至少5篇）

现在基于加权分 + 年份覆盖策略，确定了 **Top 71** 候选论文，需要补测：
- **E2 补测**：26 篇论文（完整 R1 + R2）
- **E3 补测**：10 篇论文的特定维度（选择性维度）

## 脚本说明

**脚本路径**: `scripts/retest_top71_supplement.py`

**功能特性**:
- 支持 E2 和 E3 两种补测模式
- 并发控制（默认 5 篇同时处理）
- 自动跳过已完成的评测
- 详细的日志输出
- 支持 dry-run 模式（仅查看清单）

## 执行命令

### 1. 查看补测清单（dry-run）

```bash
# E2 补测清单
python3 scripts/retest_top71_supplement.py --mode e2 --dry-run

# E3 补测清单
python3 scripts/retest_top71_supplement.py --mode e3 --dry-run
```

### 2. 执行 E2 补测（26 篇）

```bash
# 完整执行（R1 + R2），并发 5
python3 scripts/retest_top71_supplement.py \
  --mode e2 \
  --concurrency 5 \
  --output-dir results/retest-top71-supplement

# 仅执行 R1（用于测试）
python3 scripts/retest_top71_supplement.py \
  --mode e2 \
  --concurrency 5 \
  --rounds r1 \
  --output-dir results/retest-top71-supplement
```

**预期输出**:
- 26 个 R1 评测文件：`results/retest-top71-supplement/e2/round1/paper-{id}.json`
- 26 个 R2 评测文件：`results/retest-top71-supplement/e2/round2/paper-{id}.json`
- 执行日志：`results/retest-top71-supplement/e2/execution.log`

**预计耗时**: 约 2-3 小时（每篇论文 R1+R2 约 20-30 分钟）

### 3. 执行 E3 补测（10 篇，17 个维度）

```bash
# 完整执行（R1 + R2），并发 5
python3 scripts/retest_top71_supplement.py \
  --mode e3 \
  --concurrency 5 \
  --output-dir results/retest-top71-supplement

# 仅执行 R1（用于测试）
python3 scripts/retest_top71_supplement.py \
  --mode e3 \
  --concurrency 5 \
  --rounds r1 \
  --output-dir results/retest-top71-supplement
```

**预期输出**:
- 10 个 R1 评测文件：`results/retest-top71-supplement/e3/round1/paper-{id}.json`
- 10 个 R2 评测文件：`results/retest-top71-supplement/e3/round2/paper-{id}.json`
- 执行日志：`results/retest-top71-supplement/e3/execution.log`

**预计耗时**: 约 1-2 小时（每篇论文仅评测 1-2 个维度）

## 补测清单详情

### E2 补测（26 篇）

这些论文在 Top 71 中但不在原 E2 评测中：

```
317, 339, 409, 413, 489, 634, 657, 683,
1125, 1277, 1317, 1322, 1390, 1401, 1546, 1556,
1601, 1615, 1710, 1727, 1730, 1772, 1774, 1818,
1842, 1848
```

**说明**: 这些论文需要完整的 6 维度评测（R1 + R2 交叉评审）

### E3 补测（10 篇，17 个维度）

这些论文在 Top 30 中，特定维度标准差 > 5，需要选择性补测：

| Paper ID | 需补测维度 | 当前 std | 说明 |
|---------|----------|---------|------|
| 1606 | 延展性 | 22.6 | **极端高分歧**，必须补测 |
| 1865 | 创新性 | 11.6 | 高分歧 |
| 21 | 建构力 | 8.7 | 中高分歧 |
| 1510 | 创新性、建构力 | 6.2, 5.5 | 中分歧 |
| 1779 | 创新性、共识度 | 5.3, 5.4 | 中分歧 |
| 1012 | 延展性 | 8.5 | 中高分歧 |
| 1820 | 延展性 | 6.3 | 中分歧 |
| 1575 | 创新性、洞察度 | 5.6, 6.8 | 中分歧 |
| 1106 | 延展性 | 6.0 | 中分歧 |
| 1168 | 建构力、共识度 | 5.9, 16.1 | **共识度极端高分歧** |

**说明**: 这些论文仅评测特定维度（选择性 R1 + R2）

## 执行顺序建议

### 推荐顺序

1. **先执行 E2 补测**（26 篇，影响更大）
   - 优先级：E2 涉及 26 篇论文，占 Top 71 的 37%
   - 完整性：E2 完成后，Top 71 的所有论文都有完整评测数据
   - 逻辑流：E2 是"补齐缺失"，是基础工作
   
   ```bash
   python3 scripts/retest_top71_supplement.py --mode e2 --concurrency 5
   ```

2. **再执行 E3 补测**（10 篇，优化分歧）
   - 优化性质：E3 是针对已有数据的分歧优化
   - 依赖前提：E2 完成后再处理分歧更合理
   
   ```bash
   python3 scripts/retest_top71_supplement.py --mode e3 --concurrency 5
   ```

**说明**：E2 和 E3 补测的是完全不同的论文集合，互不影响，但逻辑上应该先补齐缺失（E2），再优化分歧（E3）。

### 并行执行（可选）

如果服务器资源充足，可以同时执行 E2 和 E3：

```bash
# 终端 1：E3 补测
python3 scripts/retest_top71_supplement.py --mode e3 --concurrency 5

# 终端 2：E2 补测
python3 scripts/retest_top71_supplement.py --mode e2 --concurrency 5
```

**注意**: 并行执行会增加 API 调用压力，建议监控资源使用情况。

## 验证步骤

### 1. 检查 E2 补测结果

```bash
# 检查文件数量
ls -1 results/retest-top71-supplement/e2/round1/ | wc -l  # 应该是 26
ls -1 results/retest-top71-supplement/e2/round2/ | wc -l  # 应该是 26

# 检查单个文件
python3 -c "
import json
with open('results/retest-top71-supplement/e2/round2/paper-317.json') as f:
    data = json.load(f)
    print('维度数:', len(data['dimensions']))
    print('R2 平均 std:', data['overall']['round2_avg_std'])
    print('收敛维度数:', data['overall']['dimensions_converged'])
"
```

### 2. 检查 E3 补测结果

```bash
# 检查文件数量
ls -1 results/retest-top71-supplement/e3/round1/ | wc -l  # 应该是 10
ls -1 results/retest-top71-supplement/e3/round2/ | wc -l  # 应该是 10

# 检查 paper-1606（延展性 std=22.6）
python3 -c "
import json
with open('results/retest-top71-supplement/e3/round2/paper-1606.json') as f:
    data = json.load(f)
    dim = data['dimensions']['forward_extension']
    print('延展性 R1 std:', dim['round1_std'])
    print('延展性 R2 std:', dim['round2_std'])
    print('改善幅度:', dim['round1_std'] - dim['round2_std'])
"
```

## 后续步骤

补测完成后，需要：

1. **合并结果**：将补测结果合并到原 E2/E3 结果中
2. **重新计算排名**：基于 Top 71 重新计算最终排名
3. **生成最终报告**：更新 Top 30 排名表和分布图
4. **验证年份覆盖**：确认每年至少 5 篇

## 注意事项

### API 调用限制

- **并发控制**: 默认 5 篇同时处理，避免 API 限流
- **重试机制**: 脚本会自动重试失败的请求（最多 3 次）
- **断点续传**: 已完成的评测会自动跳过，可中断后继续

### 资源监控

```bash
# 监控日志
tail -f results/retest-top71-supplement/e2/execution.log
tail -f results/retest-top71-supplement/e3/execution.log

# 监控进度
ls -1 results/retest-top71-supplement/e2/round2/ | wc -l
ls -1 results/retest-top71-supplement/e3/round2/ | wc -l
```

### 故障处理

如果评测中断：

1. **直接重新运行**：脚本会自动跳过已完成的评测
   ```bash
   python3 scripts/retest_top71_supplement.py --mode e2 --concurrency 5
   ```

2. **查看失败原因**：检查日志文件
   ```bash
   grep "失败" results/retest-top71-supplement/e2/execution.log
   ```

3. **单独重试**：可以删除失败的 JSON 文件，然后重新运行

## 预估成本

### API 调用次数

- **E2 补测**: 26 篇 × 6 维度 × 4 模型 × 2 轮 = **1,248 次调用**
- **E3 补测**: 17 个维度 × 4 模型 × 2 轮 = **136 次调用**
- **总计**: **1,384 次调用**

### 预计时间

- **E2 补测**: 约 2-3 小时
- **E3 补测**: 约 1-2 小时
- **总计**: 约 3-5 小时（串行执行）

## 联系支持

如有问题，请查看：
- 执行日志：`results/retest-top71-supplement/{e2,e3}/execution.log`
- 诊断报告：`results/diagnosis_e2_e3_scoring_standards.md`
- Top 71 清单：`results/top71_candidates.json`
