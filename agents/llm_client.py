import json
from typing import Any

import httpx
from openai import AsyncOpenAI

from config.settings import Settings


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if settings.llm_provider in {"openai", "groq"}:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key or settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1" if settings.llm_provider == "groq" else None,
            )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self.settings.llm_provider in {"openai", "groq"}:
            assert self._client is not None
            response = await self._client.chat.completions.create(
                model=self.settings.llm_model,
                temperature=self.settings.llm_temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            return json.loads(text)

        if self.settings.llm_provider == "claude":
            if not self.settings.claude_api_key:
                raise ValueError("CLAUDE_API_KEY is required when LLM_PROVIDER=claude.")
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.settings.claude_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.settings.llm_model,
                        "max_tokens": 3000,
                        "temperature": self.settings.llm_temperature,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content", [])
                text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
                return json.loads(text or "{}")

        raise ValueError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")