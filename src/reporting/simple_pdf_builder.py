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
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages

from src.reporting.summary_extractor import extract_dimension_summary

# 常见 Linux/macOS 中文字体路径。生产镜像安装 Noto CJK，本地开发可回退到
# macOS 自带字体；不依赖某一个操作系统的固定路径。
_CHINESE_FONT_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)
_CHINESE_FONT = None


def get_chinese_font() -> fm.FontProperties:
    """获取中文字体，用于PDF渲染"""
    global _CHINESE_FONT
    if _CHINESE_FONT is not None:
        return _CHINESE_FONT

    for candidate in _CHINESE_FONT_PATHS:
        font_path = Path(candidate)
        if font_path.exists():
            _CHINESE_FONT = fm.FontProperties(fname=str(font_path))
            break
    else:
        # 最后回退到系统默认字体；调用方仍可生成只含 ASCII 的报告。
        _CHINESE_FONT = fm.FontProperties()
    return _CHINESE_FONT


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
    if "position_summary" in report_data:
        return _build_editorial_pdf(report_data)

    buffer = BytesIO()
    figure, axis = plt.subplots(figsize=(8.27, 11.69))
    axis.axis("off")

    # 获取中文字体
    font = get_chinese_font()

    # 标题区域
    title = report_data.get("title") or "未命名论文"
    axis.text(
        0.5,
        0.95,
        "中国哲学社会科学自主知识创新（法学论文）AI辅助评价系统",
        fontsize=16,
        ha="center",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )
    axis.text(
        0.5,
        0.90,
        _truncate_text(title, 35),
        fontsize=12,
        ha="center",
        va="top",
        fontproperties=font,
    )

    # 综合参考分和评价结论
    total_score = report_data.get("weighted_total") or 0
    conclusion = report_data.get("conclusion") or "未评定"
    conclusion_color = _get_conclusion_color(conclusion)

    axis.text(
        0.25,
        0.83,
        f"综合参考分：{total_score}",
        fontsize=16,
        ha="center",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )
    axis.text(
        0.75,
        0.83,
        "评价结论：\n" + _wrap_text(str(conclusion), 18),
        fontsize=11,
        ha="center",
        va="top",
        color=conclusion_color,
        fontweight="bold",
        fontproperties=font,
    )

    ccb_summary = report_data.get("ccb_summary") or {}
    if ccb_summary:
        ceiling_text = ccb_summary.get("ceiling_label") or "未触发封顶"
        axis.text(
            0.5,
            0.76,
            (
                f"核心基础分 {ccb_summary.get('base_score', 0):g} · "
                f"{ceiling_text} · "
                f"前瞻加分 {ccb_summary.get('bonus_score', 0):g} · "
                f"最终值 {ccb_summary.get('final_score', total_score):g}"
            ),
            fontsize=9,
            ha="center",
            va="top",
            color="#475569",
            fontproperties=font,
        )

    # 分隔线
    axis.axhline(y=0.73, xmin=0.05, xmax=0.95, color="gray", linewidth=0.5)

    # 维度评分标题
    axis.text(
        0.5,
        0.70,
        "维度评分详情",
        fontsize=14,
        ha="center",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )

    # 维度分数 - 逐行显示，每行一个维度
    dimensions = report_data.get("dimensions") or []
    line_height = 0.095
    if dimensions:
        y_start = 0.64

        for i, dim in enumerate(dimensions):
            y_pos = y_start - i * line_height

            name = dim.get("name_zh") or "未知维度"
            score = (dim.get("ai") or {}).get("mean_score") or 0
            summary = _get_dimension_summary(dim)

            # 维度名称和分数
            axis.text(
                0.07,
                y_pos,
                f"{name}",
                fontsize=11,
                ha="left",
                va="top",
                fontweight="bold",
                fontproperties=font,
            )
            axis.text(
                0.32,
                y_pos,
                f"{score:.1f}分",
                fontsize=11,
                ha="left",
                va="top",
                fontproperties=font,
            )

            # 一句话总结（完整显示，可换行）
            wrapped_summary = _wrap_text(summary, 35)
            axis.text(
                0.42,
                y_pos,
                wrapped_summary,
                fontsize=10,
                ha="left",
                va="top",
                fontproperties=font,
            )

            # 分隔线
            if i < len(dimensions) - 1:
                axis.axhline(
                    y=y_pos - 0.078,
                    xmin=0.05,
                    xmax=0.95,
                    color="#DDDDDD",
                    linewidth=0.3,
                )

    # 专家复核结论（如有）
    expert_conclusion = report_data.get("expert_conclusion")
    if expert_conclusion:
        y_expert = 0.64 - len(dimensions) * line_height - 0.02
        axis.axhline(y=y_expert, xmin=0.05, xmax=0.95, color="gray", linewidth=0.5)
        axis.text(
            0.5,
            y_expert - 0.03,
            "专家复核意见",
            fontsize=12,
            ha="center",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        wrapped_text = _wrap_text(expert_conclusion, 40)
        axis.text(
            0.5,
            y_expert - 0.07,
            wrapped_text,
            fontsize=10,
            ha="center",
            va="top",
            fontproperties=font,
        )

    # 生成 PDF
    with PdfPages(buffer) as pdf:
        pdf.savefig(figure)

    plt.close(figure)
    return buffer.getvalue()


def _build_editorial_pdf(report_data: dict[str, Any]) -> bytes:
    """生成五轴在前、六维在后的两页编辑预审报告。"""

    buffer = BytesIO()
    font = get_chinese_font()
    title = report_data.get("title") or "未命名论文"
    position = report_data.get("position_summary") or {}
    dimensions = report_data.get("dimensions") or []
    ccb = report_data.get("ccb_summary") or {}
    total_score = report_data.get("weighted_total") or 0

    position_figure, position_axis = plt.subplots(figsize=(8.27, 11.69))
    position_axis.axis("off")
    _draw_editorial_header(
        position_axis,
        title,
        "知识体系位置归属度",
        font,
        page_number=1,
    )
    if position:
        position_axis.text(
            0.08,
            0.79,
            f"位置归属总分：{position.get('total_score', 0)} / 10",
            fontsize=16,
            ha="left",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        position_axis.text(
            0.92,
            0.79,
            (
                f"{position.get('strength_label', '待确认')} · "
                f"{position.get('agreement_label', '待确认')}"
            ),
            fontsize=10,
            ha="right",
            va="top",
            color="#475569",
            fontproperties=font,
        )
    else:
        position_axis.text(
            0.08,
            0.79,
            "位置归属结果尚未生成。",
            fontsize=13,
            ha="left",
            va="top",
            color="#92400E",
            fontproperties=font,
        )
    position_axis.axhline(
        y=0.745,
        xmin=0.06,
        xmax=0.94,
        color="#94A3B8",
        linewidth=0.6,
    )

    for index, item in enumerate(position.get("axes") or []):
        y_pos = 0.70 - index * 0.125
        position_axis.text(
            0.08,
            y_pos,
            str(item.get("axis_name") or "未知轴"),
            fontsize=12,
            ha="left",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        position_axis.text(
            0.31,
            y_pos,
            str(item.get("focus_label") or ""),
            fontsize=10,
            ha="left",
            va="top",
            color="#475569",
            fontproperties=font,
        )
        position_axis.text(
            0.92,
            y_pos,
            f"{item.get('score', 0)} / 2",
            fontsize=12,
            ha="right",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        position_axis.text(
            0.08,
            y_pos - 0.045,
            _wrap_text(str(item.get("guiding_question") or ""), 38),
            fontsize=10,
            ha="left",
            va="top",
            fontproperties=font,
        )
        if index < len(position.get("axes") or []) - 1:
            position_axis.axhline(
                y=y_pos - 0.098,
                xmin=0.06,
                xmax=0.94,
                color="#E2E8F0",
                linewidth=0.4,
            )
    position_axis.text(
        0.08,
        0.07,
        _wrap_text(str(position.get("notice") or ""), 52),
        fontsize=9,
        ha="left",
        va="bottom",
        color="#64748B",
        fontproperties=font,
    )

    dimension_figure, dimension_axis = plt.subplots(figsize=(8.27, 11.69))
    dimension_axis.axis("off")
    _draw_editorial_header(
        dimension_axis,
        title,
        "学术质量评价",
        font,
        page_number=2,
    )
    dimension_axis.text(
        0.08,
        0.79,
        f"综合参考分：{total_score:g}",
        fontsize=16,
        ha="left",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )
    if ccb:
        dimension_axis.text(
            0.08,
            0.745,
            (
                f"核心基础分 {ccb.get('base_score', 0):g} · "
                f"{ccb.get('ceiling_label') or '未触发封顶'} · "
                f"前瞻弱加分 {ccb.get('bonus_score', 0):g}"
            ),
            fontsize=9,
            ha="left",
            va="top",
            color="#475569",
            fontproperties=font,
        )
    dimension_axis.axhline(
        y=0.70,
        xmin=0.06,
        xmax=0.94,
        color="#94A3B8",
        linewidth=0.6,
    )
    for index, item in enumerate(dimensions):
        y_pos = 0.655 - index * 0.09
        dimension_axis.text(
            0.08,
            y_pos,
            str(item.get("name_zh") or "未知维度"),
            fontsize=11,
            ha="left",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        score = (item.get("ai") or {}).get("mean_score") or 0
        dimension_axis.text(
            0.32,
            y_pos,
            f"{score:.1f} 分",
            fontsize=11,
            ha="left",
            va="top",
            fontproperties=font,
        )
        dimension_axis.text(
            0.44,
            y_pos,
            _wrap_text(_get_dimension_summary(item), 34),
            fontsize=9,
            ha="left",
            va="top",
            color="#334155",
            fontproperties=font,
        )
        if index < len(dimensions) - 1:
            dimension_axis.axhline(
                y=y_pos - 0.072,
                xmin=0.06,
                xmax=0.94,
                color="#E2E8F0",
                linewidth=0.4,
            )

    expert_conclusion = report_data.get("expert_conclusion")
    if expert_conclusion:
        expert_y = 0.655 - len(dimensions) * 0.09 - 0.015
        dimension_axis.text(
            0.08,
            expert_y,
            "专家复核意见",
            fontsize=11,
            ha="left",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        dimension_axis.text(
            0.08,
            expert_y - 0.04,
            _wrap_text(str(expert_conclusion), 52),
            fontsize=9,
            ha="left",
            va="top",
            fontproperties=font,
        )

    with PdfPages(buffer) as pdf:
        pdf.savefig(position_figure)
        pdf.savefig(dimension_figure)
    plt.close(position_figure)
    plt.close(dimension_figure)
    return buffer.getvalue()


def _draw_editorial_header(
    axis: Any,
    title: str,
    section_title: str,
    font: fm.FontProperties,
    *,
    page_number: int,
) -> None:
    axis.text(
        0.5,
        0.95,
        "自主知识创新法学评价系统",
        fontsize=16,
        ha="center",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )
    axis.text(
        0.5,
        0.905,
        _truncate_text(title, 42),
        fontsize=11,
        ha="center",
        va="top",
        fontproperties=font,
    )
    axis.text(
        0.5,
        0.855,
        section_title,
        fontsize=14,
        ha="center",
        va="top",
        fontweight="bold",
        fontproperties=font,
    )
    axis.text(
        0.94,
        0.035,
        f"第 {page_number} 页 / 共 2 页",
        fontsize=8,
        ha="right",
        va="bottom",
        color="#64748B",
        fontproperties=font,
    )


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
    analysis = dim.get("analysis") or ""
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


def _truncate_text(text: str | None, max_length: int) -> str:
    """
    截断文本到指定长度。

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        截断后的文本
    """
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _wrap_text(text: str | None, line_length: int) -> str:
    """
    将长文本按指定长度换行。

    Args:
        text: 原始文本
        line_length: 每行最大字符数

    Returns:
        换行后的文本
    """
    if text is None:
        return ""
    lines = []
    for i in range(0, len(text), line_length):
        lines.append(text[i : i + line_length])
    return "\n".join(lines)
