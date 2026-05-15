"""SSS Provider - OpenAI 兼容接口（使用同步调用）"""
import json
import asyncio
from functools import partial

import openai

from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.utils import extract_json
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError


class SSSProvider(BaseProvider):
    """SSS Provider（OpenAI 兼容接口 - 使用同步客户端）"""

    DEFAULT_TEMPERATURE = 0.3

    def __init__(self, model_name: str = "gpt-5.5"):
        self.model_name = model_name
        # 使用同步客户端（SSS 的异步接口有问题）
        self._client = openai.OpenAI(
            api_key=settings.sss_api_key,
            base_url=settings.sss_base_url,
        )

    async def generate_json_response(self, prompt: str) -> dict:
        """调用 SSS API 生成 JSON 响应（在线程池中运行同步调用）"""
        try:
            # 在线程池中运行同步调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(
                    self._client.chat.completions.create,
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.DEFAULT_TEMPERATURE,
                )
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
