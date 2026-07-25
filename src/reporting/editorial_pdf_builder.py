"""面向期刊编辑流转的中文 PDF 简报。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_FONT_NAME = "SocialEvalCJK"
_FONT_BOLD_NAME = "SocialEvalCJK-Bold"
_FONT_REGISTERED = False
_FONT_CANDIDATES = (
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
    ),
    (
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ),
)


def _register_fonts() -> None:
    global _FONT_BOLD_NAME, _FONT_NAME, _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    for regular_path, bold_path in _FONT_CANDIDATES:
        regular = Path(regular_path)
        if not regular.exists():
            continue
        bold = Path(bold_path)
        kwargs = {"subfontIndex": 0} if regular.suffix.lower() == ".ttc" else {}
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(regular), **kwargs))
            bold_source = bold if bold.exists() else regular
            bold_kwargs = (
                {"subfontIndex": 0} if bold_source.suffix.lower() == ".ttc" else {}
            )
            pdfmetrics.registerFont(
                TTFont(_FONT_BOLD_NAME, str(bold_source), **bold_kwargs)
            )
        except TTFError:
            continue
        _FONT_REGISTERED = True
        return
    fallback_name = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(fallback_name))
    _FONT_NAME = fallback_name
    _FONT_BOLD_NAME = fallback_name
    _FONT_REGISTERED = True


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "EditorialTitle",
            parent=sample["Title"],
            fontName=_FONT_BOLD_NAME,
            fontSize=20,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "EditorialSubtitle",
            parent=sample["Normal"],
            fontName=_FONT_NAME,
            fontSize=10,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "EditorialSection",
            parent=sample["Heading2"],
            fontName=_FONT_BOLD_NAME,
            fontSize=15,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=4,
            spaceAfter=10,
        ),
        "subsection": ParagraphStyle(
            "EditorialSubsection",
            parent=sample["Heading3"],
            fontName=_FONT_BOLD_NAME,
            fontSize=11,
            leading=17,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=5,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "EditorialBody",
            parent=sample["BodyText"],
            fontName=_FONT_NAME,
            fontSize=9.5,
            leading=16,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#334155"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "EditorialSmall",
            parent=sample["BodyText"],
            fontName=_FONT_NAME,
            fontSize=8,
            leading=13,
            textColor=colors.HexColor("#64748B"),
        ),
        "metric": ParagraphStyle(
            "EditorialMetric",
            parent=sample["BodyText"],
            fontName=_FONT_BOLD_NAME,
            fontSize=13,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0F172A"),
        ),
        "metric_label": ParagraphStyle(
            "EditorialMetricLabel",
            parent=sample["BodyText"],
            fontName=_FONT_NAME,
            fontSize=8,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#64748B"),
        ),
    }


def _text(value: Any, *, limit: int | None = None) -> str:
    raw = str(value or "").strip()
    if limit is not None and len(raw) > limit:
        return raw[:limit].rstrip() + "……（完整内容见审计数据）"
    return raw


def _paragraph(value: Any, style: ParagraphStyle, *, limit: int | None = None):
    content = _text(value, limit=limit) or "尚未形成"
    return Paragraph(escape(content).replace("\n", "<br/>"), style)


def _list_flowables(
    values: Any,
    styles: dict[str, ParagraphStyle],
    *,
    max_items: int = 5,
    item_limit: int = 240,
) -> list:
    if not isinstance(values, list) or not values:
        return [Paragraph("未提出。", styles["small"])]
    rows = [
        Paragraph(
            f"{index}. {escape(_text(value, limit=item_limit))}",
            styles["body"],
        )
        for index, value in enumerate(values[:max_items], start=1)
    ]
    if len(values) > max_items:
        rows.append(Paragraph("其余内容见审计数据。", styles["small"]))
    return rows


def _section_heading(title: str, styles: dict[str, ParagraphStyle]) -> list:
    return [
        Paragraph(title, styles["section"]),
        HRFlowable(
            width="100%",
            thickness=0.7,
            color=colors.HexColor("#CBD5E1"),
            spaceAfter=10,
        ),
    ]


def _metadata_table(payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    metadata = payload.get("report_metadata") or {}
    submission = payload.get("submission") or {}
    data = [
        [
            Paragraph("期刊 / 编辑单元", styles["small"]),
            Paragraph(
                escape(
                    f"{metadata.get('journal_name') or '待确认'} / "
                    f"{metadata.get('unit_name') or '待确认'}"
                ),
                styles["body"],
            ),
        ],
        [
            Paragraph("外部稿号", styles["small"]),
            Paragraph(
                escape(
                    str(
                        submission.get("external_manuscript_id")
                        or submission.get("id")
                        or "待确认"
                    )
                ),
                styles["body"],
            ),
        ],
        [
            Paragraph("报告版本 / 生成时间", styles["small"]),
            Paragraph(
                escape(
                    f"第 {metadata.get('report_version', '待确认')} 版 / "
                    f"{metadata.get('generated_at_zh') or '待确认'}"
                ),
                styles["body"],
            ),
        ],
        [
            Paragraph("第二轮互评方式", styles["small"]),
            Paragraph(
                escape(str(metadata.get("review_protocol_label") or "未启用")),
                styles["body"],
            ),
        ],
    ]
    table = Table(data, colWidths=[40 * mm, 125 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _metric_table(payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    evaluation = payload.get("evaluation") or {}
    ccb = evaluation.get("ccb_summary") or {}
    six = evaluation.get("six_dimension_summary") or {}
    labels = ["六维综合参考分", "匿名模型参与", "观点差异维度", "必须专家复核"]
    values = [
        f"{float(ccb.get('final_score') or 0):.1f}",
        f"{int((six.get('model_participation') or {}).get('count') or 0)} 个",
        f"{int(six.get('difference_count') or 0)} 个",
        f"{int(six.get('expert_review_dimension_count') or 0)} 个",
    ]
    data = [
        [Paragraph(escape(value), styles["metric"]) for value in values],
        [Paragraph(label, styles["metric_label"]) for label in labels],
    ]
    table = Table(data, colWidths=[41.25 * mm] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#BFDBFE")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DBEAFE")),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )
    return table


def _five_axis_table(payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    position = (payload.get("evaluation") or {}).get("position_summary") or {}
    rows = [
        [
            Paragraph("轴名称", styles["small"]),
            Paragraph("评价对象与判断问题", styles["small"]),
            Paragraph("得分", styles["small"]),
        ]
    ]
    for axis in position.get("axes") or []:
        detail = (
            f"<b>{escape(_text(axis.get('focus_label')))}</b><br/>"
            f"{escape(_text(axis.get('guiding_question')))}"
        )
        rows.append(
            [
                Paragraph(escape(_text(axis.get("axis_name"))), styles["body"]),
                Paragraph(detail, styles["body"]),
                Paragraph(
                    f"{int(axis.get('score') or 0)} / 2",
                    styles["body"],
                ),
            ]
        )
    table = Table(rows, colWidths=[34 * mm, 112 * mm, 19 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _six_dimension_table(payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    summary = (payload.get("evaluation") or {}).get("six_dimension_summary") or {}
    rows = [
        [
            Paragraph("维度", styles["small"]),
            Paragraph("均分", styles["small"]),
            Paragraph("档位", styles["small"]),
            Paragraph("标准差", styles["small"]),
            Paragraph("差异状态", styles["small"]),
        ]
    ]
    for item in summary.get("dimensions") or []:
        rows.append(
            [
                Paragraph(escape(_text(item.get("dimension_name"))), styles["body"]),
                Paragraph(f"{float(item.get('mean_score') or 0):.1f}", styles["body"]),
                Paragraph(escape(_text(item.get("band_label"))), styles["body"]),
                Paragraph(f"{float(item.get('std_score') or 0):.2f}", styles["body"]),
                Paragraph(escape(_text(item.get("difference_label"))), styles["body"]),
            ]
        )
    table = Table(
        rows,
        colWidths=[43 * mm, 22 * mm, 22 * mm, 24 * mm, 54 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (3, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _risk_evidence(payload: dict) -> Iterable[tuple[str, list[str]]]:
    summary = (payload.get("evaluation") or {}).get("six_dimension_summary") or {}
    for dimension in summary.get("dimensions") or []:
        if dimension.get("difference_level") == "consensus":
            continue
        evidence: list[str] = []
        for model in dimension.get("model_results") or []:
            quotes = model.get("evidence_quotes")
            if isinstance(quotes, list):
                evidence.extend(str(value) for value in quotes if value)
            if len(evidence) >= 2:
                break
        yield _text(dimension.get("dimension_name")), evidence[:2]


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont(_FONT_NAME, 7.5)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(22 * mm, 12 * mm, "内部编辑参考，不替代编辑或专家终审")
    canvas.drawRightString(
        A4[0] - 22 * mm,
        12 * mm,
        f"第 {document.page} 页",
    )
    canvas.restoreState()


def build_editorial_pdf(report: dict[str, Any]) -> bytes:
    """生成综合摘要优先、五轴与六维分开的编辑简报。"""

    _register_fonts()
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=_text((report.get("submission") or {}).get("title")),
        author="中国自主知识创新（法学论文）评价系统",
    )
    submission = report.get("submission") or {}
    opinions = report.get("ai_opinions") or []
    synthesis = next(
        (
            item.get("content") or {}
            for item in opinions
            if item.get("type") == "ai_synthesis"
        ),
        {},
    )
    recommendation = report.get("recommendation") or {}
    recommendation_label = recommendation.get("display_label") or "状态待确认"

    story: list = [
        Paragraph("中国自主知识创新（法学论文）评价系统", styles["title"]),
        Paragraph(
            escape(_text(submission.get("title"), limit=120) or "未命名稿件"),
            styles["subtitle"],
        ),
        _metadata_table(report, styles),
        Spacer(1, 8 * mm),
        *_section_heading("智能辅助综合摘要", styles),
        Paragraph(
            f"<b>建议状态：</b>{escape(_text(recommendation_label))}",
            styles["body"],
        ),
        _metric_table(report, styles),
        Spacer(1, 5 * mm),
        Paragraph("综合判断", styles["subsection"]),
        _paragraph(synthesis.get("synthesis"), styles["body"], limit=1200),
        Paragraph("四模型共识", styles["subsection"]),
        *_list_flowables(synthesis.get("consensus_points"), styles),
        PageBreak(),
        *_section_heading("分歧、核验与修改建议", styles),
        Paragraph("四模型分歧", styles["subsection"]),
        *_list_flowables(synthesis.get("disagreement_points"), styles),
        Paragraph("编辑优先核验事项", styles["subsection"]),
        *_list_flowables(synthesis.get("priority_issues"), styles),
        Paragraph("修改建议", styles["subsection"]),
        *_list_flowables(synthesis.get("modification_suggestions"), styles),
        Spacer(1, 7 * mm),
        Paragraph(
            "说明：综合摘要来自既有模型评价和证据，不是人类审稿意见；"
            "任何候选建议均须由编辑结合稿件原文和专家意见独立判断。",
            styles["small"],
        ),
        PageBreak(),
        *_section_heading("五轴位置归属度", styles),
    ]
    position = (report.get("evaluation") or {}).get("position_summary") or {}
    story.extend(
        [
            Paragraph(
                (
                    f"<b>五轴总分：{int(position.get('total_score') or 0)} / 10</b>"
                    f"　{escape(_text(position.get('strength_label')))}；"
                    f"{escape(_text(position.get('agreement_label')))}"
                ),
                styles["body"],
            ),
            _five_axis_table(report, styles),
            Spacer(1, 5 * mm),
            Paragraph(
                escape(_text(position.get("notice"))),
                styles["small"],
            ),
        ]
    )
    differing_axes = [
        axis for axis in position.get("axes") or [] if axis.get("has_model_difference")
    ]
    if differing_axes:
        story.append(Paragraph("五轴差异证据节选", styles["subsection"]))
        for axis in differing_axes:
            quotes = axis.get("evidence_quotes")
            story.append(
                Paragraph(
                    escape(_text(axis.get("axis_name"))),
                    styles["body"],
                )
            )
            story.extend(_list_flowables(quotes, styles, max_items=2, item_limit=220))
    story.extend(
        [
            PageBreak(),
            *_section_heading("六维学术评价", styles),
            _six_dimension_table(report, styles),
            Spacer(1, 5 * mm),
            Paragraph("关键风险证据节选", styles["subsection"]),
        ]
    )
    risks = list(_risk_evidence(report))
    if risks:
        for dimension_name, evidence in risks:
            story.append(Paragraph(escape(dimension_name), styles["body"]))
            story.extend(_list_flowables(evidence, styles, max_items=2, item_limit=220))
    else:
        story.append(Paragraph("当前没有需要节选的显著分歧证据。", styles["small"]))
    story.extend(
        [
            PageBreak(),
            *_section_heading("专家复核与编辑决定", styles),
            Paragraph("专家复核意见", styles["subsection"]),
        ]
    )
    expert_reviews = report.get("expert_reviews") or []
    expert_items = [
        comment
        for review in expert_reviews
        for comment in review.get("comments") or []
        if comment.get("reason")
    ]
    if expert_items:
        for comment in expert_items[:6]:
            story.append(
                Paragraph(
                    (
                        f"<b>{escape(_text(comment.get('dimension_name') or '补充维度'))}"
                        f"，{float(comment.get('expert_score') or 0):.1f} 分</b><br/>"
                        f"{escape(_text(comment.get('reason'), limit=360))}"
                    ),
                    styles["body"],
                )
            )
        if len(expert_items) > 6:
            story.append(Paragraph("其余专家意见见审计数据。", styles["small"]))
    else:
        story.append(Paragraph("当前版本尚无专家复核意见。", styles["small"]))

    story.append(Paragraph("编辑决定记录", styles["subsection"]))
    decisions = report.get("editorial_decisions") or []
    if decisions:
        for decision in decisions[:6]:
            story.append(
                Paragraph(
                    (
                        f"<b>{escape(_text(decision.get('stage_label')))}："
                        f"{escape(_text(decision.get('decision_label')))}</b><br/>"
                        f"{escape(_text(decision.get('rationale'), limit=360) or '未填写理由')}"
                    ),
                    styles["body"],
                )
            )
    else:
        story.append(Paragraph("当前尚无已提交的编辑决定。", styles["small"]))
    story.extend(
        [
            Spacer(1, 6 * mm),
            Paragraph("方法边界与审计说明", styles["subsection"]),
            Paragraph(
                "五轴只判断知识体系位置归属，不评价论文质量，也不与六维加总。"
                "六维综合参考分采用核心维度、学术共识封顶和前瞻弱加分。"
                "模型分歧超过阈值时必须由专家复核，不以自动仲裁覆盖真实学术分歧。"
                "本简报只展示关键风险证据节选，完整结果见同版本结构化审计数据。",
                styles["small"],
            ),
        ]
    )

    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
