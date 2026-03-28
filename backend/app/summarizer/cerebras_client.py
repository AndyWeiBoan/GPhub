"""
Cerebras API client for AI comment generation.

Uses the official cerebras-cloud-sdk.
Free tier: 14,400 req/day for llama-3.1-8b — fastest inference (~0.3s/call).

Implements the same generate_comment() interface as GeminiClient and GroqClient
so comment_generator can use any of them interchangeably.
"""
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_MODEL_LABELS: dict[str, str] = {
    "llama-3.1-8b":   "Cerebras Llama 3.1 8B",
    "llama-3.3-70b":  "Cerebras Llama 3.3 70B",
    "gpt-oss-120b":   "Cerebras GPT OSS 120B",
}


class CerebrasClient:
    def __init__(self, api_key: str, model: str = "llama-3.1-8b"):
        self.api_key = api_key
        self.model = model
        self._client = None

        if api_key:
            try:
                from cerebras.cloud.sdk import AsyncCerebras
                self._client = AsyncCerebras(api_key=api_key)
            except Exception as e:
                logger.warning("cerebras_client_init_failed", error=str(e))

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model_label(self) -> str:
        return _MODEL_LABELS.get(self.model, self.model)

    async def generate_comment(self, title: str, content: str) -> Optional[str]:
        """
        Generate a 10-30 character Traditional Chinese comment for a news item.
        Same interface as GeminiClient and GroqClient.
        Returns None if unavailable or call fails.
        """
        if not self._client:
            logger.warning("cerebras_skip_no_client")
            return None

        prompt = (
            "你是 AI 科技新聞編輯。"
            "用 10 到 30 個繁體中文字，寫一句這篇文章的精準短評。"
            "重點是它的影響、獨特性或值得關注的原因。"
            "不要重複標題內容。不要加任何標點符號以外的格式符號。只輸出短評本身。\n\n"
            f"標題：{title}\n"
            f"摘要：{content[:500]}"
        )

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.7,
            )
            text = resp.choices[0].message.content.strip()
            text = text.replace("**", "").strip()
            if not text:
                return None
            return text
        except Exception as e:
            logger.warning("cerebras_comment_failed", title=title[:50], error=str(e))
            return None
