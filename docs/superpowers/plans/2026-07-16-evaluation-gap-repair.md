# Evaluation Gap Repair Implementation Plan

> **For Codex:** Use `superpowers:executing-plans` to execute this plan task by task. Follow TDD for every behavior change and `superpowers:verification-before-completion` before declaring success.

**Goal:** 安全补齐三大刊、交大法学、学术月刊的六维/五轴缺口与三大刊 E2 R1/R2 缺口，并验证权威路径和派生结果一致。

**Architecture:** 用 `src/evaluation/repair` 提供纯函数扫描、格式适配、重算和路径守卫；薄 CLI 负责 provider 调用、受控并发、checkpoint、暂存和原子应用。真实数据先在原工作区 audit/smoke，再全量运行。

**Tech Stack:** Python 3.10+、asyncio、现有 provider abstraction、pytest/pytest-asyncio、uv。

---

## Task 1: 建立权威路径注册表与缺口模型

**Files:**
- Create: `src/evaluation/repair/__init__.py`
- Create: `src/evaluation/repair/models.py`
- Create: `src/evaluation/repair/registry.py`
- Test: `tests/test_evaluation/test_gap_repair.py`

1. 先写失败测试：三个数据集与 E2 路径都以 `project_root` 解析，未知数据集报错，写路径越界报错。
2. 运行 `uv run pytest -q tests/test_evaluation/test_gap_repair.py`，确认失败原因是实现不存在。
3. 实现 `RepairTarget`、`Gap`、模型常量、路径注册表和 `ensure_allowed_path()`。
4. 重跑测试至通过。

## Task 2: 实现混合格式扫描与统计重算

**Files:**
- Create: `src/evaluation/repair/six_dimension.py`
- Modify: `tests/test_evaluation/test_gap_repair.py`

1. 写 fixtures 覆盖标准六维、自包含 E2、legacy E2、带 error 的五轴模型。
2. 写失败测试：只报告缺失/无效模型，不把 `error` 键视为有效；R1/R2 分别计数。
3. 实现分数/原始输出适配器、gap 扫描、单维与 overall 重算。
4. 写失败测试：合并一个槽位后旧有效值保持不变、统计更新、R2 原始响应持久化。
5. 实现不可变合并并重跑测试。

## Task 3: 实现计划、checkpoint 与受控并发调度

**Files:**
- Create: `src/evaluation/repair/runner.py`
- Create: `scripts/repair_evaluation_gaps.py`
- Create: `tests/test_scripts/test_repair_evaluation_gaps.py`

1. 使用假 provider 写失败测试：API 峰值不超过 semaphore；同篇 R2 等待缺失 R1；已有成功 checkpoint 不重调。
2. 实现 `audit/run/validate/apply` CLI 骨架、manifest/checkpoint schema 和原子 JSON 写入。
3. 实现 R1/R2 两阶段调度、最多 2 次重试和错误分类。
4. 使用现有 `build_prompt()`、`build_cross_review_prompt()` 和 provider abstraction 接入六维调用。
5. 运行脚本测试至通过，并运行 Ruff。

## Task 4: 实现五轴 paper 修复与合法 R2 终态

**Files:**
- Create: `src/evaluation/repair/five_axis.py`
- Modify: `scripts/repair_evaluation_gaps.py`
- Modify: `tests/test_evaluation/test_gap_repair.py`
- Modify: `tests/test_scripts/test_repair_evaluation_gaps.py`

1. 写失败测试：带 error 的 Qwen R1 被识别为缺口；补齐后重新路由；skip marker 和 light/full 双模型均可通过验证。
2. 复用 `src.evaluation.position.workflow` 的 prompt、route、merge 函数完成实现。
3. 确认五轴 raw response 与 provenance 被保存。
4. 重跑目标测试和 Ruff。

## Task 5: 实现暂存验证、原子应用与派生文件检查

**Files:**
- Create: `src/evaluation/repair/validation.py`
- Modify: `scripts/repair_evaluation_gaps.py`
- Modify: `tests/test_evaluation/test_gap_repair.py`
- Modify: `tests/test_scripts/test_repair_evaluation_gaps.py`

1. 写失败测试：非目标旧值变化、分数越界、模型不齐、路径越界、统计不一致都阻止 apply。
2. 实现 SHA-256 清单、备份、`os.replace` 原子应用和 apply report。
3. 增加 E2 pool/ranking ID 与 `pooled_n/method` 校验。
4. 运行全部新增测试、相关 reporting/catalog 测试和 Ruff。

## Task 6: 合并代码并在真实工作区做只读审计与并发冒烟

**Files:**
- Modify: 当前分支（合入隔离分支提交）
- Generate ignored artifact: `results/runs/completeness-repair-20260716/`

1. 在隔离分支提交一个逻辑提交并合入 `refactor/e2-ccb-cleanup`，确认工作区无意外改动。
2. 在原工作区运行 `audit`，核对缺口数与本次审计基线一致。
3. 用假 provider 运行 API 并发 12 的压力测试；再用真实 provider 以论文并发 2/API 并发 4 做代表性冒烟。
4. 验证暂存副本只改变目标槽位；失败则停止，不 apply。

## Task 7: 全量并发补测、应用与重建

**Files:**
- Modify ignored data: 注册表中的权威逐篇 JSON
- Regenerate: 对应 `summary.csv`、E2 `ranking.json`、结果 catalog

1. 以论文并发 4/API 并发 12 运行全量 repair；持续记录 checkpoint。
2. 对仍失败槽位再执行一次受控续跑；内容策略硬失败保留明确报告。
3. 运行 `validate`，只有零结构错误且旧值保持不变才执行 `apply`。
4. 运行 `scripts/rebuild_ranking_v5_ccb.py` 和现有 summary/catalog 生成入口。
5. 再次运行全量完整性审计，输出各数据集 R1/R2/五轴/E2 数量与残余风险。

## Task 8: 最终验证

1. 运行 `uv run pytest -q tests/test_evaluation/test_gap_repair.py tests/test_scripts/test_repair_evaluation_gaps.py tests/test_reporting/test_scoring.py tests/test_results_catalog.py`。
2. 运行 `uv run ruff check src/evaluation/repair scripts/repair_evaluation_gaps.py tests/test_evaluation/test_gap_repair.py tests/test_scripts/test_repair_evaluation_gaps.py`。
3. 运行 CLI `audit` 与 `validate`，保存最终报告。
4. 检查 `git diff --check`、`git status --short`，确认没有密钥、日志或忽略数据误入 Git。

