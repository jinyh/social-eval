# Slide Deck Outline

**Topic**: 法学论文 AI 辅助评审逻辑与流程复盘
**Style**: intuition-machine
**Dimensions**: clean + cool + technical + dense
**Audience**: experts
**Language**: zh
**Slide Count**: 16 slides
**Generated**: 2026-04-23 21:25

---

<STYLE_INSTRUCTIONS>
Design Aesthetic: Clean, analytical academic visuals with technical precision and restrained authority. The deck should feel like a legal-methodology workshop rather than a product pitch: crisp shapes, structured grids, quiet depth, and compact information blocks. Use diagrammatic composition, not decorative illustration, and keep the visual tone suitable for expert discussion and rule calibration.

Background:
  Texture: Clean surfaces with subtle grid overlays, thin blueprint lines, and faint diagram frames
  Base Color: Deep slate blue to cool gray gradient with high-contrast white content panels

Typography:
  Headlines: Bold geometric sans-serif with squared proportions, stable stroke weight, and strong hierarchy suitable for Chinese academic titles
  Body: Clear modern sans-serif with compact spacing, legible at medium size, optimized for dense expert-facing reading

Color Palette:
  Primary Text: Ink Black (#0F172A) - main text and key labels
  Background: Mist Gray (#F3F6FA) - content planes and quiet neutral fields
  Accent 1: Research Blue (#2F5D8C) - titles, flow arrows, emphasis blocks
  Accent 2: Signal Cyan (#58A6C7) - secondary highlights, route markers, framework connectors
  Accent 3: Review Gold (#CBAA5C) - expert input, caution, roadmap emphasis

Visual Elements:
  - Technical flow lines, bracket frames, and labeled nodes
  - Soft grid textures, layered cards, and restrained geometric separators
  - Process arrows, comparison columns, and structured scoring matrices
  - Callout chips for “规则”, “证据”, “复核”, “专家意见”

Density Guidelines:
  - Content per slide: 3-5 concise points or 1 structured diagram with short labels
  - Whitespace: Moderate; enough breathing room around focal diagram and headline blocks

Style Rules:
  Do: keep diagrams explicit, use visual grouping, lead each slide with one narrative headline, preserve academic restraint
  Do: emphasize process, boundaries, and calibration points more than promotional claims
  Don't: use startup-style gradients, glossy 3D graphics, or marketing slogans
  Don't: overload a slide with long prose paragraphs or decorative imagery unrelated to legal review logic
</STYLE_INSTRUCTIONS>

---

## Slide 1 of 16
**Type**: Cover
**Filename**: 01-slide-cover.png
Headline: 法学论文 AI 辅助评审逻辑与流程复盘
Sub-headline: 面向专家意见征询与机制共建
Body:
- 评审标准显化
- 判断链条可复核
- 邀请专家参与校准

## Slide 2 of 16
**Type**: Content
**Filename**: 02-slide-implicit-standards.png
Headline: 传统评审的难点不只在效率，更在标准难显化
Sub-headline: 专家判断高度依赖隐性经验，难以直接迁移给 AI
Body:
- 标准常以共同体经验存在，不总能直接写成规则
- 评审解释过程难复用，导致一致性与追溯性不足
- 不先外化标准，AI 只能模仿语言，无法稳定模仿判断

## Slide 3 of 16
**Type**: Content
**Filename**: 03-slide-main-workflow.png
Headline: 当前主链路把论文评审拆成可复核的七个环节
Sub-headline: 从论文输入到报告输出，每一步都对应明确的判断任务
Body:
- 文档预处理 → 前置检查 → 六维评分 → 可靠性判断
- 报告生成 → 专家复核接口 → 版本留存与追踪
- 依据来自当前配置、需求文档与代码主链路

## Slide 4 of 16
**Type**: Content
**Filename**: 04-slide-ai-intent-gap.png
Headline: AI 常常听懂了词面，却没有准确对齐评审意图
Sub-headline: “创新性”“洞察度”“可接受性”这些词，模型并不会自动与法学语境一致
Body:
- 同样一句评审要求，不同模型和不同时间可能给出不同解释
- 隐含标准越多，输出越容易漂移
- 所以需要把规则写成 YAML，并保持可调整、可追踪、可迭代

## Slide 5 of 16
**Type**: Content
**Filename**: 05-slide-yaml-overview.png
Headline: YAML 不是“参数表”，而是评审机制真正的规则层
Sub-headline: 它把专家经验从隐含判断变成可加载、可执行、可修改的规则集合
Body:
- 不只写六维和权重，还写 precheck、评分锚定、封顶规则、输出结构与复核标记
- 它是专家意见进入系统的真实入口
- 后续三页分别回答：评什么、怎么判、怎么输出与复核

## Slide 6 of 16
**Type**: Content
**Filename**: 06-slide-yaml-scope.png
Headline: YAML 先定义“评什么”，并规定判断顺序
Sub-headline: 先把评价对象和程序写清，模型才不会直接跳到结论
Body:
- precheck 决定论文能否进入六维评分
- dimensions + weight 决定六维结构与加权关系
- decision_order 规定每个维度必须先看什么、后看什么

## Slide 7 of 16
**Type**: Content
**Filename**: 07-slide-yaml-rules.png
Headline: YAML 再定义“怎么判”，也就是锚定区间与封顶边界
Sub-headline: 真正影响分数稳定性的，不只是 prompt，而是 scoring_criteria 和 ceiling_rules
Body:
- scoring_criteria 给出 excellent / good / marginal / unacceptable 的锚定区间
- ceiling_rules 决定哪些情况下必须封顶，防止基础条件不成立却虚高打分
- boundary_notes 提醒本维度评什么、不评什么，减少维度串位

## Slide 8 of 16
**Type**: Content
**Filename**: 08-slide-yaml-output-hooks.png
Headline: YAML 最后定义“怎么输出”以及“何时提示复核”
Sub-headline: 结果不仅要能生成，还要能被比较、核验和人工接手
Body:
- prompt_template 决定模型按什么方式进入该维度
- output_contract 约束必须返回哪些字段
- review_flags 把证据不足、边界模糊、需要外部核验等情况显式标出来

## Slide 9 of 16
**Type**: Content
**Filename**: 09-slide-six-dimensions.png
Headline: 六维框架把法学论文的判断链条外化出来
Sub-headline: 从起点到落脚，六个维度共同构成结构化评价路径
Body:
- 问题创新性 30%｜现状洞察度 15%｜分析框架建构力 15%
- 逻辑严密性 25%｜结论可接受性 10%｜前瞻延展性 5%
- 起点 → 定位 → 工具 → 骨架 → 落脚 → 开放

## Slide 10 of 16
**Type**: Content
**Filename**: 10-slide-iteration-directions.png
Headline: 这套机制不是一次成型，而是沿着四条方向持续收敛
Sub-headline: 关键不是追版本，而是让评审尺度越来越可解释、可校准、可复核
Body:
- 模糊概念改成检查清单
- 关键维度逐步操作化
- ceiling rules 触发条件持续收窄
- 输出更短、更结构化，利于专家核验

## Slide 11 of 16
**Type**: Content
**Filename**: 11-slide-decision-order.png
Headline: 单维评分必须先抽证据，再分档给分
Sub-headline: 固定顺序把印象打分改成证据驱动判断
Body:
- 定位评价对象
- 抽取关键证据
- 判断是否触发上限规则
- 确定分档并给出最终分数
- 输出摘要与评分理由

## Slide 12 of 16
**Type**: Content
**Filename**: 12-slide-output-contract.png
Headline: 统一输出契约让 AI 的判断可解释、可比较、可复核
Sub-headline: 关键不是只给分，而是留下可供专家审核的判断结构
Body:
- 输出字段覆盖分数、分档、摘要、核心判断、评分理由、证据、优势、缺陷、复核标记
- 统一结构便于横向比较不同模型，也便于事后回看
- 对专家最重要的是“为什么这样判”

## Slide 13 of 16
**Type**: Content
**Filename**: 13-slide-reliability-review.png
Headline: 可靠性判断决定哪里可以采纳，哪里必须请人介入
Sub-headline: 重点不是谁分高，而是分歧有多大、结论可采纳到什么程度
Body:
- 多模型结果形成均值、标准差与高低置信度标签
- 高置信度不等于无需专家，低置信度更明确提示必须复核
- 这一层把模型输出转成可采纳程度判断

## Slide 14 of 16
**Type**: Content
**Filename**: 14-slide-current-boundaries.png
Headline: 当前边界仍然清楚存在，这正是专家意见最有价值的地方
Sub-headline: 机制可以运作，但可信边界仍要靠共同体继续校准
Body:
- 规则化并不意味着已经成熟
- 维度边界、上限规则、流派识别、证据充分性仍需澄清
- 当前最需要的是高质量校准意见，而不是更多自动化

## Slide 15 of 16
**Type**: Content
**Filename**: 15-slide-roadmap.png
Headline: 下一步分两段推进：1 个月校准，半年形成稳定机制
Sub-headline: 目标不是更快自动化，而是把可用机制推进到可信机制
Body:
- 未来 1 个月：收集专家反馈、校准规则、补样本、打磨复核流程
- 未来半年：形成稳定规则体系、标准样本库与人机协同流程
- 中期再讨论跨学科扩展与制度接入

## Slide 16 of 16
**Type**: Back Cover
**Filename**: 16-slide-back-cover.png
Headline: 希望专家帮助我们把机制从可用推进到可信
Body:
- 校准六维逻辑与边界规则
- 参与样本试评与阶段性评估
- 对机制共建与试点推进给予指导和支持
