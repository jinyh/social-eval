# 法学评价框架 v2.2（研究版）说明

## 定位

`configs/frameworks/law-v2.2-20260421.yaml` 是在 `v2.1` 基础上继续迭代的研究版框架，目标是提升“大模型可判定性”，而不是立即接入当前运行时加载链路。

## 本次调整

- 保留六维结构与权重：`30 / 15 / 15 / 25 / 10 / 5`
- 保留 machine key `conclusion_consensus`，展示名改为“结论可接受性”
- 将学术伦理前置检查改为“疑点筛查 + 人工复核建议”
- 删除模型自报 `confidence` 输出，改为 `review_flags`
- 将复核阈值、验证计划、多模型可靠性等内容收拢到 `governance_appendix`

## 非目标

- 不保证兼容当前 `src/knowledge/loader.py` 的旧 schema
- 不要求当前 `src/evaluation/schemas.py` 直接接受研究版输出字段
- 不把 LLM 生成的前置检查结果视为最终学术不端裁决

## 后续建议

下一步若要工程化，应单独做一版“可实现版”：

- 统一 framework schema 与 loader
- 明确研究版输出字段如何映射到运行时结果 schema
- 处理当前环境下旧 Pydantic schema 导入链的兼容问题
