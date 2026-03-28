"""
Groq API client for AI comment generation.

Uses the official groq Python SDK (OpenAI-compatible).
Free tier: 14,400 req/day for llama-3.1-8b-instant — used for bulk comment generation.
Gemini handles weekly digest (better reasoning, lower volume).

Implements the same generate_comment() interface as GeminiClient
so comment_generator can use either without changes.
"""
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_MODEL_LABELS: dict[str, str] = {
    "llama-3.1-8b-instant":              "Llama 3.1 8B",
    "llama-3.3-70b-versatile":           "Llama 3.3 70B",
    "meta-llama/llama-4-scout-17b-16e-instruct": "Llama 4 Scout",
    "moonshotai/kimi-k2-instruct":       "Kimi K2",
    "qwen/qwen3-32b":                    "Qwen3 32B",
}


class GroqClient:
    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key
        self.model = model
        self._client = None

        if api_key:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=api_key)
            except Exception as e:
                logger.warning("groq_client_init_failed", error=str(e))

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model_label(self) -> str:
        return _MODEL_LABELS.get(self.model, self.model)

    async def generate_comment(self, title: str, content: str) -> Optional[str]:
        """
        Generate a 10-30 character Traditional Chinese comment for a news item.
        Same interface as GeminiClient.generate_comment().
        Returns None if unavailable or call fails.
        """
        if not self._client:
            logger.warning("groq_skip_no_client")
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
            logger.warning("groq_comment_failed", title=title[:50], error=str(e))
            return None
