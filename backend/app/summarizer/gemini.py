"""
Gemini API client for AI comment and weekly digest generation.

Uses google-genai SDK (official new SDK, not the deprecated google-generativeai).
Free tier: 15 req/min, 1500 req/day for gemini-2.5-flash.
"""
import asyncio
import logging
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None

        if api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning("gemini_client_init_failed", error=str(e))
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def generate_comment(self, title: str, content: str) -> Optional[str]:
        """
        Generate a 10-30 character Traditional Chinese comment for a news item.
        Returns None if API key is missing or call fails.
        """
        if not self._client:
            logger.warning("gemini_skip_no_client", reason="no api key or init failed")
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
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = response.text.strip()
            # Strip markdown bold markers if model adds them
            text = text.replace("**", "").strip()
            if not text:
                return None
            return text
        except Exception as e:
            logger.warning("gemini_comment_failed", title=title[:50], error=str(e))
            return None

    async def generate_digest(self, topic_title: str, items: list[dict]) -> Optional[str]:
        """
        Generate a 100-200 character Traditional Chinese analysis of a hot topic cluster.
        items: list of dicts with keys: title, summary (or raw_content)
        Returns None if API key is missing or call fails.
        """
        if not self._client:
            logger.warning("gemini_skip_no_client", reason="no api key or init failed")
            return None

        summaries = "\n".join(
            f"- {item.get('title', '')}: {(item.get('summary') or item.get('raw_content') or '')[:200]}"
            for item in items[:5]
        )

        prompt = (
            "你是 AI 科技週報編輯。"
            f"以下是本週關於「{topic_title}」的 {len(items)} 篇報導摘要。"
            "請用 100 到 200 個繁體中文字，分析這個議題的來龍去脈、重要性與影響。"
            "語氣專業但易讀。只輸出分析本文，不加標題或項目符號。\n\n"
            f"{summaries}"
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = response.text.strip()
            text = text.replace("**", "").strip()
            if not text:
                return None
            return text
        except Exception as e:
            logger.warning("gemini_digest_failed", topic=topic_title[:50], error=str(e))
            return None
