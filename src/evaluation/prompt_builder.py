from src.knowledge.schemas import Dimension
from src.ingestion.schemas import ProcessedPaper


def build_prompt(dimension: Dimension, paper: ProcessedPaper) -> str:
    return dimension.prompt_template.format(
        paper_content=paper.body or paper.full_text,
        references="\n".join(paper.references),
    )
