import json
import re

import openai

from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError


def _extract_json(text: str) -> str:
    """从模型输出中提取 JSON，处理 markdown 包裹和前缀后缀"""
    # 尝试提取 ```json ... ``` 块
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    # 尝试提取 ``` ... ``` 块
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1)
        if candidate.startswith("{"):
            return candidate

    # 尝试找到最外层 { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


class ZenmuxProvider(BaseProvider):
    """Zenmux 统一接口 Provider，支持通过 OpenAI 兼容 API 调用多个模型"""

    BASE_URL = "https://zenmux.ai/api/v1"

    # Kimi-K2.6 不支持自定义 temperature，只允许 1
    KIMI_MODELS = {"kimi-k2.6", "moonshotai/kimi-k2.6"}
    DEFAULT_TEMPERATURE = 0.3

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._client = openai.AsyncOpenAI(
            api_key=settings.zenmux_api_key,
            base_url=self.BASE_URL,
        )

    async def generate_json_response(self, prompt: str) -> dict:
        # Kimi 系列模型只允许 temperature=1
        temperature = 1.0 if self.model_name in self.KIMI_MODELS else self.DEFAULT_TEMPERATURE
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if not content:
                raise ProviderCallError(self.model_name, "Empty response content")

            extracted = _extract_json(content)
            return json.loads(extracted)
        except json.JSONDecodeError as e:
            raise ProviderCallError(
                self.model_name, f"JSON parse failed: {e}. Raw: {content[:200]}"
            ) from e
        except Exception as e:
            raise ProviderCallError(self.model_name, str(e)) from e

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        data = await self.generate_json_response(prompt)
        return DimensionResult(**data, model_name=self.model_name)