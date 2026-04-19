# 投稿者视图收紧设计

## 背景

当前系统已经具备完整的评审闭环能力，但投稿者视图暴露了过多 AI 评审细节，不符合"对外简洁"的产品定位。投稿者可以下载包含详细分析的 PDF，看到原始 JSON 报告，这会影响对外演示效果和产品定位。

## 目标

将投稿者视图从"详细展示型"调整为"简洁结果型"，明确区分投稿者可见内容与内部评审可见内容。

## 投稿者可见内容边界

### 可见

| 内容 | 说明 |
|------|------|
| 稿件基础信息 | 标题、上传时间、当前状态 |
| 评测结论 | 通过/未通过 |
| 总分 | 0-100 分 |
| 维度分数 | 六维度名称 + 数值 |
| 维度一句话总结 | 从 AI 分析中提取的核心观点 |
| 复核状态 | "复核中" / "已完成" |
| 最终结论 | 复核后的最终评语（如有） |

### 不可见

| 内容 | 说明 |
|------|------|
| 原始 JSON 报告 | 完整报告数据结构 |
| AI 详细分析原文 | 每维度的长文本分析 |
| 证据摘录 | `evidence_quotes` 字段 |
| 多模型对比细节 | 模型名称、各模型分数差异 |
| 置信度数值 | 标准差、高/低置信度标签 |
| 专家信息 | 专家姓名、复核意见原文 |
| 分数变化历史 | 复核前后的分数变化 |

## 实现方案

采用方案 A：前端过滤 + PDF 模板分层

### 为什么选择方案 A

1. 改动范围小，风险低
2. 后端无需改动 API 契约
3. PDF 模板可复用于其他场景
4. 见效最快，适合当前"试点可用版"阶段

## 具体改动

### 1. 前端改动

**文件**：`src/web/src/App.tsx`

**改动内容**：

1. 重构 `renderSubmitterView()` 函数
   - 移除原始 JSON 展示区域
   - 移除 AI 详细分析原文展示
   - 移除证据摘录展示
   - 移除置信度数值展示

2. 新增 `SimpleScoreCard` 组件
   - 显示维度名称 + 分数 + 一句话总结
   - 样式简洁，适合对外展示

3. 简化下载按钮
   - 只显示"下载报告"
   - 不显示"内部报告/公开报告"选项

### 2. 维度一句话总结生成逻辑

**数据来源**：从报告的 `analysis` 字段提取

**提取规则**：
1. 如果 `analysis.dimensions[i].summary` 存在，直接使用
2. 否则，从 `analysis.dimensions[i].analysis` 文本中提取首句（以句号结尾）

**新增函数**：`src/reporting/summary_extractor.py`

```python
def extract_dimension_summary(analysis_text: str, max_length: int = 100) -> str:
    """从分析文本中提取一句话总结"""
    # 取第一个句号前的内容
    # 限制最大长度
    # 返回总结文本
```

### 3. PDF 导出改动

**新增文件**：`src/reporting/simple_pdf_builder.py`

**PDF 内容**：

```
文科论文评价报告
================

稿件标题：{title}
评测时间：{timestamp}

【评测结论】
通过/未通过

【综合评分】
{total_score} 分

【维度评分】
| 维度 | 分数 |
|------|------|
| 问题创新性 | 85 |
| 现状洞察度 | 78 |
| ... | ... |

【各维度评价】
问题创新性（85分）：研究问题切中要点，具有学术价值。
现状洞察度（78分）：文献综述较为全面，但存在遗漏。
...

【最终评语】
（如有专家复核，显示复核后结论）
```

**不包含**：
- AI 分析长文本
- 证据摘录
- 置信度指标
- 专家姓名

### 4. API 端点新增

**新增端点**：`POST /api/reports/{paper_id}/export/simple`

**请求**：
- 无请求体
- 需要 submitter 或更高权限

**响应**：
- Content-Type: `application/pdf`
- 文件流

**实现位置**：`src/api/routers/reports.py`

```python
@router.post("/{paper_id}/export/simple")
async def export_simple_report(
    paper_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """导出简洁版 PDF 报告"""
    # 1. 验证权限（投稿人只能导出自己的稿件）
    # 2. 获取报告数据
    # 3. 调用 SimplePDFBuilder 生成 PDF
    # 4. 返回文件流
```

### 5. 复核状态展示

**状态定义**：
- `pending_review`：等待专家分配
- `in_review`：专家复核中
- `completed`：已完成

**投稿者视图展示**：
- 显示当前状态的中文描述
- 复核完成后显示最终结论

## 测试计划

### 单元测试

1. `test_summary_extractor.py`：测试一句话总结提取逻辑
2. `test_simple_pdf_builder.py`：测试简洁版 PDF 生成

### 集成测试

1. `test_submitter_view_api.py`：测试投稿者 API 返回的数据结构
2. `test_simple_export.py`：测试简洁版 PDF 导出端点

### 前端测试

1. `App.test.tsx`：测试投稿者视图渲染正确
2. 测试投稿者看不到隐藏字段

## 验收标准

1. 投稿者页面不显示原始 JSON
2. 投稿者页面不显示 AI 详细分析原文
3. 投稿者页面不显示证据摘录
4. 投稿者页面不显示置信度数值
5. 投稿者可以下载简洁版 PDF
6. 简洁版 PDF 不包含专家姓名和复核意见原文
7. 所有新增测试通过

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/web/src/App.tsx` | 修改 | 重构投稿者视图 |
| `src/reporting/summary_extractor.py` | 新增 | 一句话总结提取 |
| `src/reporting/simple_pdf_builder.py` | 新增 | 简洁版 PDF 生成 |
| `src/api/routers/reports.py` | 修改 | 新增简洁版导出端点 |
| `tests/test_reporting/test_summary_extractor.py` | 新增 | 单元测试 |
| `tests/test_reporting/test_simple_pdf_builder.py` | 新增 | 单元测试 |

## 后续演进方向

1. 如果未来需要更强的安全性，可演进为后端 API 分层（方案 B）
2. 如果需要支持外部系统接入，可增加 API Key 认证的公开端点
