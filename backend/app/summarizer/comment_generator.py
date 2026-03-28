"""
Batch AI comment generator.

Category priority (Cerebras/Groq handle all except github):
  1. news_article    → fast client (Cerebras → Groq)
  2. blog_post       → fast client
  3. research_paper  → fast client
  4. product_launch  → fast client
  5. community       → fast client
  6. github_project  → Gemini only (skip if Gemini quota exhausted)

Runs continuously until quota is hit (no fixed batch cap).
Already-commented items are always skipped.
"""
import asyncio
from typing import Optional, Protocol

import structlog
from sqlalchemy import select, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item, ContentCategory

logger = structlog.get_logger(__name__)

# Category priority — lower number = processed first
CATEGORY_PRIORITY: dict[str, int] = {
    ContentCategory.news_article.value:   1,
    ContentCategory.blog_post.value:      2,
    ContentCategory.research_paper.value: 3,
    ContentCategory.product_launch.value: 4,
    ContentCategory.community.value:      5,
    ContentCategory.github_project.value: 6,
}

# Categories handled by fast clients (Cerebras/Groq)
FAST_CATEGORIES = [
    ContentCategory.news_article,
    ContentCategory.blog_post,
    ContentCategory.research_paper,
    ContentCategory.product_launch,
    ContentCategory.community,
]

# Categories handled by Gemini only
GEMINI_CATEGORIES = [
    ContentCategory.github_project,
]

# No sleep for fast inference providers
_FAST_SLEEP = 0.0
_GEMINI_SLEEP = 1.0

# Fetch this many items per DB query to avoid loading everything into memory
_FETCH_CHUNK = 100


class CommentClient(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def model_label(self) -> str: ...
    async def generate_comment(self, title: str, content: str) -> Optional[str]: ...


def _build_fast_client() -> Optional[CommentClient]:
    """
    Build fastest available client: Cerebras → Groq → (no Gemini).
    Used for all non-github categories.
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
    ]

    for name, key, model, factory in candidates:
        if not key:
            continue
        try:
            client = factory(key, model)
            if client.available:
                logger.info("comment_client_selected", client=name, model=model, role="fast")
                return client
        except Exception as e:
            logger.warning("comment_client_init_failed", client=name, error=str(e))

    return None


def _build_gemini_client() -> Optional[CommentClient]:
    """
    Build Gemini client exclusively — used for github_project category.
    Returns None if no Gemini key set.
    """
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from app.summarizer.gemini import GeminiClient
        client = GeminiClient(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
        if client.available:
            logger.info("comment_client_selected", client="gemini", model=settings.GEMINI_MODEL, role="github")
            return client
    except Exception as e:
        logger.warning("comment_client_init_failed", client="gemini", error=str(e))
    return None


# Legacy: kept for backwards compat — returns fast client
def _build_client() -> Optional[CommentClient]:
    return _build_fast_client()


async def run_comment_generation(
    db: Optional[AsyncSession] = None,
    client: Optional[CommentClient] = None,
    gemini=None,  # legacy kwarg
) -> int:
    """
    Generate ai_comment for all pending items, prioritised by category.
    Runs until quota is exhausted (API errors stop the run).
    Returns total number of items successfully commented.
    """
    # Backwards compat
    if client is None and gemini is not None:
        client = gemini

    fast_client = client or _build_fast_client()
    gemini_client = _build_gemini_client()

    if not fast_client and not gemini_client:
        logger.info("comment_generation_skipped", reason="no LLM client available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        total = 0

        # ── Pass 1: Fast categories (Cerebras/Groq) ──────────────────────────
        if fast_client:
            n = await _generate_for_categories(
                db, fast_client, FAST_CATEGORIES, sleep=_FAST_SLEEP
            )
            total += n

        # ── Pass 2: GitHub (Gemini only) ─────────────────────────────────────
        if gemini_client:
            n = await _generate_for_categories(
                db, gemini_client, GEMINI_CATEGORIES, sleep=_GEMINI_SLEEP
            )
            total += n
        else:
            logger.info("github_comments_skipped", reason="no GEMINI_API_KEY")

        logger.info("comment_generation_total", total=total)
        return total

    finally:
        if own_session:
            await db.close()


async def _generate_for_categories(
    db: AsyncSession,
    client: CommentClient,
    categories: list,
    sleep: float,
) -> int:
    """
    Fetch all pending items in the given categories (priority order),
    generate comments until quota is exhausted.
    Returns number of successfully commented items.
    """
    # Build priority ordering expression for SQLAlchemy
    priority_case = case(
        {cat.value: CATEGORY_PRIORITY[cat.value] for cat in categories},
        value=Item.category,
        else_=99,
    )

    result = await db.execute(
        select(Item)
        .where(
            Item.ai_comment == None,  # noqa: E711
            Item.category.in_([c.value for c in categories]),
        )
        .order_by(priority_case, Item.total_score.desc())
        .limit(settings.COMMENT_FETCH_CHUNK)
    )
    items = result.scalars().all()

    if not items:
        logger.info("comment_generation_nothing_to_do",
                    categories=[c.value for c in categories])
        return 0

    logger.info(
        "comment_generation_started",
        categories=[c.value for c in categories],
        total=len(items),
        model=client.model_label,
    )

    success = 0
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
            success += 1
            logger.info(
                "comment_generated",
                item_id=str(item.id),
                category=str(item.category),
                title=item.title[:60],
                comment=comment,
                model=client.model_label,
            )
        else:
            # API failure likely means quota exhausted — stop this pass
            logger.warning(
                "comment_generation_quota_or_error",
                item_id=str(item.id),
                model=client.model_label,
                processed=i,
                success=success,
            )
            break

        if sleep > 0 and i < len(items) - 1:
            await asyncio.sleep(sleep)

    logger.info(
        "comment_generation_pass_done",
        categories=[c.value for c in categories],
        success=success,
        total=len(items),
        model=client.model_label,
    )
    return success
