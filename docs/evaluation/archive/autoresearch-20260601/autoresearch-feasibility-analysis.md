# Autoresearch 用于评审规范迭代优化的可行性分析

**日期**：2026-04-24  
**分析对象**：https://github.com/uditgoenka/autoresearch  
**应用场景**：法学论文评审规范配置文件的自动化迭代优化

---

## 1. Autoresearch 核心机制

### 1.1 基本原理

Autoresearch 是一个自主迭代改进引擎，基于 Karpathy 的 autoresearch 理念，核心公式：

```
约束范围 + 机械化指标 + 自主迭代 = 复合增益
```

### 1.2 工作流程

```
LOOP (永久或 N 次):
  1. 审查当前状态 + git 历史 + 结果日志
  2. 选择下一个改动（基于成功/失败/未尝试）
  3. 做一个聚焦的改动
  4. Git commit（验证前）
  5. 运行机械化验证（测试、基准、评分）
  6. 改进 → 保留；变差 → git revert；崩溃 → 修复或跳过
  7. 记录结果
  8. 重复
```

### 1.3 八大核心规则

| # | 规则 | 说明 |
|---|------|------|
| 1 | 循环直到完成 | 无界：永久；有界：N 次后总结 |
| 2 | 先读后写 | 修改前理解完整上下文 |
| 3 | 每次迭代一个改动 | 原子化改动，失败时知道原因 |
| 4 | 仅机械化验证 | 不用主观判断，只用指标 |
| 5 | 自动回滚 | 失败的改动立即回滚 |
| 6 | 简单性获胜 | 相同结果 + 更少代码 = 保留 |
| 7 | Git 是记忆 | 实验用 `experiment:` 前缀提交 |
| 8 | 卡住时深入思考 | 重新阅读、组合近似方案、尝试激进改动 |

---

## 2. 适用性分析

### 2.1 我们的场景

**目标**：优化法学论文评审规范配置文件（`law-v2.x.yaml`）

**核心挑战**：
- 降低多模型评分的标准差（std）
- 提高高置信度比例（std ≤ 5）
- 保持评分的准确性和可解释性
- 避免过度拟合特定论文

**当前迭代方式**：
1. 人工分析标准差分布
2. 识别分歧维度
3. 修改 prompt 或检查清单
4. 运行收敛测试
5. 对比结果，决定保留或回滚

### 2.2 Autoresearch 的匹配度

#### ✅ 高度匹配的部分

| Autoresearch 特性 | 我们的场景 | 匹配度 |
|-------------------|-----------|--------|
| **机械化指标** | 平均 std、高置信度比例、维度分布 | ✅ 完美匹配 |
| **约束范围** | 只修改 YAML 配置文件，不改代码 | ✅ 完美匹配 |
| **自动回滚** | 失败的配置自动回滚到上一版本 | ✅ 完美匹配 |
| **Git 记忆** | 每个实验都有 commit，可追溯历史 | ✅ 完美匹配 |
| **原子化改动** | 每次只改一个维度或一个检查项 | ✅ 完美匹配 |
| **结果日志** | TSV 格式记录每次迭代的指标变化 | ✅ 完美匹配 |

#### ⚠️ 需要适配的部分

| 挑战 | 说明 | 解决方案 |
|------|------|----------|
| **验证成本高** | 每次收敛测试需要调用多个 AI 模型，耗时 5-10 分钟 | 使用采样策略：先用单篇论文快速验证，通过后再全量测试 |
| **指标多维** | 不是单一指标，而是 6 个维度 + 总分的 std | 定义复合指标：`score = -avg_std + 10 * high_confidence_ratio` |
| **过拟合风险** | 可能针对测试集过度优化 | 使用训练集/验证集分离；定期轮换测试论文 |
| **Prompt 复杂** | YAML 配置文件有 1500+ 行，改动空间大 | 分阶段优化：先优化单个维度，再优化全局 |

#### ❌ 不适用的部分

| Autoresearch 特性 | 我们的场景 | 原因 |
|-------------------|-----------|------|
| **代码优化** | 不需要 | 我们优化的是配置文件，不是代码 |
| **测试覆盖率** | 不适用 | 我们的指标是评分稳定性，不是测试覆盖率 |
| **性能优化** | 不适用 | 我们关注评分质量，不是性能 |

---

## 3. 实施方案

### 3.1 核心配置

```yaml
Goal: 降低法学论文评审的多模型标准差，提高评分稳定性
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio
Direction: higher is better
Verify: python scripts/run_convergence_test.py --quick --metric composite
Guard: python scripts/validate_framework.py  # 确保 YAML 格式正确
```

### 3.2 复合指标定义

```python
# scripts/run_convergence_test.py --metric composite

def calculate_composite_score(results):
    """
    复合指标：平衡标准差和高置信度比例
    
    - avg_std: 六维度平均标准差（越低越好）
    - high_confidence_ratio: std ≤ 5 的维度比例（越高越好）
    
    目标：avg_std < 5，high_confidence_ratio > 0.8
    """
    avg_std = sum(dim['std'] for dim in results['dimensions']) / 6
    high_confidence_count = sum(1 for dim in results['dimensions'] if dim['std'] <= 5)
    high_confidence_ratio = high_confidence_count / 6
    
    # 复合得分：标准差权重 1，高置信度权重 10
    composite_score = -avg_std + 10 * high_confidence_ratio
    
    return composite_score
```

### 3.3 快速验证策略

为了降低验证成本，采用两阶段验证：

**阶段 1：快速验证（单篇论文，3 次采样）**
```bash
python scripts/run_convergence_test.py \
  --paper "司法公正与同理心正义_杜宴林.pdf" \
  --samples 3 \
  --metric composite
```

**阶段 2：全量验证（4 篇论文，6 次采样）**
```bash
python scripts/run_convergence_test.py \
  --papers "司法公正与同理心正义_杜宴林.pdf,国体的起源、构造和选择_佀化强.pdf,比例原则在民法上的适用及展开_郑晓剑.pdf,治国理政的法治理念和法治思维_张文显.pdf" \
  --samples 6 \
  --metric composite
```

### 3.4 改动策略

Autoresearch 每次迭代只做一个改动，可能的改动类型：

| 改动类型 | 示例 | 预期效果 |
|----------|------|----------|
| **精简检查清单** | 从 4 项减为 3 项 | 降低判断复杂度，减少分歧 |
| **增加锚点示例** | 添加正面/反面示例 | 提高判断一致性 |
| **调整评分档位** | 修改 80-100 的判断标准 | 收紧或放宽评分尺度 |
| **优化 prompt 措辞** | 从"必要性"改为"充分性" | 避免反事实推理 |
| **添加硬约束规则** | 新增上限规则 | 防止异常高分 |
| **合并重复检查项** | 删除维度间重复的判断点 | 避免重复计分 |

### 3.5 实施步骤

#### 步骤 1：准备环境

```bash
# 1. 安装 autoresearch
cd /Users/jinyh/Documents/AIProjects/SocialEval
git clone https://github.com/uditgoenka/autoresearch.git /tmp/autoresearch
cp -r /tmp/autoresearch/.claude/skills/autoresearch .claude/skills/autoresearch

# 2. 创建快速验证脚本
cat > scripts/quick_verify.sh <<'EOF'
#!/bin/bash
python scripts/run_convergence_test.py \
  --paper "司法公正与同理心正义_杜宴林.pdf" \
  --samples 3 \
  --metric composite \
  --output results/quick-verify-$(date +%Y%m%d-%H%M%S).json
EOF
chmod +x scripts/quick_verify.sh

# 3. 创建全量验证脚本
cat > scripts/full_verify.sh <<'EOF'
#!/bin/bash
python scripts/run_convergence_test.py \
  --papers "司法公正与同理心正义_杜宴林.pdf,国体的起源、构造和选择_佀化强.pdf,比例原则在民法上的适用及展开_郑晓剑.pdf,治国理政的法治理念和法治思维_张文显.pdf" \
  --samples 6 \
  --metric composite \
  --output results/full-verify-$(date +%Y%m%d-%H%M%S).json
EOF
chmod +x scripts/full_verify.sh
```

#### 步骤 2：配置 Autoresearch

在 Claude Code 中运行：

```
/autoresearch
Goal: 降低法学论文评审的多模型标准差至 < 5，提高高置信度比例至 > 80%
Scope: configs/frameworks/law-v2.*.yaml
Metric: composite_score = -avg_std + 10 * high_confidence_ratio (higher is better)
Verify: ./scripts/quick_verify.sh && grep "composite_score" results/quick-verify-*.json | tail -1
Guard: python scripts/validate_framework.py configs/frameworks/law-v2.*.yaml
Iterations: 20
```

#### 步骤 3：监控和干预

- 每 5 次迭代检查一次进度
- 如果连续 3 次没有改进，手动介入分析
- 如果 composite_score 达到目标（> 3.0），运行全量验证
- 全量验证通过后，停止迭代

---

## 4. 预期效果

### 4.1 短期效果（20 次迭代）

| 指标 | 当前值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| 平均 std | 9.5 | < 5 | 70% |
| 高置信度比例 | 16.7% | > 80% | 60% |
| Composite Score | -9.5 + 1.67 = -7.83 | > 3.0 | 65% |

### 4.2 中期效果（50 次迭代）

| 指标 | 当前值 | 目标值 | 预期达成率 |
|------|--------|--------|-----------|
| 平均 std | 9.5 | < 5 | 85% |
| 高置信度比例 | 16.7% | > 80% | 80% |
| Composite Score | -9.5 + 1.67 = -7.83 | > 3.0 | 85% |

### 4.3 长期效果（100+ 次迭代）

- 建立完整的实验日志（TSV 格式）
- 识别出最有效的优化策略
- 形成可复用的优化模式库
- 为其他学科的评审规范提供参考

---

## 5. 风险与对策

### 5.1 主要风险

| 风险 | 影响 | 概率 | 对策 |
|------|------|------|------|
| **过拟合测试集** | 在新论文上表现差 | 高 | 定期轮换测试论文；使用训练集/验证集分离 |
| **验证成本过高** | 迭代速度慢 | 中 | 使用快速验证 + 全量验证两阶段策略 |
| **改动空间过大** | 难以收敛 | 中 | 分阶段优化：先单维度，再全局 |
| **指标冲突** | 降低 std 但牺牲准确性 | 低 | 使用 Guard 确保基本质量；人工抽检 |
| **模型随机性** | 同一配置多次测试结果不同 | 高 | 增加采样次数；使用 temperature=0.3 |

### 5.2 缓解措施

1. **训练集/验证集分离**
   - 训练集：4 篇论文（用于 autoresearch 迭代）
   - 验证集：2 篇论文（用于最终验证）
   - 定期轮换（每 20 次迭代）

2. **多层验证**
   - 快速验证：单篇论文，3 次采样（2 分钟）
   - 中等验证：2 篇论文，4 次采样（5 分钟）
   - 全量验证：4 篇论文，6 次采样（10 分钟）

3. **人工抽检**
   - 每 10 次迭代抽检 1 次
   - 检查评分是否合理
   - 检查 prompt 是否仍然可读

4. **回滚机制**
   - 如果连续 5 次迭代都变差，回滚到最佳版本
   - 如果 composite_score 下降超过 20%，立即回滚

---

## 6. 替代方案对比

### 6.1 方案 A：纯人工迭代（当前方案）

**优势**：
- 完全可控
- 可以结合领域知识
- 不依赖外部工具

**劣势**：
- 迭代速度慢（每次 1-2 天）
- 容易遗漏优化点
- 难以系统化记录实验

### 6.2 方案 B：Autoresearch 自动迭代（推荐）

**优势**：
- 迭代速度快（每次 10-20 分钟）
- 系统化记录所有实验
- 可以尝试更多组合
- 自动回滚失败的改动

**劣势**：
- 需要适配验证脚本
- 可能过拟合测试集
- 需要监控和干预

### 6.3 方案 C：混合方案（最佳）

**结合 A 和 B 的优势**：
- 使用 Autoresearch 快速探索优化空间
- 人工审查和筛选有潜力的改动
- 在验证集上最终验证
- 结合领域知识调整策略

**实施方式**：
1. Autoresearch 运行 20 次迭代
2. 人工审查 top 5 改动
3. 选择最佳改动，手动微调
4. 在验证集上测试
5. 重复上述流程

---

## 7. 结论与建议

### 7.1 可行性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **技术可行性** | ⭐⭐⭐⭐⭐ | Autoresearch 完美匹配我们的场景 |
| **成本效益** | ⭐⭐⭐⭐ | 验证成本较高，但可通过采样优化 |
| **风险可控性** | ⭐⭐⭐⭐ | 主要风险是过拟合，可通过分离集缓解 |
| **实施难度** | ⭐⭐⭐ | 需要适配验证脚本，但工作量可控 |

**综合评分**：⭐⭐⭐⭐ (4/5)

### 7.2 推荐方案

**推荐使用方案 C（混合方案）**：

1. **第一阶段（探索）**：使用 Autoresearch 运行 20 次迭代，快速探索优化空间
2. **第二阶段（筛选）**：人工审查 top 5 改动，结合领域知识筛选
3. **第三阶段（验证）**：在验证集上测试筛选后的改动
4. **第四阶段（迭代）**：重复上述流程，直到达到目标

### 7.3 实施时间表

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| **准备** | 安装 autoresearch，适配验证脚本 | 2 小时 |
| **第一轮** | 运行 20 次迭代，人工审查 | 1 天 |
| **第二轮** | 运行 20 次迭代，人工审查 | 1 天 |
| **第三轮** | 运行 20 次迭代，人工审查 | 1 天 |
| **验证** | 在验证集上测试，最终调整 | 0.5 天 |

**总计**：约 3.5 天（相比纯人工迭代的 1-2 周，效率提升 3-5 倍）

### 7.4 下一步行动

1. ✅ **立即可做**：安装 autoresearch，创建验证脚本
2. ⏳ **本周完成**：运行第一轮 20 次迭代，评估效果
3. 📅 **下周完成**：根据第一轮结果，调整策略，运行第二轮
4. 🎯 **月底目标**：达到 avg_std < 5，high_confidence_ratio > 80%

---

## 8. 参考资料

- Autoresearch GitHub: https://github.com/uditgoenka/autoresearch
- Karpathy's Autoresearch: https://github.com/karpathy/autoresearch
- 我们的收敛测试历史: `docs/evaluation/convergence-test-history-20260423.md`
- 标准差分析总结: `docs/evaluation/std-analysis-summary-20260423.md`
