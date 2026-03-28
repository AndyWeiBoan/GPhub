"""
Weekly digest generator using Gemini.

Groups this week's top items by topic cluster (using existing topics engine),
generates a 100-200 char Traditional Chinese analysis for each cluster,
and upserts results into the weekly_digests table.

Idempotent: running multiple times in the same week replaces existing digests.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item, WeeklyDigest
from app.scoring.topics import extract_topics
from app.summarizer.gemini import GeminiClient

logger = structlog.get_logger(__name__)

# Max topic clusters to save per week
MAX_DIGESTS = 5
# Min items in a cluster to be worth a digest
MIN_CLUSTER_SIZE = 2
# Seconds between Gemini calls
_RATE_LIMIT_SLEEP = 2.0


def _week_label(dt: Optional[datetime] = None) -> str:
    """Return ISO week label like '2026-W13'."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return f"{dt.year}-W{dt.isocalendar()[1]:02d}"


async def run_digest_generation(
    db: Optional[AsyncSession] = None,
    gemini: Optional[GeminiClient] = None,
) -> int:
    """
    Generate weekly digest entries for the current week.
    Returns number of digests created.
    """
    if gemini is None:
        if not settings.GEMINI_API_KEY:
            logger.info("digest_generation_skipped", reason="GEMINI_API_KEY not set")
            return 0
        gemini = GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )

    if not gemini.available:
        logger.info("digest_generation_skipped", reason="Gemini client not available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        return await _generate_digests(db, gemini)
    finally:
        if own_session:
            await db.close()


async def _generate_digests(db: AsyncSession, gemini: GeminiClient) -> int:
    week = _week_label()

    # Fetch this week's items (Monday 00:00 UTC to now)
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(Item)
        .where(Item.created_at >= week_start)
        .order_by(Item.total_score.desc())
        .limit(100)
    )
    items = result.scalars().all()

    if not items:
        logger.info("digest_generation_nothing_to_do", week=week)
        return 0

    logger.info("digest_generation_started", week=week, items=len(items))

    # Use existing topic clustering engine
    topics = extract_topics(items, top_k=MAX_DIGESTS, min_count=MIN_CLUSTER_SIZE)

    if not topics:
        logger.info("digest_generation_no_clusters", week=week)
        return 0

    # Delete existing digests for this week (idempotent)
    await db.execute(
        delete(WeeklyDigest).where(WeeklyDigest.week_label == week)
    )
    await db.commit()

    created = 0
    for i, topic in enumerate(topics[:MAX_DIGESTS]):
        # Build item summaries for Gemini input
        topic_item_objs = [
            it for it in items if str(it.id) in topic.item_ids
        ]
        item_dicts = [
            {
                "title": it.title,
                "summary": it.summary or it.raw_content,
            }
            for it in topic_item_objs[:5]
        ]

        analysis = await gemini.generate_digest(topic.label, item_dicts)

        if not analysis:
            logger.warning("digest_generation_failed", topic=topic.label)
            if i < len(topics) - 1:
                await asyncio.sleep(_RATE_LIMIT_SLEEP)
            continue

        digest = WeeklyDigest(
            id=str(uuid.uuid4()),
            week_label=week,
            title=topic.label,
            analysis=analysis,
            item_ids=json.dumps(topic.item_ids),
        )
        db.add(digest)
        await db.commit()
        created += 1

        logger.info(
            "digest_created",
            week=week,
            topic=topic.label,
            item_count=len(topic.item_ids),
        )

        if i < len(topics) - 1:
            await asyncio.sleep(_RATE_LIMIT_SLEEP)

    logger.info("digest_generation_done", week=week, created=created)
    return created
