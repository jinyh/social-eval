# SocialEval 深度清理与目录治理记录

日期：2026-07-16

## 清理结果

- 六维框架以角色注册表统一寻址：生产默认 v2.56.6、交叉复核 v2.55、历史基线 v2.50.2。
- 五轴 v0.2 的轴定义、量尺、路径枚举、R2 策略、prompt 核心指令与输出契约进入独立 YAML；共用实现移至 `src/evaluation/position/`。
- CCB v0.8 独立为评分协议，最终分强制封顶 100。
- 三大刊、交大法学、学术月刊统一进入数据集中心目录；Git 只追踪元数据、摘要、manifest、排名和完整性报告。
- 全库保留 1920 条历史 PID 视图，同时提供 1916 条跨 PID 内容去重分析视图。
- R1 与 R2 内嵌 R1 的关联审计结果为 1760 条一致、160 条不一致；按既定决策仅记录，不重跑。
- 六维 R2 已进入 `src/evaluation/cross_review.py`，API、批处理和 E2 共用配置驱动实现；R2 后 std>8 进入专家复核，不自动调用 GPT 仲裁。
- 历史结果通过只读适配层统一暴露 R1/R2、CCB、原路径和解析路径；原始 JSON 不做格式迁移。
- 学术月刊 451 份逐篇 JSON 从 Git 撤下，继续作为本地忽略数据保存。
- 原始三大刊 PDF 从 1929 份整理为 1920 份；8 份完全重复副本归档，PID 105 的损坏正名文件归档并以有效副本替换。
- 历史演示文稿、PDF、渲染页、日志、网页抓取、旧计划、旧脚本归档和本地制作工程迁入仓库同级冷归档，逐文件保留 SHA-256 清单。

## 当前目录模型

| 目录 | 定位 | Git 策略 |
|---|---|---|
| `src/` | 产品代码与共用评价逻辑 | 追踪 |
| `configs/frameworks/` | 六维/五轴框架、角色注册表、schema | 追踪 |
| `configs/scoring/` | 独立总分协议 | 追踪 |
| `results/datasets/` | 按语料组织的元数据、运行摘要与逐篇结果入口 | 摘要/manifest 追踪，`per-paper/` 和 `audit/` 忽略 |
| `results/rankings/` | 全库和 E2 当前排名 | 聚合结果追踪，逐篇 E2 原始输出忽略 |
| `results/reports/current/` | 当前诊断与完整性报告 | 追踪 |
| `raw/` | 活动语料、校准/冻结/验证样本 | 小型样本按需追踪，大语料忽略 |
| `knowledge/` | 法学知识树与 ontology | 追踪 |
| `scripts/` | 可复跑的数据、评价、报告和运维工具 | 追踪；一次性脚本应在任务结束后冷归档 |
| `docs/` | 当前规程、架构、部署和报告源文件 | Markdown/源素材追踪；PPT/PDF/渲染制品冷归档 |
| `agent-skills/` | 项目专属工作流 | 追踪内容真源 |
| `ref/` | 外部参考资料 | 本地忽略 |

## 结果真源

- 总目录：`results/catalog.yaml`
- 三大刊元数据：`results/datasets/three-journals/metadata.csv`
- 三大刊去重分析元数据：`results/datasets/three-journals/metadata-deduplicated.csv`
- 六维逐篇结果：`results/datasets/<dataset>/six-dimension/<run-id>/per-paper/`
- 五轴逐篇结果：`results/datasets/<dataset>/five-axis/<run-id>/per-paper/`
- 全库 CCB：`results/rankings/all-papers-ccb-v1/`
- E2 CCB：`results/rankings/e2-ccb-v5/`
- R1 关联审计：`results/reports/current/r1-linkage-audit.json`
- 框架—代码—结果完整性审计：`results/reports/current/framework-code-result-integrity.json`

## 完整性复核（2026-07-16）

- 三大刊 1920 篇、交大法学 642 篇、学术月刊 149 篇的六维与五轴逐篇文件、摘要和 manifest 数量一致。
- 六维 R1/R2、五轴 R1/R2 与当前 E2 R1/R2 共扫描 5650 份逐篇文件，评分槽位缺失 0、结构错误 0。
- E2 严格门槛重建后为 105 篇；每篇六维均以 E1+E2 共 8 个模型分数做 `median(8)` 池化，再用 CCB 排名。当前池最低 E1 CCB 为 81.56、最低五轴为 9。
- 当前全库排名由 1815 篇 E1 与 105 篇 E1+E2 组成；Top50 分数区间为 86.24–94.32，无学科配额 underflow。

评分槽位完整不等于历史原始模型响应完整。审计报告将两者分开：三大刊 R1/R2 原始响应分别缺 147/73 条，交大法学缺 34/53 条，学术月刊 R2 缺 3571 条，当前 E2 池 R1/R2 缺 2/839 条。这些是历史运行未持久化或供应商失败留下的审计限制；不伪造、不用新调用冒充历史响应。2026-07-16 新增的 4 篇 E2 补测均保存了完整的 24 条 R1 与 24 条 R2 原始响应。

## 后续归类规则

1. 新结果必须先确定 dataset、评价类型和 run-id，再落盘；不得再向 `results/` 根目录写派生文件。
2. 可复现的小型聚合产物进入 Git；逐篇模型原始输出、日志和大语料只在本地保存。
3. 历史最终制品或阶段性交付物进入冷归档，不在 Git 和本地活动目录各留一份。
4. 新脚本必须以当前 `results/catalog.yaml` 和框架注册表为入口，不新增硬编码旧路径。
5. 历史文档可保留当时口径，但当前 README、AGENTS、部署文档和活动脚本不得引用已删除路径。

## 冷归档

位置：`../SocialEval-archive/2026-07-16-deep-clean/`

`manifest.jsonl` 每行包含原路径、归档路径、字节数、SHA-256、原因和校验状态。仓库不做 Git 历史重写。
