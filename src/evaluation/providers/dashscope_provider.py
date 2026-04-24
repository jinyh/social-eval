import json

import openai

from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.utils import extract_json
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError


class DashScopeProvider(BaseProvider):
    """阿里云百炼（DashScope）Provider，通过 OpenAI 兼容 API 调用模型"""

    # Kimi-K2.6 不支持自定义 temperature，只允许 1
    KIMI_MODELS = {"kimi-k2.6"}
    DEFAULT_TEMPERATURE = 0.3

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._client = openai.AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )

    async def generate_json_response(self, prompt: str) -> dict:
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

            extracted = extract_json(content)
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