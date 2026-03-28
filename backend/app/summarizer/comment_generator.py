"""
Batch AI comment generator.

Client priority:
  1. Groq (llama-3.1-8b-instant) — 14,400 req/day free, ~0.5s per call
  2. Gemini (2.5-flash) fallback  — 20 req/day free, used only if no Groq key

Fetches items without ai_comment (ordered by total_score DESC),
generates a 10-30 char Traditional Chinese comment for each,
and writes results back to DB. Already-commented items are skipped.
"""
import asyncio
from typing import Optional, Protocol

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item

logger = structlog.get_logger(__name__)

# Groq is fast (~0.5s/call) — no sleep needed between requests
# Gemini is slow (~8s/call) — small sleep to avoid burst issues
_GROQ_SLEEP = 0.0
_GEMINI_SLEEP = 1.0


class CommentClient(Protocol):
    """Any client that can generate a comment."""
    @property
    def available(self) -> bool: ...
    @property
    def model_label(self) -> str: ...
    async def generate_comment(self, title: str, content: str) -> Optional[str]: ...


def _build_client() -> Optional[CommentClient]:
    """
    Build the best available comment client from settings.

    Priority (fastest + highest free quota first):
      1. Cerebras  — 14,400 req/day, ~0.3s/call
      2. Groq      — 14,400 req/day, ~0.5s/call
      3. Gemini    — 20 req/day,     ~8s/call  (fallback only)

    Having multiple keys active means they are tried in order — whichever
    initialises successfully wins. To explicitly rotate load across providers,
    set all keys; the first available is used per process startup.
    """
    candidates = [
        ("cerebras", settings.CEREBRAS_API_KEY, settings.CEREBRAS_MODEL,
         lambda k, m: __import__(
             "app.summarizer.cerebras_client", fromlist=["CerebrasClient"]
         ).CerebrasClient(api_key=k, model=m)),
        ("groq", settings.GROQ_API_KEY, settings.GROQ_MODEL,
         lambda k, m: __import__(
             "app.summarizer.groq_client", fromlist=["GroqClient"]
         ).GroqClient(api_key=k, model=m)),
        ("gemini", settings.GEMINI_API_KEY, settings.GEMINI_MODEL,
         lambda k, m: __import__(
             "app.summarizer.gemini", fromlist=["GeminiClient"]
         ).GeminiClient(api_key=k, model=m)),
    ]

    for name, key, model, factory in candidates:
        if not key:
            continue
        try:
            client = factory(key, model)
            if client.available:
                logger.info("comment_client_selected", client=name, model=model)
                return client
        except Exception as e:
            logger.warning("comment_client_init_failed", client=name, error=str(e))

    return None


async def run_comment_generation(
    db: Optional[AsyncSession] = None,
    client: Optional[CommentClient] = None,
    # Legacy kwarg — still accepted so existing callers don't break
    gemini=None,
) -> int:
    """
    Generate ai_comment for items that don't have one yet.
    Returns the number of items successfully commented.
    """
    # Backwards compat: accept old 'gemini' kwarg
    if client is None and gemini is not None:
        client = gemini

    if client is None:
        client = _build_client()

    if client is None or not client.available:
        logger.info("comment_generation_skipped", reason="no LLM client available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        return await _generate_comments(db, client)
    finally:
        if own_session:
            await db.close()


async def _generate_comments(db: AsyncSession, client: CommentClient) -> int:
    result = await db.execute(
        select(Item)
        .where(Item.ai_comment == None)  # noqa: E711
        .order_by(Item.total_score.desc())
        .limit(settings.GEMINI_COMMENT_BATCH_SIZE)
    )
    items = result.scalars().all()

    if not items:
        logger.info("comment_generation_nothing_to_do")
        return 0

    # Pick sleep duration based on client type
    from app.summarizer.groq_client import GroqClient
    from app.summarizer.cerebras_client import CerebrasClient
    sleep_between = (
        _GROQ_SLEEP if isinstance(client, (GroqClient, CerebrasClient))
        else _GEMINI_SLEEP
    )

    logger.info(
        "comment_generation_started",
        total=len(items),
        model=client.model_label,
        sleep_between=sleep_between,
    )
    success_count = 0

    for i, item in enumerate(items):
        content = item.summary or item.raw_content or ""
        comment = await client.generate_comment(item.title, content)

        if comment:
            await db.execute(
                update(Item)
                .where(Item.id == item.id)
                .values(ai_comment=comment, ai_comment_model=client.model_label)
            )
            await db.commit()
            success_count += 1
            logger.info(
                "comment_generated",
                item_id=str(item.id),
                title=item.title[:60],
                comment=comment,
                model=client.model_label,
            )
        else:
            logger.warning("comment_generation_failed", item_id=str(item.id))

        if sleep_between > 0 and i < len(items) - 1:
            await asyncio.sleep(sleep_between)

    logger.info("comment_generation_done", success=success_count, total=len(items))
    return success_count
