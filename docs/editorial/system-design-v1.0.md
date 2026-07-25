# 编辑辅助预审系统设计 v1.0

## 1. 架构

编辑业务放在 `src/editorial/`，只编排已有的摄取、评价、可靠性、报告和专家复核模块。
通用评价 API 保持兼容。

```text
React EditorialWorkspace
            │
     FastAPI /api/editorial
            │
  editorial access/workflow/policy
       │        │        │
       │        │        └─ versioned journal policy
       │        └─ evaluation providers + R1/R2 + position
       └─ PostgreSQL + immutable document storage
                    │
               Celery / Redis
```

## 2. 数据模型

- `journals`：期刊；
- `editorial_units`：可独立配置和启用的编辑单元；
- `editorial_unit_memberships`：用户与编辑单元成员关系；
- `editorial_submissions`：投稿主记录和流程状态；
- `editorial_documents`：原稿、匿名稿和报告制品；
- `position_assessments`：五轴独立结果；
- `editorial_opinions`：基于四模型既有结果生成的综合摘要和编辑意见版本；
- `editorial_decisions`：预审决定、终审决定及其版本；
- `notifications`：站内通知。

`evaluation_tasks` 增加实际评价输入路径，使通用 `Paper` 保留原稿路径，而编辑流可只把
匿名派生文本送入评价。编辑业务表引用已有 `papers` 和 `evaluation_tasks`。

## 3. 隔离策略

数据库共享，但所有投稿查询都必须先通过有效 `editorial_unit_memberships` 限定
`unit_id`。管理员是显式例外并记录访问审计。详情、导出、决定和子资源不能只按资源 ID
查询后再假定有权限。

数据库唯一约束保证外部稿号只在同一编辑单元内唯一。未来如使用 PostgreSQL RLS，
应用层检查仍保留为纵深防御。

## 4. 配置

学术分和分档来自已部署的公共框架。编辑单元政策文件只引用：

- 公共框架版本；
- 期刊适配性模板；
- 决定映射；
- 意见模板；
- 报告显示策略。

运行时把配置版本写入投稿，保证历史可复现。管理界面只选择部署版本。

## 5. 工作流与幂等

每个阶段以投稿状态和已存在制品为检查点。重试时：

- 原稿不重复写入；
- 已成功、版本匹配的阶段不重复调用模型；
- 失败调用日志保留；
- 新结果用新版本追加；
- 决定和编辑意见从不覆盖。

外部期刊回调的签名和幂等键尚未确定，因此 v1 不开放外部接入端点。

## 6. 模型调用

所有调用经 `src/evaluation/providers/`。调用日志记录：

- `task_id`、调用类型和轮次；
- Prompt 与原始响应；
- 模型、供应商、开始/完成时间和耗时；
- 成功或失败及错误摘要。

业务层不直接导入供应商 SDK。匿名化文本是编辑流模型调用的唯一稿件正文输入。

## 7. 推荐门禁

决定引擎先根据公共分档和版本化期刊映射计算内部候选类别，再独立计算
建议展示状态：

- 试运行结果：编辑单元尚未正式启用；
- 建议暂缓：存在专家复核、阶段降级或待确认事项；
- 建议就绪：可向编辑展示候选类别。

任何状态都不会自动提交编辑决定。预审决定与外审后的终审决定分阶段锁定。

## 8. 专家独立评阅

专家任务分为“独立评阅”和“对照复核”：

1. 独立评阅阶段只提供匿名稿、待复核维度和空白评分表；
2. 专家提交分数与理由后立即锁定，并记录提交时间；
3. 系统随后开放四个匿名模型的逐维分数、证据和判断；
4. 专家逐项选择认可、不认可或无意见；不认可必须说明理由；
5. 两阶段记录都保留，不用专家意见覆盖原始模型结果。

## 9. 部署

本地通过测试后，使用同一组不可变镜像部署到 Linux 云主机。第一阶段采用单机
Docker Compose：反向代理、前端、API、Celery Worker、PostgreSQL、Redis。
数据库和稿件使用持久卷，异机备份。无需 Kubernetes。
