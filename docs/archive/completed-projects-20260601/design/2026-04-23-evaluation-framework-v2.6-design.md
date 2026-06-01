# 评价框架 v2.6 改进设计

**版本**: v2.6.0  
**日期**: 2026-04-23  
**状态**: 设计阶段  
**作者**: Claude Opus 4.7

## 背景

### 问题描述

在对论文《司法公正与同理心正义》的评审中（run-20260423-004741），三个模型在所有6个维度的评分差异都非常大：

| 维度 | 标准差 | 分数范围 | 置信度 |
|------|--------|----------|--------|
| 问题创新性 | 13.65 | 45-72 | 低 |
| 现状洞察度 | 20.82 | 48-88 | 低 |
| 分析框架建构力 | 17.35 | 45-76 | 低 |
| 逻辑严密性 | 10.79 | 48-68 | 低 |
| 结论可接受性 | 7.00 | 58-71 | 低 |
| 前瞻延展性 | 14.01 | 35-62 | 低 |

**加权总分**: 61.05  
**可靠性**: 6个维度全部低置信度（标准差均>5）

### 根本原因分析

1. **上限规则触发不一致**
   - 同一规则（如"未明确概括既有研究"），三个模型判断完全不同
   - Gemini认为文献综述优秀（88分），GPT和Kimi都触发封顶规则（48-58分）
   - 触发条件过于主观（"流于理论贴标签"、"未明确概括"）

2. **文本质量问题干扰判断**
   - 论文混入版面符号、页码、其他文章摘要
   - 文末标注"参考文献：（无）"，但正文有大量脚注引用（法学论文正常规范）
   - 预检误判为"引用规范不完整"，影响后续评分

3. **对"法学问题"的理解差异**
   - GPT认为是"法理学问题"（72分）
   - Gemini认为是"哲学理念倡导"（45分）
   - 缺乏客观判断标准

4. **缺少分歧处理机制**
   - 标准差>10时没有任何补救措施
   - 直接标记"低置信度"，但不提供更多信息供人工复核

## 设计目标

1. **降低模型评分差异**：通过简化和量化上限规则，提高模型一致性
2. **改进文本预处理**：识别脚注引用规范，清理版面噪音
3. **引入分歧处理机制**：当标准差过大时，触发证据补充
4. **保持向后兼容**：v2.5框架保留，可随时切换对比

## 核心改进

### 1. 简化与量化上限规则

**原则**：
- 每个维度保留2个规则（严重缺陷50分封顶，轻微缺陷60-70分封顶）
- 触发条件量化（如"至少2个学术流派"）
- 增加 detection_method 字段指导模型判断

**示例（问题创新性）**：

```yaml
ceiling_rules:
  - rule_id: "problem_originality.no_justiciable_question"
    trigger: "论文未提出可争辩的法学问题（需同时满足：①无明确问题句，②无制度/规范争议点）"
    score_ceiling: 50
    priority: 1
    detection_method: "检查是否存在疑问句或'本文试图回答'等问题标识；检查是否涉及具体法条、判例或制度争议"
    
  - rule_id: "problem_originality.weak_problem_focus"
    trigger: "问题过于宏大或分散（涉及3个以上不相关的子问题）"
    score_ceiling: 70
    priority: 2
    detection_method: "统计论文提出的核心问题数量，检查是否存在明确的主问题"
```

**示例（现状洞察度）**：

```yaml
ceiling_rules:
  - rule_id: "literature_insight.no_literature_review"
    trigger: "完全缺乏文献综述（未引用任何学术文献）"
    score_ceiling: 50
    priority: 1
    detection_method: "检查全文是否存在学者姓名、文献引用或脚注"
    
  - rule_id: "literature_insight.insufficient_review"
    trigger: "未列举至少2个主要学术流派或代表性观点"
    score_ceiling: 60
    priority: 2
    detection_method: "检查文献综述部分是否明确提及至少2个不同学者/学派的核心观点，需包含学者姓名和观点概括"
```

**删除的规则**：
- 所有 priority: 2 的次要规则（在新版本中，priority: 2 用于轻微缺陷）
- 触发条件模糊的规则（如"empty_gap_claim"）

### 2. 预处理模块增强

**目标**：识别脚注引用规范，清理文本噪音

**扩展 ProcessedPaper Schema**：

```python
@dataclass
class ProcessedPaper:
    # 现有字段
    full_text: str
    abstract: str
    body: str
    references: str
    
    # 新增字段
    footnotes: List[str] = field(default_factory=list)  # 提取的脚注列表
    citation_style: str = "unknown"  # "footnote" | "endnote" | "mixed" | "unknown"
    footnote_count: int = 0  # 脚注数量
    contamination_detected: bool = False  # 是否检测到混入内容
    contamination_info: str = ""  # 混入内容描述
```

**脚注提取逻辑**（新增 `src/ingestion/footnote_extractor.py`）：

```python
def extract_footnotes(text: str) -> tuple[List[str], str]:
    """
    提取脚注并判断引用风格
    
    识别模式：
    - ① 参见、见、参阅 + 作者名 + 文献信息
    - ② 数字标注 + 文献信息
    - ③ 检测是否有"参考文献"标题
    
    返回：
    - footnotes: 脚注列表
    - citation_style: "footnote" | "endnote" | "mixed"
    """
```

**混入内容检测**：

```python
def detect_contamination(text: str) -> tuple[bool, str]:
    """
    检测是否混入其他文章内容
    
    检测特征：
    - 文末出现其他文章的英文标题/摘要
    - 出现"责任编辑"后仍有大段文本
    - 出现期刊目录信息
    """
```

**预检 Prompt 增强**：

在预检的 prompt_template 中增加：

```
【引用规范说明】
本文采用 {citation_style} 引用规范，共检测到 {footnote_count} 处引用。
法学论文通常使用脚注引用，文末可能无独立参考文献列表，这是正常的学术规范。

【文本质量说明】
{contamination_info}
```

### 3. 分级可靠性阈值

**目标**：根据标准差大小采取不同处理策略

**扩展 ReliabilityReport Schema**：

```python
@dataclass
class ReliabilityReport:
    dimension_key: str
    mean: float
    std: float
    is_high_confidence: bool
    model_scores: dict[str, float]
    
    # 新增字段
    confidence_level: str  # "high" | "medium" | "low" | "critical"
    requires_evidence_supplement: bool  # 是否需要证据补充
    divergence_description: str  # 分歧描述
```

**分级逻辑**（修改 `src/reliability/calculator.py`）：

```python
def calculate_reliability(
    dimension_key: str,
    results: list[DimensionResult],
    thresholds: dict = None,
) -> ReliabilityReport:
    """
    计算可靠性，采用分级阈值
    
    默认阈值：
    - std <= 5: high confidence
    - 5 < std <= 10: medium confidence
    - 10 < std <= 15: low confidence
    - std > 15: critical divergence (触发证据补充)
    """
    if thresholds is None:
        thresholds = {
            "high": 5.0,
            "medium": 10.0,
            "low": 15.0,
        }
    
    # 判断置信度等级
    if std <= thresholds["high"]:
        confidence_level = "high"
        divergence_desc = ""
    elif std <= thresholds["medium"]:
        confidence_level = "medium"
        divergence_desc = "模型评分存在中等差异，建议人工复核"
    elif std <= thresholds["low"]:
        confidence_level = "low"
        divergence_desc = "模型评分差异较大，需要人工复核"
    else:
        confidence_level = "critical"
        divergence_desc = "模型评分严重分歧，已触发证据补充机制"
    
    requires_supplement = std > thresholds["low"]
    
    return ReliabilityReport(
        dimension_key=dimension_key,
        mean=mean,
        std=std,
        is_high_confidence=(std <= thresholds["high"]),
        model_scores={r.model_name: r.score for r in results},
        confidence_level=confidence_level,
        requires_evidence_supplement=requires_supplement,
        divergence_description=divergence_desc,
    )
```

### 4. 证据补充机制

**目标**：当标准差>15时，要求模型补充详细证据

**证据补充 Prompt**（新增 `src/evaluation/evidence_supplement.py`）：

```python
EVIDENCE_SUPPLEMENT_PROMPT = """
你对【{dimension_name_zh}】维度的评分为 {score} 分，但与其他模型的评分存在较大差异：

你的评分：{your_score}
其他模型评分：{other_scores}
标准差：{std:.2f}

请补充 3-5 条具体的文本证据，说明你的判断依据。每条证据需要：
1. 引用原文具体段落或句子（不超过100字）
2. 说明这段文本如何支持你的评分（不超过80字）

输出 JSON 格式：
{{
  "supplementary_evidence": [
    {{
      "quote": "原文引用",
      "explanation": "如何支持评分"
    }}
  ]
}}
"""
```

**集成到评审流程**（修改 `src/evaluation/orchestrator.py`）：

```python
async def evaluate_paper_with_supplement(
    paper: ProcessedPaper,
    framework: Framework,
    providers: list[BaseProvider],
) -> EvaluationResult:
    """
    评审流程：
    1. 多模型并发评分
    2. 计算可靠性
    3. 对于 requires_evidence_supplement=True 的维度，触发证据补充
    4. 将补充证据附加到报告
    """
    # 第一轮评分
    results = await evaluate_all_dimensions(paper, framework, providers)
    
    # 计算可靠性
    reliability_reports = []
    for dim_key in framework.dimensions:
        dim_results = [r for r in results if r.dimension_key == dim_key]
        reliability = calculate_reliability(dim_key, dim_results)
        reliability_reports.append(reliability)
    
    # 证据补充（仅对 std > 15 的维度）
    supplementary_evidence = {}
    for reliability in reliability_reports:
        if reliability.requires_evidence_supplement:
            dim_key = reliability.dimension_key
            dim_name = framework.get_dimension(dim_key).name_zh
            
            # 为每个模型请求补充证据
            for provider in providers:
                your_score = reliability.model_scores[provider.name]
                other_scores = [s for p, s in reliability.model_scores.items() if p != provider.name]
                
                evidence = await request_evidence_supplement(
                    provider=provider,
                    dimension_key=dim_key,
                    dimension_name_zh=dim_name,
                    your_score=your_score,
                    other_scores=other_scores,
                    std=reliability.std,
                    paper_text=paper.full_text,
                )
                
                supplementary_evidence[(dim_key, provider.name)] = evidence
    
    return EvaluationResult(
        results=results,
        reliability_reports=reliability_reports,
        supplementary_evidence=supplementary_evidence,
    )
```

**报告中显示**（修改 `src/reporting/builder.py`）：

对于严重分歧的维度，增加"证据补充"部分：

```
【问题创新性】标准差：16.5 🔴 严重分歧

模型1 (GPT-5.4): 72分
补充证据：
  1. "有必要引入'同理心正义'理论" → 明确提出了理论创新点
  2. "同理心正义是否能经受住...考量？" → 提出了可争辩的问题

模型2 (Gemini-3.1): 45分  
补充证据：
  1. "应转而寻求一种正义的首要原则" → 属于哲学理念倡导，非法学问题
  2. 全文未涉及具体法条或制度争议 → 缺乏法学规范焦点
```

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    评审流程 v2.6                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 文本预处理（增强版）                                      │
│     - 基础清理（页码、页眉页脚）                              │
│     - 脚注提取与引用风格识别                                  │
│     - 混入内容检测                                            │
│     输出：ProcessedPaper (含 footnotes, citation_style)      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 预检（多模型共识）                                        │
│     - 使用增强的 prompt（包含引用风格说明）                   │
│     - 识别脚注引用为正常规范                                  │
│     输出：pass / conditional_pass / reject                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 六维评分（使用 v2.6 框架）                                │
│     - 简化的上限规则（每维度2个，量化触发条件）               │
│     - 三模型并发评分                                          │
│     输出：18个 DimensionResult                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 可靠性计算（分级阈值）                                    │
│     - std ≤ 5: high confidence                               │
│     - 5 < std ≤ 10: medium confidence                        │
│     - 10 < std ≤ 15: low confidence                          │
│     - std > 15: critical divergence → 触发证据补充            │
│     输出：6个 ReliabilityReport                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. 证据补充（条件触发）                                      │
│     - 仅对 std > 15 的维度执行                                │
│     - 要求每个模型补充 3-5 条具体证据                         │
│     - 说明评分依据                                            │
│     输出：supplementary_evidence dict                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  6. 报告生成                                                  │
│     - 显示分歧等级（🟢🟡🟠🔴）                                │
│     - 对严重分歧维度显示补充证据                              │
│     - 标注需人工复核的维度                                    │
└─────────────────────────────────────────────────────────────┘
```

## 数据流

```python
# 输入
paper_file: str  # PDF/DOCX/TXT

# 预处理输出
ProcessedPaper:
  - full_text: str
  - footnotes: List[str]  # 新增
  - citation_style: str  # 新增
  - footnote_count: int  # 新增
  - contamination_detected: bool  # 新增
  - contamination_info: str  # 新增

# 评分输出
DimensionResult:
  - dimension_key: str
  - score: int
  - reasoning: str
  - limit_rule_triggered: List[dict]

# 可靠性输出
ReliabilityReport:
  - dimension_key: str
  - mean: float
  - std: float
  - is_high_confidence: bool
  - confidence_level: str  # 新增
  - requires_evidence_supplement: bool  # 新增
  - divergence_description: str  # 新增

# 证据补充输出
supplementary_evidence: Dict[(dim_key, provider_name), List[dict]]
  - quote: str
  - explanation: str

# 最终报告
EvaluationReport:
  - results: List[DimensionResult]
  - reliability_reports: List[ReliabilityReport]
  - supplementary_evidence: dict  # 新增
```

## 实施计划

### 阶段1：框架配置（1-2小时）

**文件**：`configs/frameworks/law-v2.6-20260423.yaml`

**任务**：
1. 复制 v2.5 框架为 v2.6
2. 更新 metadata（版本号、changelog）
3. 简化每个维度的 ceiling_rules（保留2个）
4. 量化触发条件
5. 增加 detection_method 字段

### 阶段2：预处理增强（2-3小时）

**文件**：
- `src/ingestion/schemas.py`
- `src/ingestion/preprocessor.py`
- `src/ingestion/footnote_extractor.py`（新增）

**任务**：
1. 扩展 ProcessedPaper schema
2. 实现脚注提取逻辑
3. 实现混入内容检测
4. 修改预检 prompt template

### 阶段3：可靠性分级（1小时）

**文件**：
- `src/reliability/schemas.py`
- `src/reliability/calculator.py`

**任务**：
1. 扩展 ReliabilityReport schema
2. 实现分级阈值逻辑
3. 生成分歧描述

### 阶段4：证据补充（2-3小时）

**文件**：
- `src/evaluation/evidence_supplement.py`（新增）
- `src/evaluation/orchestrator.py`
- `src/evaluation/schemas.py`

**任务**：
1. 实现证据补充 prompt
2. 实现证据补充请求逻辑
3. 集成到评审流程
4. 扩展 EvaluationResult schema

### 阶段5：报告生成（1-2小时）

**文件**：
- `src/reporting/builder.py`
- `src/reporting/exporters.py`

**任务**：
1. 在报告中显示分歧等级
2. 显示补充证据
3. 标注需人工复核的维度

### 阶段6：测试验证（1-2小时）

**任务**：
1. 使用"司法公正与同理心正义"论文测试
2. 对比 v2.5 和 v2.6 的评分差异
3. 验证标准差是否降低
4. 验证证据补充是否触发

**总工作量**：约8-13小时

## 错误处理

### 1. 脚注提取失败
- **降级策略**：citation_style = "unknown"
- **影响**：预检 prompt 中不提供引用风格说明
- **继续流程**：是

### 2. 证据补充 API 失败
- **降级策略**：记录错误日志
- **影响**：在报告中标注"证据补充失败"
- **继续流程**：是（不影响原始评分）

### 3. 上限规则触发冲突
- **处理策略**：取最低上限（最严格规则优先）
- **记录**：记录所有触发的规则

### 4. 标准差计算异常
- **单模型**：std = 0
- **所有模型评分相同**：std = 0
- **处理**：正常流程

## 测试策略

### 单元测试

**脚注提取**：
- 测试用例：10篇不同引用风格的论文
- 验证：footnotes 列表准确性
- 验证：citation_style 判断准确性

**混入内容检测**：
- 测试用例：5篇混入内容的论文
- 验证：contamination_detected 准确性
- 验证：contamination_info 描述准确性

**上限规则触发**：
- 测试用例：每个规则至少2个触发案例
- 验证：触发判断准确性
- 验证：封顶分数正确性

**分级阈值计算**：
- 测试用例：不同标准差的评分组合
- 验证：confidence_level 判断准确性
- 验证：requires_evidence_supplement 触发准确性

### 集成测试

**v2.5 vs v2.6 对比**：
- 使用"司法公正与同理心正义"论文
- 对比标准差变化
- 对比上限规则触发情况
- 验证证据补充是否触发

**预期结果**：
- 标准差降低至少20%
- 上限规则触发更一致
- 严重分歧维度触发证据补充

### 回归测试

**测试集**：
- 使用已有的测试论文集（至少10篇）
- 对比 v2.5 和 v2.6 的评分分布
- 验证不会降低整体评分质量

## 向后兼容

1. **v2.5 框架保留**：可随时切换
2. **新增字段使用默认值**：不影响现有代码
3. **证据补充为可选功能**：可通过配置关闭
4. **API 接口不变**：输入输出格式兼容

## 预期效果

### 量化指标

**标准差降低**：
- 目标：平均标准差从当前的 14.0 降低到 < 10.0
- 高置信度维度比例：从 0/6 提升到 ≥ 3/6

**上限规则触发一致性**：
- 目标：同一规则的触发判断，三模型一致率 > 80%

**证据补充触发率**：
- 预期：10-20% 的维度触发证据补充（std > 15）

### 定性改进

1. **评分更可靠**：模型对同一论文的判断更一致
2. **分歧更透明**：严重分歧时提供补充证据，便于人工复核
3. **预检更准确**：识别脚注引用规范，减少误判
4. **规则更清晰**：量化触发条件，减少主观判断

## 风险与缓解

### 风险1：规则简化导致质量下降
- **缓解**：保留 v2.5 作为对照，持续监控评分质量
- **回滚策略**：如果 v2.6 质量下降，立即回滚到 v2.5

### 风险2：证据补充增加成本
- **缓解**：仅在 std > 15 时触发（预计10-20%的维度）
- **优化**：可配置是否启用证据补充

### 风险3：脚注提取不准确
- **缓解**：提取失败时降级为 "unknown"，不影响流程
- **改进**：持续优化提取算法

### 风险4：量化标准过于机械
- **缓解**：保留 detection_method 作为指导，不强制执行
- **调整**：根据实际效果调整量化标准

## 后续优化方向

1. **引入外部文献数据库**：验证文献覆盖度
2. **增加跨维度一致性检查**：识别不合理的评分组合
3. **优化证据补充机制**：使用对抗式辩论提高质量
4. **支持更多文档规范**：识别不同学科的引用风格

## 参考资料

- 评审案例：`outputs/run-20260423-004741-司法公正与同理心正义_杜宴林/`
- 当前框架：`configs/frameworks/law-v2.5-20260422.yaml`
- 架构文档：`docs/architecture/20260414_ADR-001_evaluation-framework-v2.md`
