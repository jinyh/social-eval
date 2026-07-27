#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
)


def _register_font() -> str:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    ]
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("Chinese", str(path), subfontIndex=0))
            return "Chinese"
    raise RuntimeError("未找到可用中文字体")


def _plain_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("`", "").replace("**", "")
    return text


def build_pdf(source: Path, destination: Path) -> None:
    font = _register_font()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9.5,
        leading=16,
        textColor=colors.HexColor("#25324A"),
        spaceAfter=5,
    )
    title = ParagraphStyle(
        "ChineseTitle",
        parent=body,
        fontSize=22,
        leading=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#123B70"),
        spaceAfter=14,
    )
    heading = ParagraphStyle(
        "ChineseHeading",
        parent=body,
        fontSize=15,
        leading=22,
        textColor=colors.HexColor("#0F5C99"),
        spaceBefore=12,
        spaceAfter=7,
    )
    bullet = ParagraphStyle(
        "ChineseBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
    )

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#708090"))
        canvas.drawString(20 * mm, 12 * mm, "文科期刊智能辅助预审业务全流程")
        canvas.drawRightString(190 * mm, 12 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = BaseDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="文科期刊智能辅助预审业务全流程",
        author="自主知识创新法学评价系统",
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="body",
    )
    document.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])
    story = []
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = _plain_markdown(raw_line.strip())
        if not line or line.startswith("|") or re.fullmatch(r"[-| :]+", line):
            if not line:
                story.append(Spacer(1, 2))
            continue
        if line.startswith("# "):
            story.append(Paragraph(line[2:], title))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], heading))
        elif line.startswith("- "):
            story.append(Paragraph(f"• {line[2:]}", bullet))
        elif re.match(r"^\d+\. ", line):
            story.append(Paragraph(line, bullet))
        else:
            story.append(Paragraph(line, body))
    document.build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs/editorial/business-process-v1.2.md"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/SocialEval-business-process-v1.2.pdf"),
    )
    args = parser.parse_args()
    build_pdf(args.source, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
