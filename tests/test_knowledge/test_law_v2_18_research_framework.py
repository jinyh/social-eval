from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.18-20260424.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_18_problem_originality_prompt_rejects_theme_statement_as_research_question():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "problem_originality")
    prompt = dimension["prompt_template"]

    assert "主题声明、政策口号或权威表述的系统归纳，不等于法学研究问题" in prompt
    assert "只要全文主要是在阐释既定立场，而非提出可争辩的法学争点，就不得因为主题重大而给高分" in prompt


def test_v2_18_literature_insight_prompt_forbids_counting_internal_contrast_as_school_coverage():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "literature_insight")
    prompt = dimension["prompt_template"]

    assert "作者自己在正文中并列介绍“形式法治/实质法治”等概念关系，不自动构成法学流派覆盖" in prompt
    assert "只有把这些立场明确放入既有学术研究或学界争论脉络中，才计算为流派识别" in prompt


def test_v2_18_analytical_framework_prompt_distinguishes_topic_outline_from_operational_framework():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "analytical_framework")
    prompt = dimension["prompt_template"]

    assert "“三个要义”“六个方面”“若干坚持”等内容提纲，如果没有转化为可重复适用的判断步骤或评价标准，不算分析框架" in prompt
    assert "理论综述或政策阐释中的结构化归纳，只能算主题整理，不能直接按“框架可操作性”高分处理" in prompt


def test_v2_18_conclusion_consensus_prompt_forbids_high_score_from_institutional_compatibility_alone():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "conclusion_consensus")
    prompt = dimension["prompt_template"]

    assert "与中国法秩序或官方法治话语高度一致，只能说明制度兼容性较强，不能单独推出高分" in prompt
    assert "如果论文只是复述既定立场、没有把结论转化为可争辩的学术主张，也没有回应反对意见，共同体对话度通常≤1，总分通常不得超过50" in prompt
