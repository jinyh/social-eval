# tests/test_reporting/test_simple_pdf_builder.py
import fitz

from src.reporting.editorial_pdf_builder import build_editorial_pdf
from src.reporting.simple_pdf_builder import build_simple_pdf


def test_build_simple_pdf_returns_bytes():
    report_data = {
        "title": "测试论文标题",
        "weighted_total": 85,
        "conclusion": "通过",
        "dimensions": [
            {
                "name_zh": "问题创新性",
                "ai": {"mean_score": 90},
                "summary": "问题具有创新性",
            },
            {
                "name_zh": "逻辑严密性",
                "ai": {"mean_score": 80},
                "summary": "逻辑较为严密",
            },
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
            {
                "name_zh": "问题创新性",
                "ai": {"mean_score": 70},
                "analysis": "这是一段分析文本。",
            },
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


def test_editorial_pdf_places_five_axis_before_six_dimension():
    report_data = {
        "title": "测试投稿",
        "weighted_total": 82,
        "conclusion": "建议修改",
        "ccb_summary": {
            "base_score": 80,
            "bonus_score": 2,
            "ceiling_label": "未触发封顶",
        },
        "position_summary": {
            "total_score": 8,
            "strength_label": "归属证据较强",
            "agreement_label": "两模型意见一致",
            "notice": "五轴不评价论文质量，也不参与录退决定。",
            "axes": [
                {
                    "axis_name": "对象归属度",
                    "focus_label": "研究问题归属",
                    "guiding_question": "核心问题是否归属于中国法学语境",
                    "score": 2,
                }
            ],
        },
        "dimensions": [
            {
                "name_zh": "研究创新性",
                "ai": {"mean_score": 82},
                "summary": "创新判断摘要",
            }
        ],
    }

    pdf_bytes = build_simple_pdf(report_data)
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    assert document.page_count == 2
    assert len(document[0].get_pixmap().samples) > 0
    assert len(document[1].get_pixmap().samples) > 0


def test_v4_editorial_pdf_is_a_five_page_summary_first_brief():
    report = {
        "schema_version": "editorial-report-v4",
        "report_metadata": {
            "report_version": 4,
            "generated_at_zh": "2026年07月25日 19:30",
            "journal_name": "交大法学",
            "unit_name": "交大法学编辑部",
        },
        "submission": {
            "id": "submission-1",
            "external_manuscript_id": "JD-2026-001",
            "title": "数字平台治理中法律责任配置与规范结构研究",
        },
        "recommendation": {
            "state": "ready",
            "display_label": "修改后重投",
        },
        "evaluation": {
            "ccb_summary": {
                "final_score": 81.6,
            },
            "position_summary": {
                "total_score": 8,
                "strength_label": "归属证据较强",
                "agreement_label": "两模型存在局部差异",
                "notice": "五轴不评价论文质量，也不参与录退决定。",
                "axes": [
                    {
                        "axis_name": "对象归属度",
                        "focus_label": "研究问题归属",
                        "guiding_question": "核心问题是否归属于中国法学语境",
                        "score": 2,
                        "has_model_difference": False,
                        "evidence_quotes": [],
                    },
                    {
                        "axis_name": "材料归属度",
                        "focus_label": "核心材料归属",
                        "guiding_question": "材料是否来自中国规范、判例、史料、数据",
                        "score": 2,
                        "has_model_difference": False,
                        "evidence_quotes": [],
                    },
                    {
                        "axis_name": "范畴自主度",
                        "focus_label": "分析范畴自主",
                        "guiding_question": "核心范畴是否经中国法语境重置",
                        "score": 1,
                        "has_model_difference": True,
                        "evidence_quotes": ["文章对平台责任范畴进行了中国法语境重释。"],
                    },
                    {
                        "axis_name": "解释目标归属度",
                        "focus_label": "解释目标方向",
                        "guiding_question": "最终目标是否指向中国法学知识生产",
                        "score": 2,
                        "has_model_difference": False,
                        "evidence_quotes": [],
                    },
                    {
                        "axis_name": "体系映射度",
                        "focus_label": "知识体系映射",
                        "guiding_question": "知识能否映射到知识树位置",
                        "score": 1,
                        "has_model_difference": False,
                        "evidence_quotes": [],
                    },
                ],
            },
            "six_dimension_summary": {
                "model_participation": {"count": 4},
                "difference_count": 2,
                "expert_review_dimension_count": 1,
                "dimensions": [
                    {
                        "dimension_name": name,
                        "mean_score": 80 + index,
                        "band_label": "良",
                        "std_score": 4 + index,
                        "difference_level": (
                            "expert_review" if index == 2 else "consensus"
                        ),
                        "difference_label": (
                            "必须专家复核" if index == 2 else "四模型基本一致"
                        ),
                        "model_results": [
                            {"evidence_quotes": ["关键论证仍需要补充规范依据。"]}
                        ],
                    }
                    for index, name in enumerate(
                        [
                            "研究创新性",
                            "现状洞察度",
                            "理论建构力",
                            "逻辑连贯性",
                            "学术共识度",
                            "前瞻延展性",
                        ]
                    )
                ],
            },
        },
        "ai_opinions": [
            {
                "type": "ai_synthesis",
                "content": {
                    "synthesis": "论文问题意识清晰，但规范基础仍需加强。",
                    "consensus_points": ["四模型均认可论文的问题意识。"],
                    "disagreement_points": ["对理论建构完整性的判断不同。"],
                    "priority_issues": ["优先核验核心规范依据。"],
                    "modification_suggestions": ["补充反对观点并逐项回应。"],
                },
            }
        ],
        "expert_reviews": [],
        "editorial_decisions": [],
    }

    pdf_bytes = build_editorial_pdf(report)
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    assert document.page_count == 5
    assert all(len(page.get_pixmap().samples) > 0 for page in document)
