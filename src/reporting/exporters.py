from __future__ import annotations

import json
from pathlib import Path
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from sqlalchemy.orm import Session

from src.models.report import Report, ReportExport

EXPORT_ROOT = Path("data/exports")


def export_report_json(report: Report) -> bytes:
    return json.dumps(report.report_data, ensure_ascii=False, indent=2).encode("utf-8")


def export_report_pdf(report: Report) -> bytes:
    buffer = BytesIO()
    figure, axis = plt.subplots(figsize=(8.27, 11.69))
    axis.axis("off")
    axis.text(0.02, 0.97, "SocialEval Report", fontsize=18, va="top")
    axis.text(0.02, 0.92, f"Type: {report.report_type}", fontsize=12, va="top")
    axis.text(
        0.02,
        0.88,
        f"Weighted total: {report.report_data.get('weighted_total', 0)}",
        fontsize=12,
        va="top",
    )

    rows = [
        [dimension["name_en"], dimension["ai"]["mean_score"]]
        for dimension in report.report_data.get("dimensions", [])
    ]
    if rows:
        table = axis.table(
            cellText=rows,
            colLabels=["Dimension", "Score"],
            bbox=[0.02, 0.45, 0.7, 0.35],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)

    with PdfPages(buffer) as pdf:
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
    file_path = EXPORT_ROOT / f"{report.id}-{report.version}-{report.report_type}.{suffix}"
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
