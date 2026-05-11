import asyncio
from abc import ABC, abstractmethod

from src.core.config import settings
from src.core.exceptions import ProviderTimeoutError
from src.evaluation.schemas import DimensionResult


class BaseProvider(ABC):
    model_name: str
    timeout: float = settings.provider_timeout

    async def generate_json_response(self, prompt: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} must implement generate_json_response")

    async def call_with_timeout(self, coro):
        """包装异步调用，超时抛 ProviderTimeoutError"""
        try:
            return await asyncio.wait_for(coro, timeout=self.timeout)
        except asyncio.TimeoutError:
            raise ProviderTimeoutError(self.model_name, self.timeout)

    @abstractmethod
    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        """调用 AI 模型评估单个维度，返回结构化结果"""
