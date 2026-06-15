from typing import Tuple
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.prompts import get_prompt

class OpenAIClientSingleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpenAIClientSingleton, cls).__new__(cls)
            cls._instance.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        return cls._instance

    async def _call_api(self, prompt: str, model: str = "gpt-4o-mini") -> Tuple[str, int]:
        if not self.client:
            raise ValueError("OPENAI_API_KEY is not configured.")

        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        tokens = response.usage.total_tokens if response.usage else 0
        return content, tokens

    async def classify(self, text: str, categories: str, custom_template: str = None) -> Tuple[str, int]:
        prompt = get_prompt("classify", custom_template, text=text, categories=categories)
        return await self._call_api(prompt)

    async def summarize(self, text: str, custom_template: str = None) -> Tuple[str, int]:
        prompt = get_prompt("summarize", custom_template, text=text)
        return await self._call_api(prompt)

    async def extract_fields(self, text: str, fields: str, custom_template: str = None) -> Tuple[str, int]:
        prompt = get_prompt("extract_fields", custom_template, text=text, fields=fields)
        return await self._call_api(prompt)

    async def generate_reply(self, context: str, tone: str, custom_template: str = None) -> Tuple[str, int]:
        prompt = get_prompt("generate_reply", custom_template, context=context, tone=tone)
        return await self._call_api(prompt)

openai_client = OpenAIClientSingleton()
