# Autoresearch v2.56 配置

## 背景

v2.56 测试结果（5 篇论文）：
- 平均 std: 28.16（v2.55: 33.48）
- 改善幅度: 15.9%（不足，目标 < 20）
- 最高 std 维度：
  1. problem_originality（研究创新性）: 平均 27.8，最大 30.8
  2. analytical_framework（理论建构力）: 平均 21.6，最大 28.3

**结论**：维度命名与 prompt 语义对齐有改善，但不足以达到生产要求。需要更深入的 prompt 优化。

## 目标

- **主目标**：降低多模型标准差至 < 20（当前 28.16）
- **次要目标**：提高高置信度比例（std ≤ 5）至 > 60%
- **复合指标**：composite_score = -avg_std + 10 * high_confidence_ratio > 2.0

## 策略

### 阶段 1：优化 problem_originality（研究创新性）

**当前问题诊断**：
1. Prompt 过长（约 900 行），包含大量检查项和示例
2. 前置扣分机制（3 个检查项）可能增加判断复杂度
3. 可争辩性 4 项标准 + 枢纽性 4 项标准 = 8 项判断点，过于细碎
4. 材料创新降权规则与主评分流程交织，可能导致混淆

**优化方向**：
- 精简前置扣分检查项（从 3 项减为 2 项或合并）
- 合并可争辩性标准（从 4 项减为 3 项）
- 简化枢纽性标准（从 4 项减为 3 项）
- 增加锚点示例（正面/反面各 2 个）
- 优化措辞，避免反事实推理

### 阶段 2：优化 analytical_framework（理论建构力）

**当前问题诊断**：
1. "理论贴标签"判断标准模糊（"完全无定义"vs"已转化"）
2. 跨学科概念转化判断复杂（需要判断是否有"法学转化步骤"）
3. 框架调用频率统计（"少于 3 次"）难以量化

**优化方向**：
- 明确"法学转化步骤"的判断标准（提供具体示例）
- 简化框架调用判断（从"频率统计"改为"是否在后文实质使用"）
- 增加正面/反面锚点示例

### 阶段 3：全维度优化

在前两个维度优化后，检查其他维度是否需要调整。

## 验证配置

### 快速验证（单篇论文）

```bash
./scripts/quick_verify_v2.56.sh configs/frameworks/law-v2.56-prompt-aligned.yaml
```

**测试论文**：`raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf`

**模型配置**：
- deepseek-v4-pro
- glm-5.1
- kimi-k2.6
- qwen3.6-plus

**预计时间**：3-5 分钟

**基线指标**（2026-05-22 测试）：
- avg_std: 13.97
- high_confidence_ratio: 0.0%
- composite_score: -13.97

**各维度 std**：
- problem_originality: 24.5 ❌
- literature_insight: 21.1 ❌
- analytical_framework: 8.1 ⚠️
- logical_coherence: 9.1 ⚠️
- conclusion_consensus: 7.5 ⚠️
- forward_extension: 13.5 ❌

### 全量验证（4 篇论文）

当快速验证达到目标后，运行全量验证：

```bash
# 使用 calibration-regression 中的 3 篇论文
for paper in raw/calibration-regression/*.pdf; do
    ./scripts/quick_verify_v2.56.sh configs/frameworks/law-v2.56-prompt-aligned.yaml "$paper"
done
```

**验证标准**：
- 3 篇论文平均 avg_std < 20
- 至少 2 篇论文 high_confidence_ratio > 0.5
- 平均 composite_score > 2.0

## Autoresearch 命令

### 阶段 1：优化 problem_originality

```
/autoresearch
Goal: 降低 problem_originality 维度的多模型标准差至 < 20
Scope: configs/frameworks/law-v2.56-prompt-aligned.yaml (只修改 dimensions[0].prompt_template)
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify_v2.56.sh configs/frameworks/law-v2.56-prompt-aligned.yaml && python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/v2.56/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.56-prompt-aligned.yaml'))"
Iterations: 20
```

### 阶段 2：优化 analytical_framework

```
/autoresearch
Goal: 降低 analytical_framework 维度的多模型标准差至 < 20
Scope: configs/frameworks/law-v2.56-prompt-aligned.yaml (只修改 dimensions[2].prompt_template)
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify_v2.56.sh configs/frameworks/law-v2.56-prompt-aligned.yaml && python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/v2.56/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.56-prompt-aligned.yaml'))"
Iterations: 20
```

### 阶段 3：全维度优化

```
/autoresearch
Goal: 降低所有维度的多模型标准差至 < 20
Scope: configs/frameworks/law-v2.56-prompt-aligned.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify_v2.56.sh configs/frameworks/law-v2.56-prompt-aligned.yaml && python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/v2.56/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.56-prompt-aligned.yaml'))"
Iterations: 20
```

## 改动类型

每次迭代只做一个改动：

| 改动类型 | 示例 | 预期效果 |
|----------|------|----------|
| **精简检查清单** | 从 4 项减为 3 项 | 降低判断复杂度，减少分歧 |
| **合并重复检查项** | 合并"可争辩性"中的重复判断 | 避免重复计分 |
| **增加锚点示例** | 添加正面/反面示例 | 提高判断一致性 |
| **优化措辞** | 从"必要性"改为"充分性" | 避免反事实推理 |
| **简化判断标准** | 从"频率统计"改为"是否实质使用" | 降低量化难度 |
| **明确边界条件** | 明确"法学转化步骤"的判断标准 | 减少模糊判断 |

## 监控和干预

**每 5 次迭代检查一次进度**：

```bash
# 查看 composite_score 趋势
for f in results/autoresearch/v2.56/quick-verify-*.json; do
    echo "$f: $(python -c "import json; d=json.load(open('$f')); print(f\"composite={d['overall']['composite_score']:.2f}, avg_std={d['overall']['avg_std']:.2f}\")")"
done | tail -10
```

**干预条件**：
- 连续 3 次没有改进 → 手动分析，调整策略
- composite_score > 2.0 → 运行全量验证
- 全量验证通过 → 停止迭代，进入 Phase 2 测试

## 风险缓解

**过拟合风险**：
- 使用 calibration-regression 中的论文（已用于 v2.50.2 调参）
- 最终在 holdout-test 中的 4 篇论文上验证
- 如果 holdout-test 表现显著下降，回退到上一个版本

**验证成本**：
- 快速验证：单篇论文，约 3-5 分钟
- 全量验证：3 篇论文，约 10-15 分钟
- 只在达到目标后运行全量验证

**模型随机性**：
- 使用 temperature=0.3（已在 provider 中配置）
- 单次评估（4 个模型），依赖模型间的一致性而非重复采样

## 预期时间表

| 阶段 | 迭代次数 | 预计时间 | 目标 |
|------|----------|----------|------|
| 阶段 1 | 20 | 1-1.5 小时 | problem_originality std < 25 |
| 阶段 2 | 20 | 1-1.5 小时 | analytical_framework std < 20 |
| 阶段 3 | 20 | 1-1.5 小时 | 全维度 avg_std < 20 |
| 全量验证 | - | 15 分钟 | 确认达标 |
| Holdout 验证 | - | 20 分钟 | 确认无过拟合 |

**总计**：约 4-5 小时

## 成功标准

**快速验证达标**：
- avg_std < 20
- high_confidence_ratio > 0.5
- composite_score > 2.0

**全量验证达标**：
- 3 篇论文平均 avg_std < 20
- 至少 2 篇论文 high_confidence_ratio > 0.5
- 平均 composite_score > 2.0

**Holdout 验证达标**：
- 4 篇论文平均 avg_std < 22（允许略高于训练集）
- 至少 2 篇论文 high_confidence_ratio > 0.4
- 平均 composite_score > 1.5

**人工抽检通过**：
- 评分仍然合理（不是为了降低 std 而牺牲准确性）
- Prompt 仍然可读（不是过度优化导致难以理解）
- 没有明显的过拟合迹象（在新论文上表现正常）

## 下一步

1. ✅ 运行基线测试，获取 v2.56 当前指标
2. ⏳ 启动阶段 1：优化 problem_originality
3. ⏳ 启动阶段 2：优化 analytical_framework
4. ⏳ 启动阶段 3：全维度优化
5. ⏳ 全量验证
6. ⏳ Holdout 验证
7. ⏳ 如果通过，进入 Phase 2 完整评审（1836 篇）
