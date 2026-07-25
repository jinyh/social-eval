"""编辑预审的形式完整性检查。"""

from __future__ import annotations

import re
from typing import Any


_REFERENCE_PATTERN = re.compile(r"(参考文献|注释|脚注|\[\d+\]|①|②|③|（\d+）|\(\d+\))")
_SECTION_PATTERN = re.compile(
    r"(^|\n)\s*(摘要|关键词|引言|导论|结语|结论|一、|二、|三、)",
    re.MULTILINE,
)


def evaluate_formal_completeness(text: str) -> dict[str, Any]:
    """检查文本长度、基本结构和引注线索，不替代人工格式审查。"""

    normalized = text.strip()
    issues: list[str] = []
    if len(normalized) < 2_000:
        issues.append("可解析正文少于 2000 字，可能不是完整论文。")
    has_sections = bool(_SECTION_PATTERN.search(normalized))
    if not has_sections:
        issues.append("未识别到摘要、引言、结语或中文章节标题。")
    has_reference_markers = bool(_REFERENCE_PATTERN.search(normalized))
    if not has_reference_markers:
        issues.append("未识别到参考文献、脚注或注释标记。")

    return {
        "status": "pass" if not issues else "boundary",
        "character_count": len(normalized),
        "has_section_structure": has_sections,
        "has_reference_markers": has_reference_markers,
        "issues": issues,
        "requires_editor_confirmation": bool(issues),
        "notice": "本检查只识别形式完整性线索，不判断论文质量。",
    }
