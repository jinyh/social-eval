# SocialEval 迁移记录

> 日期:2026-07-18 ｜ 迁移:`jinyh` → `bright` 账户(同一台 Mac)

## 迁移状态(已完成)

| 项 | 值 |
|---|---|
| 目标路径 | `/Users/bright/Projects/SocialEval` |
| 属主 | `bright:staff` |
| 大小 | 4.9G |
| 文件数 | 13239 |
| git HEAD | `0bff25b`（`fix: 修复迁移后的双引擎配置`，2026-07-18 迁移当时的 HEAD） |
| git status | 迁移时刻工作树干净；`main` 领先 `origin/main` 1 提交（`0bff25b`）待推送（后续提交会前进，此处为迁移时快照） |

### 迁移时排除项

- `.venv`(虚拟环境,含 jinyh 绝对路径的 shebang,跨账户失效；已在 bright 下按锁文件重建)
- `.ruff_cache` / `.pytest_cache` / `__pycache__` / `*.pyc`(缓存)
- `.DS_Store` / `._*`(AppleDouble 资源叉垃圾)

### 迁移手法(供回溯)

两步规避 macOS TCC 隐私保护(root 无法读 jinyh 的 `~/Documents`):

1. **jinyh 自己** `tar` 打包到 `/Users/Shared/SocialEval`(jinyh 能读自己的 Documents、能写 Shared)
2. **root** 把 Shared 副本 `mv` 到 `/Users/bright/Projects/SocialEval` 并 `chown -R bright:staff`

源 `jinyh` 账户下的 `SocialEval` 仍在,未删除。NAS 上的 restic 全量备份(`MacBackup/restic` 快照 `ade098c5`)不受影响。

---

## 2026-07-18 迁移审计与收尾

- Codex 与 Claude Code 共用 `AGENTS.md` 作为项目上下文真源；`CLAUDE.md` 只保留跳转入口。
- 项目 skill 内容真源为 `agent-skills/`，安装脚本默认同时链接到 `~/.codex/skills/` 与 `~/.claude/skills/`。
- Python 版本固定为 3.10；旧 `.venv` 不复用。
- 三大刊元数据、六维、五轴和原始 PDF 均核验为 1920 篇；当前 E2 池为 105 篇。
- 旧 `core.hookspath` 已解除，`repair-evaluation-gaps` linked worktree 与残留分支已清理（内容等价于 main 上的 `bde47a1`，删除无损失）。
- 双引擎（Codex/Claude Code）skill 目录边界已在 `AGENTS.md` 写明；`skills-lock.json` 已补登 `expert-audit-report`。
- GitHub Ed25519 主机密钥已按官方指纹核验；bright 公钥已加入 `jinyh` 账户，`git ls-remote` 与 `git push --dry-run` 均验证通过。
- `.venv` 已用 Python 3.10 和 `uv.lock` 重建，完整测试通过。
- 文档声明的冷归档 `../SocialEval-archive/2026-07-16-deep-clean/` 未随主仓库出现，需从旧账户或 NAS/restic 单独恢复。
- `.env` 只迁移了本地配置骨架；模型 API Key、SMTP 凭据及生产 `SECRET_KEY` 需在 bright 账户重新注入。

## bright 账户环境重建

```bash
cd ~/Projects/SocialEval

# 1. 重建虚拟环境(旧 .venv 已排除)
uv sync --extra dev --frozen # 项目用 uv 管理(pyproject.toml + uv.lock)

# 2. 确认 git 状态
git status                    # 提交迁移收尾变更后应为干净
git log --oneline -1          # 应为迁移收尾提交（迁移当时为 0bff25b）
git remote -v                 # origin 指向 GitHub,沿用原 remote

# 3. 推送时用 bright 自己的 git 凭证(jinyh 的凭证不跨账户生效)
git ls-remote origin HEAD
git push --dry-run origin main
```

### 可能遇到的问题

- **`git: dubious ownership`**:仓库属主是 bright,若以非 bright 用户(如 root/sudo)运行 git 会告警。用 bright 自己运行则无此问题;必要时 `git config --global --add safe.directory ~/Projects/SocialEval`。
- **`uv` 未安装**:在 bright 账户装 `brew install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh | sh`。
- **Python 版本**:项目要求 3.10+。`uv python list` 看可用版本,`uv python pin 3.10` 指定。
