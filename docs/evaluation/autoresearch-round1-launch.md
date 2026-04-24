# Autoresearch 第一轮迭代启动命令

## 配置信息

**测试论文**：比例原则在民法上的适用及展开_郑晓剑.pdf  
**论文类型**：教义学类论文  
**测试模型**：GLM 5.1, Kimi K2.6, Qwen 3.6 Plus  
**迭代次数**：20 次  
**预计耗时**：约 1 小时

## 启动命令

在 Claude Code 中运行以下命令：

```
/autoresearch
Goal: 降低法学论文评审的多模型标准差至 < 5，提高高置信度比例至 > 80%
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml && /Users/jinyh/Documents/AIProjects/SocialEval/.venv/bin/python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: /Users/jinyh/Documents/AIProjects/SocialEval/.venv/bin/python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"
Iterations: 20
```

## 基线得分

**v2.19 基线**（2026-04-25 00:14）：

- Composite Score: **-6.33**
- 平均 std: **8.0**
- 高置信度比例: **16.7%**

**各维度详情**：

| 维度 | GLM 5.1 | Kimi K2.6 | Qwen 3.6+ | 平均 | Std | 置信度 |
|------|---------|-----------|-----------|------|-----|--------|
| 问题创新性 | 90 | 78 | 88 | 85.3 | 6.4 | medium |
| **现状洞察度** | 92 | **62** | 92 | 82.0 | **17.3** | **critical** |
| 分析框架建构力 | 90 | 82 | 92 | 88.0 | 5.3 | medium |
| 逻辑严密性 | 82 | 72 | 83 | 79.0 | 6.1 | medium |
| **结论可接受性** | 92 | **72** | 92 | 85.3 | **11.5** | low |
| 前瞻延展性 | 60 | 62 | 62 | 61.3 | 1.2 | high ✅ |

**关键问题**：
1. 现状洞察度 std=17.3（最严重，Kimi 给 62 分，GLM 和 Qwen 都给 92 分）
2. 结论可接受性 std=11.5（次严重，Kimi 给 72 分，GLM 和 Qwen 都给 92 分）
3. Kimi 系统性偏保守

**v2.20 测试结果**（2026-04-25 00:XX）：

- Composite Score: **-8.13** (比 v2.19 更差)
- 平均 std: **9.9** (比 v2.19 更差)
- 逻辑严密性 std: **8.1** (从 6.1 升至 8.1，反而变差)

**决策**：回退到 v2.19，直接启动 autoresearch，让 AI 自动优化。

## 第一轮目标

| 指标 | 起始值 (v2.19) | 目标值 | 差距 |
|------|----------------|--------|------|
| Composite Score | -6.33 | > -5.0 | +1.33 |
| 平均 std | 8.0 | < 7.0 | -1.0 |
| 高置信度比例 | 16.7% | > 30% | +13.3% |

## 监控计划

### 每 5 次迭代检查

```bash
# 查看最近 5 次结果
ls -lt results/autoresearch/quick-verify-*.json | head -5

# 查看 composite_score 趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(.venv/bin/python -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10
```

### 干预条件

- 连续 3 次没有改进 → 手动分析
- Composite Score > -5.5 → 提前结束，进入第二轮
- 连续 5 次变差 → 回滚到最佳版本

## 预期改动类型

基于 v2.19 的当前状态，第一轮可能的改动：

1. **精简检查清单**
   - 从 4-5 项减为 3 项
   - 优先优化标准差最高的维度

2. **增加锚点示例**
   - 为每个维度添加正面/反面示例
   - 特别是针对国产模型

3. **调整评分档位**
   - 明确 80-100 / 60-79 / 40-59 的判断标准
   - 避免模糊的"优秀""良好"描述

4. **优化 prompt 措辞**
   - 使用更直白的中文表述
   - 避免学术化的复杂句式

5. **强化边界说明**
   - 明确每个维度的评价范围
   - 避免维度间重复计分

## 结果记录

### 迭代日志

Autoresearch 会自动记录到 TSV 文件，格式如下：

```tsv
iteration  commit   metric  delta   status    description
0          a1b2c3d  -8.5    0.0     baseline  v2.19 + 国产三模型
1          b2c3d4e  -7.8    +0.7    keep      精简现状洞察度检查清单为3项
2          -        -8.1    -0.3    discard   调整问题创新性评分档位（分歧增大）
...
```

### 最佳结果

第一轮结束后记录：

- 最佳 Composite Score: ___
- 对应的 commit: ___
- 主要改动: ___

## 下一步

第一轮完成后：

1. 如果达到目标（> -5.5）→ 开始第二轮
2. 如果未达到目标 → 分析原因，调整策略
3. 运行全量验证（可选）→ 确认在多篇论文上的表现

---

**创建时间**：2026-04-25  
**状态**：准备启动
