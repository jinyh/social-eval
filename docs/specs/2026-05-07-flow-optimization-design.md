# 两端流程优化设计：Submitter + Editor 入口

**日期**：2026-05-07
**状态**：Draft
**范围**：Submitter 和 Editor 两种入口的完整流程优化

---

## Context

当前 SocialEval 前端存在两个核心问题：

1. **Editor 缺少完整 Dashboard**：Editor 登录后只能看到复核队列和内部报告，没有论文管理、批量上传、启动评价的能力
2. **Submitter 上传后自动触发 pipeline**：投稿人上传即创建 EvaluationTask 并自动启动评价，但实际业务中应由编辑决定何时启动

此外，公开报告需要编辑审批后才对投稿人可见，且编辑可选择调用大模型生成综合摘要和修改建议。

---

## 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 管道模式 | 统一管道式 | 两种入口共享同一 pipeline，差异仅在入口动作和权限 |
| Pipeline 触发 | 编辑手动触发 | 编辑控制何时启动评价，投稿人上传只创建 Paper |
| 公开报告可见性 | 编辑审批后可见 | 新增 `published` 终态，审批前投稿人看不到报告 |
| 专家分配数量 | 至少 3 人 | 前端改为多选，最低 3 人 |
| 状态展示 | 中文 | 所有前端状态标签使用中文 |
| 公开报告生成 | 可选 AI 辅助 | 编辑可选择调用大模型总结 3 个模型 + 3 个专家意见 |

---

## 流程设计

### Submitter 流程

```
1. 上传论文
   → 创建 Paper（status = "待处理"），不创建 EvaluationTask
   → 系统提示："论文已提交，等待编辑处理"

2. 等待 → 前端轮询状态
   状态中文映射：
   - 待处理 → 编辑尚未启动评价
   - 评价中 → AI 评价进行中
   - 专家复核中 → 已分配专家
   - 评价完成 → 评价完成但报告未发布（投稿人看不到报告）
   - 报告审批中 → 编辑正在审批公开报告
   - 已发布 → 编辑已批准，可查看公开报告
   - 准入未通过 → precheck reject
   - 处理失败 → 技术异常

3. 查看公开报告（仅"已发布"状态后可见）
   → 综合总分 + 六维评分均值 + AI 生成摘要 + 修改建议（如有）+ 专家意见摘要
   → 下载简洁 PDF
```

### Editor 流程

```
1. 接收投稿 / 自行上传
   ┌─ 投稿人上传的论文 → 自动出现在"待处理"列表（只有 Paper，无 Task）
   └─ 编辑自行批量上传 → 多文件一次提交，BatchTask 容器

2. 选择论文启动评价
   → 编辑勾选单篇或多篇 → 批量触发
   → 为每篇创建 EvaluationTask + 触发 pipeline
   → 选中论文状态从"待处理"变为"评价中"

3. 监控评价进度
   → 批量视角：总篇数 / 已完成 / 失败数
   → 单篇视角：状态、precheck 结果、可靠性汇总

4. 评价完成 → 内部报告自动生成 + 公开报告草稿生成（待审批）

5. 进入复核决策
   → 低置信度论文自动出现在复核队列
   → 高置信度论文编辑可手动追加复核
   → 分配专家：至少 3 人（多选下拉）

6. 专家复核完成 → 报告重新生成
   → 公开报告草稿更新，仍为"待审批"

7. 编辑审批公开报告
   ┌─ 选择"AI 辅助生成" → 调用大模型：
   │   输入：3 个模型各维度评分 + 证据 + 3 个专家意见（如有）
   │   输出：
   │     - 综合评分摘要（六维总览 + 整体判断）
   │     - 修改建议（可选）
   │   编辑审核 AI 输出 → 可微调 → 确认批准
   │
   └─ 选择"直接批准" → 使用过滤版内部报告作为公开报告
       （等同当前 public_filter.py 的行为）

8. 批准发布 → 状态变为"已发布" → 投稿人端可见
```

---

## 状态机更新

当前状态机（`src/core/state_machine.py`）：

```
pending    → {processing, closed}
processing → {completed, reviewing, recovering, closed}
reviewing  → {completed, recovering, closed}
recovering → {processing, closed}
completed  → {reviewing, closed}
closed     → {}
```

优化后状态机：

```
pending        → {processing, closed}
processing     → {completed, reviewing, recovering, closed}
reviewing      → {completed, recovering, closed}
completed      → {report_pending, reviewing, closed}
report_pending → {published, closed, recovering}
published      → {}                    ← 新终态，投稿人可看公开报告
recovering     → {processing, closed}
closed         → {}
```

中文状态映射表：

| 状态 | 中文 | Submitter 可看报告 | Editor 可操作 |
|------|------|:------------------:|:-------------:|
| pending | 待处理 | ❌ | 启动评价 / 删除 |
| processing | 评价中 | ❌ | 监控进度 |
| reviewing | 专家复核中 | ❌ | 分配专家 / 监控 |
| completed | 评价完成 | ❌ | 审批报告 / 追加复核 |
| report_pending | 报告审批中 | ❌ | 审批操作 / AI 辅助生成 |
| published | 已发布 | ✅ | 查看 |
| recovering | 处理失败 | ❌ | 重试 / 关闭 |
| closed | 已关闭 | ❌ | 查看 |
| precheck_failed | 准入未通过 | ❌ | 重新上传提示 |

---

## 数据模型变化

### Paper 模型（新增字段）

无新增字段。状态值扩展至包含 `report_pending` 和 `published`。

### Report 模型（新增字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_approved` | Boolean, default=False | 公开报告是否经编辑批准 |
| `approved_by` | String(36), nullable | 批准者 user_id |
| `approved_at` | DateTime, nullable | 批准时间 |

### EvaluationTask 模型

无新增字段。创建时机从"上传时自动"变为"编辑启动时手动"。

### 新增 API 端点

| 端点 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/api/papers/{id}/start-evaluation` | POST | editor, admin | 编辑手动启动评价，创建 EvaluationTask + 触发 pipeline |
| `/api/papers/batch-start` | POST | editor, admin | 批量启动多篇论文的评价 |
| `/api/papers/{id}/generate-summary` | POST | editor, admin | 调用大模型生成公开摘要 + 修改建议 |
| `/api/papers/{id}/approve-report` | POST | editor, admin | 编辑批准公开报告发布 |
| `/api/papers/{id}/reject-report` | POST | editor, admin | 编辑拒绝公开报告（退回修改） |

### 修改的 API 端点

| 端点 | 变化 | 说明 |
|------|------|------|
| `POST /api/papers` | 不再自动创建 EvaluationTask | 上传只创建 Paper |
| `POST /api/papers/batch` | 同上 | 批量上传只创建 Paper |
| `POST /api/reviews/{task_id}/assign` | 前端多选至少 3 人 | 后端已支持多人，前端需改为多选 |
| `GET /api/papers/{id}/report` | 仅 published 状态可访问（对 submitter） | 当前 completed 即可访问 |

### 修改的 API Schemas

`SubmitterPortal.tsx` 中的 `statusLabel` 映射更新：

```typescript
const statusLabel: Record<string, string> = {
  pending: "待处理",
  processing: "评价中",
  reviewing: "专家复核中",
  completed: "评价完成",
  report_pending: "报告审批中",
  published: "已发布",
  recovering: "处理失败",
  closed: "已关闭",
  precheck_failed: "准入未通过",
};
```

---

## AI 辅助公开报告生成

### 输入

调用大模型时，输入包含：

- 论文标题
- 每个维度的 3 个模型评分 + evidence_quotes + analysis
- 每个维度的均值 / std / 置信度标签
- 每个维度的专家复核意见（如有）：expert_score + reason
- 是否生成修改建议（布尔参数）

### 输出

```json
{
  "conclusion": "大模型生成的综合判断文字",
  "dimensions": [
    {
      "name_zh": "问题创新性",
      "name_en": "Problem Originality",
      "score": 75,
      "summary": "大模型生成的该维度评语",
      "revision_suggestion": "大模型生成的修改建议（可选，仅在请求时生成）"
    }
  ],
  "overall_suggestion": "大模型生成的整体修改建议（可选）",
  "expert_conclusion": "如有专家复核，大模型总结的专家整体意见方向"
}
```

### 实现方式

- 新增 `src/reporting/summary_generator.py`，复用 `src/evaluation/providers/` 的统一抽象层
- 大模型调用记录同样持久化到 `AICallLog`
- 生成结果写入 `Report.report_data`（覆盖草稿版）
- 编辑可在此结果基础上微调后再批准

---

## Submitter 上传变化

### 当前实现

上传时 `_create_paper_and_task()` 同时创建 Paper 和 EvaluationTask，然后 `_dispatch_pipeline()` 自动触发 pipeline。

### 优化后实现

上传时只创建 Paper（不创建 EvaluationTask），`status = "pending"`，文件保存后返回 `paper_id`。EvaluationTask 的创建和 pipeline 触发由编辑端 `/api/papers/{id}/start-evaluation` 负责。

Submitter 上传流程简化为：

```
POST /api/papers → 创建 Paper + 保存文件 → 返回 { paper_id, paper_status: "pending" }
```

---

## 前端组件变化概要

### SubmitterPortal.tsx

- 上传后只返回 paper_id（不再返回 task_id）
- 状态标签改为中文
- 公开报告仅在 `published` 状态时展示
- 新增"报告审批中"状态提示
- 删除功能不变

### Editor Dashboard（新组件）

Editor 从 `ReviewWorkspace` 升级为完整 Dashboard，包含：

1. **论文管理区**：待处理列表（含投稿人提交 + 编辑自上传）+ 批量上传 + 启动评价
2. **进度监控区**：批量进度 + 单篇状态
3. **复核工作区**：复核队列 + 多专家分配（至少 3 人）
4. **报告审批区**：内部报告查看 + AI 辅助生成摘要 + 批准/拒绝发布

### ReviewWorkspace.tsx

- 专家分配从单选改为多选（最少 3 人）
- 状态标签改为中文
- 新增 `report_pending` 状态展示
- 编辑视角增加审批操作入口

### InternalReportView.tsx

- 无大变化，状态标签改为中文

---

## 验证计划

### 后端验证

1. 运行 `pytest tests/` 确保现有测试不受影响
2. 新增测试：
   - `test_start_evaluation_api`：编辑手动启动评价的 API 测试
   - `test_batch_start_api`：批量启动评价测试
   - `test_generate_summary_api`：AI 辅助公开报告生成测试
   - `test_approve_report_api`：报告审批测试
   - `test_state_machine_transitions`：新增 `report_pending` 和 `published` 状态转换测试

3. 状态机验证：确保 `pending → processing → completed → report_pending → published` 完整路径可走通
4. 权限验证：submitter 无法访问 `/start-evaluation`、`/generate-summary`、`/approve-report`
5. 公开报告可见性验证：submitter 在 `published` 前无法获取公开报告

### 前端验证

1. 启动 `npm run dev`，登录 submitter 账号测试上传和状态轮询
2. 登录 editor 账号测试：
   - 查看待处理论文列表
   - 批量上传多篇论文
   - 勾选并启动评价
   - 分配 3 个专家
   - 审批公开报告（含 AI 辅助生成）
3. 登录 expert 账号测试复核提交
4. 回到 submitter 验证"已发布"后公开报告可见

### 数据库迁移验证

1. `alembic revision --autogenerate` 生成迁移脚本
2. 检查 Report 表新增字段（is_approved, approved_by, approved_at）
3. `alembic upgrade head` 应用迁移
4. 确认现有数据不受影响（is_approved 默认 False）

---

## 关键文件清单

### 后端需修改

| 文件 | 变化 |
|------|------|
| `src/core/state_machine.py` | 新增 `report_pending`, `published` 状态转换 |
| `src/models/paper.py` | 状态注释更新（无代码变化） |
| `src/models/report.py` | 新增 `is_approved`, `approved_by`, `approved_at` |
| `src/api/routers/papers.py` | 上传不再创建 Task + 新增 start-evaluation / batch-start / generate-summary / approve-report |
| `src/api/routers/reports.py` | 公开报告权限检查增加 published 状态判断 |
| `src/api/routers/reviews.py` | 无变化（专家分配后端已支持多人） |
| `src/reporting/summary_generator.py` | 新增：AI 辅助公开报告生成模块 |
| `src/reporting/public_filter.py` | 无变化（仍作为"直接批准"模式的后端） |
| `src/reporting/versioning.py` | `generate_reports_for_task` 中写入草稿版 `is_approved=False` |
| `src/evaluation/orchestrator.py` | pipeline 完成后状态改为 `completed`（不变），不再直接设 `paper.status = "completed"` |

### 前端需修改

| 文件 | 变化 |
|------|------|
| `src/web/src/components/SubmitterPortal.tsx` | 状态中文 + 上传简化 + published 判断 |
| `src/web/src/components/ReviewWorkspace.tsx` | 编辑视角增加论文管理 + 启动评价 + 审批 + 专家多选 |
| `src/web/src/components/StudentSummary.tsx` | 状态中文 |
| `src/web/src/components/InternalReportView.tsx` | 状态中文 |
| `src/web/src/lib/api.ts` | 新增 startEvaluation / batchStart / generateSummary / approveReport |
| `src/web/src/lib/types.ts` | 新增状态值 + 新增 API 返回类型 |