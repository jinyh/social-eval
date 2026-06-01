# Scite API 评估报告

**评估日期**：2026-04-16  
**评估人**：Claude (Opus 4.6)  
**项目**：SocialEval - AI辅助法学论文评价系统

---

## 一、Scite 核心能力

**Scite** 是一个AI驱动的学术引文分析平台，具备以下特点：

### 1. 智能引文分类（Smart Citations）

- **数据库规模**：16亿+引文，覆盖2.5亿+学术文献
- **核心功能**：使用机器学习将引文分类为三类：
  - **支持**（Supporting）：后续研究支持该论文的观点
  - **提及**（Mentioning）：仅提及该论文
  - **对比/反驳**（Contrasting）：后续研究对该论文提出质疑或反驳

### 2. 引文上下文分析

- 提供引文的完整上下文片段
- 帮助判断引用的准确性和相关性

### 3. 文献质量评估

- 追踪论文被引用的方式（支持vs反驳）
- 识别领域内最受支持或最具争议的研究

---

## 二、API/集成方式

### ✅ 有API支持

Scite提供了基于 **Model Context Protocol (MCP)** 的集成方式，于2026年2月正式发布。

#### Scite MCP 特性

| 特性 | 说明 |
|------|------|
| **协议** | Model Context Protocol (MCP) |
| **支持的AI工具** | ChatGPT、Claude、Copilot、Cursor、**Claude Code** |
| **访问方式** | 通过MCP协议直接调用Scite的数据库和分析能力 |
| **优势** | 无需自己处理API认证和数据解析，AI工具可直接调用 |

#### 参考资料

- [Introducing Scite MCP](https://scite.ai/blog/introducing-scite-mcp)
- [Research Solutions Launches Scite MCP](https://finviz.com/news/323121/research-solutions-launches-scite-mcp-connecting-chatgpt-claude-other-ai-tools-to-scientific-literature)
- [Scite Integrations](https://scite.ai/integrations)
- [How to Use Claude Code for Dissertation Writing](https://scite.ai/blog/claude-code-dissertation-writing)

---

## 三、对SocialEval项目的适用性分析

### ✅ 潜在价值

#### 1. 辅助"现状洞察度"维度评估（15%权重）

- 可以分析论文引用的文献质量
- 检测引用是否准确、是否存在断章取义
- 评估论文在学术对话中的位置（是否引用了关键争议点）

#### 2. 增强"引用规范性"准入检查

- 验证引用的真实性（是否存在捏造引用）
- 检测引用上下文是否与原文一致

#### 3. 提供客观数据支撑

- 为AI评价提供可验证的引文分析数据
- 减少主观判断的不确定性

### ⚠️ 关键局限性

#### 1. 学科覆盖问题

- Scite主要面向**自然科学、医学、生命科学**领域
- **法学文献覆盖度未知**，需要实际测试
- 搜索结果未显示Scite对法学领域的专门支持

#### 2. 中文文献支持不明确

- Scite的16亿引文数据库主要来自英文学术出版物
- **中文法学期刊的覆盖度存疑**
- SocialEval的目标用户是中文法学论文，这是最大的不确定性

#### 3. 法学引用特殊性

- 法学论文引用类型多样：判例、法条、学说、实证数据
- Scite的分类模型（支持/提及/对比）是否适用于法学引用逻辑？
- 法学的"对比"不等于"反驳"，可能是不同学派的正常学术争鸣

---

## 四、集成建议

### 方案A：先做可行性验证（推荐）

#### 第一步：功能测试

1. **注册Scite账号**，测试以下内容：
   - 搜索中文法学期刊论文（如《中国法学》《法学研究》）
   - 检查Scite是否能识别这些论文的引文关系
   - 评估Smart Citations分类对法学文献的准确性

#### 第二步：小范围试点

1. 选择5-10篇已有人工评审结果的法学论文
2. 使用Scite分析其引用质量
3. 对比Scite的分析结果与人工评审的"现状洞察度"评分
4. 计算相关性，判断是否有参考价值

#### 第三步：技术集成

如果验证通过，可以通过Scite MCP集成到评价流程：

```python
# 在 src/evaluation/providers/ 下新增 scite_provider.py
# 作为"现状洞察度"维度的辅助数据源（不是唯一依据）

class SciteProvider:
    """Scite引文分析提供者"""
    
    async def analyze_citations(self, paper_id: str) -> CitationAnalysis:
        """
        分析论文的引用质量
        
        Returns:
            CitationAnalysis: 包含支持/提及/对比引文的统计和上下文
        """
        pass
```

### 方案B：暂不集成，关注替代方案

如果Scite对中文法学文献支持不足，可以考虑：

#### 1. 中国知网（CNKI）的引文分析API

- **优势**：覆盖中文法学期刊最全
- **数据**：被引频次、下载量、影响因子等
- **适用性**：专为中文学术文献设计

#### 2. 北大法宝的引文网络

- **优势**：专注于中国法学文献
- **数据**：包含判例引用关系
- **适用性**：法学专业数据库

#### 3. 自建引文分析模块

- 基于SocialEval已有的法学论文语料库
- 使用LLM分析引用上下文的准确性和相关性
- 完全可控，可针对法学特点定制

---

## 五、行动建议

### 立即行动

1. ✅ 访问 [scite.ai](https://scite.ai/) 注册账号（可能有免费试用）
2. ✅ 测试中文法学文献的覆盖度
3. ✅ 如果覆盖度不足，联系Scite团队询问是否有扩展计划

### 中期规划

- 在需求文档v0.5中明确"引文质量分析"的数据源选择
- 如果Scite不适用，考虑CNKI或北大法宝的API
- 评估自建引文分析模块的成本和可行性

### 技术准备

- 无论最终选择哪个工具，都应在`src/evaluation/providers/`下预留引文分析接口
- 保持架构灵活性，便于后续切换数据源
- 设计统一的引文分析数据模型（CitationAnalysis）

---

## 六、风险评估

| 风险项 | 风险等级 | 缓解措施 |
|--------|----------|----------|
| 中文法学文献覆盖不足 | 🔴 高 | 优先验证覆盖度，准备替代方案（CNKI/北大法宝） |
| 法学引用逻辑不适配 | 🟡 中 | 小范围试点，对比人工评审结果 |
| API成本过高 | 🟡 中 | 评估定价模型，考虑自建方案 |
| 集成复杂度 | 🟢 低 | Scite MCP已支持Claude Code，集成相对简单 |

---

## 七、参考资料

### Scite官方资源

- [Scite AI for Research](https://scite.ai/)
- [Scite Integrations](https://scite.ai/integrations)
- [Introducing Scite MCP](https://scite.ai/blog/introducing-scite-mcp)
- [February 2026 Release Notes](https://scite.ai/blog/february-2026-release-notes)

### 学术论文

- [scite: A smart citation index that displays the context of citations and classifies their intent using deep learning](https://direct.mit.edu/qss/article/2/3/882/102990/scite-A-smart-citation-index-that-displays-the) - MIT Press, 2021
- [Citation Verification with AI-Powered Full-Text Analysis and Evidence-Based Reasoning](https://arxiv.org/html/2511.16198) - arXiv, 2025

### 法学引文分析相关

- [Enhancing LLM with Citations in Legal Domain](https://arxiv.org/html/2412.14556v2) - arXiv, 2024
  - 介绍了CitaLaw数据集，可能对法学引文分析有启发

### 中文法学资源

- [People's Republic of China Legal Research](https://guides.library.harvard.edu/c.php?g=310179&p=2071165) - Harvard Library
- [China Legal Knowledge (CLKD)](https://www.eastview.com/resources/e-collections/clkd/)

---

## 八、结论

**Scite有API且集成方便，但中文法学文献覆盖度是最大的不确定性。**

### 推荐路径

1. **短期**（1-2周）：注册Scite账号，验证中文法学文献覆盖度
2. **中期**（1个月）：如果覆盖度不足，评估CNKI/北大法宝API
3. **长期**（3-6个月）：根据验证结果，决定是集成Scite、使用替代方案，还是自建引文分析模块

### 关键决策点

- ✅ **如果Scite覆盖中文法学文献**：优先集成，利用其成熟的Smart Citations技术
- ❌ **如果覆盖度不足**：转向CNKI或北大法宝，或考虑自建方案

---

**文档版本**：v1.0  
**最后更新**：2026-04-16  
**状态**：待验证
