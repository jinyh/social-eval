---
title: 中国自主知识体系研究论文 AI 辅助评审规程
version: v0.16
status: 大规模评估候选版
updated: 2026-05-11
framework: configs/frameworks/law-v2.46-20260511.yaml
---

# 中国自主知识体系研究论文 AI 辅助评审规程 v0.16

## 1. 规程概述

### 1.1 规程目的

本规程用于“中国自主知识体系研究”项目的法学论文 AI 辅助初筛。v0.16 面向近 10 年法学三大刊约 2000 篇论文的大规模评估，目标是在低漏选优先的前提下，把人工审阅工作量压缩到可管理的候选池。

AI 输出只用于初筛、分流、排序、证据整理和复核提示，不作为最终样本纳入、代表性论文认定、奖励或排名的唯一依据。

### 1.2 AI 定位

AI 是辅助工具，不是替代工具。

AI 可以做：

- 识别明显不属于项目口径的论文
- 对可评论文生成六维学术质量信号
- 整理文内可观察的自主知识体系信号
- 暴露多模型分歧、信号矛盾和文本证据薄弱处
- 为专家复核提供结构化问题清单

AI 不能做：

- 裁定论文是否真正构建中国自主法学知识体系
- 替代专家终审或主编判断
- 裁定真实首创性、长期学术影响或政策影响
- 根据政治正确性、话语主流性或主题重要性直接给高分
- 因使用西方理论、比较法或域外材料直接判定缺乏自主性

### 1.3 v0.16 相对 v0.15 的调整

v0.16 保留 v0.15 的四阶段主流程，并补充三项面向 2000 篇大规模评估的操作化要求：

- **项目口径预检保持为阶段1主任务**：文本质量问题只能作为旁路风险记录，不得取代“进入评分 / 边界复核 / 明显不适格”的项目口径判断。
- **阶段3信号可量化但不计入基础分**：自主知识体系信号输出 0-8 的 `autonomous_signal_score`，用于排序、分层抽检和引文分析结合，不作为第七评分维度。
- **阶段4复核分层更明确**：预检层复核解决门槛问题，评价层复核解决六维评分与自主信号之间的可靠性问题。

## 2. 评审流程

### 2.1 流程概览

```text
论文输入
    ↓
【阶段1：项目口径预检】
判断：进入评分 / 边界复核 / 明显不适格？
    ↓
明显不适格 → 输出预检说明 → 人工确认（预检层复核）→ 结束
边界 → 进入六维评分并自动标记复核
进入评分 → 进入六维评分
    ↓
【阶段2：六维评分】
评价：研究创新性、现状洞察度、分析框架建构力、逻辑严密性、结论可接受性、前瞻延展性
    ↓
计算总分（0-100分）
    ↓
【阶段3：自主知识体系信号校验】
整理：中国问题中心性、中国实践解释尝试、外部理论转化动作、可复核概念或命题
    ↓
【阶段4：评价层复核判断】
判断：是否触发评价层复核条件？
    ↓
是 → 进入专家复核
否 → 输出评审报告
```

### 2.2 四阶段关系

**阶段1：项目口径预检**

阶段1只回答门槛问题：论文是否具有进入本项目六维评价的文内候选信号。输出三类结论：

- `enter_six_dimension_review`：进入六维评分
- `boundary_review`：边界进入评分并自动标记预检层复核
- `obviously_ineligible`：明显不适格，不进入六维评分，输出预检说明并交人工确认

**阶段2：六维评分**

阶段2评价学术质量，不重新判断项目口径。六维评分产生基础分、前瞻延展性加分、结论可接受性上限和最终分。

**阶段3：自主知识体系信号校验**

阶段3整理文内可观察的自主知识体系信号。它可以复用阶段2分析结果，但必须形成独立输出。该阶段不是第七个评分维度，不直接加分或扣分。

**阶段4：评价层复核判断**

阶段4只判断评价结果是否可靠，不重新评分。它比对阶段2六维结果与阶段3信号结果，识别矛盾、分歧和需要专家裁断的问题。

### 2.3 文本质量旁路

PDF/OCR/脚注/参考文献抽取质量属于工程风险，不是正式评审阶段。v2.46 可输出 `text_quality_gate`，但该字段只用于判断是否需要重新抽取、清洗或人工核验，不得把可读文本中的 OCR 残留、页码混入、脚注乱码、参考文献列表抽取失败直接等同于 `boundary_review`。

只有正文严重不可读、主体缺页、核心论点无法定位时，文本质量才可导致当前不可评分。

## 3. 阶段1：项目口径预检

### 3.1 预检目的

阶段1排除明显不属于“中国自主知识体系研究”项目口径的论文，同时保留边界论文以控制漏选风险。

预检回答的问题是：

> 这篇论文是否具有进入本项目六维评价的文内候选信号？若信号不足，是否属于边界论文或明显不适格论文？

### 3.2 四类预检信号

AI 检查以下四类信号：

1. **是否涉及中国问题**：论文是否涉及中国制度、规范、司法、治理、社会实践、法学争论或文化资源中的问题。
2. **是否有法学问题**：论文是否提出可争辩的法学问题，而非只有口号、政策复述或材料堆砌。
3. **是否有中国实践解释尝试**：论文是否尝试解释中国实践中的制度、规范、司法、治理或社会实践难题。
4. **是否有理论转化或可复核命题**：论文是否把外部理论、比较法、跨学科理论或本土文化资源转化为法学概念、判断标准、解释路径、制度命题或规范命题。

### 3.3 三类预检结论

| 预检结论 | 是否进入六维评分 | 复核状态 | 说明 |
|---|---:|---|---|
| 进入评分 | 是 | 无需预检层复核 | 以中国问题为中心且有可争辩法学问题；或已完成理论转化/形成可复核命题 |
| 边界复核 | 是 | 必须预检层复核 | 只满足部分信号，AI 不确定是否属于项目口径 |
| 明显不适格 | 否 | 必须人工确认 | 缺少中国问题中心性且无法定位法学问题、实践解释或理论转化 |

### 3.4 预检不得直接排除的情形

下列情形不得直接判为明显不适格：

- 论文使用西方理论、比较法或域外材料
- 论文观点非主流、批判性强或与主流立场存在张力
- 论文未直接使用“自主知识体系”表述
- 论文属于传统法教义学问题，但能回应中国规范、制度、司法或法学争论
- 论文只满足部分预检信号，但存在可定位的中国问题、法学问题或理论转化线索

## 4. 阶段2：六维评分

### 4.1 六维递进链条

六维按递进链条理解，而不是六个互相替代的并列指标。

| 层级 | 维度 | 作用 |
|---|---|---|
| 命题与定位 | 研究创新性、现状洞察度 | 判断论文是否有值得讨论的问题及其学术位置 |
| 工具与论证 | 分析框架建构力、逻辑严密性 | 判断论文是否有可操作工具和有效论证推进 |
| 风险与延展 | 结论可接受性、前瞻延展性 | 标记共同体/制度风险，并在条件满足时给弱加分 |

不得倒置顺序：

- 不得因结论政治正确或立场主流而补救创新不足
- 不得因展望宏大而补救前四维塌陷
- 不得因材料新颖而跳过论证质量检查
- 不得因涉及中国特殊制度议题而自动给高分
- 不得把“中国特色”“自主知识体系”“文化主体性”等标签直接当作法学问题成立的证据

### 4.2 六维定义

1. **研究创新性**：论文是否提出清晰、可争辩且有推进价值的法学问题或命题。
2. **现状洞察度**：论文是否建立“既有研究到哪里、争点在哪里、本文从哪里切入”的研究地图。
3. **分析框架建构力**：论文是否形成可操作、可复用、能被后文调用的分析工具。
4. **逻辑严密性**：框架、材料、规范依据和结论之间是否形成充分支撑链条。
5. **结论可接受性**：结论是否能被法学共同体定位和回应，是否存在明显制度或共同体风险。
6. **前瞻延展性**：论文是否在现有论证基础上打开下一轮研究、制度讨论或解释路径。

### 4.3 总分协议

批量评估以 `final_score` 作为候选排序主分：

```text
base_score = (研究创新性×30 + 现状洞察度×20 + 分析框架建构力×15 + 逻辑严密性×20) / 85
```

前瞻延展性只在以下条件全部满足时加分：

- 逻辑严密性 >= 60
- 结论可接受性 >= 60
- 四个主评分维度中不存在 < 50 的塌陷项

结论可接受性决定总分上限：

- 结论可接受性 >= 75：不上限
- 60-74：总分上限 75
- < 60：总分上限 65

最终分：

```text
final_score = min(base_score + forward_extension_bonus, conclusion_consensus_ceiling)
```

若批量脚本保留 legacy `weighted_total`，必须标注其为简单加权参考分，不得与 `final_score` 混用。

## 5. 阶段3：自主知识体系信号校验

### 5.1 阶段定位

阶段3是独立的特征提取步骤，但不是第七个评分维度。

阶段3的作用：

- **证据整理**：呈现论文中与中国自主知识体系相关的文内证据
- **维度辅助**：帮助专家理解六维评分中的中国问题、实践解释和理论转化依据
- **复核触发**：当六维评分与自主信号明显矛盾时触发评价层复核
- **候选分层**：为 2000 篇批量评估中的排序、抽检和引文分析提供辅助标签

### 5.2 四类核心信号

1. **中国问题中心性**：论文是否围绕中国制度、规范、司法、治理、社会实践或中国法学争论提出问题。
2. **中国实践解释尝试**：论文是否尝试解释中国实践中的真实难题，而非只把中国材料作为背景或例证。
3. **外部理论转化动作**：论文是否把西方理论、域外制度、比较法或跨学科理论转化为服务中国问题的法学概念、判断标准、解释步骤或规范命题。
4. **可复核概念或命题**：论文是否提出可定位、可复述、可检验的概念、类型、机制、解释框架或规范命题。

### 5.3 信号量化

v0.16 允许对四类信号进行量化，但该量化不进入基础分公式。

每项信号取值：

- 2：`yes` / `sufficient` / `not_applicable`
- 1：`partial` / `uncertain`
- 0：`no` / `insufficient`

四项相加得到 `autonomous_signal_score`，范围 0-8：

| 分数 | 标签 | 用途 |
|---:|---|---|
| 7-8 | strong | 重点候选、引文分析优先结合 |
| 4-6 | medium | 常规候选分层 |
| 1-3 | weak | 高分弱信号抽检 |
| 0 | absent | 高质量普通法学论文与项目候选区分 |

量化结果只能用于候选排序、分层抽检、专家复核优先级和第二阶段引文分析结合，不能单独决定高分或低分。

### 5.4 典型风险

阶段3应标记以下风险：

- `policy_restatement_without_legal_thesis`：政策复述，没有形成法学命题
- `tradition_as_value_claim_without_legal_transformation`：传统文化只作价值宣示，没有法学转化
- `china_material_as_background_only`：中国材料只作背景，没有进入论证链条
- `direct_transplant_without_context_transformation`：直接移植外部理论或制度，未说明中国语境转化
- `slogan_inflation_without_legal_argument`：标识性概念密集，但无法定位具体法学问题
- `power_allocation_without_process_control`：讨论权力配置但不处理程序、责任、救济或规范衔接

## 6. 阶段4：评价层复核判断

### 6.1 复核分层

复核分为两个层次：

- **预检层复核**：阶段1触发，处理论文是否适合进入评价流程的门槛问题。
- **评价层复核**：阶段4触发，处理六维评分与阶段3信号之间的可靠性问题。

### 6.2 预检层复核触发

| 触发条件 | 后续流程 |
|---|---|
| `boundary_review` | 进入六维评分，完成评价后自动进入专家复核 |
| `obviously_ineligible` | 不进入六维评分，输出预检说明，交人工确认 |

预检层复核具有终局性。专家可以确认不适格、确认边界论文可继续评价，或改判为正常进入评分。

### 6.3 评价层复核触发

出现以下任一情形，必须进入评价层复核：

**六维评分异常**

- 研究创新性 >= 80 且逻辑严密性 >= 75，但结论可接受性 < 60
- 前瞻延展性明显高于前四维表现
- 材料或案例非常新，但论证链条薄弱
- AI 给出高总分，但证据片段不足或无法定位
- 多模型或多次评审在任一主评分维度上分歧过大

**自主知识体系信号矛盾**

- 六维总分 > 70，但中国问题中心性为 `no` 或中国实践解释尝试为 `no`
- 六维总分 < 50，但四项自主信号均为强信号
- 研究创新性 >= 80，但可复核概念或命题为 `no`
- 标题、摘要或正文大量使用“中国特色”“自主知识体系”“文化主体性”等标识性概念，但 AI 无法定位具体法学问题

**中国特殊制度议题风险**

- 涉及政党、监察、党内法规等特殊制度议题，但只作政策阐释或权威表述归纳
- 直接移植域外理论评价中国特殊制度，未说明制度差异和转化路径
- 涉及传统文化资源，但只作价值宣示，未转化为法学概念、制度解释或规范命题
- 涉及权力配置、监督制约或国家治理议题，但不处理程序控制、责任机制、权利救济或规范衔接

### 6.4 建议复核

v0.16 增加 `recommended` 复核状态。它不同于必须复核，不阻断输出评审报告，但应提高专家抽检或后续引文分析优先级。

典型场景：

- `final_score` 较高，但阶段3命中 `slogan_inflation_without_legal_argument`
- `final_score` 较高，但阶段3命中 `china_material_as_background_only`
- `final_score` 较高，但 `autonomous_signal_strength` 为 `weak` 或 `absent`
- 文本质量存在中高风险，但不影响六维评分执行

## 7. 输出规范

### 7.1 预检输出

项目口径预检的精确 prompt、字段、枚举值与文本质量旁路字段，以 `configs/frameworks/law-v2.46-20260511.yaml` 的 `precheck.prompt_template` 和 `precheck.output_contract` 为准。本节只说明报告中必须呈现的规程层结构。

```json
{
  "project_scope_precheck": {
    "conclusion": "enter_six_dimension_review/boundary_review/obviously_ineligible",
    "enter_six_dimension_review": "yes/boundary/no",
    "triggered_signals": {
      "involves_china_issues": "yes/no/partial/uncertain",
      "has_legal_question": "yes/no/partial/uncertain",
      "china_practice_explanation_attempted": "yes/no/partial/uncertain",
      "theory_transformation_or_verifiable_thesis": "yes/no/partial/uncertain"
    },
    "evidence_quotes": ["原文证据1", "原文证据2"],
    "boundary_reasons": [],
    "obviously_ineligible_reasons": [],
    "requires_manual_confirmation": true
  },
  "text_quality_gate": {
    "status": "ok/risk/block",
    "risk_level": "none/low/medium/high",
    "issues": [],
    "evidence_quotes": []
  }
}
```

`text_quality_gate` 是旁路工程字段，不改变正式四阶段流程。

### 7.2 六维评分输出

六维评分的精确字段、字数限制、prompt 与 JSON 契约以 `configs/frameworks/law-v2.46-20260511.yaml` 的顶层 `output_contract` 和 `dimensions[].prompt_template` 为准。本节只规定规程层最低输出要求，避免在文档与 YAML 中维护两套可能分叉的细节。

每个维度至少输出：

- `dimension`
- `score`
- `band`
- `summary`
- `core_judgment`
- `score_rationale`
- `evidence_quotes`
- `strengths`
- `weaknesses`
- `limit_rule_triggered`
- `review_flags`

### 7.3 自主知识体系信号输出

自主知识体系信号校验的精确 prompt、输出模板、量化映射和 JSON 契约，以 `configs/frameworks/law-v2.46-20260511.yaml` 的 `autonomous_knowledge_signals.prompt_template`、`autonomous_knowledge_signals.output_template` 和 `autonomous_knowledge_signals.output_contract` 为准。

```json
{
  "autonomous_knowledge_signals": {
    "china_problem_centered": "yes/no/partial/uncertain",
    "china_practice_explanation_attempted": "yes/no/partial/uncertain",
    "external_theory_transformation": "sufficient/partial/insufficient/not_applicable/uncertain",
    "verifiable_concept_or_thesis": "yes/no/partial/uncertain",
    "signal_scores": {
      "china_problem_centered": 0,
      "china_practice_explanation_attempted": 0,
      "external_theory_transformation": 0,
      "verifiable_concept_or_thesis": 0
    },
    "autonomous_signal_score": 0,
    "autonomous_signal_strength": "strong/medium/weak/absent",
    "involves_special_chinese_institutional_issue": "yes/no/uncertain",
    "issue_types": [],
    "uses_traditional_cultural_resource": "yes/no/uncertain",
    "evidence_quotes": [],
    "risks": [],
    "triggers_review": false,
    "review_reason": ""
  }
}
```

### 7.4 聚合输出

最终报告至少输出：

- `precheck_conclusion`
- `base_score`
- `bonus_score`
- `conclusion_consensus_ceiling`
- `final_score`
- `autonomous_signal_score`
- `autonomous_signal_strength`
- `multi_model_stats`
- `review_status`: `none` / `recommended` / `required`
- `review_level`: `none` / `precheck_level` / `evaluation_level`
- `triage_recommendation`
- `triggered_rules`

### 7.5 复核报告输出

触发复核时，报告必须优先呈现：

1. 原文证据
2. AI 判断分歧
3. 自主知识体系信号校验结果
4. 触发复核的具体规则
5. 需要专家裁断的问题

不得只把 AI 的最终建议推送给专家，避免锚定专家判断。

## 8. 2000 篇大规模评估执行规则

### 8.1 运行前验证

进入 2000 篇前必须按以下顺序验证：

1. `raw/calibration-regression/`：检查新框架是否破坏既有判断。
2. `raw/holdout-test/`：冻结测试，只修正明确的规则冲突、输出格式或维度错位问题。
3. `raw/validation/`：最终验证，一次性运行，不得边跑边调 rubric。

### 8.2 第一阶段候选分层

第一阶段输出不固定硬性比例，候选规模由最终分布决定。建议分层：

- **高分候选**：`final_score > 75`，优先进入后续分析。
- **重点候选**：`final_score 65-75` 且 `autonomous_signal_strength` 为 `strong` 或 `medium`。
- **边界候选**：`final_score 60-65` 附近且自主信号强，交由专家质检决定是否保留。
- **抽检对象**：高分弱信号、低分强信号、文本质量高风险、多模型分歧高风险。

### 8.3 专家质检

专家最低抽查不少于 20 篇被排除论文，并按年份、期刊、领域分层。若发现遗漏风险，应扩大抽查并调整阈值。

### 8.4 进入第二阶段

第二阶段引文分析应结合：

- `final_score`
- `autonomous_signal_score`
- 年均引文量
- 引文质量
- 引文语境
- 专家质检结果

引文量不高但自主信号极强的论文应保留一部分，避免遗漏理论创新但传播尚未充分展开的论文。
