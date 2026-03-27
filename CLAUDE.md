# SocialEval — 项目上下文

## 项目简介

**SocialEval** 是一套面向自主知识体系的 AI 辅助学术评价系统，以法学论文评审为切入点，支持拓展至人文社科各学科。

核心机制：多模型并发评价 → 一致性验证 → 专家复核 → 标准化报告输出

需求文档：`docs/requirements/SocialEval-requirements-v0.1.md`

---

## 架构方向

### 技术选型（待确认）
- **后端**：Python（FastAPI），uv 管理依赖
- **前端**：React + TypeScript
- **数据库**：PostgreSQL（论文/评分/审计日志），Redis（任务队列）
- **任务队列**：Celery + Redis（异步评审任务）
- **AI 接入**：统一抽象层，支持 OpenAI / Anthropic / DeepSeek

### 规划目录结构（代码开发前参考）
```
src/
  ingestion/       # F1: 文档摄取与预处理
  knowledge/       # F2: 知识体系配置（YAML/JSON 动态加载）
  evaluation/      # F3: AI 评价引擎（多模型并发）
  reliability/     # F4: 可靠性验证层（均值/标准差/置信度）
  review/          # F5: 专家复核工作流
  reporting/       # F6: 报告生成（PDF / JSON 导出）
  api/             # F8: RESTful API
  web/             # F7: Web 前端
configs/
  frameworks/      # 各学科知识体系 YAML 配置文件
docs/
  requirements/    # 需求文档
  architecture/    # ADR（架构决策记录）
tests/             # 镜像 src/ 结构
```

---

## 核心领域知识

### 六维评价框架（法学默认配置）

| 维度 | 英文名 | 描述 |
|------|--------|------|
| 问题创新性 | Problem Originality | 研究问题的独创性与价值 |
| 现状洞察度 | Literature Insight | 对既有文献的把握与批判 |
| 理论建构力 | Theoretical Construction | 理论框架的完整性与自洽性 |
| 逻辑严密性 | Logical Coherence | 论证推理的严谨程度 |
| 学术共识度 | Scholarly Consensus | 与主流学术共同体的对话程度 |
| 前瞻延展性 | Forward Extension | 研究对未来议题的开拓潜力 |

评分范围：0–100，可靠性阈值：**标准差 ≤ 5 分**为高置信度

---

## 开发规范

### 语言与工具
- Python 3.10+，依赖管理用 `uv`
- TypeScript（前端），禁用 `any` 和 `@ts-ignore`
- Ruff（Python lint/format），ESLint + Prettier（前端）

### 关键约束
- **AI 模型调用**必须通过统一抽象层，禁止在业务层直接 import SDK
- **知识体系配置**只能通过 `configs/frameworks/` 的 YAML/JSON 文件定义，禁止硬编码维度
- **所有 AI 调用记录**须持久化（输入/输出/时间戳/模型名），不可只存最终结果
- **API 接口**必须 Token 认证，不得暴露未鉴权端点

### 安全红线
- `.env` 必须在 `.gitignore` 中，不得提交任何 API Key
- 所有用户上传文件须做类型校验（PDF/DOCX/TXT）

### 提交规范
- Conventional Commits：`feat:` / `fix:` / `refactor:` / `docs:`
- 每个 PR 不超过 400 行，每次 commit = 一个逻辑变更

---

## 待澄清事项（来自需求 v0.1）

在开始相关模块开发前，须先澄清：

- [ ] OCR 支持：是否需要中文扫描版 PDF 支持？
- [ ] 多模型并发数：默认值和上限各是多少？
- [ ] 专家通知触发条件：仅低置信度论文，还是全部论文？
- [ ] 用户注册方式：自注册 or 管理员邀请？

---

## 参考资料

| 文件 | 说明 |
|------|------|
| `ref/法学论文的人工评价逻辑.pptx` | 法学论文人工评价方法论 |
| `ref/AI_Legal_Paper_Evaluation_System.pptx` | AI 评价系统方案演示 |
| `ref/lecture_citation_quality.pdf` | 引用质量相关学术参考 |
| `ref/【会议纪要V2】...研讨会.docx` | 专家研讨会纪要 |

---

## 项目级 Skills

项目专属 skill 统一放在 `agent-skills/`，这里是内容真源；不要分别维护 Claude/Codex 两套副本。

### 当前可用

- `socialeval-project-context`
  - 文件：`agent-skills/socialeval-project-context/SKILL.md`
  - 触发场景：在本仓库里做功能开发、修复、测试、方案设计时
  - 作用：统一加载项目背景、领域约束、目录约定与实现边界

### 使用约定

- 需要项目上下文时，优先读取对应的 `agent-skills/<name>/SKILL.md`
- 新增项目专属工作流时，在 `agent-skills/` 下新增独立目录，避免继续扩写本文件
- 若本地代理支持用户级 skill 目录，可用 `scripts/install_project_skills.py` 把仓库内 skill 软链接到本机技能目录，例如 `~/.agents/skills/`
