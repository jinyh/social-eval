# SocialEval 部署与当前进展交接

> 更新时间：2026-07-26（Asia/Taipei）
>
> 用途：供后续 Claude Code/Codex 在不重新猜测上下文的情况下继续本机测试和
> 交大 jCloud 生产部署。

## 1. 当前结论

- 生产化账户安全、数据库迁移、Docker 编排、HTTPS 入口、备份、健康检查、
  保留策略和部署文档已经实现。
- 生产化账户与运维基线提交为 `b88b515`；最近已提交功能基线为 `d8b40a1`
  （五轴已切换 Qwen3.7-Max）。其后的投稿人注册、投稿工作流和管理员双栏改动已
  验证并部署到本机测试容器，但本交接时仍在工作区，必须先提交再交付 jCloud。
- 本机 `socialeval-test` 已使用新代码完成重建，六个常驻服务均健康。
- 本机测试数据库已迁移到 Alembic `016 (head)`；原命名卷和原测试数据仍在。
- 本机测试邀请公开基址已覆盖为 `https://localhost`；修复前邮件中的
  `http://localhost:5173` 旧链接不会自动改写，须在管理员邀请记录中重新发送。
- 尚未部署到交大 jCloud，也没有推送到远程镜像仓库。
- `docker-compose.test.yml` 已纳入版本管理；它用于复用已有测试命名卷并绕开只适用于
  正式域名的生产启动门禁。不要当成生产配置使用。

## 2. 已实现功能

### 2.1 账户与权限

- 投稿人使用邮箱自助注册，完成邮箱验证后登录；自助注册固定为投稿人，不能指定
  编辑、专家或管理员角色。
- 编辑、专家和管理员继续由管理员邀请，不开放自助注册。
- 投稿人不能调用可指定框架和模型的通用上传接口，只能选择正式启用期刊并使用该
  编辑单元的不可变策略快照投稿。
- 密码摘要改为 Argon2id；旧 PBKDF2 摘要在成功登录后自动升级。
- 用户可修改密码，并选择撤销全部接口密钥。
- 支持忘记密码、邮件重置和管理员强制重置。
- 管理员强制重置后，旧密码、全部旧会话和全部接口密钥立即失效。
- 用户角色变化或账户停用后，旧会话和接口密钥立即失效。
- 保留“至少一名有效管理员”及“有在办责任时禁止停用/换角色”的保护。
- 管理员必须绑定 TOTP 双因素认证；支持一次性恢复码、恢复码重新生成和运维紧急
  重置。
- 邀请和密码重置令牌只以哈希或加密形式落库；邮件提交成功后清除发件箱中的加密
  令牌。
- 接口密钥最长有效 90 天，可在账户设置或管理员后台撤销。

### 2.2 管理界面

- 管理员工作台采用可收缩左侧导航和右侧工作区，分为系统总览、用户与权限、
  期刊与编辑单元、期刊策略、启用验证和模型升级验证。
- “用户与权限”内部采用纵向信息流：全宽用户目录在前，内部成员邀请表单和邀请记录
  依次在后；用户目录不再与邀请表单左右并排。
- 管理员可选择编辑单元和已有期刊策略版本查看；已冻结版本不能原地覆盖，只能基于
  现有版本创建新草稿。
- 账户设置中可修改密码、管理接口密钥、重新生成双因素认证恢复码。
- 管理员可筛选用户、调整角色、停用/恢复、发送密码重置邮件、撤销接口密钥。
- 管理员可查看、重发和撤销邀请。
- 编辑工作台保持“左侧可收缩导航、右侧工作区”的双栏结构；从 768px 浏览器宽度
  开始显示常驻左栏，避免 Retina 笔记本窗口误进入单页移动布局。
- 匿名化人工门禁在“稿件概览”和“处理与决定”中均提供确认入口；按钮明确要求核对
  网页匿名稿无身份信息后才能继续，不能把原稿含姓名本身当作确认依据。
- 新投稿先由确定性规则处理身份字段，再由配置
  `editorial-anonymization-v1` 指定的 GLM-5.2 检测高风险段落并按原文精确替换。
  自动处理成功后流程继续并向责任编辑发送站内通知；模型不确定、片段无法匹配或调用
  失败时安全降级到人工门禁。该用途独立于六维生产模型集。
- 管理员可将编辑单元从“试运行”验证并切换为“正式启用”，也可填写原因后退回
  “试运行”；回退保留历史稿件、评价、决定、验证和审计记录。
- 期刊适配口径和模型选择使用不可变策略版本。管理员维护草稿并登记验证，单元负责人
  在编辑工作台完成学术签署，管理员不能代签；投稿始终绑定创建时的策略快照。
- 激活链接使用 `/activate#token=...`，密码重置链接使用
  `/reset-password#token=...`，令牌不会进入服务器访问日志的 URL 查询部分。
- 投稿人、编辑、专家和管理员的分角色手册见
  [用户手册索引](../user-manuals/README.md)。
- 投稿人只看到正式启用期刊及其公开策略字段；可提交本人稿件、查看可公开进度、
  接收编辑发布的作者结果并申请撤稿。编辑可见投稿人身份，但模型和专家只读取匿名稿。
- 作者结果发布固定到当次选择的公开报告版本；后续生成新报告不会未经编辑再次发布
  就自动对投稿人可见。

### 2.3 生产运维

- `docker-compose.prod.yml` 使用 Caddy 作为唯一公网入口，仅暴露 80/443。
- API、Worker、PostgreSQL、Redis、前端和代理均设置健康检查、资源限制及日志轮转。
- 稿件、数据库和 Caddy 状态绑定到 `SOCIALEVAL_DATA_ROOT` 指向的独立数据盘。
- `deploy/scripts/prepare_data_dirs.sh` 负责创建目录并设置容器 UID/GID。
- `deploy/scripts/backup.sh` 使用 `pg_dump`、`pg_restore --list` 和 Restic 备份。
- 已提供备份、健康检查、保留清理及失败邮件告警的 systemd 单元和定时器。
- 公网只开放 `/api/health/live`；包含数据库、Redis 和存储状态的
  `/api/health/ready` 只允许从容器内部检查。
- 生产启动会拒绝 HTTP、本机域名、默认/占位密钥、未启用管理员双因素认证或邮件
  配置不完整等情况。

### 2.4 编辑预审与模型状态

- 编辑工作台当前按“智能辅助综合摘要在前，五轴在前、六维在后”组织报告。
- 五轴首屏只显示总分，可展开五个轴的分值范围和原文证据；五轴不评价论文质量，
  不与六维加总。
- 六维标准名称为研究创新性、现状洞察度、理论建构力、逻辑连贯性、学术共识度和
  前瞻延展性。
- 编辑看到四个匿名模型的实际分歧；专家先在网页中阅读结构化匿名稿并独立评阅，
  锁定后才能对照模型结果。
- 新候选协议不再按“宽松组/严格组”运行。第二轮中，每个模型匿名参考另外三个模型
  的完整第一轮意见；旧分组只用于复现变更前创建的候选任务。
- 全局稳定模型集仍是 `six-dimension-v1`：GLM-5.1、Qwen3.6-Plus、
  DeepSeek-v4-Pro、Kimi-k2.6。
- 试运行编辑单元的新投稿使用 `six-dimension-v2-candidate`：GLM-5.2、
  Qwen3.7-Max、DeepSeek-v4-Pro、Kimi-k2.6，并采用四模型同级匿名互评。
- 两款升级模型的 24 篇隔离配对已经跑完，但当前框架完整闭环仅完成 1/6。正式启用
  仍需补齐闭环、编辑抽样和单元负责人签署；历史投稿不回写。
- 《交大法学》《学术月刊》的正式校准与启用仍应以本机 `raw/label/` 授权材料、
  冻结样本和最终验证记录为依据，原始材料不得提交 Git 或交给普通连接器。

## 3. 已完成验证

- 后端：`286 passed`。
- 前端：`24 passed`，Vite 生产构建通过。
- Ruff、Python 格式、Shell 语法、`uv lock --check`、Compose 配置和 Caddy
  配置验证通过。
- PostgreSQL 临时实例验证：
  `全量升级到 014 → 插入已有邀请数据 → 回退到 013 → 再升级到 014`。
- 策略版本迁移验证：
  `全量升级到 015 → 回退到 014 → 再升级到 015`。
- 投稿人迁移已在保留原测试数据的 PostgreSQL 上完成
  `015 → 016`，迁移容器退出码为 `0`。
- 本地生产 API/前端镜像和 `socialeval-test-*` 测试镜像均构建成功。
- 当前测试环境：
  - `api`：健康；
  - `worker`：健康；
  - `postgres`：健康；
  - `redis`：健康；
  - `frontend`、`proxy`：运行中；
  - `migrate`：退出码 `0`；
  - 内部就绪检查：database、redis、storage 均为 `ok`；
  - 数据库迁移：`016 (head)`。
- 2026-07-26 邀请修复复核：
  - API 与 Worker 的有效 `PUBLIC_BASE_URL` 均为 `https://localhost`；
  - `https://localhost/activate` 返回 `200`；
  - 公网 `/api/health/live` 返回正常；
  - 公网 `/api/health/ready` 按设计返回 `404`，详细就绪状态只供容器内部检查。
- 2026-07-26 合成法学稿端到端冒烟：
  - 62 个工作单元全部完成，模型调用和工作单元失败数均为 0；
  - 六维由 GLM-5.2、Qwen3.7-Max、DeepSeek-v4-Pro、Kimi-k2.6 完成
    6 个维度、两轮同级互评；
  - 该次冒烟运行时五轴仍使用 DeepSeek-v4-Pro、Qwen3.6-Plus；随后已将未来五轴
    任务直接切换为 DeepSeek-v4-Pro、Qwen3.7-Max，历史结果不回写；
  - 综合参考分、五轴、综合意见和内外两类报告均已生成；
  - 由于维度分歧超过门槛，稿件正确进入专家复核，试运行建议保持扣留。
- 本机保留此前测试数据，并新增一篇不含真实个人信息的合成稿用于当前端到端冒烟。
  交接文档不记录未公开稿件题目、正文或逐篇模型输出。

## 4. 本机测试环境

访问地址：

```text
https://localhost
```

本地 Caddy 使用测试证书，命令行检查可使用 `curl -k`。浏览器是否需要手工信任证书
取决于本机证书状态。

测试环境沿用以下外部命名卷：

```text
socialeval-test_postgres_data
socialeval-test_redis_data
socialeval-test_app_data
socialeval-test_caddy_data
socialeval-test_caddy_config
```

不要删除这些卷，也不要使用会清理卷的命令。重建测试环境使用：

```bash
SOCIALEVAL_DATA_ROOT=/tmp/socialeval-test-unused \
docker compose -p socialeval-test \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.test.yml \
  up -d --build
```

`SOCIALEVAL_DATA_ROOT` 在这里仅用于满足基础生产 Compose 的插值要求；
`docker-compose.test.yml` 会把所有持久化目标替换为上述已有外部命名卷。

验证命令：

```bash
SOCIALEVAL_DATA_ROOT=/tmp/socialeval-test-unused \
docker compose -p socialeval-test \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.test.yml ps

docker exec socialeval-test-api-1 alembic current
curl -kfsS https://localhost/api/health/live
```

测试覆盖文件明确设置 `APP_ENV=development` 和
`SESSION_HTTPS_ONLY=false`，但仍要求管理员双因素认证。它只适用于本机，不得叠加到
jCloud 生产命令中。测试环境使用开发字段加密口径，新产生的双因素认证密钥和短期
令牌不得迁移到生产数据库。

测试覆盖文件还将 API 和 Worker 的公开基址设为 `https://localhost`，确保新邀请与
密码重置邮件指向当前 Docker 入口。修复前已经发送的邮件必须从管理员后台重新发送；
重建容器不会修改旧邮件内容，也不会自动产生外部邮件。

## 5. 当前生产配置状态

本机 `.env.production` 仍是本地测试配置，不能直接上传 jCloud。生产自检目前会
指出以下类别的问题：

- `PUBLIC_BASE_URL` 仍是本机 HTTP 地址；
- `ALLOWED_ORIGINS` 尚未与正式来源对齐；
- 尚未设置独立、至少 32 字符且非占位值的 `FIELD_ENCRYPTION_KEY`。

不要在文档、提交、聊天或日志中写出 `.env.production` 的真实内容。正式环境至少要
重新确认：

```text
APP_DOMAIN
PUBLIC_BASE_URL
ALLOWED_HOSTS
ALLOWED_ORIGINS
SECRET_KEY
FIELD_ENCRYPTION_KEY
POSTGRES_PASSWORD
DATABASE_URL
SOCIALEVAL_DATA_ROOT
SMTP_*
OPERATIONS_ALERT_RECIPIENTS
模型供应商接口密钥
Restic/S3 备份凭据
```

`SECRET_KEY` 与 `FIELD_ENCRYPTION_KEY` 必须独立随机生成。字段加密密钥一经生产使用
不得随意更换，否则已有 TOTP 密钥和待发送安全令牌将无法解密。

## 6. jCloud 下一步

按以下顺序继续：

1. 确认正式域名、DNS、学校 SMTP 账号和发件人地址已经批准。
2. 准备 Ubuntu 主机、独立数据盘、私有 Restic/S3 备份存储及仅允许必要来源的 SSH。
3. 只开放公网 80/443；PostgreSQL 和 Redis 不映射公网端口。
4. 在服务器生成正式 `.env.production`，权限设为 `0600`。
5. 运行 `scripts/check_production_readiness.py`；不得通过测试覆盖文件绕过失败项。
6. 运行 `deploy/scripts/prepare_data_dirs.sh` 初始化独立数据盘目录。
7. 以 commit `d8b40a1` 或其后明确审核过的提交构建并标记镜像；当前本机分支
   尚未推送，不能从远端旧 `main` 直接部署。
8. 先启动 PostgreSQL/Redis，再运行 `migrate`，确认 `016 (head)` 后启动其余服务。
9. 创建首个管理员或迁移获批准的账户，首次登录立即绑定双因素认证并离线保存恢复码。
10. 完成投稿人注册与邮箱验证、内部成员邀请与激活、密码重置、角色变化、投稿、
    模型评阅、专家复核、作者结果发布、撤稿、报告和 SMTP 的端到端冒烟。
11. 初始化 Restic，手工完成一次备份和临时数据库恢复演练，再启用 systemd 定时器。
12. 观察 API 5xx、Celery 队列、模型超时、SMTP 失败、磁盘空间和备份新鲜度至少
    24 小时。

生产命令和回滚步骤以
[上线检查清单](launch-checklist.md)及
[备份恢复手册](backup-and-recovery-runbook.md)为准。

## 7. 上线前必须再次确认

- 数据保留默认值目前为：稿件内容 365 天、审计 1095 天。正式上线前应由期刊和学校
  确认该口径是否符合业务、档案和合规要求。
- 外部期刊接入的签名、幂等策略和 MinerU 启用方式尚未冻结，不应在本次 jCloud
  单机部署中擅自扩展。
- `raw/label/`、未发表稿件和真实审稿意见不得进入 Git、普通浏览器连接器、Web
  Search 或未经审计的外部工具。
- 模型调用必须继续经过 `src/evaluation/providers/`；默认并发 3，上限 5。
- 本机测试数据库不得直接当作生产数据库；至少应重新创建正式管理员安全材料和生产
  字段加密口径。
- 上线前需要确认模型供应商对未公开稿件的数据处理条款和学校授权范围。

## 8. Claude Code 接手时的第一组检查

```bash
git status --short
git log -3 --oneline
docker compose ls --all
docker ps -a --filter label=com.docker.compose.project=socialeval-test
uv lock --check
```

然后阅读：

1. 根目录 `AGENTS.md`；
2. 本文档；
3. `docs/deployment/launch-checklist.md`；
4. `docs/deployment/backup-and-recovery-runbook.md`；
5. `docs/editorial/deployment-single-host-docker.md`。

不得在未核对当前卷挂载、目标数据库和备份状态前执行破坏性 Docker、数据库或文件
命令。

## 9. 绕门禁生产操作记录（2026-08-06，用户授权）

为测试投稿人预审路径，用户授权在生产 social（`111.186.57.186`）绕门禁执行以下
操作，事后需走正式门禁补齐：

- 交大法学单元（`00000000-0000-0000-0000-000000000101`）绕门禁切
  `rollout_state=active` + 绑 `active_policy_version_id=b0146939-817d-4c0f-a938-e2f9538a13cf`
  （trial policy v1.1）；该 trial policy `status` 改 `active`、`activated_by=a1aa8f14-...`
  （admin `socialeval@sjtu.edu.cn`）。
- 改 frozen `editorial_policy_versions.snapshot.opinion.synthesis_prompt_template` 两次
  （先去照抄占位，后同步 `fd70907`/`09275a1` 改进 prompt），每次重算 `content_sha256`
  （`policy_from_version` 校验通过）。
- `synthesis_model` 留空 → 综合意见用 `providers[0]=glm-5.2`（用户要求 glm-5.2）。
- 候选集（`six-dimension-v2-candidate` glm-5.2/qwen3.7-max）随单元启用进入生产评审
  （候选集验证闭环 1/6，未达转正门禁）。
- 部署链：工作线一 `732d902`/`e71148b` → `fd70907`/`a3eafc3` → `09275a1`/`136586e`。
- 回滚锚点：`backup-20260806-v2/v3/v4` 镜像 tag + 各 merge commit
  （`git reset --hard <commit>` + `docker tag backup→latest` + `up -d`）。
- 综合意见示例：投稿 `8440e9c8` 有 glm-5.2 真实综合意见（法言法语、7 条改进、
  modification 字符串前缀【必改】/【可选】）。

遗留：

- 候选集转正门禁未完成（编辑抽样 + unit_admin 签署 + 验证闭环 1/6→达标）。
- yaml `synthesis_model=qwen3.7-max-2026-06-08` 与生产实际 glm-5.2 不一致，
  建议改 yaml 为空或 glm-5.2。
- 正式启用门禁（`validation_run` + unit_admin 签署 + `set_rollout_state`）需补齐
  后才能合规。

