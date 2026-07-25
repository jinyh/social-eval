import pytest

from src.editorial.fit import _validate_fit_payload


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
