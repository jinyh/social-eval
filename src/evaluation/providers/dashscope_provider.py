import json

import openai
from pydantic import ValidationError

from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.utils import extract_json
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError, ProviderResponseValidationError


class DashScopeProvider(BaseProvider):
    """阿里云百炼（DashScope）Provider，通过 OpenAI 兼容 API 调用模型"""

    DEFAULT_TEMPERATURE = 0.3

    def __init__(
        self,
        model_name: str,
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        extra_body: dict | None = None,
        max_completion_tokens: int | None = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.extra_body = extra_body or {}
        self.max_completion_tokens = max_completion_tokens
        self._last_response_metadata: dict = {}
        self._client = openai.AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )

    async def generate_json_response(self, prompt: str) -> dict:
        content = ""
        try:
            request = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": self.temperature,
                "extra_body": self.extra_body or None,
            }
            if self.max_completion_tokens is not None:
                request["max_completion_tokens"] = self.max_completion_tokens
            response = await self._client.chat.completions.create(
                **request,
            )
            choice = response.choices[0]
            content = choice.message.content
            usage = getattr(response, "usage", None)
            self._last_response_metadata = {
                "finish_reason": getattr(choice, "finish_reason", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }
            if not content:
                raise ProviderCallError(self.model_name, "Empty response content")
            if self._last_response_metadata["finish_reason"] not in (None, "stop"):
                raise ProviderCallError(
                    self.model_name,
                    "模型输出未正常结束："
                    f"{self._last_response_metadata['finish_reason']}",
                    raw_response=content,
                )

            extracted = extract_json(content)
            return json.loads(extracted)
        except json.JSONDecodeError as e:
            raise ProviderCallError(
                self.model_name,
                f"JSON parse failed: {e}",
                raw_response=content,
            ) from e
        except ProviderCallError:
            raise
        except Exception as e:
            raise ProviderCallError(self.model_name, str(e)) from e

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        data = await self.generate_json_response(prompt)
        try:
            return DimensionResult(**data, model_name=self.model_name)
        except ValidationError as exc:
            invalid_fields = tuple(
                ".".join(str(part) for part in error["loc"]) for error in exc.errors()
            )
            metadata = ", ".join(
                f"{key}={value}"
                for key, value in self._last_response_metadata.items()
                if value is not None
            )
            raise ProviderResponseValidationError(
                self.model_name,
                f"结构化输出校验失败（{metadata or '无响应元数据'}）：{exc}",
                raw_response=json.dumps(data, ensure_ascii=False),
                invalid_fields=invalid_fields,
            ) from exc
