# SocialEval 路线重排与契约对齐设计

## 背景

当前仓库已经具备 ingestion / knowledge / evaluation / reliability / models 的原型能力，但仍缺少 API、报告、复核、任务编排与前端，整体状态更接近“领域内核原型”，而非“可交付系统”。

在继续开发前，必须先消除三类结构性冲突：

1. **领域契约冲突**：文档以 law v2.0 为当前框架，但代码仍按 v1 schema / prompt 结构实现。
2. **认证契约冲突**：需求要求 Web 使用 Session、第三方系统使用 API Key，而现有 roadmap 草案按 JWT-first 设计。
3. **状态与报告契约冲突**：现有 ORM 仍是原型状态枚举，无法承载复核、恢复、版本化报告等业务流。

## 设计目标

1. 先让“文档声明的当前系统”在代码层成立。
2. 先打通后端闭环，再做报告美化与全角色前端。
3. 所有阶段都以 `docs/requirements/SocialEval-requirements-v0.4.md` 和 `CLAUDE.md` 为约束源。

## 重新分阶段方案

### 阶段 0：契约对齐

目标：统一 v2 配置 / schema / loader / prompt / 测试基线，使当前法学框架真的可加载、可渲染、可验证。

范围：
- 修正 `schema_v2.json`
- 对齐 `law-v2.0-20260413.yaml`
- 让 loader 支持 v2，并保留 v1 兼容
- 统一 prompt 渲染逻辑（含 precheck）
- 增补/更新测试

### 阶段 1：平台骨架与认证

目标：实现 FastAPI 主入口、Session 认证、API Key 认证、角色权限依赖与基础路由。

原则：
- 不走 JWT-first
- Web 端优先 Session / Cookie
- 外部系统优先 API Key

### 阶段 2：评审闭环 MVP

目标：实现 上传 → 预处理 → precheck → 多模型评分 → reliability → 状态查询 → 结果入库 的最小闭环。

### 阶段 3：报告与专家复核

目标：实现内部/公开报告、导出、低置信度进复核队列、专家指派、复核提交与报告重生成。

### 阶段 4：状态机、审计与恢复

目标：补足任务状态机、审计留痕、异常恢复、批量任务聚合。

### 阶段 5：前端交付

目标：按“编辑端优先”策略交付前端。

执行顺序：
1. 编辑端
2. 投稿人最小闭环
3. 专家端
4. 管理员端

## 关键设计决策

### 1. v2 作为当前活动框架

- `law-v2.0-20260413.yaml` 视为当前法学框架真源
- `law_v1.yaml` 保留为兼容与回归测试样本
- loader 负责同时兼容 v1 / v2，并输出统一的 `Framework`

### 2. Prompt 渲染采用“双模式”

- 旧版模板：显式使用 `{paper_content}` / `{references}` 占位符
- v2 模板：若无占位符，则由 prompt builder 自动追加论文正文与参考文献上下文

这样既兼容 v1，也避免 v2 因 JSON 花括号触发 `.format()` 解析错误。

### 3. 路线图先修地基，再做功能

任何阶段都不得建立在错误的 schema、错误的认证口径或错误的状态机上。

## 阶段 0 验收标准

1. `load_framework("configs/frameworks/law-v2.0-20260413.yaml")` 成功
2. `Framework` 暴露统一字段：`name / discipline / version / std_threshold / dimensions`
3. v2 prompt 可正确生成正文+参考文献上下文
4. v2 precheck prompt 可正确生成正文上下文
5. 相关测试通过
