from pydantic import BaseModel


class Dimension(BaseModel):
    key: str
    name_zh: str
    name_en: str
    weight: float
    prompt_template: str


class Framework(BaseModel):
    name: str
    discipline: str
    version: str
    std_threshold: float
    dimensions: list[Dimension]
