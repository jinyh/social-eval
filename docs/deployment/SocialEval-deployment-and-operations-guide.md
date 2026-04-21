# SocialEval 部署与运维说明

**版本**：2026-04-16  
**适用代码版本**：当前 `main` 分支  
**适用范围**：开发环境、本地联调、单机上线、打包交付、Docker 使用与常见运维问题

---

## 1. 先看结论：这个项目当前应该怎么部署

当前仓库已经具备：

- 后端 API（FastAPI）
- 异步任务（Celery + Redis）
- 数据库迁移（Alembic）
- 前端界面（React + TypeScript + Vite）
- 报告导出、专家复核、审计与恢复能力

但**当前仓库的 Docker 配置只负责依赖服务**：

- PostgreSQL
- Redis

也就是说，**当前最推荐的部署方式**不是“整个项目全部塞进一个 docker-compose 一键启动”，而是：

### 推荐方式：单机部署 / 本地部署

1. 用 Docker 启动依赖：
   - PostgreSQL
   - Redis
2. 用 Python 启动后端 API
3. 用 Celery 启动异步 Worker
4. 用 Vite/Nginx 提供前端

这也是当前仓库最稳定、最符合现状的方式。

---

## 2. 当前仓库的部署形态说明

### 2.1 现在已经有的东西

- `docker-compose.yml`
  - 负责启动 `postgres:16`
  - 负责启动 `redis:7-alpine`
- `src/api/main.py`
  - FastAPI 主入口
- `src/tasks/celery_app.py`
  - Celery 应用入口
- `src/tasks/evaluation_task.py`
  - Celery 任务定义
- `src/web/`
  - React + TypeScript 前端工程

### 2.2 现在还没有的东西

当前仓库**没有提供**以下内容：

- 后端 Dockerfile
- 前端 Dockerfile
- 生产版 compose（例如 `docker-compose.prod.yml`）
- 反向代理配置模板（如 Nginx 配置文件）
- systemd / supervisor / NSSM 的现成服务文件

所以你现在要理解为：

> **这个项目已经能运行、能上线，但运维编排还没有被完全“容器化封装”。**

---

## 3. Docker 在这个项目里是干什么的

### 3.1 Docker 目前只负责依赖服务

当前 `docker-compose.yml` 内容非常简单：

- `postgres`
- `redis`

也就是说：

- **后端 API 不在 Docker 里跑**
- **Celery Worker 不在 Docker 里跑**
- **前端也不在 Docker 里跑**

### 3.2 什么时候必须用 Docker

当你要快速起：

- PostgreSQL
- Redis

时，最方便的方法就是：

```bash
docker compose up -d
```

### 3.3 什么时候可以不用 Docker

如果你的机器上已经有：

- PostgreSQL 16
- Redis 7

而且你自己会配连接串，那么也可以完全不用 Docker。

也就是说：

> Docker 不是这个项目运行的唯一前提，  
> 但它是当前最方便的依赖启动方式。

---

## 4. 如何判断 Docker 能不能用

在 Windows 上，你至少要满足下面几个条件：

1. 已安装 **Docker Desktop**
2. Docker Desktop 已启动
3. WSL2 / Hyper-V 可用
4. 当前终端能连接 Docker daemon

### 4.1 最直接的判断命令

```bash
docker version
docker ps
docker compose version
```

如果这些命令都不报错，说明 Docker 可以用。

如果报的是类似下面的错误：

```text
failed to connect to the docker API
```

通常说明：

- Docker Desktop 没启动
- 或者 Docker Desktop 没装好

---

## 5. Windows 上怎么启动 Docker

### 5.1 首次安装

1. 安装 **Docker Desktop**
2. 安装时启用：
   - WSL2
   - Linux containers
3. 重启电脑（如安装程序要求）

### 5.2 日常启动

1. 打开开始菜单
2. 启动 **Docker Desktop**
3. 等右下角图标稳定、状态显示“Running”
4. 打开 PowerShell
5. 执行：

```powershell
docker version
docker ps
```

如果能正常返回，说明 Docker 已经启动成功。

### 5.3 常见失败现象

#### 情况 A：`docker version` 报连接错误

说明 Docker daemon 没起来。  
处理方式：

1. 确认 Docker Desktop 已打开
2. 等待 10~30 秒再试
3. 如果还是不行，重启 Docker Desktop
4. 再不行，重启电脑

#### 情况 B：WSL2 不可用

Docker Desktop 会提示虚拟化问题。  
需要：

- 打开 BIOS 虚拟化
- 启用 Windows 的 WSL / Hyper-V

---

## 6. Docker 大概占多少内存

当前这个项目的 Docker 依赖容器只有两个：

- PostgreSQL
- Redis

### 6.1 容器本体大致内存

开发环境下通常大概是：

- PostgreSQL：约 `100MB ~ 300MB`
- Redis：约 `10MB ~ 50MB`

合计一般：

> **150MB ~ 400MB 左右**

### 6.2 实际体感为什么更高

因为 Windows 上 Docker Desktop / WSL2 本身也要吃内存。  
所以整套体验上建议预留：

> **2GB ~ 3GB 内存**

### 6.3 机器建议

- 4GB：不推荐
- 8GB：可用，但会紧
- 16GB：比较舒服

更正式的云资源建议请看：

- `docs/architecture/SocialEval-mvp-cloud-sizing.md`

---

## 7. 本地开发环境部署（推荐起步方式）

这是最推荐的日常启动方式。

### 7.1 前置要求

你需要准备：

- Python 3.10+（当前实测 Python 3.12 可用）
- Node.js（当前实测 Node 24 可用）
- npm
- Docker Desktop
- Git

### 7.2 克隆项目并进入目录

```bash
git clone <your-repo-url>
cd social-eval
```

### 7.3 安装 Python 依赖

```bash
uv sync --extra dev
```

### 7.4 配置环境变量

复制模板：

```bash
cp .env.example .env
```

Windows PowerShell 可以写成：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少填这些：

```env
DATABASE_URL=postgresql://socialeval:socialeval@localhost:5432/socialeval
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@socialeval.local
```

### 7.5 启动 PostgreSQL + Redis

```bash
docker compose up -d
```

检查容器状态：

```bash
docker ps
```

### 7.6 初始化数据库

```bash
alembic upgrade head
```

### 7.7 启动后端 API

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

启动后可访问：

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/health`

### 7.8 启动 Celery Worker

另开一个终端：

```bash
uv run celery -A src.tasks.celery_app.celery_app worker --loglevel=info
```

> 注意：如果你不启动 Worker，上传论文后异步任务不会真正消费。  
> 测试里能跑通，是因为测试环境会注入同步执行器；真实运行需要 Worker。

### 7.9 启动前端

```bash
cd src/web
npm install
npm run dev
```

前端默认地址：

- `http://localhost:5173`

后端已经允许：

- `http://localhost:5173`
- `http://127.0.0.1:5173`

通过 CORS 访问后端。

---

## 8. 本地验证顺序（建议按这个检查）

### 8.1 依赖服务

```bash
docker ps
```

你应该能看到：

- postgres
- redis

### 8.2 后端

```bash
curl http://localhost:8000/api/health
```

期望返回：

```json
{"status":"ok","service":"socialeval"}
```

### 8.3 前端

浏览器打开：

- `http://localhost:5173`

### 8.4 Celery

观察 worker 日志，确保没有连接 Redis 失败。

---

## 9. 生产/上线部署推荐方案（当前最合适）

当前代码最适合用**单机部署**上线。

### 9.1 推荐结构

单机上运行：

- Nginx
- FastAPI
- Celery Worker
- PostgreSQL
- Redis

如果按当前仓库状态部署，推荐方式是：

#### 方案 A：依赖用 Docker，应用直接跑宿主机

- PostgreSQL：Docker
- Redis：Docker
- API：宿主机 Python
- Celery：宿主机 Python
- 前端：构建后交给 Nginx

这是**当前最推荐**的方式。

#### 方案 B：数据库/Redis 用云服务或宿主机原生安装

也完全可行，只要：

- `DATABASE_URL`
- `REDIS_URL`

配置正确即可。

---

## 10. Linux 单机上线步骤（推荐）

以下以 Ubuntu 22.04 为例。

### 10.1 安装基础环境

建议准备：

- Python 3.12
- Node.js 20+/24
- npm
- uv
- Docker / Docker Compose
- Nginx

### 10.2 拉代码

```bash
git clone <your-repo-url>
cd social-eval
```

### 10.3 后端依赖

```bash
uv sync --extra dev
```

如果你做纯生产，也可以只装主依赖，但当前最简单的是沿用上面命令。

### 10.4 环境变量

创建 `.env`，至少填：

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- AI 提供商 API Keys
- SMTP 配置

### 10.5 启动依赖服务

```bash
docker compose up -d
```

### 10.6 迁移数据库

```bash
alembic upgrade head
```

### 10.7 构建前端

```bash
cd src/web
npm ci
npm run build
cd ../..
```

构建产物在：

- `src/web/dist/`

### 10.8 启动 API

先简单跑：

```bash
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

如果你要更稳，可以直接用多 worker：

```bash
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 4
```

### 10.9 启动 Celery

```bash
uv run celery -A src.tasks.celery_app.celery_app worker --loglevel=info
```

### 10.10 用 Nginx 提供前端与反向代理

推荐：

- `/` 提供静态前端（`src/web/dist`）
- `/api` 反代到 `127.0.0.1:8000`

一个最小示例：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /opt/social-eval/src/web/dist;
    index index.html;

    location / {
        try_files $uri /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 11. systemd 管理建议（Linux）

为了开机自启，建议把 API 和 Celery 做成 systemd 服务。

### 11.1 API 服务示例

`/etc/systemd/system/socialeval-api.service`

```ini
[Unit]
Description=SocialEval API
After=network.target

[Service]
WorkingDirectory=/opt/social-eval
ExecStart=/usr/bin/env uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
EnvironmentFile=/opt/social-eval/.env

[Install]
WantedBy=multi-user.target
```

### 11.2 Celery 服务示例

`/etc/systemd/system/socialeval-worker.service`

```ini
[Unit]
Description=SocialEval Celery Worker
After=network.target

[Service]
WorkingDirectory=/opt/social-eval
ExecStart=/usr/bin/env uv run celery -A src.tasks.celery_app.celery_app worker --loglevel=info
Restart=always
EnvironmentFile=/opt/social-eval/.env

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now socialeval-api
sudo systemctl enable --now socialeval-worker
```

---

## 12. 数据库迁移怎么做

### 12.1 首次部署

```bash
alembic upgrade head
```

### 12.2 后续版本升级

拉最新代码后再次执行：

```bash
alembic upgrade head
```

当前仓库已有迁移：

- `001` 初始表结构
- `002` 认证字段
- `003` pipeline 字段
- `004` 报告与复核字段
- `005` 审计与 batch 字段

### 12.3 回滚

如需回滚一步：

```bash
alembic downgrade -1
```

---

## 13. “封装之后怎么做”——这里分三种理解

你说的“封装”一般有三种可能，我分别解释。

### 13.1 封装为前端可交付包

如果你指的是前端打包：

```bash
cd src/web
npm run build
```

结果：

- 前端静态文件产出到 `src/web/dist/`

然后你可以：

- 交给 Nginx
- 交给 CDN
- 放到对象存储静态站点

这一步已经能做。

### 13.2 封装为后端可部署程序

如果你指的是后端：

当前后端是 Python 应用，最推荐的不是“打成 exe”，而是：

1. 保留源码部署
2. 用 `uv` 管依赖
3. 用 systemd / supervisor 管进程

如果你确实要做 Python 包，也可以尝试：

```bash
uv build
```

但当前项目更适合**源码部署**，因为还涉及：

- Alembic 迁移
- 静态资源
- Celery worker
- `.env`
- 数据目录

### 13.3 封装成全容器化交付

如果你是问“能不能最后全部封装成 docker 镜像上线”，答案是：

> **可以，但当前仓库还没有做完这一层封装。**

如果后续要做，建议新增：

- `Dockerfile.backend`
- `Dockerfile.frontend`
- `docker-compose.prod.yml`

推荐结构：

- backend image：运行 FastAPI
- worker image：运行 Celery
- frontend image：构建静态资源并交给 Nginx

不过这属于下一步运维工程，不是当前仓库现状。

---

## 14. 当前最现实的“上线交付包”长什么样

如果你今天就要把项目交给别人部署，最实用的交付内容应该是：

1. **源码仓库**
2. `.env.example`
3. 这份部署说明
4. 数据库迁移脚本
5. 前端构建产物（可选）

如果你想做成一个“交付目录”，建议包含：

```text
social-eval/
  .env.example
  README.md
  docs/deployment/SocialEval-deployment-and-operations-guide.md
  docker-compose.yml
  alembic/
  src/
  src/web/dist/   # 可选，若已提前构建
```

---

## 15. Docker 的常用命令（本项目）

### 启动依赖

```bash
docker compose up -d
```

### 查看容器

```bash
docker ps
```

### 查看日志

```bash
docker compose logs -f
```

### 停止容器

```bash
docker compose down
```

### 停止并清空卷（危险）

```bash
docker compose down -v
```

> 这会删除 PostgreSQL 数据卷。  
> 如果你不想丢数据，不要随便加 `-v`。

---

## 16. 常见问题排查

### 16.1 `docker version` 报错

说明 Docker Desktop 没启动或没装好。

### 16.2 `docker compose up -d` 后 5432/6379 端口冲突

说明本机已经有：

- PostgreSQL
- Redis

解决方法：

1. 停掉本机已有服务
2. 或修改 `docker-compose.yml` 的宿主机端口
3. 同时修改 `.env` 里的连接串

### 16.3 `alembic upgrade head` 失败

先确认：

- PostgreSQL 已启动
- `DATABASE_URL` 正确
- 用户名密码正确

### 16.4 前端能开，后端登录不了

先检查：

- 后端是否真的跑在 `8000`
- 前端访问地址是不是 `5173`
- CORS 当前只允许：
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

如果你换了端口或域名，需要改 `src/api/main.py` 里的 CORS 配置。

### 16.5 上传了论文但没有处理

大概率是：

- **Celery worker 没启动**

你需要确认这个命令正在运行：

```bash
uv run celery -A src.tasks.celery_app.celery_app worker --loglevel=info
```

### 16.6 PDF 导出报错

当前项目使用的是 matplotlib 生成 PDF 输出，  
不像典型 WeasyPrint 方案那样依赖系统的 `pango` / `cairo`。

所以这方面依赖相对轻一些。

### 16.7 Session 登录在跨域下失效

如果前后端跨域或走 HTTPS，后续要进一步调整：

- Session cookie 配置
- 域名
- `https_only`
- 反向代理头

当前仓库默认适合：

- 本地开发
- 单域名代理部署

---

## 17. 上线前检查清单

建议上线前逐项确认：

### 基础环境

- [ ] Python / uv 可用
- [ ] Node / npm 可用
- [ ] Docker 可用
- [ ] `.env` 已配置

### 依赖

- [ ] PostgreSQL 正常
- [ ] Redis 正常
- [ ] `alembic upgrade head` 成功

### 应用

- [ ] API 可访问：`/api/health`
- [ ] 前端可访问
- [ ] Celery worker 正常连接 Redis
- [ ] 登录流程可用
- [ ] 上传论文后任务能进入处理
- [ ] 报告页面与导出可用
- [ ] 专家复核流程可用

### 运维

- [ ] 日志可查看
- [ ] 数据目录有备份策略
- [ ] PostgreSQL 有备份方案
- [ ] 只开放必要端口

---

## 18. 推荐的实际部署策略

如果你现在要把项目真正落地，我建议这样做：

### 开发/联调环境

- Docker Desktop 启 PostgreSQL + Redis
- 本地跑 API / Celery / 前端

### 第一版上线

- 单台 Ubuntu 22.04
- Docker 跑 PostgreSQL + Redis
- systemd 跑 API + Celery
- Nginx 托管前端 dist 并反代 `/api`

### 后续再做

- 后后端 Dockerfile
- 前端 Dockerfile
- 生产 compose
- 对象存储
- HTTPS
- 备份/监控/告警

---

## 19. 最后一句：当前项目“最正确”的理解

你可以把当前项目理解成：

> **业务功能已经齐了，部署方式以“源码 + 依赖容器 + 系统服务”最合适；**
>  
> **如果要进一步做成一键式全容器化产品，还需要再补一层运维封装。**

