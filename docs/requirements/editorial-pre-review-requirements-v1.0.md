# 期刊编辑辅助预审系统 需求规格 v1.0

> 版本：v1.0（2026-07-23 初稿）
> 状态：活文档，持续迭代。本文档为需求规格，不含实现计划；实现 plan 待需求冻结后另起。
> 关联：`AGENTS.md`（= `CLAUDE.md` 软链）项目上下文；前期评价体系见 `docs/requirements/SocialEval-requirements-v0.4.md` 与 `AGENTS.md` 评价框架快速参考。

### 变更日志
- v1.0 (2026-07-23)：初稿。明确三场景（编辑预审 / 投稿人模块预留 / 作者模拟预审待确认）；优良中差分档驱动决定，决定细分四档；label 12 篇作评估基准 + 输出格式模板且不入 Git；本项目内新建 `src/editorial/` 子包。

## 1. 背景与目标

SocialEval 前期已建成面向**已发表论文**的 AI 多模型评价体系（六维评分 + 五轴位置归属度 + CCB 总分 + 专家复核 + 报告导出），并在交大法学（642 篇）、中国法学（1920 篇）、学术月刊（149 篇）上完成大规模评审。

本期新目标：为《交大法学》《学术月刊》编辑部构建一套**投稿稿件编辑辅助预审系统**。对象是**未发表投稿**（含大量应退稿），产出**综合预审报告**辅助编辑做退稿/大改/录用决策。

label 目录下两个期刊提供了 **12 篇真实审稿意见**（交大法学 5 + 学术月刊 7），作为评估基准与输出格式模板。

## 2. 业务场景

三个场景，共享同一评审引擎与报告内核，区别在面向对象、输出视角与权限：

- **场景 A（本期重点）编辑预审**：编辑收到投稿 → 产出预审报告（评分 + 审稿意见 + 决定建议）→ 编辑在前端复核并 override 决定。面向编辑部内部，含"仅编辑部可见"意见段。
- **场景 B（未来，预留接入）投稿人模块**：投稿、查进度、看面向作者的意见。现有 `SubmitterPortal` 前端已存在，未来在其上扩展。
- **场景 C（建议新增，待确认）作者模拟预审**：面向法学院同学/老师的"投稿前自检"，跑同一引擎获得改进建议以提高质量。输出视角偏向"如何改进"而非"退/录用决定"，不需要编辑部内部意见与 override 流程。详见 §5 F8。

三者同库分层，不另起独立项目。

## 3. 核心定位（已确认）

**两者结合产出预审报告**：
- 客观依据层：直接复用前期六维评分 + 五轴位置归属度 + CCB 总分（对投稿跑现有 pipeline）。
- **分档映射层（新增口径）**：各维度分数映射为 **优 / 良 / 中 / 差** 四档。决定建议基于维度分档组合，而非 CCB 数值阈值。CCB 仍可调、可呈现作参考，但不再是决定口径。
- 意见文本层：AI 生成期刊风格审稿意见（总评 + 逐条问题 + 修改建议 + 结论行）。
- 决定层：AI 给细分档决定建议（见下），编辑可 override。
- 三层合一为综合预审报告。

**决定细分档（已确认需细分）**：拟四档 —— 退稿 / 重大修改 / 小修改后录用 / 直接录用。细分档数待最终确认。映射规则（维度分档组合 → 决定档）在 `configs/frameworks/editorial-*.yaml` 定义，不硬编码。

## 4. 输入与输出

- **输入**：投稿稿件（`.docx` 为主，兼 PDF/TXT），经 `src/ingestion/` 解析。
- **输出**：综合预审报告（JSON + PDF），含：
  - 六维评分 + 雷达图 + CCB 总分
  - 五轴位置归属度（可选呈现）
  - AI 审稿意见文本（按期刊风格结构化）
  - 细分档决定建议 + 置信/倾向说明
  - 审稿意见可追溯至六维证据引文（`evidence_quotes`）

## 5. 功能需求

### F1 投稿摄取（复用）
- 复用 `src/ingestion/preprocessor.process_file`（PDF/DOCX/TXT，PyMuPDF + python-docx）。
- 已知缺口：PDF 版面/表格/OCR 能力浅；投稿 docx 基本够用，深度版面识别留作扩展点（MinerU 纳入后续版本，按需求 v0.4 待澄清项）。

### F2 六维/五轴评分（直接复用 + 分档映射）
- 复用 `src/evaluation/orchestrator.run_evaluation_pipeline` + providers 抽象层 + `configs/frameworks/law-v2.56.6-20260522.yaml`。
- 对投稿跑六维 R1→R2 + 五轴两轮，产出六维分、std、CCB 总分。
- **新增分档映射**：六维分 → 优良中差四档。分档阈值在 `configs/frameworks/editorial-*.yaml` 定义（可调，按投稿分布校准）。
- CCB 口径不改（用户确认直接复用），作参考呈现；决定口径走分档组合，不走 CCB 阈值。

### F3 AI 审稿意见生成（新增）
- 新增"审稿意见生成器"：以六维分档 + 五轴 + 证据引文为输入，让 LLM 生成期刊风格审稿意见。
- **输出结构**对齐两期刊 label 格式：
  - 总评（选题价值、优点）
  - 逐条问题 / 缺陷（分点）
  - 修改建议（分点）
  - 结论行（显式细分档决定建议，如"退稿"/"重大修改"/"小修改后录用"/"直接录用"）
- **prompt 真源**必须放 `configs/frameworks/`（新建如 `editorial-review-opinion-v0.1.yaml`），遵守"prompt/契约真源在 yaml"约束，业务代码只渲染/校验。
- 两期刊格式差异处理：生成器按期刊配置选择结构模板（学术月：单审稿人 + 显式结论行；交大法学：双审稿人风格 + 编辑部内部意见段）。
- 多期刊支持：期刊级配置（prompt 模板、分档阈值、决定映射）按 `journal` 字段切换，为后续新增期刊留口。

### F4 综合预审报告（扩展）
- 复用 `src/reporting/`（scoring/versioning/simple_pdf_builder/public_filter/charts）。
- 新增预审报告 builder：聚合六维评分层 + 意见文本层 + 决定层。
- PDF 排版沿用 `simple_pdf_builder`，期刊级排版留作扩展。

### F5 label 对齐评估器（新增）
- 将 label 12 篇作为评估基准：对这 12 篇投稿跑预审 pipeline，与人工审稿意见对比。
- **核心指标（已确认）**：
  1. 决定层对齐：AI 细分档建议 vs 人工决定（交大法学从正文推断决定，学术月从结论行/文件名读取）。
  2. 问题点语义重合度：AI 逐条问题 vs 人工逐条问题，先做简单版（embedding 相似或问题条数/主题对比），复杂版后续迭代。
- 输出对齐报告（决定一致率、问题重合度分布、分歧案例）。
- label 同时作**输出格式模板**：意见生成器的结构模板从 label 归纳。

### F6 编辑工作台前端（扩展）
- 在现有 `src/web/` 加 `EditorialWorkspace` 组件（复用 shadcn/ui + 现有 API client）。
- 功能：投稿列表、预审报告查看、决定 override、审计日志。
- 复用现有 `InternalReportView` / `DimensionRadarChart` 等组件。

### F7 期刊与编辑部组织（多期刊支持，权限简化）
- 现有 `editor` 角色无期刊级权限粒度。本期新增 `journals` 表与期刊级配置（prompt 模板 / 分档阈值 / 决定映射按 `journal` 切换），为后续新增期刊（交大法学、学术月刊之外）留口。
- 编辑部多期刊权限粒度（某编辑只能看本刊）本期可简化，权限精控留后续。

### F8 作者模拟预审（建议新增，待确认）
- 面向法学院同学/老师，投稿前自检：跑同一六维 + 审稿意见引擎，输出**作者向预审报告**。
- 与编辑预审的差异仅在输出层：
  - 视角偏向"如何改进"，给可执行修改路径；
  - 不输出"退稿/录用"硬决定，改为"改进优先级"与"达标差距"；
  - 不含编辑部内部意见、无 override 流程、无期刊投稿状态机。
- 引擎、摄取、评分、意见生成器完全复用，仅新增作者向报告 builder 与前端入口（`SubmitterPortal` 内加"模拟预审"）。
- 本期是否实现待你确认；若纳入，建议作为 M5 里程碑。

## 6. 数据需求

### 6.1 label 评估集（已就位，未跟踪）
- `raw/label/交大法学审稿意见/`：5 子目录（第一~五篇），每篇 `{投稿编号}.docx` + `拒稿意见.docx`；双审稿人 + "仅编辑部可见"段；无结构化结论字段（决定需从正文推断）。
- `raw/label/学术月刊审稿意见/`：14 文件 7 组，`N-1{决定}原文：标题.docx` + `N-2意见.{doc,docx}`；单审稿人；显式结论行（不予录用/建议退稿/建议重大修改/录用）；文件名编码决定类型。
- **关键属性**：12 篇均为退稿/大改投稿，不在任何已发表论文数据集内（与 642/1920/149 元数据零命中），是独立的人工审稿 ground-truth 标注集。
- **归位与版本控制**：纳入 `raw/label/` 既有样本分组约定（评估集，不参与调参）。**全部 label 文件（含 expert/negative/positive 及两期刊审稿意见）不入 Git**，加入 `.gitignore`（含真实审稿意见，隐私考虑）。

### 6.2 数据模型复用与新增
- 复用：`papers / evaluation_tasks / dimension_scores / reliability_results / reports / users / api_keys / audit_logs / expert_reviews / review_comments`。
- 新增（初步判断，实现期细化）：
  - AI 生成的审稿意见需与现有 `review_comments`（专家复核意见）区分，建议新增 `editorial_opinions` 或在 `reports.report_data` 内结构化。
  - 细分档决定建议与编辑 override：新增 `editorial_decisions`（建议决定、最终决定、override 理由、actor）。

## 7. 复用资产清单（来自 Phase 1 探索）

| 层 | 复用 | 接入点 |
|---|---|---|
| 基础设施 | `src/core/*`（config/database/storage/audit/email/auth） | 直接用 |
| 认证授权 | `src/api/auth/*` + `editor` 角色 | 新增 editorial 路由挂 `require_roles("editor")` |
| 摄取 | `src/ingestion/preprocessor.process_file` | F1 |
| 评审引擎 | `src/evaluation/orchestrator.run_evaluation_pipeline` + providers + 六维/五轴 | F2 |
| 报告 | `src/reporting/*`（scoring/versioning/simple_pdf_builder/public_filter/charts） | F4 |
| 专家复核 | `src/review/*` | 编辑 override 可复用提交链路 |
| API | `src/api/routers/*` 现有端点 | 新增 `routers/editorial.py` |
| 前端 | `src/web/*`（SubmitterPortal/InternalReportView 等） | 新增 EditorialWorkspace |
| 数据模型 | `src/models/*` 13 张表 | 复用 + 小幅新增 |

## 8. 项目组织（已确认）

- **本项目内继续**，不另起独立项目。理由：资产同构度高；未来投稿人模块需复用现有 `SubmitterPortal`；前期六维/providers/报告为同库资产。
- 新建子包 `src/editorial/`，隔离编辑预审业务逻辑，不污染前期"已发表论文评价"资产。
- 配置真源：审稿意见 prompt/输出契约放 `configs/frameworks/editorial-*.yaml`；评分层仍用现有 `law-v2.56.6-20260522.yaml`。

## 9. 开放点回执与剩余待定

已决：
1. **期刊组织**：本期做 `journals` 表 + 期刊级配置（多期刊可扩展，交大法学/学术月刊之外可加）；权限精控简化、留后续。
2. **CCB / 决定口径**：CCB 可调作参考；决定基于各维度**优良中差分档**组合，不走 CCB 阈值。
3. **label 入 Git**：全部不入，加 `.gitignore`。
4. **投稿人模块**：本期预留接入点不实现。
5. **决定细分**：需细分，拟四档（退稿/重大修改/小修改后录用/直接录用），档数待最终确认。

剩余待定：
6. **问题重合度算法**（F5）：先做简单版，复杂版后续迭代。两期刊格式不一的统一处理先取简单策略。
7. **作者模拟预审（F8）**：是否本期纳入？倾向纳入（引擎零增量、前端有底座、业务闭环），深度待定。

## 10. 验证里程碑（占位，待实现 plan 细化）

- M1：label 12 篇 ingestion + 六维 pipeline 跑通，产出六维分 + 优良中差分档。
- M2：审稿意见生成器 + 预审报告 builder 跑通单篇（含细分档决定建议）。
- M3：label 对齐评估器跑通 12 篇，产出决定一致率 + 问题重合度（简单版）。
- M4：编辑工作台前端可上传/看报告/override 决定；多期刊配置切换（交大法学/学术月刊）。
- M5（待确认）：作者模拟预审报告 builder + `SubmitterPortal` 入口。
