# Autoresearch 配置指南

## 快速开始

### 1. 环境准备

已完成：
- ✅ 安装 autoresearch skill 到 `.claude/skills/autoresearch/`
- ✅ 创建快速验证脚本 `scripts/quick_verify.sh`
- ✅ 创建全量验证脚本 `scripts/full_verify.sh`
- ✅ 适配 `run_convergence_test.py` 支持 `--metric composite`

### 2. 运行 Autoresearch

在 Claude Code 中运行以下命令：

```
/autoresearch
Goal: 降低法学论文评审的多模型标准差至 < 5，提高高置信度比例至 > 80%
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml && python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"
Iterations: 20
```

### 3. 复合指标说明

**公式**：
```
composite_score = -avg_std + 10 * high_confidence_ratio
```

**目标**：
- `avg_std < 5`（平均标准差小于 5）
- `high_confidence_ratio > 0.8`（80% 的维度高置信度）
- `composite_score > 3.0`（复合得分大于 3.0）

**当前基线**（v2.19）：
- `avg_std = 9.5`
- `high_confidence_ratio = 0.167`（16.7%）
- `composite_score = -9.5 + 10 * 0.167 = -7.83`

**改进空间**：
- 需要提升 `10.83` 分才能达标

### 4. 改动策略

Autoresearch 每次迭代只做一个改动，可能的改动类型：

| 改动类型 | 示例 | 预期效果 |
|----------|------|----------|
| **精简检查清单** | 从 4 项减为 3 项 | 降低判断复杂度，减少分歧 |
| **增加锚点示例** | 添加正面/反面示例 | 提高判断一致性 |
| **调整评分档位** | 修改 80-100 的判断标准 | 收紧或放宽评分尺度 |
| **优化 prompt 措辞** | 从"必要性"改为"充分性" | 避免反事实推理 |
| **添加硬约束规则** | 新增上限规则 | 防止异常高分 |
| **合并重复检查项** | 删除维度间重复的判断点 | 避免重复计分 |

### 5. 监控和干预

**每 5 次迭代检查一次进度**：
```bash
# 查看最近的结果
ls -lt results/autoresearch/quick-verify-*.json | head -5

# 查看 composite_score 趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(python -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10
```

**干预条件**：
- 连续 3 次没有改进 → 手动分析，调整策略
- `composite_score > 3.0` → 运行全量验证
- 全量验证通过 → 停止迭代

### 6. 全量验证

当快速验证达到目标后，运行全量验证：

```bash
./scripts/full_verify.sh configs/frameworks/law-v2.19-20260424.yaml
```

**验证标准**：
- 4 篇论文的平均 `composite_score > 3.0`
- 每篇论文的 `avg_std < 7`（允许个别论文略高）
- 至少 3 篇论文的 `high_confidence_ratio > 0.6`

### 7. 结果日志

Autoresearch 会自动记录每次迭代的结果到 TSV 文件：

```tsv
iteration  commit   metric  delta   status    description
0          a1b2c3d  -7.83   0.0     baseline  initial state (v2.19)
1          b2c3d4e  -6.92   +0.91   keep      精简现状洞察度检查清单为3项
2          -        -7.15   -0.23   discard   调整问题创新性评分档位（分歧增大）
3          c3d4e5f  -6.21   +0.71   keep      添加逻辑严密性锚点示例
...
```

### 8. 风险缓解

**过拟合风险**：
- 使用训练集/验证集分离
- 定期轮换测试论文（每 20 次迭代）
- 最终在验证集上测试

**验证成本**：
- 快速验证：单篇论文，约 2-3 分钟
- 全量验证：4 篇论文，约 10-15 分钟
- 只在达到目标后运行全量验证

**模型随机性**：
- 使用 `temperature=0.3`（已在 provider 中配置）
- 增加采样次数（快速验证 3 次，全量验证 6 次）

### 9. 预期时间表

| 阶段 | 迭代次数 | 预计时间 | 目标 |
|------|----------|----------|------|
| 第一轮 | 20 | 1 小时 | composite_score > -5.0 |
| 第二轮 | 20 | 1 小时 | composite_score > -2.0 |
| 第三轮 | 20 | 1 小时 | composite_score > 0.0 |
| 第四轮 | 20 | 1 小时 | composite_score > 3.0 |
| 全量验证 | - | 15 分钟 | 确认达标 |

**总计**：约 4.5 小时（相比纯人工的 1-2 周）

### 10. 故障排查

**问题：验证脚本失败**
```bash
# 检查 Python 环境
python --version  # 应该是 3.10+

# 检查依赖
pip list | grep -E "anthropic|openai|yaml"

# 手动运行测试
python scripts/run_convergence_test.py --help
```

**问题：composite_score 不变化**
- 检查是否真的修改了 YAML 文件
- 检查 git commit 是否成功
- 查看 autoresearch 日志，确认改动类型

**问题：验证速度太慢**
- 减少模型数量（只用 gpt-5.4）
- 减少维度数量（先优化单个维度）
- 使用更快的模型（如 gpt-4o-mini）

### 11. 高级配置

**只优化单个维度**：
```
Scope: configs/frameworks/law-v2.*.yaml
Verify: python scripts/run_convergence_test.py --framework configs/frameworks/law-v2.19-20260424.yaml --paper "raw/司法公正与同理心正义_杜宴林.pdf" --models "gpt-5.4" --dimensions "problem_originality" --metric composite --no-precheck
```

**使用单模型快速测试**：
```
Verify: python scripts/run_convergence_test.py --framework configs/frameworks/law-v2.19-20260424.yaml --paper "raw/司法公正与同理心正义_杜宴林.pdf" --models "gpt-5.4" --metric composite --no-precheck
```

**分阶段优化**：
1. 第一阶段：只优化 `problem_originality`（20 次迭代）
2. 第二阶段：只优化 `literature_insight`（20 次迭代）
3. 第三阶段：优化全部维度（20 次迭代）

### 12. 成功标准

**快速验证达标**：
- `composite_score > 3.0`
- `avg_std < 5`
- `high_confidence_ratio > 0.8`

**全量验证达标**：
- 4 篇论文平均 `composite_score > 3.0`
- 每篇论文 `avg_std < 7`
- 至少 3 篇论文 `high_confidence_ratio > 0.6`

**人工抽检通过**：
- 评分仍然合理（不是为了降低 std 而牺牲准确性）
- Prompt 仍然可读（不是过度优化导致难以理解）
- 没有明显的过拟合迹象（在新论文上表现正常）

---

## 附录：命令速查

```bash
# 快速验证
./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml

# 全量验证
./scripts/full_verify.sh configs/frameworks/law-v2.19-20260424.yaml

# 查看最近的 composite_score
python -c "import json; print(json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"

# 查看趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(python -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10

# 验证 YAML 格式
python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"
```
