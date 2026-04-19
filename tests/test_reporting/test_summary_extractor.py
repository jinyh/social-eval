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
