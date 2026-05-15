"""KETAN Provider - OpenAI 兼容接口"""
import json

import openai

from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.utils import extract_json
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError


class KetanProvider(BaseProvider):
    """KETAN Provider（OpenAI 兼容接口）"""

    DEFAULT_TEMPERATURE = 0.3

    def __init__(self, model_name: str = "gpt-5.5"):
        self.model_name = model_name
        self._client = openai.AsyncOpenAI(
            api_key=settings.ketan_api_key,
            base_url=settings.ketan_base_url,
        )

    async def generate_json_response(self, prompt: str) -> dict:
        """调用 KETAN API 生成 JSON 响应"""
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.DEFAULT_TEMPERATURE,
            )
            content = response.choices[0].message.content
            if not content:
                raise ProviderCallError(self.model_name, "Empty response content")

            # 使用工具函数提取 JSON
            extracted = extract_json(content)
            return json.loads(extracted)
        except json.JSONDecodeError as e:
            raise ProviderCallError(
                self.model_name, f"JSON parse failed: {e}. Raw: {content[:200]}"
            ) from e
        except Exception as e:
            raise ProviderCallError(self.model_name, str(e)) from e

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        """评估单个维度"""
        data = await self.generate_json_response(prompt)
        return DimensionResult(**data, model_name=self.model_name)
