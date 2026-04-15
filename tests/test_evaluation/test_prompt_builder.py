from src.evaluation.prompt_builder import build_prompt
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.loader import load_framework


def test_law_framework_prompts_are_actionable_and_renderable():
    framework = load_framework("configs/frameworks/law_v1.yaml")
    paper = ProcessedPaper(
        full_text="论文全文",
        body="论文正文",
        references=["参考文献一", "参考文献二"],
        structure_status="detected",
    )

    required_markers = [
        "不得直接凭整体印象",
        "证据片段",
        "缺陷触发",
        "跨维度边界",
        "分档锚点",
        "请严格按以下 JSON 格式返回",
    ]

    for dimension in framework.dimensions:
        prompt = build_prompt(dimension, paper)
        assert "论文正文" in prompt
        assert "参考文献一" in prompt
        assert f'"dimension": "{dimension.key}"' in prompt
        for marker in required_markers:
            assert marker in prompt
