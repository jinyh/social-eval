# src/reporting/simple_pdf_builder.py
"""简洁版 PDF 生成器，用于投稿者下载。

只包含：
- 论文标题
- 评价结论
- 总分
- 各维度分数及一句话总结
- 专家最终结论（如有）

不包含：
- AI 详细分析文本
- 证据引用
- 置信度指标
- 专家姓名
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from src.reporting.summary_extractor import extract_dimension_summary


def build_simple_pdf(report_data: dict[str, Any]) -> bytes:
    """
    生成简洁版 PDF 报告。

    Args:
        report_data: 报告数据字典，包含：
            - title: 论文标题
            - weighted_total: 加权总分
            - conclusion: 评价结论
            - dimensions: 维度列表，每个维度包含 name_zh, ai.mean_score, summary/analysis
            - expert_conclusion: (可选) 专家复核结论

    Returns:
        PDF 文件的字节数据
    """
    buffer = BytesIO()
    figure, axis = plt.subplots(figsize=(8.27, 11.69))
    axis.axis("off")

    # 标题
    title = report_data.get("title", "未命名论文")
    axis.text(0.5, 0.97, "学术评价报告", fontsize=18, ha="center", va="top", fontweight="bold")
    axis.text(0.5, 0.92, _truncate_text(title, 40), fontsize=14, ha="center", va="top")

    # 评价结论
    conclusion = report_data.get("conclusion", "未评定")
    conclusion_color = _get_conclusion_color(conclusion)
    axis.text(0.5, 0.86, f"评价结论: {conclusion}", fontsize=14, ha="center", va="top", color=conclusion_color)

    # 总分
    total_score = report_data.get("weighted_total", 0)
    axis.text(0.5, 0.81, f"总分: {total_score}", fontsize=16, ha="center", va="top", fontweight="bold")

    # 维度分数表格
    dimensions = report_data.get("dimensions", [])
    if dimensions:
        rows = []
        for dim in dimensions:
            name = dim.get("name_zh", "未知维度")
            score = dim.get("ai", {}).get("mean_score", 0)
            summary = _get_dimension_summary(dim)
            rows.append([name, f"{score}", _truncate_text(summary, 30)])

        table = axis.table(
            cellText=rows,
            colLabels=["评价维度", "分数", "一句话总结"],
            bbox=[0.05, 0.30, 0.90, 0.45],
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        # 调整列宽
        cell_dict = table.get_celld()
        for key in cell_dict:
            if key[0] == 0:  # 表头
                cell_dict[key].set_text_props(fontweight="bold")

    # 专家复核结论（如有）
    expert_conclusion = report_data.get("expert_conclusion")
    if expert_conclusion:
        axis.text(0.5, 0.22, "专家复核意见", fontsize=12, ha="center", va="top", fontweight="bold")
        # 长文本需要换行处理
        wrapped_text = _wrap_text(expert_conclusion, 35)
        axis.text(0.1, 0.18, wrapped_text, fontsize=10, va="top", wrap=True)

    # 生成 PDF
    with PdfPages(buffer) as pdf:
        pdf.savefig(figure, bbox_inches="tight")

    plt.close(figure)
    return buffer.getvalue()


def _get_dimension_summary(dim: dict[str, Any]) -> str:
    """
    获取维度的一句话总结。

    优先使用 summary 字段，否则从 analysis 提取。

    Args:
        dim: 维度数据

    Returns:
        一句话总结
    """
    summary = dim.get("summary")
    if summary and summary.strip():
        return summary.strip()

    # 兜底：从 analysis 提取
    analysis = dim.get("analysis", "")
    return extract_dimension_summary(analysis)


def _get_conclusion_color(conclusion: str) -> str:
    """
    根据结论返回显示颜色。

    Args:
        conclusion: 评价结论

    Returns:
        matplotlib 颜色字符串
    """
    if conclusion == "通过":
        return "green"
    elif conclusion == "待改进":
        return "orange"
    elif conclusion == "退稿":
        return "red"
    return "black"


def _truncate_text(text: str, max_length: int) -> str:
    """
    截断文本到指定长度。

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _wrap_text(text: str, line_length: int) -> str:
    """
    将长文本按指定长度换行。

    Args:
        text: 原始文本
        line_length: 每行最大字符数

    Returns:
        换行后的文本
    """
    lines = []
    for i in range(0, len(text), line_length):
        lines.append(text[i : i + line_length])
    return "\n".join(lines)
