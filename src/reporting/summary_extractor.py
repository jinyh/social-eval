# src/reporting/summary_extractor.py
"""从分析文本中提取一句话总结（兜底方案）"""
from __future__ import annotations

import re


def extract_dimension_summary(analysis_text: str, max_length: int = 50) -> str:
    """
    从分析文本中提取一句话总结。

    策略：
    1. 优先取包含结论性词汇的句子
    2. 否则取首句
    3. 限制最大长度
    4. 移除引用符号

    Args:
        analysis_text: 分析文本
        max_length: 最大长度（默认50字）

    Returns:
        一句话总结
    """
    if not analysis_text or not analysis_text.strip():
        return "暂无总结"

    # 移除引用符号（「」『』等）
    text = re.sub(r"[「」『』【】]", "", analysis_text)

    # 按句号分割
    sentences = re.split(r"[。！？]", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return "暂无总结"

    # 结论性关键词
    conclusion_keywords = ["综上所述", "总体", "核心观点", "主要", "总体而言", "概言之"]

    # 优先找包含结论性词汇的句子
    for sentence in sentences:
        for keyword in conclusion_keywords:
            if keyword in sentence:
                return _truncate(sentence, max_length)

    # 否则取首句
    return _truncate(sentences[0], max_length)


def _truncate(text: str, max_length: int) -> str:
    """截断文本到指定长度"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 1] + "…"
