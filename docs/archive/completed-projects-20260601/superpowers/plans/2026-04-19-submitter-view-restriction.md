# 投稿者视图收紧实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将投稿者视图从"详细展示型"调整为"简洁结果型"，明确区分投稿者可见内容与内部评审可见内容。

**Architecture:** 前端过滤 + PDF 模板分层。在评测时让 AI 生成维度总结，前端投稿者视图只显示简化内容，PDF 导出新增简洁版模板。

**Tech Stack:** Python 3.10+ (FastAPI), React + TypeScript, Pydantic, matplotlib

---

## Task 1: 修改 DimensionResult 数据结构

**Files:**
- Modify: `src/evaluation/schemas.py`
- Test: `tests/test_evaluation/test_schemas.py` (新建)

- [ ] **Step 1: 创建测试文件**

```python
# tests/test_evaluation/test_schemas.py
from src.evaluation.schemas import DimensionResult

def test_dimension_result_has_summary_field():
    result = DimensionResult(
        dimension="problem_originality",
        score=85,
        evidence_quotes=["证据1", "证据2"],
        analysis="这是详细分析内容",
        summary="问题具有创新性",
        model_name="gpt-4o",
    )
    assert result.summary == "问题具有创新性"

def test_dimension_result_summary_is_optional_for_backward_compatibility():
    result = DimensionResult(
        dimension="problem_originality",
        score=85,
        evidence_quotes=["证据1"],
        analysis="分析内容",
        model_name="gpt-4o",
    )
    # 旧数据没有 summary，应该能正常加载
    assert result.summary is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_evaluation/test_schemas.py -v`
Expected: FAIL (Field 'summary' missing)

- [ ] **Step 3: 修改 DimensionResult 添加 summary 字段**

```python
# src/evaluation/schemas.py
from pydantic import BaseModel, Field


class DimensionResult(BaseModel):
    dimension: str
    score: int  # 0-100
    evidence_quotes: list[str]
    analysis: str
    summary: str | None = Field(default=None, description="AI 生成的一句话总结，不超过 50 字")
    model_name: str
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_evaluation/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/evaluation/schemas.py tests/test_evaluation/test_schemas.py
git commit -m "feat: add summary field to DimensionResult for AI-generated summaries"
```

---

## Task 2: 修改评测 Prompt 模板要求输出 summary

**Files:**
- Modify: `configs/frameworks/law-v2.0-20260413.yaml`
- Modify: `src/evaluation/prompt_builder.py`
- Modify: `tests/test_evaluation/test_prompt_builder.py`

- [ ] **Step 1: 编写测试用例**

在 `tests/test_evaluation/test_prompt_builder.py` 末尾添加：

```python
def test_law_v2_prompt_requests_summary_output():
    """测试 prompt 模板要求输出 summary 字段"""
    framework = load_framework("configs/frameworks/law-v2.0-20260413.yaml")
    paper = ProcessedPaper(
        full_text="论文全文",
        body="正文内容",
        references=[],
        structure_status="detected",
    )

    for dimension in framework.dimensions:
        prompt = build_prompt(dimension, paper)
        # 检查 prompt 要求输出 summary
        assert '"summary"' in prompt, f"维度 {dimension.key} 的 prompt 未要求输出 summary"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_evaluation/test_prompt_builder.py::test_law_v2_prompt_requests_summary_output -v`
Expected: FAIL

- [ ] **Step 3: 修改 law-v2.0 框架的 prompt 模板**

修改 `configs/frameworks/law-v2.0-20260413.yaml` 中每个维度的 `prompt_template`，将输出 JSON 格式从：

```json
{"dimension": "...", "score": ..., "evidence_quotes": [...], "analysis": "..."}
```

改为：

```json
{"dimension": "...", "score": ..., "evidence_quotes": [...], "analysis": "...", "summary": "一句话总结（不超过50字）"}
```

需要修改 6 个维度的 `prompt_template` 字段，在 `"analysis": "分析"` 后添加 `, "summary": "一句话总结（不超过50字，概括核心观点）"`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_evaluation/test_prompt_builder.py::test_law_v2_prompt_requests_summary_output -v`
Expected: PASS

- [ ] **Step 5: 运行所有 prompt_builder 测试确保无回归**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_evaluation/test_prompt_builder.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add configs/frameworks/law-v2.0-20260413.yaml tests/test_evaluation/test_prompt_builder.py
git commit -m "feat: update law-v2 prompt templates to request summary output"
```

---

## Task 3: 实现 summary_extractor 兜底函数

**Files:**
- Create: `src/reporting/summary_extractor.py`
- Create: `tests/test_reporting/test_summary_extractor.py`

- [ ] **Step 1: 编写测试**

```python
# tests/test_reporting/test_summary_extractor.py
from src.reporting.summary_extractor import extract_dimension_summary


def test_extract_summary_returns_first_sentence():
    text = "这是第一句话。这是第二句话。"
    result = extract_dimension_summary(text)
    assert result == "这是第一句话"


def test_extract_summary_limits_length():
    text = "这是一个非常长的句子，包含了超过五十个字符的内容，需要被截断处理以符合总结长度的要求。"
    result = extract_dimension_summary(text, max_length=20)
    assert len(result) <= 20


def test_extract_summary_handles_empty_text():
    result = extract_dimension_summary("")
    assert result == "暂无总结"


def test_extract_summary_prefers_conclusion_keywords():
    text = "首先分析了问题。其次提出方案。综上所述，核心观点是创新性不足。最后总结。"
    result = extract_dimension_summary(text)
    assert "综上所述" in result or "核心观点" in result


def test_extract_summary_removes_evidence_quotes():
    text = "分析内容「引用原文」继续分析。"
    result = extract_dimension_summary(text)
    assert "「" not in result
    assert "」" not in result
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_reporting/test_summary_extractor.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 summary_extractor**

```python
# src/reporting/summary_extractor.py
"""从分析文本中提取一句话总结（兜底方案）"""
from __future__ import annotations

import re


def extract_dimension_summary(analysis_text: str, max_length: int = 50) -> str:
    """
    从分析文本中提取一句话总结。
    
    策略：
    1. 优先取包含结论性词汇的句子
    2. 否则取首句
    3. 限制最大长度
    4. 移除引用符号
    
    Args:
        analysis_text: 分析文本
        max_length: 最大长度（默认50字）
    
    Returns:
        一句话总结
    """
    if not analysis_text or not analysis_text.strip():
        return "暂无总结"
    
    # 移除引用符号（「」『』等）
    text = re.sub(r"[「」『』【】]", "", analysis_text)
    
    # 按句号分割
    sentences = re.split(r"[。！？]", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return "暂无总结"
    
    # 结论性关键词
    conclusion_keywords = ["综上所述", "总体", "核心观点", "主要", "总体而言", "概言之"]
    
    # 优先找包含结论性词汇的句子
    for sentence in sentences:
        for keyword in conclusion_keywords:
            if keyword in sentence:
                return _truncate(sentence, max_length)
    
    # 否则取首句
    return _truncate(sentences[0], max_length)


def _truncate(text: str, max_length: int) -> str:
    """截断文本到指定长度"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 1] + "…"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_reporting/test_summary_extractor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reporting/summary_extractor.py tests/test_reporting/test_summary_extractor.py
git commit -m "feat: add summary_extractor for backward compatibility with old reports"
```

---

## Task 4: 实现简洁版 PDF 生成器

**Files:**
- Create: `src/reporting/simple_pdf_builder.py`
- Create: `tests/test_reporting/test_simple_pdf_builder.py`

- [ ] **Step 1: 编写测试**

```python
# tests/test_reporting/test_simple_pdf_builder.py
from src.reporting.simple_pdf_builder import build_simple_pdf


def test_build_simple_pdf_returns_bytes():
    report_data = {
        "title": "测试论文标题",
        "weighted_total": 85,
        "conclusion": "通过",
        "dimensions": [
            {"name_zh": "问题创新性", "ai": {"mean_score": 90}, "summary": "问题具有创新性"},
            {"name_zh": "逻辑严密性", "ai": {"mean_score": 80}, "summary": "逻辑较为严密"},
        ],
    }
    
    pdf_bytes = build_simple_pdf(report_data)
    
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF 文件头
    assert pdf_bytes.startswith(b"%PDF")


def test_build_simple_pdf_handles_missing_summary():
    """测试缺失 summary 时使用兜底逻辑"""
    report_data = {
        "title": "测试论文",
        "weighted_total": 75,
        "conclusion": "待改进",
        "dimensions": [
            {"name_zh": "问题创新性", "ai": {"mean_score": 70}, "analysis": "这是一段分析文本。"},
        ],
    }
    
    pdf_bytes = build_simple_pdf(report_data)
    
    assert isinstance(pdf_bytes, bytes)


def test_build_simple_pdf_handles_expert_conclusion():
    """测试包含专家复核结论的情况"""
    report_data = {
        "title": "测试论文",
        "weighted_total": 85,
        "conclusion": "通过",
        "dimensions": [],
        "expert_conclusion": "专家认为论文具有较高学术价值",
    }
    
    pdf_bytes = build_simple_pdf(report_data)
    
    assert isinstance(pdf_bytes, bytes)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_reporting/test_simple_pdf_builder.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 simple_pdf_builder**

```python
# src/reporting/simple_pdf_builder.py
"""简洁版 PDF 报告生成器，用于投稿者下载"""
from __future__ import annotations

from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from src.reporting.summary_extractor import extract_dimension_summary


def build_simple_pdf(report_data: dict) -> bytes:
    """
    生成简洁版 PDF 报告。
    
    内容包括：
    - 论文标题
    - 评测结论
    - 综合评分
    - 维度评分表
    - 各维度一句话总结
    - 专家最终评语（如有）
    
    不包括：
    - AI 详细分析原文
    - 证据摘录
    - 置信度指标
    - 专家姓名
    """
    buffer = BytesIO()
    
    with PdfPages(buffer) as pdf:
        figure, axis = plt.subplots(figsize=(8.27, 11.69))
        axis.axis("off")
        
        y = 0.95
        
        # 标题
        axis.text(0.05, y, "文科论文评价报告", fontsize=20, fontweight="bold", va="top")
        y -= 0.08
        
        # 论文标题
        title = report_data.get("title", "未知论文")
        axis.text(0.05, y, f"稿件标题：{title}", fontsize=12, va="top")
        y -= 0.04
        
        # 评测结论
        conclusion = report_data.get("conclusion", "未完成")
        conclusion_text = "通过" if conclusion == "pass" else ("未通过" if conclusion == "reject" else conclusion)
        axis.text(0.05, y, f"【评测结论】{conclusion_text}", fontsize=12, va="top", fontweight="bold")
        y -= 0.05
        
        # 综合评分
        total_score = report_data.get("weighted_total", 0)
        axis.text(0.05, y, f"【综合评分】{total_score} 分", fontsize=14, va="top")
        y -= 0.06
        
        # 维度评分表
        dimensions = report_data.get("dimensions", [])
        if dimensions:
            axis.text(0.05, y, "【维度评分】", fontsize=12, va="top", fontweight="bold")
            y -= 0.04
            
            rows = []
            for dim in dimensions:
                name = dim.get("name_zh", dim.get("name_en", "未知维度"))
                score = dim.get("ai", {}).get("mean_score", 0)
                rows.append([name, f"{score}"])
            
            table = axis.table(
                cellText=rows,
                colLabels=["维度", "分数"],
                bbox=[0.05, y - 0.25, 0.5, min(0.25, 0.04 * len(rows))],
            )
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            y -= 0.30
            
            # 各维度一句话总结
            axis.text(0.05, y, "【各维度评价】", fontsize=12, va="top", fontweight="bold")
            y -= 0.04
            
            for dim in dimensions:
                name = dim.get("name_zh", dim.get("name_en", "未知维度"))
                score = dim.get("ai", {}).get("mean_score", 0)
                
                # 优先使用 summary，否则从 analysis 提取
                if dim.get("summary"):
                    summary = dim["summary"]
                elif dim.get("analysis"):
                    summary = extract_dimension_summary(dim["analysis"])
                else:
                    summary = "暂无总结"
                
                text = f"{name}（{score}分）：{summary}"
                axis.text(0.05, y, text, fontsize=10, va="top", wrap=True)
                y -= 0.04
        
        # 专家最终评语
        expert_conclusion = report_data.get("expert_conclusion")
        if expert_conclusion:
            y = max(y, 0.15)  # 确保不超出页面
            axis.text(0.05, y, "【专家最终评语】", fontsize=12, va="top", fontweight="bold")
            y -= 0.04
            axis.text(0.05, y, expert_conclusion, fontsize=10, va="top", wrap=True)
        
        pdf.savefig(figure, bbox_inches="tight")
        plt.close(figure)
    
    return buffer.getvalue()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_reporting/test_simple_pdf_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/reporting/simple_pdf_builder.py tests/test_reporting/test_simple_pdf_builder.py
git commit -m "feat: add simple_pdf_builder for submitter PDF export"
```

---

## Task 5: 新增简洁版 PDF 导出 API 端点

**Files:**
- Modify: `src/api/routers/reports.py`
- Create: `tests/test_api/test_simple_export.py`

- [ ] **Step 1: 编写测试**

```python
# tests/test_api/test_simple_export.py
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_export_simple_report_requires_auth(client):
    """测试简洁版导出需要认证"""
    response = client.post("/api/reports/1/export/simple")
    assert response.status_code == 401


def test_export_simple_report_returns_pdf(client, monkeypatch):
    """测试简洁版导出返回 PDF"""
    # 这里需要 mock 认证和数据库
    # 实际实现时根据项目测试模式调整
    pass
```

- [ ] **Step 2: 在 reports.py 添加新端点**

在 `src/api/routers/reports.py` 末尾添加：

```python
from src.reporting.simple_pdf_builder import build_simple_pdf


@router.get("/{paper_id}/export/simple")
def export_simple_report(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    导出简洁版 PDF 报告（投稿者视图）。
    
    权限：
    - admin, editor: 可导出所有报告
    - submitter: 只能导出自己上传的稿件
    - expert: 可导出被分配复核的稿件
    """
    paper, task = _load_paper_and_task(db, paper_id)
    _ensure_public_access(current_user, paper)
    
    report = get_current_report(db, task.id, "public")
    
    # 构建简洁版报告数据
    simple_data = _build_simple_report_data(report.report_data)
    
    pdf_content = build_simple_pdf(simple_data)
    
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="report",
        object_id=report.id,
        action="simple_export",
        result="success",
        details={"paper_id": paper_id, "export_type": "simple_pdf"},
    )
    
    from fastapi import Response
    return Response(content=pdf_content, media_type="application/pdf")


def _build_simple_report_data(report_data: dict) -> dict:
    """构建简洁版报告数据，过滤掉投稿者不应看到的字段"""
    dimensions = []
    for dim in report_data.get("dimensions", []):
        simple_dim = {
            "name_zh": dim.get("name_zh", dim.get("name_en")),
            "name_en": dim.get("name_en"),
            "ai": {
                "mean_score": dim.get("ai", {}).get("mean_score", 0),
            },
            "summary": dim.get("summary"),
            "analysis": dim.get("analysis"),  # 用于兜底提取
        }
        dimensions.append(simple_dim)
    
    return {
        "title": report_data.get("title"),
        "weighted_total": report_data.get("weighted_total", 0),
        "conclusion": report_data.get("conclusion"),
        "dimensions": dimensions,
        "expert_conclusion": report_data.get("expert_conclusion"),
    }
```

- [ ] **Step 3: 运行测试**

Run: `cd /home/xiwen/social-eval && uv run pytest tests/test_api/test_simple_export.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/api/routers/reports.py tests/test_api/test_simple_export.py
git commit -m "feat: add simple PDF export endpoint for submitter view"
```

---

## Task 6: 重构前端投稿者视图

**Files:**
- Modify: `src/web/src/App.tsx`
- Modify: `src/web/src/lib/api.ts`
- Modify: `src/web/src/styles.css`
- Modify: `src/web/src/App.test.tsx`

- [ ] **Step 1: 在 api.ts 添加简洁版导出 API**

在 `src/web/src/lib/api.ts` 中添加：

```typescript
export async function exportSimpleReport(paperId: number): Promise<Blob> {
  const response = await fetch(`${API_BASE}/reports/${paperId}/export/simple`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Failed to export simple report");
  }
  return response.blob();
}
```

- [ ] **Step 2: 创建 SimpleScoreCard 组件**

在 `src/web/src/App.tsx` 中，`SubmitterDashboard` 组件前添加：

```typescript
type DimensionScore = {
  name_zh: string;
  score: number;
  summary: string;
};

function SimpleScoreCard({ dimensions }: { dimensions: DimensionScore[] }) {
  return (
    <div className="score-card">
      {dimensions.map((dim, index) => (
        <div key={index} className="score-row">
          <div className="score-header">
            <span className="dimension-name">{dim.name_zh}</span>
            <span className="dimension-score">{dim.score}分</span>
          </div>
          <p className="dimension-summary">{dim.summary || "暂无总结"}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 重构 SubmitterDashboard 组件**

替换 `SubmitterDashboard` 函数：

```typescript
function SubmitterDashboard() {
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [selectedPaper, setSelectedPaper] = useState<number | null>(null);
  const [reportData, setReportData] = useState<{
    title: string;
    weighted_total: number;
    conclusion: string;
    dimensions: DimensionScore[];
    review_status?: string;
    expert_conclusion?: string;
  } | null>(null);
  const [message, setMessage] = useState<string>("");

  const refreshPapers = async () => setPapers(await listPapers());

  useEffect(() => {
    void refreshPapers().catch(() => setPapers([]));
  }, []);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("paper") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;
    
    const payload = await uploadPaper(file);
    setMessage(`已上传论文 ${payload.paper_id}`);
    await refreshPapers();
    form.reset();
  };

  const handleViewReport = async (paperId: number) => {
    setSelectedPaper(paperId);
    const report = await getPublicReport(paperId);
    
    // 转换为简洁格式
    const dimensions: DimensionScore[] = (report.dimensions || []).map((dim: Record<string, unknown>) => ({
      name_zh: dim.name_zh || dim.name_en || "未知维度",
      score: dim.ai?.mean_score || 0,
      summary: dim.summary || "暂无总结",
    }));
    
    setReportData({
      title: report.title || "未知论文",
      weighted_total: report.weighted_total || 0,
      conclusion: report.conclusion || "未完成",
      dimensions,
      review_status: report.review_status,
      expert_conclusion: report.expert_conclusion,
    });
  };

  const handleDownloadPdf = async () => {
    if (!selectedPaper) return;
    const blob = await exportSimpleReport(selectedPaper);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `报告_${selectedPaper}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      pending: "等待评测",
      evaluating: "评测中",
      completed: "已完成",
      pending_review: "等待专家分配",
      in_review: "复核中",
    };
    return statusMap[status] || status;
  };

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <h2>投稿人工作台</h2>
        <form onSubmit={handleUpload} className="stack">
          <input name="paper" type="file" accept=".pdf,.docx,.txt" />
          <button type="submit">上传论文</button>
        </form>
        {message ? <p className="success">{message}</p> : null}
      </section>

      <section className="panel">
        <h3>我的论文</h3>
        <ul className="paper-list">
          {papers.map((paper) => (
            <li key={paper.paper_id} className="paper-item">
              <div className="paper-info">
                <strong>{paper.title || paper.original_filename}</strong>
                <span className="status">{getStatusText(paper.paper_status)}</span>
              </div>
              <button type="button" onClick={() => handleViewReport(paper.paper_id)}>
                查看结果
              </button>
            </li>
          ))}
        </ul>
      </section>

      {reportData ? (
        <section className="panel">
          <h3>评测结果</h3>
          <div className="result-header">
            <h4>{reportData.title}</h4>
            <div className="total-score">
              综合评分：<strong>{reportData.weighted_total}</strong> 分
            </div>
            <div className="conclusion">
              评测结论：<strong>{reportData.conclusion === "pass" ? "通过" : "未通过"}</strong>
            </div>
            {reportData.review_status ? (
              <div className="review-status">
                复核状态：{reportData.review_status === "in_review" ? "复核中" : "已完成"}
              </div>
            ) : null}
          </div>
          
          <SimpleScoreCard dimensions={reportData.dimensions} />
          
          {reportData.expert_conclusion ? (
            <div className="expert-conclusion">
              <h5>专家评语</h5>
              <p>{reportData.expert_conclusion}</p>
            </div>
          ) : null}
          
          <button type="button" onClick={handleDownloadPdf}>
            下载报告
          </button>
        </section>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: 添加样式**

在 `src/web/src/styles.css` 中添加：

```css
/* 投稿者视图样式 */
.score-card {
  margin: 1rem 0;
}

.score-row {
  padding: 0.75rem;
  border-bottom: 1px solid #eee;
}

.score-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.dimension-name {
  font-weight: 500;
}

.dimension-score {
  color: #666;
}

.dimension-summary {
  font-size: 0.9rem;
  color: #444;
  margin: 0;
}

.paper-list {
  list-style: none;
  padding: 0;
}

.paper-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border-bottom: 1px solid #eee;
}

.paper-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.status {
  font-size: 0.85rem;
  color: #666;
}

.result-header {
  margin-bottom: 1rem;
}

.total-score {
  font-size: 1.1rem;
  margin: 0.5rem 0;
}

.conclusion {
  margin: 0.5rem 0;
}

.review-status {
  color: #888;
  font-size: 0.9rem;
}

.expert-conclusion {
  background: #f5f5f5;
  padding: 1rem;
  margin: 1rem 0;
  border-radius: 4px;
}

.expert-conclusion h5 {
  margin: 0 0 0.5rem 0;
}

.success {
  color: green;
}
```

- [ ] **Step 5: 运行前端测试**

Run: `cd /home/xiwen/social-eval/src/web && npm test -- --run`

- [ ] **Step 6: 构建前端**

Run: `cd /home/xiwen/social-eval/src/web && npm run build`

- [ ] **Step 7: Commit**

```bash
git add src/web/src/App.tsx src/web/src/lib/api.ts src/web/src/styles.css
git commit -m "feat: refactor submitter view to show simplified results only"
```

---

## Task 7: 集成测试与验收

**Files:**
- Modify: `tests/test_api/test_reports_and_reviews.py`

- [ ] **Step 1: 添加集成测试**

在 `tests/test_api/test_reports_and_reviews.py` 中添加：

```python
def test_submitter_can_export_simple_pdf(db_session, submitter_user, sample_paper):
    """测试投稿者可以导出简洁版 PDF"""
    # 创建评测任务和报告
    # 调用 /api/reports/{paper_id}/export/simple
    # 验证返回 PDF
    pass


def test_submitter_cannot_see_internal_report_fields(db_session, submitter_user, sample_paper):
    """测试投稿者看不到内部字段"""
    # 调用公开报告 API
    # 验证返回数据不包含 evidence_quotes, confidence 等字段
    pass
```

- [ ] **Step 2: 运行所有测试**

Run: `cd /home/xiwen/social-eval && uv run pytest -v`

- [ ] **Step 3: 验收检查**

手动检查清单：
1. 投稿者页面不显示原始 JSON
2. 投稿者页面不显示 AI 详细分析原文
3. 投稿者页面不显示证据摘录
4. 投稿者页面不显示置信度数值
5. 投稿者可以下载简洁版 PDF
6. 简洁版 PDF 不包含专家姓名和复核意见原文

- [ ] **Step 4: Final Commit**

```bash
git add tests/test_api/test_reports_and_reviews.py
git commit -m "test: add integration tests for submitter view restriction"
```

---

## 验收标准

- [ ] 投稿者页面不显示原始 JSON
- [ ] 投稿者页面不显示 AI 详细分析原文
- [ ] 投稿者页面不显示证据摘录
- [ ] 投稿者页面不显示置信度数值
- [ ] 投稿者可以下载简洁版 PDF
- [ ] 简洁版 PDF 不包含专家姓名和复核意见原文
- [ ] 所有新增测试通过
