# 5轴6维与 E2 缺口修复设计

## 目标

补齐三大刊、交大法学、学术月刊现有权威结果中的模型级缺口，并在不重跑完整论文、不覆盖有效历史输出的前提下，恢复以下数据契约：

- 六维 E1：每篇、每维的 R1 与 R2 均包含四个指定模型；
- 五轴：每篇 R1 包含 DeepSeek 与 Qwen，R2 依照 v0.2 路由明确为 `skip`、`light` 或 `full`；
- 三大刊 E2：候选池 110 篇每维的 R1 与 R2 均包含四个指定模型；
- 派生统计、E2 ranking 和结果目录索引与修复后的逐篇数据一致；
- 所有真实模型调用均保留模型、轮次、维度、耗时、原始响应和错误信息。

## 已确认现状

权威逐篇目录为：

- `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/`
- `results/datasets/jiaodafaxue/six-dimension/phase2-r2-v2.55/per-paper/`
- `results/datasets/xueshuyuekan/six-dimension/phase2-r2-v2.55/per-paper/`
- `results/datasets/<dataset>/five-axis/position-v0.2/per-paper/`
- `results/rankings/e2-ccb-v5/per-paper/round1/`
- `results/rankings/e2-ccb-v5/per-paper/round2/`

当前至少有 617 个六维/E2 模型×维度评分槽位缺失，另有交大法学五轴 paper-99 的 Qwen R1 解析失败。四个六维模型均由 DashScope provider 提供，当前环境可实例化。

现有批处理脚本不适合作为修复入口：它们通常在文件存在时整篇跳过，部分默认输出到 `results/runs/`，并会重跑大量已完成调用。

## 方案比较

### 方案 A：整篇重跑

实现简单，但会重跑已有模型结果，成本高，并改变大量不需要改变的历史判断。拒绝采用。

### 方案 B：手工为每类结果写一次性脚本

短期可用，但三套六维数据和 E2 混合格式会产生重复逻辑，难以再次审计。拒绝采用。

### 方案 C：统一“缺口清单 + 槽位级修复 + 暂存合并”

采用本方案。先扫描生成稳定的缺口清单，只调用缺失的模型×轮次×维度；修复结果先写入暂存区，通过结构校验后才原子合并到权威文件。

## 架构

新增一个可测试的修复模块和一个薄 CLI：

- `src/evaluation/repair/`：路径注册表、缺口扫描、格式适配、统计重算、合并校验；
- `scripts/repair_evaluation_gaps.py`：参数解析、模型调用、受控并发、暂存与应用；
- `tests/test_evaluation/test_gap_repair.py`：纯函数与路径约束测试；
- `tests/test_scripts/test_repair_evaluation_gaps.py`：使用假 provider 的并发/断点续传测试。

CLI 分四个阶段：

1. `audit`：只读扫描，生成 `repair-manifest.json`；
2. `run`：按清单补 R1，等待 R1 屏障完成后补 R2，写入暂存副本；
3. `validate`：验证模型集合、分数范围、R2 上下文、统计一致性和路径边界；
4. `apply`：仅将验证通过的暂存副本原子替换权威文件，并生成修复前备份和 provenance。

## 数据与合并规则

### 六维 E1

- 使用 `law-v2.55-cross-review.yaml` 的维度 prompt 和 R2 交叉评审逻辑；
- R1 只补缺失模型，并把原始响应写入 `raw_outputs`；
- R2 只补缺失模型。目标模型的 R1 原始输出必须存在；对方组至少一个 R1 原始输出必须存在；
- R2 原始响应写入 `round2_raw_outputs`，而不是只保留修订分；
- 每次合并后重算单维 mean/std、变化量和 overall；原有有效评分不修改。

### 五轴

- 仅修复语义无效的模型输出，不能把带 `error` 的模型键当作完成；
- 先补齐 R1，再重新计算 R2 路由；
- `skip` 是完整且合法的 R2 状态，必须有明确 marker；`light/full` 必须补齐两个模型；
- 重新生成 merged/final，但保留旧记录到 repair provenance。

### E2

- 同时适配历史 `model_scores` 格式与自包含 `round1_scores` 格式；
- R1 与 R2 都补齐四模型；
- 修复后运行 `scripts/rebuild_ranking_v5_ccb.py`，要求 110 篇 × 6 维全部 `pooled_n=8`、method 为 `median(8)`；
- ranking 的论文 ID 必须与 pool 完全一致。

## 路径与安全

- 所有默认路径以仓库根目录解析，不依赖启动时的工作目录；
- 只允许写入注册表列出的逐篇目录、指定暂存目录和本地忽略备份目录；
- 暂存目录默认 `results/runs/completeness-repair-20260716/`；
- 应用前逐文件保存 SHA-256、备份路径和变更槽位；
- 已有有效评分按字节级值比较，任何意外变化都使验证失败；
- 不修改独立 R1 审计快照；权威对象是自包含 R1+R2 逐篇结果。

## 并发与失败恢复

- 冒烟阶段：2 篇并发、API 并发 4，覆盖 R1 缺失、R2 缺失和两种 E2 格式；
- 全量阶段：论文并发 4、API 并发 12；所有调用受同一个 semaphore 约束；
- 同一论文 R1 完成后才能调度其 R2；不同论文并发；
- 单槽位最多 2 次尝试，退避重试；内容审查错误不做无限重试；
- 每个完成槽位立即写 checkpoint，进程中断后只续跑未成功槽位；
- 失败不会应用半成品，最终报告列出仍缺失的精确槽位。

## 验收标准

1. 单元测试证明：部分文件不会被整篇跳过；路径不能越出仓库/注册目录；原值不被覆盖；混合 E2 格式均能识别。
2. 假 provider 并发测试证明：最大在途请求不超过设置值，R2 不早于所需 R1，重启后能断点续传。
3. 冒烟测试成功且只改变预期槽位后，才能进入全量真实调用。
4. 最终审计：
   - 三刊物六维 R1/R2 的每维四模型完整；
   - 三刊物五轴均为有效双模型 R1，R2 有合法终态；
   - E2 R1/R2 每维四模型完整；
   - E2 ranking 110 篇全部 `pooled_n=8`；
   - manifests、summary 和 catalog 路径存在且数量与逐篇文件一致。

