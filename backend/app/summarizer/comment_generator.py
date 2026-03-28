"""
AI comment generator — score-ranked parallel strategy.

Priority: highest total_score first, regardless of category.
This ensures trending topic lead items always get commented first.

Per run:
  1. Fetch top FAST_TOTAL_LIMIT uncommented non-github items by total_score DESC
  2. Split into up to 3 buckets (one per available fast provider)
  3. Run all buckets in parallel via asyncio.gather()
  4. Separately: top GITHUB_LIMIT github items → Gemini only

Blog paywall items are skipped (known domains + short content).
Already-commented items (ai_comment IS NOT NULL) are never re-processed.
"""
import asyncio
import math
from typing import Optional, Protocol

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Item, ContentCategory

logger = structlog.get_logger(__name__)

# Total non-github items to comment per run (split across fast providers)
FAST_TOTAL_LIMIT = 300
# GitHub items per run (Gemini only)
GITHUB_LIMIT = 60

# Non-github categories (ordered by editorial priority — used only for
# tiebreaking within the same score; actual ordering is by total_score DESC)
FAST_CATEGORIES = [
    ContentCategory.news_article,
    ContentCategory.blog_post,
    ContentCategory.research_paper,
    ContentCategory.product_launch,
    ContentCategory.community,
]

GEMINI_CATEGORIES = [ContentCategory.github_project]

# Blog paywall detection
PAYWALL_DOMAINS = {
    "medium.com", "wired.com", "nytimes.com", "wsj.com", "ft.com",
    "technologyreview.com", "theatlantic.com", "bloomberg.com",
    "washingtonpost.com", "economist.com", "hbr.org", "forbes.com",
    "businessinsider.com", "theinformation.com",
}
PAYWALL_MIN_CONTENT_LEN = 200

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


def _build_all_fast_clients() -> list[CommentClient]:
    """Return all available fast clients (Cerebras + Groq)."""
    clients: list[CommentClient] = []
    factories = [
        ("cerebras", settings.CEREBRAS_API_KEY, settings.CEREBRAS_MODEL,
         lambda k, m: __import__(
             "app.summarizer.cerebras_client", fromlist=["CerebrasClient"]
         ).CerebrasClient(api_key=k, model=m)),
        ("groq", settings.GROQ_API_KEY, settings.GROQ_MODEL,
         lambda k, m: __import__(
             "app.summarizer.groq_client", fromlist=["GroqClient"]
         ).GroqClient(api_key=k, model=m)),
    ]
    for name, key, model, factory in factories:
        if not key:
            continue
        try:
            client = factory(key, model)
            if client.available:
                clients.append(client)
                logger.info("comment_client_available", client=name, model=model)
        except Exception as e:
            logger.warning("comment_client_init_failed", client=name, error=str(e))
    return clients


def _build_gemini_client() -> Optional[CommentClient]:
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from app.summarizer.gemini import GeminiClient
        client = GeminiClient(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
        if client.available:
            return client
    except Exception as e:
        logger.warning("comment_client_init_failed", client="gemini", error=str(e))
    return None


# Legacy alias
def _build_client() -> Optional[CommentClient]:
    return _build_fast_client()


def _is_paywalled(item: Item) -> bool:
    url = item.url or ""
    for domain in PAYWALL_DOMAINS:
        if domain in url:
            return True
    content = item.summary or item.raw_content or ""
    return len(content.strip()) < PAYWALL_MIN_CONTENT_LEN


async def run_comment_generation(
    db: Optional[AsyncSession] = None,
    client: Optional[CommentClient] = None,
    gemini=None,  # legacy kwarg
) -> int:
    """
    Generate comments in parallel across all available providers.
    Items are ranked by total_score DESC so trending topic leads
    always get commented first.
    Returns total items successfully commented.
    """
    if client is None and gemini is not None:
        client = gemini

    # Build all available clients
    if client is not None:
        fast_clients = [client]
    else:
        fast_clients = _build_all_fast_clients()

    gemini_client = _build_gemini_client()

    if not fast_clients and not gemini_client:
        logger.info("comment_generation_skipped", reason="no LLM client available")
        return 0

    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()

    try:
        total = 0

        # ── Fetch top uncommented non-github items by score ───────────────────
        fast_cat_values = [c.value for c in FAST_CATEGORIES]
        result = await db.execute(
            select(Item)
            .where(
                Item.ai_comment == None,  # noqa: E711
                Item.category.in_(fast_cat_values),
            )
            .order_by(Item.total_score.desc())
            .limit(FAST_TOTAL_LIMIT)
        )
        all_items = [
            item for item in result.scalars().all()
            if not (item.category == ContentCategory.blog_post.value and _is_paywalled(item))
        ]

        if all_items and fast_clients:
            # Split items round-robin across available fast clients
            # e.g. 3 items, 2 clients → client[0] gets items[0,2], client[1] gets items[1]
            n_clients = len(fast_clients)
            buckets: list[list[Item]] = [[] for _ in range(n_clients)]
            for i, item in enumerate(all_items):
                buckets[i % n_clients].append(item)

            logger.info(
                "comment_generation_parallel_start",
                total_items=len(all_items),
                n_providers=n_clients,
                providers=[c.model_label for c in fast_clients],
                bucket_sizes=[len(b) for b in buckets],
            )

            # Run all buckets in parallel
            results = await asyncio.gather(
                *[
                    _process_items(db, fast_clients[i], buckets[i], _FAST_SLEEP)
                    for i in range(n_clients)
                ]
            )
            total += sum(results)

        # ── GitHub via Gemini ─────────────────────────────────────────────────
        if gemini_client:
            github_result = await db.execute(
                select(Item)
                .where(
                    Item.ai_comment == None,  # noqa: E711
                    Item.category == ContentCategory.github_project.value,
                )
                .order_by(Item.total_score.desc())
                .limit(GITHUB_LIMIT)
            )
            github_items = github_result.scalars().all()
            if github_items:
                n = await _process_items(db, gemini_client, list(github_items), _GEMINI_SLEEP)
                total += n
        else:
            logger.info("github_comments_skipped", reason="no GEMINI_API_KEY")

        logger.info("comment_generation_total", total=total)
        return total

    finally:
        if own_session:
            await db.close()


async def _process_items(
    db: AsyncSession,
    client: CommentClient,
    items: list[Item],
    sleep: float,
) -> int:
    """Process a list of items with one client, stop on quota exhaustion."""
    if not items:
        return 0

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
                model=client.model_label,
                category=str(item.category),
                title=item.title[:60],
                comment=comment,
            )
        else:
            logger.warning(
                "comment_quota_or_error",
                model=client.model_label,
                processed=i,
                success=success,
            )
            break

        if sleep > 0 and i < len(items) - 1:
            await asyncio.sleep(sleep)

    return success
