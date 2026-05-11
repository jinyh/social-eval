from __future__ import annotations

from src.ingestion.schemas import ProcessedPaper
from src.knowledge.schemas import Dimension, Framework


def _paper_content(paper: ProcessedPaper) -> str:
    return paper.body or paper.full_text


def _reference_content(paper: ProcessedPaper) -> str:
    if not paper.references:
        return "（无）"
    return "\n".join(paper.references)


def _append_context(template: str, paper: ProcessedPaper) -> str:
    return (
        f"{template.rstrip()}\n\n"
        f"论文正文：\n{_paper_content(paper)}\n"
        f"---\n"
        f"参考文献列表：\n{_reference_content(paper)}"
    )


def _render_template(template: str, paper: ProcessedPaper) -> str:
    if "{paper_content}" in template or "{references}" in template:
        return template.format(
            paper_content=_paper_content(paper),
            references=_reference_content(paper),
        )
    return _append_context(template, paper)


def build_prompt(dimension: Dimension, paper: ProcessedPaper) -> str:
    return _render_template(dimension.prompt_template, paper)


def build_precheck_prompt(framework: Framework, paper: ProcessedPaper) -> str:
    if framework.precheck is None:
        raise ValueError("当前框架未配置 precheck")
    return _render_template(framework.precheck.prompt_template, paper)


_JSON_SIGNAL_TEMPLATE = (
    '{\n'
    '  "china_problem_centered": "yes/no/partial/uncertain",\n'
    '  "china_practice_explanation_attempted": "yes/no/partial/uncertain",\n'
    '  "external_theory_transformation": "sufficient/partial/insufficient/not_applicable/uncertain",\n'
    '  "verifiable_concept_or_thesis": "yes/no/partial/uncertain",\n'
    '  "involves_special_chinese_institutional_issue": "yes/no/uncertain",\n'
    '  "issue_types": ["party/intra_party_regulation/supervision/state_governance/other"],\n'
    '  "uses_traditional_cultural_resource": "yes/no/uncertain",\n'
    '  "evidence_quotes": ["原文证据1", "原文证据2"],\n'
    '  "risks": [],\n'
    '  "signal_scores": {"china_problem_centered": 0-2, "china_practice_explanation_attempted": 0-2, "external_theory_transformation": 0-2, "verifiable_concept_or_thesis": 0-2},\n'
    '  "autonomous_signal_score": 0-8,\n'
    '  "autonomous_signal_strength": "strong/medium/weak/absent",\n'
    '  "triggers_review": true/false,\n'
    '  "review_reason": ""\n'
    '}'
)


def build_signal_check_prompt(framework: Framework, paper: ProcessedPaper) -> str:
    """构建自主知识体系信号校验 prompt。"""
    if not hasattr(framework, "raw_config") or not framework.raw_config:
        raise ValueError("当前框架未配置信号校验")

    signals_config = framework.raw_config.get("autonomous_knowledge_signals")
    if not signals_config:
        raise ValueError("当前框架未配置 autonomous_knowledge_signals")

    yaml_template = signals_config.get("prompt_template")
    if yaml_template:
        output_template = str(signals_config.get("output_template", "")).strip()
        template = str(yaml_template).replace("{output_template}", output_template)
        return _render_template(template, paper)

    prompt_parts = [
        "请对这篇法学论文进行【自主知识体系信号校验】。",
        "",
        "本步骤是独立的检查步骤，不是第七个评分维度，不进入基础分公式。",
        "只整理文内可观察的自主知识体系信号，用于辅助六维评分和触发评价层复核。",
        "",
        "请检查以下四类核心信号：",
    ]

    for signal in signals_config.get("signals", []):
        prompt_parts.append(
            f"\n□ {signal.get('name_zh', signal['key'])}：{signal.get('description', '')}"
        )
        prompt_parts.append(f"  判断值：{', '.join(signal.get('values', []))}")

    prompt_parts.append("\n请同时识别以下辅助信息：")
    for meta in signals_config.get("auxiliary_metadata", []):
        prompt_parts.append(
            f"\n□ {meta.get('name_zh', meta['key'])}：判断值：{', '.join(meta.get('values', []))}"
        )

    prompt_parts.append("\n典型风险（如发现请标记）：")
    for risk in signals_config.get("typical_risks", []):
        prompt_parts.append(f"  - {risk}")

    quantification = signals_config.get("quantification")
    if quantification:
        prompt_parts.append("\n信号量化要求：")
        prompt_parts.append(
            "  - 四项核心信号分别按 0/1/2 输出 signal_scores；"
            "0 表示 no/insufficient，1 表示 partial/uncertain，"
            "2 表示 yes/sufficient/not_applicable。"
        )
        prompt_parts.append(
            "  - autonomous_signal_score 为四项分数总和，只用于排序、"
            "分层和复核优先级，不进入六维基础分。"
        )
        prompt_parts.append(
            "  - autonomous_signal_strength："
            f"{quantification.get('strength_bands', 'strong/medium/weak/absent')}"
        )

    prompt_parts.append("\n矛盾触发条件（如果以下条件成立，自动触发评价层复核）：")
    for trigger in signals_config.get("contradiction_triggers", []):
        prompt_parts.append(f"  - {trigger.get('rule', '')}: {trigger.get('condition', '')}")

    prompt_parts.append("")
    prompt_parts.append("请输出 JSON：")
    prompt_parts.append(_JSON_SIGNAL_TEMPLATE)

    template = "\n".join(prompt_parts)
    return _append_context(template, paper)
