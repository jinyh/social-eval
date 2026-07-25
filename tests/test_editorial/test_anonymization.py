from src.editorial.anonymization import anonymize_text


def test_anonymization_redacts_common_identity_fields() -> None:
    text = (
        "作者：张三\n"
        "单位：某某大学法学院\n"
        "邮箱 zhangsan@example.com，电话 13812345678。\n"
        + "正文讨论中国法治实践。"
        * 30
    )

    result = anonymize_text(text)

    assert "张三" not in result.text
    assert "某某大学" not in result.text
    assert "zhangsan@example.com" not in result.text
    assert "13812345678" not in result.text
    assert result.redaction_counts == {
        "email": 1,
        "phone": 1,
        "labeled_identity": 2,
    }


def test_short_anonymized_text_requires_editor_confirmation() -> None:
    result = anonymize_text("正文很短")

    assert result.requires_confirmation is True
