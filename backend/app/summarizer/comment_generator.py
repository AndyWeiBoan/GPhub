"""
Batch AI comment generator using Gemini.

Fetches items without ai_comment (ordered by total_score DESC),
generates a 10-30 char Traditional Chinese comment for each,
and writes results back to DB. Already-commented items are skipped.
"""
import asyncio
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item
from app.summarizer.gemini import GeminiClient

logger = structlog.get_logger(__name__)

# Seconds to wait between API calls — conservative for free tier (15 req/min)
_RATE_LIMIT_SLEEP = 2.0


async def run_comment_generation(
    db: Optional[AsyncSession] = None,
    gemini: Optional[GeminiClient] = None,
) -> int:
    """
    Generate ai_comment for items that don't have one yet.
    Returns the number of items successfully commented.

    Can be called with an existing db session and GeminiClient (for testing),
    or will create its own session and client from settings.
    """
    # Build client from settings if not provided
    if gemini is None:
        if not settings.GEMINI_API_KEY:
            logger.info("comment_generation_skipped", reason="GEMINI_API_KEY not set")
            return 0
        gemini = GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )

    if not gemini.available:
        logger.info("comment_generation_skipped", reason="Gemini client not available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        return await _generate_comments(db, gemini)
    finally:
        if own_session:
            await db.close()


async def _generate_comments(db: AsyncSession, gemini: GeminiClient) -> int:
    # Fetch items without ai_comment, highest score first
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

    logger.info("comment_generation_started", total=len(items))
    success_count = 0

    for i, item in enumerate(items):
        content = item.summary or item.raw_content or ""
        comment = await gemini.generate_comment(item.title, content)

        if comment:
            await db.execute(
                update(Item)
                .where(Item.id == item.id)
                .values(ai_comment=comment)
            )
            await db.commit()
            success_count += 1
            logger.info(
                "comment_generated",
                item_id=str(item.id),
                title=item.title[:60],
                comment=comment,
            )
        else:
            logger.warning("comment_generation_failed", item_id=str(item.id))

        # Rate limit: don't sleep after the last item
        if i < len(items) - 1:
            await asyncio.sleep(_RATE_LIMIT_SLEEP)

    logger.info("comment_generation_done", success=success_count, total=len(items))
    return success_count
