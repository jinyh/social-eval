from __future__ import annotations

import json
import textwrap
from pathlib import Path
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from sqlalchemy.orm import Session

from src.models.report import Report, ReportExport
from src.reporting.simple_pdf_builder import get_chinese_font

EXPORT_ROOT = Path("data/exports")


def export_report_json(report: Report) -> bytes:
    return json.dumps(report.report_data, ensure_ascii=False, indent=2).encode("utf-8")


def export_report_pdf(report: Report) -> bytes:
    """生成全中文、多页内部或公开评价报告。"""

    buffer = BytesIO()
    font = get_chinese_font()
    with PdfPages(buffer) as pdf:
        figure, axis = plt.subplots(figsize=(8.27, 11.69))
        axis.axis("off")
        axis.text(
            0.5,
            0.95,
            "自主知识创新法学评价报告",
            fontsize=17,
            ha="center",
            va="top",
            fontweight="bold",
            fontproperties=font,
        )
        report_type = "内部报告" if report.report_type == "internal" else "作者报告"
        axis.text(
            0.06,
            0.89,
            f"报告类型：{report_type}",
            fontsize=11,
            va="top",
            fontproperties=font,
        )
        axis.text(
            0.06,
            0.85,
            f"核心—封顶—加分综合参考分：{report.report_data.get('weighted_total', 0)}",
            fontsize=12,
            va="top",
            fontproperties=font,
        )
        axis.text(
            0.06,
            0.80,
            "提示：该分数仅供辅助参考，不替代编辑或专家判断。",
            fontsize=10,
            va="top",
            color="#475569",
            fontproperties=font,
        )
        rows = [
            [dimension.get("name_zh", "未知维度"), dimension["ai"]["mean_score"]]
            for dimension in report.report_data.get("dimensions", [])
        ]
        if rows:
            table = axis.table(
                cellText=rows,
                colLabels=["评价维度", "参考分"],
                bbox=[0.06, 0.38, 0.88, 0.35],
            )
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            for cell in table.get_celld().values():
                cell.get_text().set_fontproperties(font)
        pdf.savefig(figure)
        plt.close(figure)

        for dimension in report.report_data.get("dimensions", []):
            summary = str(
                dimension.get("summary") or dimension.get("ai", {}).get("summary") or ""
            )
            analysis = dimension.get("ai", {}).get("analysis") or []
            if not summary and analysis:
                summary = str(analysis[0])
            figure, axis = plt.subplots(figsize=(8.27, 11.69))
            axis.axis("off")
            axis.text(
                0.06,
                0.94,
                str(dimension.get("name_zh", "未知维度")),
                fontsize=16,
                va="top",
                fontweight="bold",
                fontproperties=font,
            )
            axis.text(
                0.06,
                0.88,
                f"参考分：{dimension.get('ai', {}).get('mean_score', 0)}",
                fontsize=12,
                va="top",
                fontproperties=font,
            )
            axis.text(
                0.06,
                0.82,
                "\n".join(textwrap.wrap(summary or "暂无摘要。", width=42)),
                fontsize=10,
                va="top",
                linespacing=1.7,
                fontproperties=font,
            )
            pdf.savefig(figure)
            plt.close(figure)
    return buffer.getvalue()


def persist_report_export(
    db: Session,
    *,
    report: Report,
    export_type: str,
    content: bytes,
) -> ReportExport:
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    suffix = "json" if export_type == "json" else "pdf"
    file_path = (
        EXPORT_ROOT / f"{report.id}-{report.version}-{report.report_type}.{suffix}"
    )
    file_path.write_bytes(content)
    export = ReportExport(
        report_id=report.id,
        export_type=export_type,
        file_path=str(file_path),
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return export
