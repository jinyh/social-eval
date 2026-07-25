#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import xlsxwriter

DECISIONS = ("不送外审", "修改后重投", "送外审", "优先送外审")
CONFIDENCE = ("高", "中等", "较低")
YES_NO = ("是", "否")


def _write_sample_sheet(
    workbook: xlsxwriter.Workbook,
    name: str,
    prefix: str,
    count: int,
    formats: dict,
) -> None:
    sheet = workbook.add_worksheet(name)
    headers = (
        "匿名编号",
        "期刊",
        "编辑预审决定",
        "主要问题一",
        "主要问题二",
        "主要问题三",
        "判断信心",
        "需要专家复核",
        "盲标人",
        "盲标日期",
        "完成状态",
    )
    sheet.write_row(0, 0, headers, formats["header"])
    for index in range(1, count + 1):
        row = index
        sheet.write(row, 0, f"{prefix}-{index:02d}", formats["fixed"])
        sheet.write(row, 1, name.replace("盲标", ""), formats["fixed"])
        for column in range(2, 10):
            sheet.write_blank(row, column, None, formats["input"])
        excel_row = row + 1
        sheet.write_formula(
            row,
            10,
            f'=IF(AND(C{excel_row}<>"",D{excel_row}<>"",'
            f'G{excel_row}<>"",H{excel_row}<>""),"已完成","待填写")',
            formats["status"],
            "待填写",
        )
    sheet.data_validation(
        1,
        2,
        count,
        2,
        {"validate": "list", "source": list(DECISIONS)},
    )
    sheet.data_validation(
        1,
        6,
        count,
        6,
        {"validate": "list", "source": list(CONFIDENCE)},
    )
    sheet.data_validation(
        1,
        7,
        count,
        7,
        {"validate": "list", "source": list(YES_NO)},
    )
    sheet.autofilter(0, 0, count, len(headers) - 1)
    sheet.freeze_panes(1, 2)
    sheet.set_column("A:A", 14)
    sheet.set_column("B:B", 14)
    sheet.set_column("C:C", 16)
    sheet.set_column("D:F", 28)
    sheet.set_column("G:H", 15)
    sheet.set_column("I:J", 13)
    sheet.set_column("K:K", 12)
    sheet.set_row(0, 28)
    sheet.set_default_row(32)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 1)
    sheet.set_margins(0.25, 0.25, 0.4, 0.4)


def build_workbook(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(destination)
    workbook.set_properties(
        {
            "title": "双期刊编辑盲校准工作簿",
            "subject": "交大法学与学术月刊编辑预审盲标",
            "author": "SocialEval",
        }
    )
    base = {"font_name": "Heiti SC", "font_size": 10, "valign": "vcenter"}
    formats = {
        "header": workbook.add_format(
            {
                **base,
                "bold": True,
                "font_color": "white",
                "bg_color": "#155E95",
                "border": 1,
                "align": "center",
                "text_wrap": True,
            }
        ),
        "fixed": workbook.add_format(
            {**base, "bg_color": "#E8EEF5", "border": 1, "align": "center"}
        ),
        "input": workbook.add_format(
            {
                **base,
                "bg_color": "#FFF4CC",
                "border": 1,
                "text_wrap": True,
            }
        ),
        "status": workbook.add_format(
            {**base, "bg_color": "#E7F5EC", "border": 1, "align": "center"}
        ),
        "title": workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 20,
                "font_color": "#123B70",
                "align": "center",
            }
        ),
        "section": workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 13,
                "font_color": "#0F5C99",
            }
        ),
        "body": workbook.add_format({**base, "text_wrap": True}),
        "summary_header": workbook.add_format(
            {
                **base,
                "bold": True,
                "bg_color": "#DCEAF5",
                "border": 1,
                "align": "center",
            }
        ),
        "summary": workbook.add_format({**base, "border": 1, "align": "center"}),
    }

    guide = workbook.add_worksheet("使用说明")
    guide.merge_range("A1:F2", "双期刊编辑盲校准工作簿", formats["title"])
    guide.write("A4", "使用顺序", formats["section"])
    instructions = (
        "一、先阅读匿名稿，不打开历史审稿意见。",
        "二、在黄色单元格填写预审决定、三个主要问题、信心和专家复核需求。",
        "三、完成后由第二人复核，保存文件并计算 SHA-256；此后不得覆盖。",
        "四、锁定盲标后，才能在独立记录中录入历史审稿决定和问题点。",
        "五、校准材料只在本机处理，不上传到网页搜索或普通连接器。",
    )
    for row, line in enumerate(instructions, start=4):
        guide.merge_range(row, 0, row, 5, line, formats["body"])
    guide.write("A11", "完成情况", formats["section"])
    guide.write_row(
        12, 0, ("期刊", "样本数", "已完成", "完成率"), formats["summary_header"]
    )
    guide.write_row(13, 0, ("交大法学", 5), formats["summary"])
    guide.write_formula(
        13,
        2,
        "=COUNTIF('交大法学盲标'!K2:K6,\"已完成\")",
        formats["summary"],
        0,
    )
    guide.write_formula(13, 3, "=C14/B14", formats["summary"], 0)
    guide.write_row(14, 0, ("学术月刊", 7), formats["summary"])
    guide.write_formula(
        14,
        2,
        "=COUNTIF('学术月刊盲标'!K2:K8,\"已完成\")",
        formats["summary"],
        0,
    )
    guide.write_formula(14, 3, "=C15/B15", formats["summary"], 0)
    guide.set_column("A:A", 18)
    guide.set_column("B:D", 14)
    guide.set_column("E:F", 18)
    guide.set_row(0, 30)
    guide.set_landscape()
    guide.fit_to_pages(1, 1)

    _write_sample_sheet(workbook, "交大法学盲标", "JDFX", 5, formats)
    _write_sample_sheet(workbook, "学术月刊盲标", "XSYK", 7, formats)
    workbook.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "outputs/socialeval-production-test/"
            "SocialEval-editorial-calibration-workbook-v1.0.xlsx"
        ),
    )
    args = parser.parse_args()
    build_workbook(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
