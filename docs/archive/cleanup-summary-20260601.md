# Cleanup Summary 2026-06-01

本次清理采用保守归档策略：保留当前活跃数据和 Phase 2 全量评审真源，只删除明确生成物或完全重复副本，并把旧实验产物移动到既有 archive 体系。

## 保留真源

- `configs/frameworks/law-v2.50.2-20260514.yaml`
- `configs/frameworks/law-v2.55-cross-review.yaml`
- `configs/frameworks/law-v2.56.6-20260522.yaml`
- `configs/frameworks/schema_v2.json`
- `raw/fullpaper/`
- `raw/calibration-regression/`
- `raw/holdout-test/`
- `raw/validation/`
- `results/fullevaluation/`

## 清理内容

- 删除 `.DS_Store`、`__pycache__/`、`*.pyc`、`.pytest_cache/`、`.ruff_cache/`、`.cache/` 等本地生成物。
- 删除误嵌套的 `configs/frameworks/configs/`。
- 删除字节完全一致的 macOS 冲突副本 `* 2.*` / `* 2`。
- 将不完全一致或缺少基准文件的冲突副本保留到 `archive/conflict-copies-20260601/`，并在该目录的 `README.md` 记录来源。

## 归档内容

- 历史框架配置继续保留在 `configs/frameworks/archive/v2.0-v2.54-20260522/`。
- 历史 schema 保留在 `configs/frameworks/archive/schemas/`。
- `results/phase2-evaluation/` 移至 `results/archive/phase2-superseded-20260601/`，其 `round2` 内容已被 `results/fullevaluation/round2/` 覆盖。
- 小规模框架迭代结果移至 `results/archive/framework-iteration-tests-20260601/`。
- 旧实验/诊断脚本移至 `scripts/archive/experiments-20260601/`。

## 恢复方式

- 历史框架：从 `configs/frameworks/archive/v2.0-v2.54-20260522/` 读取，或临时复制回 `configs/frameworks/` 顶层。
- 已归档 Phase 2 旧结果：从 `results/archive/phase2-superseded-20260601/phase2-evaluation/` 读取。
- 旧实验结果：从 `results/archive/framework-iteration-tests-20260601/` 读取。
- 旧实验脚本：从 `scripts/archive/experiments-20260601/` 执行；脚本内默认框架路径已指向归档位置。
