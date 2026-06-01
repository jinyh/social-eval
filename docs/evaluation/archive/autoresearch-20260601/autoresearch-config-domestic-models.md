# Autoresearch 配置 - 国产三模型版本

## 模型配置

**测试模型**：GLM 5.1、Kimi K2.6、Qwen 3.6 Plus  
**提供商**：DashScope 百炼（统一接入）  
**原因**：专注测试国产模型的稳定性和一致性

## 快速开始

### 在 Claude Code 中运行

```
/autoresearch
Goal: 降低法学论文评审的多模型标准差至 < 5，提高高置信度比例至 > 80%
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml && /Users/jinyh/Documents/AIProjects/SocialEval/.venv/bin/python -c "import json; print('composite_score:', json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"
Guard: /Users/jinyh/Documents/AIProjects/SocialEval/.venv/bin/python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"
Iterations: 20
```

## 验证脚本配置

### 快速验证：`scripts/quick_verify.sh`

```bash
# 模型配置
--models "glm-5.1,kimi-k2.6,qwen3.6-plus"

# 单篇论文
--paper "raw/司法公正与同理心正义_杜宴林.pdf"

# 预计耗时：2-3 分钟
```

### 全量验证：`scripts/full_verify.sh`

```bash
# 模型配置
--models "glm-5.1,kimi-k2.6,qwen3.6-plus"

# 4 篇论文
PAPERS=(
    "raw/司法公正与同理心正义_杜宴林.pdf"
    "raw/国体的起源、构造和选择_佀化强.pdf"
    "raw/比例原则在民法上的适用及展开_郑晓剑.pdf"
    "raw/治国理政的法治理念和法治思维_张文显.pdf"
)

# 预计耗时：10-15 分钟
```

## 模型特性对比

| 模型 | 提供商 | 稳定性 | JSON 输出 | 备注 |
|------|--------|--------|-----------|------|
| **GLM 5.1** | DashScope | 待验证 | ✅ 稳定 | 智谱 AI，新增模型 |
| **Kimi K2.6** | DashScope | ✅ 稳定 | ✅ 稳定 | 月之暗面，已验证 |
| **Qwen 3.6 Plus** | DashScope | 待验证 | ✅ 稳定 | 阿里通义，新增模型 |

**注意**：
- 所有模型都通过 DashScope 百炼调用
- Zenmux 版本的 Kimi 解析失败率 100%，已弃用
- 国产模型的 JSON 输出格式稳定

## 当前基线（v2.19 + 国产三模型）

基于历史测试数据估算：

| 指标 | 预估值 | 目标值 | 差距 |
|------|--------|--------|------|
| 平均 std | 9-10 | < 5 | -4 to -5 |
| 高置信度比例 | 15-20% | > 80% | +60-65% |
| Composite Score | -8 to -7 | > 3.0 | +10 to +11 |

**说明**：
- 国产模型的稳定性可能略低于 GPT-5.4
- 但通过 autoresearch 迭代优化，预期可以达到相同目标
- 优势：成本更低，响应更快，数据更安全

## 优化策略

### 针对国产模型的特殊优化

1. **增加示例锚点**
   - 国产模型更依赖具体示例
   - 每个维度至少提供 2 个正面示例 + 2 个反面示例

2. **简化检查清单**
   - 从 4-5 项减为 3 项
   - 使用更直白的中文表述

3. **明确评分档位**
   - 提供明确的分数区间和判断标准
   - 避免模糊的"优秀""良好"等描述

4. **强化边界说明**
   - 明确每个维度的评价范围
   - 避免维度间重复计分

## 预期效果

### 第一轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -8.0 | > -5.5 | 65% |
| 平均 std | 9.5 | < 8.5 | 60% |
| 高置信度比例 | 16.7% | > 25% | 55% |

### 第二轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -5.5 | > -3.0 | 70% |
| 平均 std | 8.5 | < 7.0 | 65% |
| 高置信度比例 | 25% | > 40% | 65% |

### 第三轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -3.0 | > -1.0 | 75% |
| 平均 std | 7.0 | < 6.0 | 70% |
| 高置信度比例 | 40% | > 60% | 70% |

### 第四轮（20 次迭代，约 1 小时）

| 指标 | 起始值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| Composite Score | -1.0 | > 3.0 | 80% |
| 平均 std | 6.0 | < 5.0 | 75% |
| 高置信度比例 | 60% | > 80% | 75% |

**总计**：约 4-5 小时完成 80 次迭代

## 监控指标

### 每 5 次迭代检查

```bash
# 查看最近 5 次结果
ls -lt results/autoresearch/quick-verify-*.json | head -5

# 查看 composite_score 趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(.venv/bin/python -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10
```

### 关键指标

1. **Composite Score**：主要优化目标
2. **平均 std**：稳定性指标
3. **高置信度比例**：质量指标
4. **最差维度**：优先优化目标

## 风险提示

### 国产模型特有风险

1. **API 限流**
   - DashScope 可能有调用频率限制
   - 如遇限流，增加重试间隔

2. **输出格式变化**
   - 国产模型的 JSON 输出可能偶尔不稳定
   - 已在 provider 中添加容错处理

3. **模型更新**
   - 国产模型更新频繁
   - 定期验证模型行为是否变化

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

## 附录：命令速查

```bash
# 快速验证
./scripts/quick_verify.sh configs/frameworks/law-v2.19-20260424.yaml

# 全量验证
./scripts/full_verify.sh configs/frameworks/law-v2.19-20260424.yaml

# 查看最近的 composite_score
.venv/bin/python -c "import json; print(json.load(open(sorted(__import__('glob').glob('results/autoresearch/quick-verify-*.json'))[-1]))['overall']['composite_score'])"

# 查看趋势
for f in results/autoresearch/quick-verify-*.json; do
    echo "$f: $(.venv/bin/python -c "import json; print(json.load(open('$f'))['overall']['composite_score'])")"
done | tail -10

# 验证 YAML 格式
.venv/bin/python -c "import yaml; yaml.safe_load(open('configs/frameworks/law-v2.19-20260424.yaml'))"

# 手动测试单个模型
.venv/bin/python scripts/run_convergence_test.py \
    --framework configs/frameworks/law-v2.19-20260424.yaml \
    --paper "raw/司法公正与同理心正义_杜宴林.pdf" \
    --models "glm-5.1" \
    --metric composite \
    --no-precheck
```
