"""
AI comment generator — top-60-per-category strategy.

Per run:
  Fast client (Cerebras → Groq):
    news_article    top 60 by total_score
    blog_post       top 60 (skip paywalled: short content OR known paywall domain)
    research_paper  top 60
    product_launch  top 60
    community       top 60

  Gemini only:
    github_project  top 60 (skipped if no Gemini key / quota gone)

Already-commented items (ai_comment IS NOT NULL) are never touched.
"""
import asyncio
from typing import Optional, Protocol

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item, ContentCategory

logger = structlog.get_logger(__name__)

# Items per category per run
TOP_N_PER_CATEGORY = 60

# Blog paywall detection
PAYWALL_DOMAINS = {
    "medium.com", "wired.com", "nytimes.com", "wsj.com", "ft.com",
    "technologyreview.com", "theatlantic.com", "bloomberg.com",
    "washingtonpost.com", "economist.com", "hbr.org", "forbes.com",
    "businessinsider.com", "theinformation.com",
}
PAYWALL_MIN_CONTENT_LEN = 200  # shorter than this = likely truncated/paywalled

# Categories for fast client, in priority order
FAST_CATEGORIES = [
    ContentCategory.news_article,
    ContentCategory.blog_post,
    ContentCategory.research_paper,
    ContentCategory.product_launch,
    ContentCategory.community,
]

GEMINI_CATEGORIES = [
    ContentCategory.github_project,
]

_FAST_SLEEP   = 0.0
_GEMINI_SLEEP = 1.0


class CommentClient(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def model_label(self) -> str: ...
    async def generate_comment(self, title: str, content: str) -> Optional[str]: ...


def _build_fast_client() -> Optional[CommentClient]:
    """Cerebras → Groq. No Gemini."""
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
                logger.info("comment_client_selected", client=name, model=model)
                return client
        except Exception as e:
            logger.warning("comment_client_init_failed", client=name, error=str(e))
    return None


def _build_gemini_client() -> Optional[CommentClient]:
    """Gemini only — for github_project."""
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from app.summarizer.gemini import GeminiClient
        client = GeminiClient(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
        if client.available:
            logger.info("comment_client_selected", client="gemini", model=settings.GEMINI_MODEL)
            return client
    except Exception as e:
        logger.warning("comment_client_init_failed", client="gemini", error=str(e))
    return None


# Legacy alias
def _build_client() -> Optional[CommentClient]:
    return _build_fast_client()


def _is_paywalled(item: Item) -> bool:
    """Return True if a blog post is likely paywalled and has no useful content."""
    # Check known paywall domains
    url = item.url or ""
    for domain in PAYWALL_DOMAINS:
        if domain in url:
            return True
    # Check content length — too short means truncated/blocked
    content = item.summary or item.raw_content or ""
    if len(content.strip()) < PAYWALL_MIN_CONTENT_LEN:
        return True
    return False


async def run_comment_generation(
    db: Optional[AsyncSession] = None,
    client: Optional[CommentClient] = None,
    gemini=None,  # legacy kwarg
) -> int:
    """
    Generate comments for top 60 items per category.
    Already-commented items are skipped (ai_comment IS NULL filter).
    Returns total number of items successfully commented.
    """
    if client is None and gemini is not None:
        client = gemini

    fast_client   = client or _build_fast_client()
    gemini_client = _build_gemini_client()

    if not fast_client and not gemini_client:
        logger.info("comment_generation_skipped", reason="no LLM client available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        total = 0

        # ── Fast categories ───────────────────────────────────────────────────
        if fast_client:
            for category in FAST_CATEGORIES:
                n = await _process_category(db, fast_client, category, _FAST_SLEEP)
                total += n

        # ── GitHub via Gemini ─────────────────────────────────────────────────
        if gemini_client:
            for category in GEMINI_CATEGORIES:
                n = await _process_category(db, gemini_client, category, _GEMINI_SLEEP)
                total += n
        else:
            logger.info("github_comments_skipped", reason="no GEMINI_API_KEY")

        logger.info("comment_generation_total", total=total)
        return total

    finally:
        if own_session:
            await db.close()


async def _process_category(
    db: AsyncSession,
    client: CommentClient,
    category: ContentCategory,
    sleep: float,
) -> int:
    """
    Fetch top TOP_N_PER_CATEGORY uncommented items for one category,
    generate comments, stop on quota exhaustion.
    """
    result = await db.execute(
        select(Item)
        .where(
            Item.ai_comment == None,  # noqa: E711
            Item.category == category.value,
        )
        .order_by(Item.total_score.desc())
        .limit(TOP_N_PER_CATEGORY)
    )
    items = result.scalars().all()

    if not items:
        logger.info("category_nothing_to_do", category=category.value)
        return 0

    logger.info("category_comment_start",
                category=category.value, count=len(items), model=client.model_label)

    success = 0
    for i, item in enumerate(items):
        # Skip paywalled blog posts
        if category == ContentCategory.blog_post and _is_paywalled(item):
            logger.debug("blog_paywall_skip", item_id=str(item.id), url=item.url)
            continue

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
            logger.info("comment_generated",
                        category=category.value,
                        title=item.title[:60],
                        comment=comment,
                        model=client.model_label)
        else:
            # Null response = quota likely exhausted — stop this category
            logger.warning("comment_quota_or_error",
                           category=category.value,
                           model=client.model_label,
                           processed=i, success=success)
            break

        if sleep > 0 and i < len(items) - 1:
            await asyncio.sleep(sleep)

    logger.info("category_comment_done",
                category=category.value, success=success, total=len(items))
    return success
