# Codex 审查任务：law-v2.46 框架全面审查

## 审查目标

对 `configs/frameworks/law-v2.46-20260511.yaml`（1820 行）做两层审查：

1. **工程一致性**：节点间的字段对齐、枚举闭合、数据流衔接——确保代码能正确消费这份 YAML
2. **Prompt 质量**：各阶段 prompt_template 的指令清晰度、歧义风险、引导偏差——确保 AI 模型能稳定产出高质量评估

两层审查独立输出，互不混淆。

## 审查维度

### 1. output_contract ↔ prompt_template 字段对齐

检查以下 4 份契约：
- `precheck.output_contract.required_fields`
- `output_contract.required_fields`（六维通用）
- `autonomous_knowledge_signals.output_contract.required_fields`
- `aggregate_output_contract.required_fields`

对每份契约：
- prompt_template 中要求模型输出的 JSON 字段是否 **完全覆盖** required_fields（不少）
- prompt_template 是否要求了 required_fields **之外** 的字段（不多）
- 如果有 `output_template` 示例，示例中的 key 是否与 required_fields 一致

### 2. scoring_protocol ↔ dimensions 一致性

- `scoring_protocol.core_dimensions` 引用的 key 是否都在 `dimensions[]` 中定义
- `scoring_protocol.ceiling_dimension.key` 和 `scoring_protocol.bonus_dimension.key` 是否在 `dimensions[]` 中定义
- 权重检查：`core_dimensions` 的 weight 之和是否等于 `dimensions[]` 中对应维度的 weight 之和
- `bonus_dimension.prerequisites` 引用的维度 key 是否都存在

### 3. 枚举闭合性

- `field_constraints.*.allowed_values` 中列出的枚举值，是否覆盖了 prompt_template 中提到的所有可能输出值
- `enums.review_flags` 中定义的 key，是否覆盖了各维度 prompt_template 中提到的 review_flags
- 各维度 `ceiling_rules[].rule_id` 的命名是否遵循 `{dimension_key}.{rule_name}` 格式且无重复

### 4. bands ↔ ceiling_rules 分数区间一致性

对每个维度：
- `bands` 定义的分数区间是否连续且无重叠（覆盖 0-100）
- `ceiling_rules[].score_ceiling` 的值是否落在某个 band 的边界上（合理性检查）
- 如果 prompt_template 中提到"先分档再给分"，bands 的描述是否与 prompt 中的评分指引一致

### 5. 预检分层逻辑一致性

- `precheck.text_quality_gate` 和 `precheck.project_scope_precheck` 的输出是否能组合出 `precheck.output_contract` 要求的所有字段
- `precheck.output_contract.field_constraints.conclusion.allowed_values` 是否与 `aggregate_output_contract.field_constraints.precheck_conclusion.allowed_values` 一致
- `precheck` 的 `pass_required` 规则是否与 prompt_template 中的判断逻辑对应

### 6. 信号校验 ↔ 聚合层衔接

- `autonomous_knowledge_signals.signals[]` 定义的 key 是否与 `autonomous_knowledge_signals.output_contract.required_fields` 对应
- `autonomous_knowledge_signals.quantification` 中的量化规则（如 score 范围 0-8）是否与 `aggregate_output_contract.field_constraints.autonomous_signal_score.range` 一致
- `aggregate_output_contract` 中引用的信号相关字段（autonomous_signal_score, autonomous_signal_strength, signal_model_agreement）是否在信号校验的输出中有对应来源

### 7. 自主知识体系信号专项（重点）

这是 v0.16 的核心创新，需要重点验证信号系统内部的一致性：

#### 7.1 量化规则跨节点一致性

检查以下三处对"0/1/2 量化"的描述是否**字字对齐**：
- `autonomous_knowledge_signals.prompt_template` 中"信号量化要求"段落
- `autonomous_knowledge_signals.quantification.mapping`
- `autonomous_knowledge_signals.output_contract.field_constraints.signal_scores`

重点核对：
- `score_2` 对应的判断值列表（yes / sufficient / not_applicable）是否完全一致
- `score_1` 对应的判断值列表（partial / uncertain）是否完全一致
- `score_0` 对应的判断值列表（no / insufficient）是否完全一致
- 总分范围 0-8 是否一致
- strength_bands 阈值（strong=7-8, medium=4-6, weak=1-3, absent=0）是否一致

#### 7.2 信号 values 枚举一致性

`autonomous_knowledge_signals.signals[]` 每个信号的 `values` 列表，是否与：
- `prompt_template` 中该信号"判断值"段落列出的值完全一致
- `output_template` 示例中该信号的可能值一致
- `quantification.mapping` 中的值有对应映射关系

注意：`external_theory_transformation` 的值（sufficient/partial/insufficient/not_applicable/uncertain）与其他三个信号（yes/no/partial/uncertain）不同，要检查这个差异是否在所有相关位置都正确反映。

#### 7.3 contradiction_triggers 可执行性

对 `contradiction_triggers[]` 中每条规则：
- `condition` 引用的字段（如 final_score, china_problem_centered, problem_originality）是否在本框架或 aggregate_output_contract 中有定义
- 阈值（如 final_score > 70）是否与 scoring_protocol 的分数区间合理对应
- `slogan_heavy_but_no_legal_question` 这条规则的 condition 描述的是文本特征而非结构化字段，代码层是否有能力执行？如果不能执行，应标记为"仅供人工复核参考"

#### 7.4 typical_risks 引用完整性

- `typical_risks[]` 列出的 6 条风险，是否在 `prompt_template` 中完整列出（作为 risks 字段的可选值）
- 这 6 条风险是否与 `src/evaluation/result_validator.py` 中的 `_SIGNAL_RISK_REVIEW_FLAGS` 集合一致（这是代码侧的真源）
- 如果你能读到 result_validator.py，请对比；否则在报告中说明"需要核对代码侧常量"

#### 7.5 "不进入基础分"的约束是否贯穿

检查以下位置是否都明确声明"信号不进入基础分"：
- `autonomous_knowledge_signals.not_scoring_dimension: true`
- `prompt_template` 中的量化要求段落
- `quantification.guardrail`
- `output_contract.guardrails`
- `scoring_protocol` 中是否意外引用了信号字段（不应引用）

报告任何暗示信号会影响基础分的位置。

## 输出格式

按以下格式输出发现：

```
## 发现汇总

### 严重（会导致运行时错误或评分逻辑错误）
1. [位置] 描述 → 建议修复

### 警告（不影响运行但可能导致混淆或未来维护问题）
1. [位置] 描述 → 建议修复

### 信息（风格或最佳实践建议）
1. [位置] 描述

## 通过的检查项
- 列出所有检查通过的维度（简要说明）
```

## 注意事项

- Part A 不评价法学评审标准本身是否合理，只检查工程逻辑自洽
- Part B 不评价法学学科观点的对错，只评估 prompt 作为"给 AI 的指令"是否清晰、稳定、无歧义
- 如果某个检查项因为 YAML 结构不支持而无法完成，说明原因
- 对于"不确定是否算问题"的情况，归入"警告"而非"严重"

---

# Part B：Prompt 质量审查

## 审查目标

评估各阶段 prompt_template 作为"给 AI 模型的评估指令"的质量。关注：指令是否清晰无歧义、是否会导致评分漂移、是否有引导偏差、是否能让不同模型产出一致结果。

## 审查维度

### B1. 指令清晰度与可执行性

对每个 prompt_template（precheck、六维各维度、autonomous_knowledge_signals），检查：

- **任务边界是否明确**：模型是否清楚知道"评什么"和"不评什么"（evaluate vs do_not_evaluate）
- **判断标准是否可操作**：评分依据是否具体到模型可以执行，还是停留在抽象描述
- **输出格式是否无歧义**：JSON 字段的类型、长度限制、枚举值是否在 prompt 中明确告知
- **是否有矛盾指令**：同一 prompt 中是否存在互相冲突的要求

### B2. 评分锚定与区分度

对六维各维度的 prompt_template + bands 定义：

- **bands 描述是否有区分度**：excellent / good / marginal / unacceptable 四档的描述是否足够不同，模型能否据此稳定分档
- **分数区间是否有锚定**：模型是否知道"80 分长什么样"vs"60 分长什么样"
- **ceiling_rules 是否可检测**：trigger 条件描述的是模型能从文本中观察到的特征，还是需要外部知识才能判断
- **是否存在"默认高分"倾向**：prompt 是否无意中引导模型倾向给高分（如正面描述过多、负面条件过严）

### B3. 引导偏差检查

- **价值预设**：prompt 是否暗示某种立场比另一种更好（如暗示"中国问题"比"比较法问题"更有价值）
- **术语偏差**：是否使用了可能让模型产生特定联想的措辞（如"创新"一词是否被过度正面化）
- **示例偏差**：如果 prompt 中有示例，示例是否覆盖了高分和低分场景，还是只展示了某一端
- **否定指令有效性**：do_not_evaluate 中的"不要"指令是否足够具体，模型是否可能绕过

### B4. 跨维度一致性

- **评判标准是否重叠**：不同维度的 prompt 是否要求模型评判同一件事（如"论证质量"可能同时出现在 analytical_framework 和 logical_coherence 中）
- **证据引用是否冲突**：不同维度是否可能引用同一段文本作为证据，导致"双重计分"
- **do_not_evaluate 是否互相引用**：维度 A 说"这个归维度 B 评"，维度 B 是否确实评了

### B5. 模型稳定性风险

- **开放性指令**：是否有过于开放的指令可能导致不同模型理解不同（如"综合考虑"、"酌情判断"）
- **长度与注意力**：prompt 是否过长导致模型可能忽略后半部分的约束（特别是 guardrails 和 do_not_evaluate）
- **输出约束位置**：JSON 格式要求和字段约束是否放在 prompt 末尾（最佳位置），还是埋在中间
- **temperature 敏感性**：当前 prompt 在 temperature=0.3 下是否足够约束，还是依赖低 temperature 来掩盖指令模糊

### B6. 自主知识体系信号 prompt 专项

- **四类信号的判断标准是否可操作**：模型是否能仅凭论文文本判断"中国问题中心性"，还是需要领域专家知识
- **"uncertain" 的使用条件**：是否明确告知模型什么情况下应该输出 uncertain，避免模型把所有模糊情况都标为 uncertain
- **风险识别的可执行性**：6 条 typical_risks 的描述是否具体到模型能从文本中识别，还是需要深度学术判断
- **量化指令是否会干扰判断**：要求模型同时做定性判断（yes/no）和定量评分（0/1/2）是否会导致锚定效应

## 输出格式

```
## Part B 发现汇总

### 高优先级（可能导致评分漂移或模型间不一致）
1. [维度/阶段] 问题描述 → 建议优化方向

### 中优先级（可能影响边界案例的判断稳定性）
1. [维度/阶段] 问题描述 → 建议优化方向

### 低优先级（风格优化，不影响核心功能）
1. [维度/阶段] 问题描述

### 亮点（做得好的设计，值得保留）
- 列出 prompt 设计中特别好的模式
```
