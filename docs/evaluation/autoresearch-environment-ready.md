# Autoresearch 环境准备完成报告

**日期**：2026-04-25  
**状态**：✅ 环境准备完成，等待测试验证

---

## 已完成的工作

### 1. ✅ 安装 Autoresearch

- **位置**：`.claude/skills/autoresearch/`
- **来源**：https://github.com/uditgoenka/autoresearch
- **版本**：2.0.0-beta.0.2
- **状态**：已安装，可以使用 `/autoresearch` 命令

### 2. ✅ 适配 Composite 指标

**修改文件**：`scripts/run_convergence_test.py`

**新增功能**：
- 添加 `--metric composite` 参数
- 计算复合得分：`composite_score = -avg_std + 10 * high_confidence_ratio`
- 支持两种输出模式：
  - `standard`：完整 JSON 输出（默认）
  - `composite`：只输出单一数值（用于 autoresearch）

**示例输出**：
```
composite_score: -7.83
```

### 3. ✅ 创建验证脚本

#### 快速验证脚本：`scripts/quick_verify.sh`

- **用途**：快速迭代验证（2-3 分钟）
- **配置**：单篇论文，3 个模型
- **输出**：`results/autoresearch/quick-verify-{timestamp}.json`

**用法**：
```bash
./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml
```

#### 全量验证脚本：`scripts/full_verify.sh`

- **用途**：最终验证（10-15 分钟）
- **配置**：4 篇论文，3 个模型
- **输出**：`results/autoresearch/full-verify-{timestamp}-*.json`

**用法**：
```bash
./scripts/full_verify.sh configs/frameworks/law-v2.19-20260424.yaml
```

### 4. ✅ 创建配置文档

**文档列表**：
1. `docs/evaluation/autoresearch-feasibility-analysis.md` - 可行性分析
2. `docs/evaluation/autoresearch-setup-guide.md` - 配置指南

---

## 当前基线（v2.19）

基于历史测试数据估算：

| 指标 | 当前值 | 目标值 | 差距 |
|------|--------|--------|------|
| 平均 std | 9.5 | < 5 | -4.5 |
| 高置信度比例 | 16.7% | > 80% | +63.3% |
| Composite Score | -7.83 | > 3.0 | +10.83 |

---

## 下一步：运行第一轮迭代

### 方式 1：完整 Autoresearch（推荐）

在 Claude Code 中运行：

```
/autoresearch
Goal: 降低法学论文评审的多模型标准差至 < 5，提高高置信度比例至 > 80%
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml && python3 -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: python3 -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"
Iterations: 20
```

### 方式 2：手动测试（验证环境）

先手动运行一次验证，确认环境正常：

```bash
# 1. 测试快速验证
./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml

# 2. 查看结果
cat results/autoresearch/quick-verify-*.json | tail -1 | python3 -m json.tool

# 3. 提取 composite_score
python3 -c "import json; print(json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
```

如果上述命令都能正常运行，说明环境准备完成，可以开始 autoresearch 迭代。

---

## 预期效果

### 第一轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -7.83 | > -5.0 | 70% |
| 平均 std | 9.5 | < 8.0 | 65% |
| 高置信度比例 | 16.7% | > 30% | 60% |

### 第二轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -5.0 | > -2.0 | 75% |
| 平均 std | 8.0 | < 6.5 | 70% |
| 高置信度比例 | 30% | > 50% | 70% |

### 第三轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -2.0 | > 0.0 | 80% |
| 平均 std | 6.5 | < 5.5 | 75% |
| 高置信度比例 | 50% | > 70% | 75% |

### 第四轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | 0.0 | > 3.0 | 85% |
| 平均 std | 5.5 | < 5.0 | 80% |
| 高置信度比例 | 70% | > 80% | 80% |

---

## 监控和干预

### 每 5 次迭代检查进度

```bash
# 查看最近 5 次结果
ls -lt results/autoresearch/quick-verify-*.json | head -5

# 查看 composite_score 趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(python3 -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10
```

### 干预条件

| 情况 | 干预措施 |
|------|----------|
| 连续 3 次没有改进 | 手动分析，调整策略 |
| Composite Score > 3.0 | 运行全量验证 |
| 全量验证通过 | 停止迭代，发布新版本 |
| 连续 5 次变差 | 回滚到最佳版本 |
| Composite Score 下降 > 20% | 立即回滚 |

---

## 风险提示

### 1. 过拟合风险

**症状**：
- 快速验证得分很高，但全量验证得分低
- 在新论文上表现差

**缓解措施**：
- 定期轮换测试论文（每 20 次迭代）
- 使用训练集/验证集分离
- 最终在验证集上测试

### 2. 验证成本

**症状**：
- 每次迭代耗时过长（> 5 分钟）

**缓解措施**：
- 使用单模型快速测试（只用 gpt-5.4）
- 减少维度数量（先优化单个维度）
- 使用更快的模型（如 gpt-4o-mini）

### 3. 模型随机性

**症状**：
- 同一配置多次测试结果差异大

**缓解措施**：
- 使用 `temperature=0.3`（已配置）
- 增加采样次数
- 使用更稳定的模型（GPT-5.4）

---

## 故障排查

### 问题：验证脚本失败

```bash
# 检查 Python 环境
python3 --version  # 应该是 3.10+

# 检查依赖
pip3 list | grep -E "anthropic|openai|yaml"

# 手动运行测试
python3 scripts/run_convergence_test.py --help
```

### 问题：找不到论文文件

```bash
# 检查论文文件是否存在
ls -la raw/*.pdf

# 如果缺少论文，从备份恢复或使用其他论文
```

### 问题：API 调用失败

```bash
# 检查环境变量
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# 检查 .env 文件
cat .env | grep -E "OPENAI|ANTHROPIC"
```

---

## 成功标准

### 快速验证达标

- ✅ `composite_score > 3.0`
- ✅ `avg_std < 5`
- ✅ `high_confidence_ratio > 0.8`

### 全量验证达标

- ✅ 4 篇论文平均 `composite_score > 3.0`
- ✅ 每篇论文 `avg_std < 7`
- ✅ 至少 3 篇论文 `high_confidence_ratio > 0.6`

### 人工抽检通过

- ✅ 评分仍然合理
- ✅ Prompt 仍然可读
- ✅ 没有明显的过拟合迹象

---

## 文件清单

### 新增文件

- ✅ `.claude/skills/autoresearch/` - Autoresearch skill
- ✅ `scripts/quick_verify.sh` - 快速验证脚本
- ✅ `scripts/full_verify.sh` - 全量验证脚本
- ✅ `docs/evaluation/autoresearch-feasibility-analysis.md` - 可行性分析
- ✅ `docs/evaluation/autoresearch-setup-guide.md` - 配置指南
- ✅ `docs/evaluation/autoresearch-environment-ready.md` - 本文件

### 修改文件

- ✅ `scripts/run_convergence_test.py` - 添加 `--metric composite` 参数

---

## 总结

环境准备已完成，所有必需的脚本和配置都已就绪。现在可以开始运行第一轮 autoresearch 迭代。

**建议**：先手动运行一次快速验证，确认环境正常，然后再启动 autoresearch。

**预计总耗时**：约 4-5 小时（4 轮迭代 + 全量验证）

**预期效果**：将 composite_score 从 -7.83 提升至 > 3.0，达到目标标准。
