import json
import openai
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult
from src.core.config import settings
from src.core.exceptions import ProviderCallError


class OpenAIProvider(BaseProvider):
    model_name = "gpt-4o"

    def __init__(self):
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            return DimensionResult(**data, model_name=self.model_name)
        except Exception as e:
            raise ProviderCallError(self.model_name, str(e)) from e
