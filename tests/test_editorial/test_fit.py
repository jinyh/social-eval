import pytest

from src.editorial.fit import _format_fit_profile, _validate_fit_payload


def test_fit_profile_includes_versioned_journal_scope() -> None:
    prompt = _format_fit_profile(
        {
            "accepted_scope": ["法学理论", "制度研究"],
            "excluded_scope": ["泛社会评论"],
            "column_positioning": ["专题论文"],
            "article_types": ["研究论文"],
            "target_readers": ["法学研究者"],
            "special_notes": "比较法须回应中国问题",
        }
    )

    assert "收稿范围：法学理论；制度研究" in prompt
    assert "明确排除范围：泛社会评论" in prompt
    assert "目标读者：法学研究者" in prompt
    assert "比较法须回应中国问题" in prompt


def test_fit_payload_normalizes_structured_reasons_and_evidence() -> None:
    result = _validate_fit_payload(
        {
            "status": "pass",
            "reasons": [{"reason": "符合期刊关注范围"}],
            "evidence_quotes": [{"quote": "稿件中的相关原文"}],
            "requires_editor_confirmation": False,
        }
    )

    assert result["reasons"] == ["符合期刊关注范围"]
    assert result["evidence_quotes"] == ["稿件中的相关原文"]


def test_fit_payload_rejects_unrecognized_structured_items() -> None:
    with pytest.raises(ValueError, match="理由必须是文字列表"):
        _validate_fit_payload(
            {
                "status": "pass",
                "reasons": [{"unknown": "无法识别"}],
                "evidence_quotes": [],
                "requires_editor_confirmation": False,
            }
        )
